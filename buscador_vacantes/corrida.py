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

from buscador_vacantes import config as cfg
from buscador_vacantes import registro, rotacion
from buscador_vacantes.asistente import cli as asistente_cli
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.enlaces import bot_para_enlaces
from buscador_vacantes.clasificador import Clasificador, Dudosa
from buscador_vacantes.estado import Estado, EstadoNoInicializado, a_texto, ahora_utc
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.filtros import Filtros, Motivo
from buscador_vacantes.formato import componer
from buscador_vacantes.fuentes.base import Fuente, Intento, ResultadoFuente, TipoError
from buscador_vacantes.fuentes.computrabajo import Computrabajo
from buscador_vacantes.fuentes.elempleo import Elempleo
from buscador_vacantes.fuentes.getonboard import GetOnBoard
from buscador_vacantes.fuentes.linkedin import LinkedIn
from buscador_vacantes.fuentes.magneto import Magneto
from buscador_vacantes.fuentes.spe import ServicioPublicoEmpleo
from buscador_vacantes.ia_cliente import ClienteIA
from buscador_vacantes.incidentes import Detector, ResultadoEvaluacion
from buscador_vacantes.lock import CorridaActiva, Lock
from buscador_vacantes.migrar_historial import migrar
from buscador_vacantes.modelo import Vacante, Veredicto
from buscador_vacantes.normalizar import huella
from buscador_vacantes.notificador_telegram import Notificador, crear_notificador
from buscador_vacantes.publicacion import ResultadoPublicacion, publicar
from buscador_vacantes.reportero import DatosFuente, Reportero
from buscador_vacantes.resumen import Resumen
from buscador_vacantes.salud import Salud
from buscador_vacantes.simulacion import FALLAS_IA, NotificadorConsola, simular

log = logging.getLogger("buscador")

FUENTES: dict[str, type[Fuente]] = {
    "linkedin": LinkedIn,
    "computrabajo": Computrabajo,
    "elempleo": Elempleo,
    "magneto": Magneto,
    "getonboard": GetOnBoard,
    "spe": ServicioPublicoEmpleo,
}
HISTORIAL_HERMES = Path("~/.hermes/cron/output/historial_vacantes.json")
HORAS_COLA_ENVIO = 24
ESPERA_LOCK_RESUMEN_S = 600
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
    incidentes: ResultadoEvaluacion | None = None
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
            f"sembradas={self.sembradas} sin_red={self.sin_red} "
            f"incidentes={self._resumen_incidentes()} duracion={self.duracion_s:.1f}s"
        )

    def _resumen_incidentes(self) -> dict[str, list[str]]:
        if self.incidentes is None:
            return {}
        return {
            "nuevos": [i.clave for i in self.incidentes.nuevos],
            "recuperados": [i.clave for i in self.incidentes.recuperados],
        }


def es_sin_red(intentos: list[Intento]) -> bool:
    """Todos los intentos fallaron por conexión/DNS y ninguno obtuvo respuesta HTTP."""
    return bool(intentos) and all(
        i.tipo_error == TipoError.CONEXION and not i.con_respuesta for i in intentos
    )


