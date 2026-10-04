"""Buscador de vacantes de prácticas, aprendiz y junior TI → canal de Telegram.

Uso:
    uv run buscador.py                         corrida normal
    uv run buscador.py --dry-run --fuente getonboard
    uv run buscador.py --seed                  marca todo como visto sin enviar
    uv run buscador.py --chat-prueba           envía al chat de prueba
    uv run buscador.py migrar [--archivo RUTA] importa el historial de Hermes
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import signal
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import config as cfg
import registro
import rotacion
from clasificador import Clasificador, Dudosa
from estado import Estado, EstadoNoInicializado, a_texto, ahora_utc
from fechas import ZONA
from filtros import Filtros, Motivo
from formato import componer
from fuentes.base import Fuente, Intento, ResultadoFuente, TipoError
from fuentes.getonboard import GetOnBoard
from ia_cliente import ClienteIA
from lock import CorridaActiva, Lock
from migrar_historial import migrar
from modelo import Vacante, Veredicto
from normalizar import huella
from notificador_telegram import Notificador, crear_notificador
from publicacion import ResultadoPublicacion, publicar
from salud import Salud

log = logging.getLogger("buscador")

FUENTES: dict[str, type[Fuente]] = {
    "getonboard": GetOnBoard,
}
HISTORIAL_HERMES = Path("~/.hermes/cron/output/historial_vacantes.json")
HORAS_COLA_ENVIO = 24
DESCARTES = (Motivo.SENIORITY, Motivo.ANTIGUEDAD, Motivo.UBICACION, Motivo.NO_TI)


@dataclass
class Modo:
    dry_run: bool = False
    seed: bool = False
    chat_prueba: bool = False
    fuente: str | None = None

    @property
    def nombre(self) -> str:
        if self.dry_run:
            return "dry-run"
        if self.seed:
            return "seed"
        return "prueba" if self.chat_prueba else "normal"

    @property
    def envia(self) -> bool:
        return not (self.dry_run or self.seed)


@dataclass
class ResumenCorrida:
    corrida_id: int | None = None
    modo: str = "normal"
    resultados: list[ResultadoFuente] = field(default_factory=list)
    omitidas: dict[str, str] = field(default_factory=dict)  # fuente → motivo
    crudas: int = 0
    descartes: Counter = field(default_factory=Counter)
    duplicadas: int = 0
    aceptadas_reglas: list[Vacante] = field(default_factory=list)
    dudosas: list[Vacante] = field(default_factory=list)
    ia_aceptadas: int = 0
    ia_rechazadas: int = 0
    ia_desde_cache: int = 0
    ia_llamadas: int = 0
    pendientes: int = 0
    vencidas: int = 0
    a_publicar: list[Vacante] = field(default_factory=list)
    publicacion: ResultadoPublicacion | None = None
    sembradas: int = 0
    sin_red: bool = False
    duracion_s: float = 0.0

    @property
    def intentos(self) -> list[Intento]:
        return [i for r in self.resultados for i in r.intentos]

    @property
    def enviadas(self) -> int:
        return len(self.publicacion.enviadas) if self.publicacion else 0

    def linea_log(self) -> str:
        requests = {
            r.fuente: [i.status or str(i.tipo_error) for i in r.intentos] for r in self.resultados
        }
        descartes = {m.value: self.descartes.get(m, 0) for m in DESCARTES}
        return (
            f"Corrida {self.corrida_id} ({self.modo}): requests={requests} crudas={self.crudas} "
            f"descartes={descartes} duplicadas={self.duplicadas} "
            f"aceptadas_reglas={len(self.aceptadas_reglas)} dudosas={len(self.dudosas)} "
            f"ia_aceptadas={self.ia_aceptadas} ia_rechazadas={self.ia_rechazadas} "
            f"ia_cache={self.ia_desde_cache} pendientes={self.pendientes} "
            f"vencidas={self.vencidas} ia_llamadas={self.ia_llamadas} enviadas={self.enviadas} "
            f"sembradas={self.sembradas} sin_red={self.sin_red} duracion={self.duracion_s:.1f}s"
        )


def es_sin_red(intentos: list[Intento]) -> bool:
    """Todos los intentos fallaron por conexión/DNS y ninguno obtuvo respuesta HTTP."""
    return bool(intentos) and all(
        i.tipo_error == TipoError.CONEXION and not i.con_respuesta for i in intentos
    )


def html_a_consola(texto: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", texto))


class Corrida:
    def __init__(
        self,
        config: cfg.Configuracion,
        secretos: cfg.Secretos,
        estado: Estado,
        modo: Modo,
        *,
        notificador: Notificador | None = None,
        ia: ClienteIA | None = None,
        fuentes: dict[str, type[Fuente]] | None = None,
        reloj: Callable[[], datetime] = lambda: datetime.now(ZONA),
        dormir: Callable[[float], None] = time.sleep,
        raiz: Path = cfg.RAIZ,
        salida: Callable[[str], None] = print,
    ) -> None:
        self.config = config
        self.secretos = secretos
        self.estado = estado
        self.modo = modo
        self.notificador = notificador
        self.ia = ia
        self.fuentes = fuentes if fuentes is not None else FUENTES
        self.reloj = reloj
        self.dormir = dormir
        self.raiz = raiz
        self.salida = salida
        self.filtros = Filtros(config.filtros)

    # --- pasos --------------------------------------------------------------------------

    def _fuentes_a_consultar(self) -> list[str]:
        if self.modo.fuente:
            if self.modo.fuente not in self.config.fuentes:
                raise ValueError(f"Fuente desconocida: {self.modo.fuente}")
            if self.modo.fuente not in self.fuentes:
                raise ValueError(f"La fuente {self.modo.fuente} todavía no está implementada")
            activa = self.config.fuentes[self.modo.fuente].activa
            if not activa and not self.modo.dry_run:
                raise ValueError(f"La fuente {self.modo.fuente} está desactivada en config.yaml")
            return [self.modo.fuente]
        return [
            nombre
            for nombre, conf in self.config.fuentes.items()
            if conf.activa and nombre in self.fuentes
        ]

    def _consultar(self, resumen: ResumenCorrida) -> list[Vacante]:
        palabras = self.config.palabras_clave
        nucleo, cola = palabras.nucleo, palabras.cola_larga_plana
        vacantes: list[Vacante] = []
        for nombre in self._fuentes_a_consultar():
            conf = self.config.fuentes[nombre]
            fuente = self.fuentes[nombre](
                conf, self.config.red, self.estado, resumen.corrida_id, dormir=self.dormir,
                reloj=self.reloj,
            )  # fmt: skip
            try:
                hasta = fuente.cooldown_vigente(self.reloj())
                if hasta:
                    resumen.omitidas[nombre] = f"en cooldown hasta {hasta.astimezone(ZONA):%H:%M}"
                    log.info("%s omitida: %s", nombre, resumen.omitidas[nombre])
                    continue
                lote = rotacion.calcular_lote(
                    self.estado, nombre, nucleo, cola, conf.presupuesto, conf.reservado_nucleo
                )
                resultado = fuente.ejecutar(lote)
                rotacion.avanzar_lote(
                    self.estado, nombre, resultado.ejecutadas, len(nucleo), len(cola)
                )
                resumen.resultados.append(resultado)
                vacantes.extend(resultado.vacantes)
            except Exception:  # noqa: BLE001 - una fuente rota no detiene a las demás
                log.exception("Error inesperado en la fuente %s", nombre)
                resumen.omitidas[nombre] = "error inesperado"
            finally:
                fuente.cerrar()
        return vacantes

    def _evaluar(self, vacantes: list[Vacante], resumen: ResumenCorrida) -> None:
        ahora = self.reloj()
        prueba = self.modo.chat_prueba
        vistas_corrida: set[str] = set()
        for vacante in vacantes:
            resumen.crudas += 1
            h = huella(vacante.titulo, vacante.empresa, vacante.clave)
            evaluacion = self.filtros.evaluar(vacante, ahora)
            if evaluacion.veredicto == Veredicto.RECHAZAR:
                resumen.descartes[evaluacion.motivo] += 1
                continue
            if (
                vacante.clave in vistas_corrida
                or h in vistas_corrida
                or self.estado.ya_vista(vacante.clave, h, prueba=prueba)
            ):
                resumen.duplicadas += 1
                continue
            vistas_corrida.update((vacante.clave, h))
            if evaluacion.veredicto == Veredicto.ACEPTAR:
                vacante.categoria = evaluacion.categoria
                resumen.aceptadas_reglas.append(vacante)
            else:
                resumen.dudosas.append(vacante)

    def _cola_de_envio(self, ya_incluidas: set[str]) -> list[Vacante]:
        """Vacantes aceptadas cuyo envío falló antes; vencen a las 24 h."""
        if self.modo.chat_prueba:
            return []
        ahora = self.reloj()
        reintentos = []
        for vacante, h, desde in self.estado.obtener_por_enviar():
            if ahora - desde > timedelta(hours=HORAS_COLA_ENVIO):
                log.warning("Vacante descartada tras %s h sin poder enviarse: %s",
                            HORAS_COLA_ENVIO, vacante.clave)  # fmt: skip
                self.estado.quitar_por_enviar(vacante.clave)
            elif vacante.clave not in ya_incluidas and not self.estado.ya_vista(vacante.clave, h):
                reintentos.append(vacante)
        return reintentos

    def _sembrar(self, resumen: ResumenCorrida) -> None:
        ahora = self.reloj()
        for vacante in resumen.aceptadas_reglas + resumen.dudosas:
            h = huella(vacante.titulo, vacante.empresa, vacante.clave)
            self.estado.registrar_vista(vacante, h, momento=ahora)
            resumen.sembradas += 1
        self.estado.marcar_inicializada(ahora)

    def _clasificar(self, resumen: ResumenCorrida) -> list[Vacante]:
        clasificador = Clasificador(self.config.clasificador, self.ia, self.estado, self.filtros)
        nuevas = [Dudosa(v, huella(v.titulo, v.empresa, v.clave)) for v in resumen.dudosas]
        resultado = clasificador.clasificar(nuevas, self.reloj())
        resumen.ia_aceptadas = len(resultado.aceptadas)
        resumen.ia_rechazadas = len(resultado.rechazadas)
        resumen.ia_desde_cache = resultado.desde_cache
        resumen.ia_llamadas = resultado.llamadas
        resumen.pendientes = len(resultado.pendientes)
        resumen.vencidas = len(resultado.vencidas)
        prueba = self.modo.chat_prueba
        return [
            d.vacante for d in resultado.aceptadas
            if not self.estado.ya_vista(d.vacante.clave, d.huella, prueba=prueba)
        ]  # fmt: skip

    def _publicar(self, resumen: ResumenCorrida) -> None:
        if not resumen.a_publicar:
            return
        chat = (
            self.secretos.telegram_chat_prueba
            if self.modo.chat_prueba
            else self.secretos.telegram_chat_id
        )
        candidatas = [(v, huella(v.titulo, v.empresa, v.clave)) for v in resumen.a_publicar]
        resumen.publicacion = publicar(
            candidatas, self.notificador, self.estado, self.config.banner, chat, self.reloj(),
            prueba=self.modo.chat_prueba, raiz=self.raiz, dormir=self.dormir,
        )  # fmt: skip

    def _imprimir_dry_run(self, resumen: ResumenCorrida) -> None:
        escribir = self.salida
        escribir("=== Dry-run: no se envía nada ni se marca nada como enviado ===")
        for resultado in resumen.resultados:
            escribir(f"\n[{resultado.fuente}]")
            for i in resultado.intentos:
                error = f" ERROR {i.tipo_error}" if i.tipo_error else ""
                escribir(f"  {i.keyword!r}: HTTP {i.status or '-'} · {i.items} vacantes · "
                         f"{i.ms} ms{error}")  # fmt: skip
        for nombre, motivo in resumen.omitidas.items():
            escribir(f"\n[{nombre}] omitida: {motivo}")
        descartes = ", ".join(f"{m.value} {resumen.descartes.get(m, 0)}" for m in DESCARTES)
        escribir(f"\nCrudas: {resumen.crudas} · descartes: {descartes} · "
                 f"ya vistas: {resumen.duplicadas}")  # fmt: skip
        escribir(f"Dudosas ({len(resumen.dudosas)}), irían a la IA:")
        for v in resumen.dudosas:
            escribir(f"  ? {v.titulo} — {v.empresa} — {v.ubicacion or '-'}")
        escribir(f"\nAceptadas por reglas ({len(resumen.aceptadas_reglas)}):\n")
        for mensaje in componer(resumen.aceptadas_reglas, self.reloj()):
            escribir(html_a_consola(mensaje.texto))
            escribir("-" * 60)

    def _guardar_corrida(self, resumen: ResumenCorrida, error: str | None) -> None:
        descartes = {m.value: resumen.descartes.get(m, 0) for m in DESCARTES}
        with self.estado.transaccion() as cx:
            cx.execute(
                """
                UPDATE corridas SET fin = ?, crudas = ?, descartes_json = ?, duplicadas = ?,
                    dudosas = ?, ia_aceptadas = ?, ia_rechazadas = ?, pendientes = ?,
                    enviadas = ?, sin_red = ?, error = ?
                WHERE id = ?
                """,
                (
                    a_texto(ahora_utc()), resumen.crudas, json.dumps(descartes),
                    resumen.duplicadas, len(resumen.dudosas), resumen.ia_aceptadas,
                    resumen.ia_rechazadas, resumen.pendientes, resumen.enviadas,
                    int(resumen.sin_red), error, resumen.corrida_id,
                ),
            )  # fmt: skip

    # --- flujo --------------------------------------------------------------------------

    def ejecutar(self) -> ResumenCorrida:
        inicio = time.monotonic()
        modo = self.modo
        if modo.envia:
            self.estado.exigir_inicializada()
        resumen = ResumenCorrida(modo=modo.nombre)
        if not modo.dry_run:
            borrados = self.estado.limpiar(
                self.reloj(), self.config.estado.dias_vistas, self.config.estado.dias_intentos
            )
            if any(borrados.values()):
                log.info("Limpieza: %s", borrados)
        with self.estado.transaccion() as cx:
            resumen.corrida_id = cx.execute(
                "INSERT INTO corridas(inicio, modo) VALUES (?, ?)",
                (a_texto(ahora_utc()), modo.nombre),
            ).lastrowid

        error = None
        try:
            vacantes = self._consultar(resumen)
            resumen.sin_red = es_sin_red(resumen.intentos)
            if resumen.sin_red:
                log.warning("Sin conexión a internet: todas las fuentes fallaron por red")
            self._evaluar(vacantes, resumen)
            if modo.dry_run:
                self._imprimir_dry_run(resumen)
            elif modo.seed:
                self._sembrar(resumen)
            else:
                aceptadas = list(resumen.aceptadas_reglas)
                # La IA va después de las reglas y nunca bloquea el envío
                try:
                    aceptadas += self._clasificar(resumen)
                except Exception:  # noqa: BLE001
                    log.exception("Error en el clasificador; se envían las aceptadas por reglas")
                aceptadas += self._cola_de_envio({v.clave for v in aceptadas})
                resumen.a_publicar = aceptadas
                self._publicar(resumen)
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            resumen.duracion_s = time.monotonic() - inicio
            self._guardar_corrida(resumen, error)
            log.info(resumen.linea_log())
        return resumen


# --- CLI ------------------------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="buscador.py", description="Buscador de vacantes TI → Telegram"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="imprime las vacantes sin enviar ni marcar nada")  # fmt: skip
    parser.add_argument("--fuente", help="consulta solo esta fuente")
    parser.add_argument("--seed", action="store_true",
                        help="marca todo lo encontrado como visto sin enviar")  # fmt: skip
    parser.add_argument("--chat-prueba", action="store_true",
                        help="envía al chat de prueba sin marcar envíos al canal")  # fmt: skip
    parser.add_argument("--config", type=Path, default=cfg.RAIZ / "config.yaml")
    parser.add_argument("--env", type=Path, default=cfg.RAIZ / ".env")
    sub = parser.add_subparsers(dest="comando")
    migrar_p = sub.add_parser("migrar", help="importa el historial JSON de Hermes")
    migrar_p.add_argument("--archivo", type=Path, default=HISTORIAL_HERMES)
    return parser


def _ruta(raiz: Path, ruta: Path) -> Path:
    ruta = ruta.expanduser()
    return ruta if ruta.is_absolute() else raiz / ruta


class _TiempoAgotado(Exception):
    pass


def _limitar_tiempo(minutos: float) -> None:
    def manejador(signum, frame):
        raise _TiempoAgotado(f"La corrida superó {minutos} minutos")

    signal.signal(signal.SIGALRM, manejador)
    signal.alarm(int(minutos * 60))


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.seed and (args.dry_run or args.chat_prueba):
        print("--seed no se combina con --dry-run ni --chat-prueba", file=sys.stderr)
        return 2
    try:
        config = cfg.cargar_configuracion(args.config)
        modo = Modo(args.dry_run, args.seed, args.chat_prueba, args.fuente)
        secretos = cfg.cargar_secretos(
            config,
            args.env,
            exigir_envio=modo.envia and args.comando is None,
            exigir_chat_prueba=modo.chat_prueba,
        )
    except cfg.ErrorConfiguracion as exc:
        print(f"Error de configuración:\n{exc}", file=sys.stderr)
        return 2

    raiz = cfg.RAIZ
    registro.configurar(
        _ruta(raiz, config.rutas.logs), config.registro.retencion_dias, secretos.valores(),
        config.zona_horaria,
    )  # fmt: skip
    try:
        with Lock(_ruta(raiz, config.rutas.lock)):
            estado = Estado.abrir(_ruta(raiz, config.rutas.base_datos))
            try:
                if args.comando == "migrar":
                    resultado = migrar(estado, args.archivo.expanduser())
                    print(f"Migración: {resultado}")
                    return 0
                return _correr(config, secretos, estado, modo, raiz)
            finally:
                estado.cerrar()
    except CorridaActiva as exc:
        log.warning("%s; esta ejecución termina sin hacer requests", exc)
        return 0


def _correr(
    config: cfg.Configuracion, secretos: cfg.Secretos, estado: Estado, modo: Modo, raiz: Path
) -> int:
    programada = modo.envia
    salud = Salud(secretos.healthcheck_url, activo=config.salud.activo and programada,
                  timeout_s=config.salud.timeout_s)  # fmt: skip
    notificador = (
        crear_notificador(config.telegram, secretos.telegram_bot_token) if modo.envia else None
    )
    ia = None
    if modo.envia and config.usa_ia and secretos.deepseek_api_key:
        ia = ClienteIA(config.ia, secretos.deepseek_api_key, estado, secretos=secretos.valores())
    salud.inicio()
    _limitar_tiempo(config.operacion.timeout_corrida_min)
    try:
        resumen = Corrida(
            config, secretos, estado, modo, notificador=notificador, ia=ia, raiz=raiz
        ).ejecutar()
    except EstadoNoInicializado as exc:
        log.error("%s", exc)
        salud.fallo(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 - incluye _TiempoAgotado
        log.exception("La corrida terminó con error")
        salud.fallo(repr(exc))
        return 1
    else:
        salud.exito(resumen.linea_log())
        return 0
    finally:
        signal.alarm(0)
        for recurso in (notificador, ia, salud):
            if recurso is not None:
                recurso.cerrar()


if __name__ == "__main__":
    sys.exit(main())