def deduplicar(vacantes: list[Vacante]) -> list[Vacante]:
    """Quita del lote las repetidas por clave o huella (p. ej. una pendiente de la IA de una
    fuente y la copia aceptada por reglas de otra), conservando la primera."""
    vistas: set[str] = set()
    unicas = []
    for vacante in vacantes:
        h = huella(vacante.titulo, vacante.empresa, vacante.clave)
        if vacante.clave in vistas or h in vistas:
            continue
        vistas.update((vacante.clave, h))
        unicas.append(vacante)
    return unicas


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
                if fuente.consulta_fija:
                    # Fuente que no usa palabras clave: lee sus páginas más recientes
                    lote = [
                        rotacion.Consulta(fuente.consulta_fija, rotacion.NUCLEO, pagina)
                        for pagina in range(1, conf.presupuesto + 1)
                    ]
                else:
                    paginas = conf.paginas_nucleo
                    if paginas > 1 and not fuente.soporta_paginas:
                        log.warning("%s no soporta paginación: se lee solo la página 1", nombre)
                        paginas = 1
                    lote = rotacion.calcular_lote(
                        self.estado, nombre, nucleo, cola, conf.presupuesto, conf.reservado_nucleo,
                        paginas,
                    )  # fmt: skip
                resultado = fuente.ejecutar(lote)
                # El dry-run no mueve la rotación de producción; la consulta fija no rota
                if not self.modo.dry_run and not fuente.consulta_fija:
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
        if self.modo.fuente:
            # Sembrar una fuente (p. ej. al activarla) no inicializa la base para todas
            log.info("Siembra de %s: la base no se marca como inicializada", self.modo.fuente)
        else:
            self.estado.marcar_inicializada(ahora)

    def _clasificar(self, resumen: ResumenCorrida) -> list[Vacante]:
        con_filtro = frozenset(n for n, f in self.config.fuentes.items() if f.filtra_nivel)
        clasificador = Clasificador(
            self.config.clasificador, self.ia, self.estado, self.filtros, con_filtro
        )
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
        chat = self._chat_destino()
        candidatas = [(v, huella(v.titulo, v.empresa, v.clave)) for v in resumen.a_publicar]
        resumen.publicacion = publicar(
            candidatas, self.notificador, self.estado, self.config.banner, chat, self.reloj(),
            prueba=self.modo.chat_prueba, raiz=self.raiz, dormir=self.dormir,
            bot_asistente=bot_para_enlaces(self.config),
        )  # fmt: skip

    def _chat_destino(self) -> str | None:
        if self.modo.chat_prueba:
            return self.secretos.telegram_chat_prueba
        return self.secretos.telegram_chat_id

    def _incidentes(self, resumen: ResumenCorrida) -> None:
        """Detecta incidentes y avisa. Corre después del envío y nunca lo bloquea."""
        detector = Detector(self.estado, self.config.incidentes)
        publicacion = resumen.publicacion
        rechazos = [r.descripcion for r in publicacion.rechazos] if publicacion else []
        resumen.incidentes = detector.evaluar(
            resumen.corrida_id,
            self.reloj(),
            self._fuentes_a_consultar(),
            sin_red=resumen.sin_red,
            rechazos_envio=rechazos,
            envio_exitoso=bool(publicacion and publicacion.mensajes_enviados and not rechazos),
        )
        if resumen.incidentes.vacio or self.notificador is None:
            return
        datos = {
            nombre: DatosFuente(clase.selectores, self.config.fuentes[nombre].presupuesto)
            for nombre, clase in self.fuentes.items()
            if nombre in self.config.fuentes
        }
        fuentes_ok = [
            r.fuente for r in resumen.resultados
            if any(i.status is not None and 200 <= i.status < 300 for i in r.intentos)
        ]  # fmt: skip
        reportero = Reportero(
            self.config.reportero, self.ia, self.estado, detector, self.notificador,
            self._chat_destino(), datos, reloj=self.reloj,
        )  # fmt: skip
        reportero.notificar(resumen.incidentes, resumen.intentos, fuentes_ok)

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
                resumen.a_publicar = deduplicar(aceptadas)
                self._publicar(resumen)
                # El reportero va aislado: sus errores nunca afectan a las vacantes ya enviadas
                try:
                    self._incidentes(resumen)
                except Exception:  # noqa: BLE001
                    log.exception("Error en el detector o el reportero de incidentes")
        except BaseException as exc:  # también el límite de tiempo: queda registrado
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
    parser.add_argument(
        "--simular-incidente",
        metavar="FUENTE:TIPO",
        help="corre el reportero con un incidente de ejemplo y lo envía al chat de prueba "
        "(con --dry-run lo imprime), sin tocar el estado real",
    )
    parser.add_argument(
        "--simular-falla-ia",
        choices=sorted(FALLAS_IA),
        help="con --simular-incidente, fuerza la alerta plana de respaldo",
    )
    parser.add_argument("--config", type=Path, default=cfg.RAIZ / "config.yaml")
    parser.add_argument("--env", type=Path, default=cfg.RAIZ / ".env")
    sub = parser.add_subparsers(dest="comando")
    migrar_p = sub.add_parser("migrar", help="importa el historial JSON de Hermes")
    migrar_p.add_argument("--archivo", type=Path, default=HISTORIAL_HERMES)
    sub.add_parser("resumen", help="envía el resumen diario (una vez al día)")
    sub.add_parser(
        "promover-prueba",
        help="al pasar a producción, marca como enviadas las vacantes de la fase de prueba",
    )
    asistente_cli.agregar_subcomandos(sub)
    return parser


def _ruta(raiz: Path, ruta: Path) -> Path:
    ruta = ruta.expanduser()
    return ruta if ruta.is_absolute() else raiz / ruta


class _TiempoAgotado(BaseException):  # noqa: N818
    """Hereda de BaseException para que ningún `except Exception` intermedio lo detenga."""


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
    if args.simular_incidente:
        return _simular(args)
    if args.comando == "asistente":
        # El asistente es otro servicio: no toma el lock de las corridas del buscador
        return asistente_cli.ejecutar(args)
    try:
        config = cfg.cargar_configuracion(args.config)
        modo = Modo(args.dry_run, args.seed, args.chat_prueba, args.fuente)
        exigir_envio = (args.comando is None and modo.envia) or (
            args.comando == "resumen" and not args.dry_run
        )
        secretos = cfg.cargar_secretos(
            config,
            args.env,
            exigir_envio=exigir_envio,
            exigir_chat_prueba=modo.chat_prueba,
            # El resumen no hace ping de salud
            exigir_salud=config.salud.activo and args.comando is None,
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
        # Los subcomandos esperan a que termine una corrida en curso en lugar de perderse
        espera = ESPERA_LOCK_RESUMEN_S if args.comando else 0
        with Lock(_ruta(raiz, config.rutas.lock), esperar_s=espera):
            estado = Estado.abrir(_ruta(raiz, config.rutas.base_datos))
            try:
                if args.comando == "migrar":
                    resultado = migrar(estado, args.archivo.expanduser())
                    print(f"Migración: {resultado}")
                    return 0
                if args.comando == "promover-prueba":
                    print(f"Vacantes de la fase de prueba marcadas como enviadas: "
                          f"{estado.promover_prueba()}")  # fmt: skip
                    return 0
                if args.comando == "resumen":
                    return _resumen(config, secretos, estado, modo)
                return _correr(config, secretos, estado, modo, raiz)
            finally:
                estado.cerrar()
    except CorridaActiva as exc:
        if args.comando:
            print(f"No se ejecutó '{args.comando}': {exc}. Intenta de nuevo.", file=sys.stderr)
            return 1
        log.warning("%s; esta ejecución termina sin hacer requests", exc)
        return 0


def _simular(args: argparse.Namespace) -> int:
    try:
        config = cfg.cargar_configuracion(args.config)
        secretos = cfg.cargar_secretos(
            config, args.env, exigir_envio=False, exigir_chat_prueba=not args.dry_run
        )
        if (
            not args.dry_run
            and config.telegram.modo == "bot_api"
            and not secretos.telegram_bot_token
        ):
            raise cfg.ErrorConfiguracion("Falta TELEGRAM_BOT_TOKEN para enviar al chat de prueba")
    except cfg.ErrorConfiguracion as exc:
        print(f"Error de configuración:\n{exc}", file=sys.stderr)
        return 2
    registro.configurar(
        _ruta(cfg.RAIZ, config.rutas.logs), config.registro.retencion_dias, secretos.valores(),
        config.zona_horaria,
    )  # fmt: skip
    if args.dry_run:
        notificador: Notificador = NotificadorConsola()
        chat = "consola"
    else:
        notificador = crear_notificador(config.telegram, secretos.telegram_bot_token)
        chat = secretos.telegram_chat_prueba
    try:
        simular(
            args.simular_incidente, config, notificador, chat, FUENTES,
            api_key=secretos.deepseek_api_key, falla_ia=args.simular_falla_ia,
        )  # fmt: skip
    except ValueError as exc:
        print(f"Simulación inválida: {exc}", file=sys.stderr)
        return 2
    finally:
        notificador.cerrar()
    return 0


def _resumen(config: cfg.Configuracion, secretos: cfg.Secretos, estado: Estado, modo: Modo) -> int:
    if modo.dry_run:
        notificador: Notificador = NotificadorConsola()
        chat = "consola"
    else:
        notificador = crear_notificador(config.telegram, secretos.telegram_bot_token)
        chat = secretos.telegram_chat_prueba if modo.chat_prueba else secretos.telegram_chat_id
    ia = None
    if secretos.deepseek_api_key:
        ia = ClienteIA(config.ia, secretos.deepseek_api_key, estado, secretos=secretos.valores())
    base_asistente = None
    try:
        if config.asistente is not None and config.asistente.activo:
            base_asistente = BaseAsistente.abrir(_ruta(cfg.RAIZ, config.asistente.base_datos))
        Resumen(
            config.resumen,
            ia,
            estado,
            notificador,
            chat,
            prueba=modo.chat_prueba,
            asistente=base_asistente,
            navegador_caido_min=(
                config.asistente.extension.navegador_caido_min if config.asistente else 2
            ),
        ).enviar(registrar=not modo.dry_run)
    except Exception:  # noqa: BLE001
        log.exception("Error generando el resumen diario")
        return 1
    finally:
        notificador.cerrar()
        if ia is not None:
            ia.cerrar()
        if base_asistente is not None:
            base_asistente.cerrar()
    return 0


def _correr(
    config: cfg.Configuracion, secretos: cfg.Secretos, estado: Estado, modo: Modo, raiz: Path
) -> int:
    programada = modo.envia
    salud = Salud(secretos.healthcheck_url, activo=config.salud.activo and programada,
                  timeout_s=config.salud.timeout_s)  # fmt: skip
    # Con el botón ⚡ del canal activo, la corrida publica con el bot asistente: Telegram solo
    # le avisa los toques de un botón al bot que envió el mensaje.
    token = secretos.telegram_bot_token
    if bot_para_enlaces(config) and secretos.asistente_bot_token:
        token = secretos.asistente_bot_token
    notificador = crear_notificador(config.telegram, token) if modo.envia else None
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
    except (Exception, _TiempoAgotado) as exc:  # noqa: BLE001
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
