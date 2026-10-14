"""Cola de postulaciones: estados, asignación a navegadores, plazos, topes y modo automático.

Cada transición es condicional (``UPDATE … WHERE estado IN (…)``): un doble toque, dos
navegadores o un reinicio nunca ejecutan dos veces la misma postulación. Una postulación que
llegó a pulsar el envío nunca vuelve a la cola: termina enviada, fallida o incierta.
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.estado import a_texto, de_texto
from buscador_vacantes.fechas import ZONA


class E(StrEnum):
    """Estados de una postulación."""

    EN_COLA = "en_cola"
    ESPERANDO_NAVEGADOR = "esperando_navegador"
    TOMADA = "tomada"
    EN_CURSO = "en_curso"
    ESPERANDO_USUARIO = "esperando_usuario"
    ESPERANDO_SESION = "esperando_sesion"
    VERIFICACION = "verificacion"
    CUENTA_DISTINTA = "cuenta_distinta"
    ENVIADA = "enviada"
    YA_POSTULADA = "ya_postulada"
    VACANTE_CERRADA = "vacante_cerrada"
    BLOQUEADA = "bloqueada"
    FORMULARIO_DESCONOCIDO = "formulario_desconocido"
    INCIERTA = "incierta"
    FALLIDA = "fallida"
    RESPALDO = "respaldo"  # se entregó el paquete para copiar
    CANCELADA = "cancelada"
    COMPLETADO = "completado"  # trabajo completar_perfil terminado


ESPERANDO = (E.EN_COLA, E.ESPERANDO_NAVEGADOR)
ACTIVAS = (E.TOMADA, E.EN_CURSO, E.VERIFICACION)
# Resultados que puede reportar la extensión al terminar
FINALES_EXTENSION = {
    E.ENVIADA, E.YA_POSTULADA, E.VACANTE_CERRADA, E.FORMULARIO_DESCONOCIDO, E.INCIERTA,
    E.FALLIDA, E.ESPERANDO_SESION, E.CUENTA_DISTINTA, E.BLOQUEADA, E.COMPLETADO,
}  # fmt: skip
# Estados que entregan el paquete de respaldo al usuario
CON_RESPALDO = {E.BLOQUEADA, E.FORMULARIO_DESCONOCIDO, E.FALLIDA, E.RESPALDO}
# Resultados que el usuario puede reintentar tocando ⚡ otra vez. No hay riesgo de duplicar:
# antes de llenar nada la extensión revisa si el portal ya tiene la postulación (ya_postulada)
REINTENTABLES = (E.BLOQUEADA, E.FORMULARIO_DESCONOCIDO, E.FALLIDA, E.RESPALDO, E.CANCELADA)


class Tipo(StrEnum):
    POSTULAR = "postular"
    COMPLETAR_PERFIL = "completar_perfil"


@dataclass
class Postulacion:
    id: int
    usuario_id: int
    id_corto: str | None
    tipo: Tipo
    plataforma: str | None
    estado: E
    motivo: str | None
    origen: str
    navegador_id: int | None
    envio_pulsado: bool
    creada: datetime
    actualizada: datetime
    tomada_en: datetime | None
    terminada_en: datetime | None
    afinidad: int | None

    @classmethod
    def de_fila(cls, f: sqlite3.Row) -> Postulacion:
        return cls(
            f["id"], f["usuario_id"], f["id_corto"], Tipo(f["tipo"]), f["plataforma"],
            E(f["estado"]), f["motivo"], f["origen"], f["navegador_id"],
            bool(f["envio_pulsado"]), de_texto(f["creada"]), de_texto(f["actualizada"]),
            de_texto(f["tomada_en"]), de_texto(f["terminada_en"]), f["afinidad"],
        )  # fmt: skip


@dataclass
class Evento:
    """Algo que el bot debe avisar al usuario (o al dueño)."""

    tipo: str
    postulacion_id: int
    usuario_id: int
    estado: E
    detalle: str | None = None


class Cola:
    def __init__(self, base: BaseAsistente, config: cfg.Asistente) -> None:
        self.base = base
        self.config = config

    # --- consultas -----------------------------------------------------------------

    def obtener(self, postulacion_id: int) -> Postulacion | None:
        fila = self.base.cx.execute(
            "SELECT * FROM postulaciones WHERE id = ?", (postulacion_id,)
        ).fetchone()
        return Postulacion.de_fila(fila) if fila else None

    def de_usuario(self, usuario_id: int, id_corto: str) -> Postulacion | None:
        fila = self.base.cx.execute(
            "SELECT * FROM postulaciones WHERE usuario_id = ? AND id_corto = ?",
            (usuario_id, id_corto),
        ).fetchone()
        return Postulacion.de_fila(fila) if fila else None

    def _inicio_dia(self, ahora: datetime) -> str:
        return a_texto(datetime.combine(ahora.astimezone(ZONA).date(), time(0), tzinfo=ZONA))

    def postulaciones_hoy(self, usuario_id: int, ahora: datetime) -> int:
        """Cuentan las que llegaron a ejecutarse (no las canceladas ni las de respaldo)."""
        fila = self.base.cx.execute(
            "SELECT COUNT(*) FROM postulaciones WHERE usuario_id = ? AND tipo = 'postular' "
            "AND tomada_en >= ?",
            (usuario_id, self._inicio_dia(ahora)),
        ).fetchone()
        return fila[0]

    # --- registro de pasos -----------------------------------------------------------

    def paso(
        self, cx: sqlite3.Connection, pid: int, paso: str, ahora: datetime,
        estado: str | None = None, detalle=None,
    ) -> None:  # fmt: skip
        if detalle is not None and not isinstance(detalle, str):
            detalle = json.dumps(detalle, ensure_ascii=False)
        cx.execute(
            "INSERT INTO postulacion_pasos(postulacion_id, ts, estado, paso, detalle) "
            "VALUES (?, ?, ?, ?, ?)",
            (pid, a_texto(ahora), estado, paso, detalle),
        )

    def _cambiar(
        self, pid: int, desde: tuple[str, ...], hacia: E, ahora: datetime,
        motivo: str | None = None, **extra,
    ) -> bool:  # fmt: skip
        """Transición condicional. True si se aplicó."""
        columnas = ", ".join(f"{k} = ?" for k in extra)
        marcas = ", ".join("?" for _ in desde)
        with self.base.transaccion() as cx:
            cur = cx.execute(
                f"UPDATE postulaciones SET estado = ?, motivo = ?, actualizada = ?"
                f"{', ' + columnas if columnas else ''} WHERE id = ? AND estado IN ({marcas})",
                (hacia, motivo, a_texto(ahora), *extra.values(), pid, *desde),
            )
            if cur.rowcount:
                self.paso(cx, pid, "estado", ahora, hacia, motivo)
            return bool(cur.rowcount)

    # --- alta en la cola ---------------------------------------------------------------

    def encolar(
        self, usuario_id: int, id_corto: str, plataforma: str | None, ahora: datetime,
        *, origen: str = "boton", afinidad: int | None = None,
    ) -> tuple[Postulacion, bool]:  # fmt: skip
        """Devuelve (postulación, creada). Si ya existía, la existente sin cambios."""
        if existente := self.de_usuario(usuario_id, id_corto):
            return existente, False
        try:
            with self.base.transaccion() as cx:
                pid = cx.execute(
                    "INSERT INTO postulaciones(usuario_id, id_corto, tipo, plataforma, estado, "
                    "origen, afinidad, creada, actualizada) VALUES (?, ?, 'postular', ?, ?, ?, "
                    "?, ?, ?)",
                    (usuario_id, id_corto, plataforma, E.EN_COLA, origen, afinidad,
                     a_texto(ahora), a_texto(ahora)),
                ).lastrowid  # fmt: skip
                self.paso(cx, pid, "encolada", ahora, E.EN_COLA, origen)
        except sqlite3.IntegrityError:  # carrera con otro toque: gana el primero
            existente = self.de_usuario(usuario_id, id_corto)
            assert existente is not None
            return existente, False
        nueva = self.obtener(pid)
        assert nueva is not None
        return nueva, True

    def encolar_completar_perfil(self, usuario_id: int, plataforma: str, ahora: datetime) -> int:
        """Un solo trabajo pendiente de completar perfil por usuario y plataforma."""
        fila = self.base.cx.execute(
            "SELECT id FROM postulaciones WHERE usuario_id = ? AND tipo = 'completar_perfil' "
            "AND plataforma = ? AND estado IN (?, ?, ?, ?)",
            (usuario_id, plataforma, *ESPERANDO, E.TOMADA, E.EN_CURSO),
        ).fetchone()
        if fila:
            return fila["id"]
        with self.base.transaccion() as cx:
            pid = cx.execute(
                "INSERT INTO postulaciones(usuario_id, tipo, plataforma, estado, origen, creada, "
                "actualizada) VALUES (?, 'completar_perfil', ?, ?, 'sistema', ?, ?)",
                (usuario_id, plataforma, E.EN_COLA, a_texto(ahora), a_texto(ahora)),
            ).lastrowid
            self.paso(cx, pid, "encolada", ahora, E.EN_COLA, "completar_perfil")
        return pid

    def debe_encolar_automatico(
        self, usuario_umbral: int | None, afinidad: int | None, plataforma: str | None,
        usuario_id: int, ahora: datetime,
    ) -> bool:  # fmt: skip
        """Modo automático: solo plataformas automáticas, afinidad ≥ umbral y dentro del tope."""
        if usuario_umbral is None or afinidad is None or plataforma is None:
            return False
        ajustes = self.config.plataformas.get(plataforma)
        if not ajustes or not ajustes.automatica:
            return False
        if self.postulaciones_hoy(usuario_id, ahora) >= self.config.topes.usuario_dia:
            return False
        return afinidad >= usuario_umbral

    # --- asignación a la extensión -------------------------------------------------------

    def _pausa_para(self, pid: int) -> timedelta:
        rango = self.config.ejecucion.pausa_s
        return timedelta(seconds=random.Random(pid).uniform(rango.min, rango.max))

    def siguiente(
        self, usuario_id: int, portales_listos: set[str], ahora: datetime
    ) -> Postulacion | None:
        """El próximo trabajo que puede tomar un navegador del usuario, o None.

        Completar perfil va primero. Se respetan el tope diario y la pausa entre postulaciones.
        """
        if self.base.cx.execute(
            "SELECT 1 FROM postulaciones WHERE usuario_id = ? AND estado IN (?, ?, ?)",
            (usuario_id, *ACTIVAS),
        ).fetchone():
            return None  # de a una por usuario
        filas = self.base.cx.execute(
            "SELECT * FROM postulaciones WHERE usuario_id = ? AND estado IN (?, ?) "
            "ORDER BY CASE tipo WHEN 'completar_perfil' THEN 0 ELSE 1 END, creada, id",
            (usuario_id, *ESPERANDO),
        ).fetchall()
        candidata = next(
            (Postulacion.de_fila(f) for f in filas if f["plataforma"] in portales_listos), None
        )
        if candidata is None:
            return None
        if candidata.tipo == Tipo.POSTULAR:
            if self.postulaciones_hoy(usuario_id, ahora) >= self.config.topes.usuario_dia:
                return None
            ultima = self.base.cx.execute(
                "SELECT MAX(terminada_en) FROM postulaciones WHERE usuario_id = ? "
                "AND tipo = 'postular' AND terminada_en IS NOT NULL",
                (usuario_id,),
            ).fetchone()[0]
            if ultima and ahora < de_texto(ultima) + self._pausa_para(candidata.id):
                return None
        return candidata

    def tomar(self, pid: int, navegador_id: int, ahora: datetime) -> bool:
        """Asignación atómica: si dos navegadores la piden, solo uno la obtiene."""
        return self._cambiar(
            pid, ESPERANDO, E.TOMADA, ahora, navegador_id=navegador_id, tomada_en=a_texto(ahora)
        )

    def iniciar(self, pid: int, navegador_id: int, ahora: datetime) -> bool:
        return self._cambiar_de_navegador(pid, navegador_id, (E.TOMADA,), E.EN_CURSO, ahora)

    def _cambiar_de_navegador(
        self, pid: int, navegador_id: int, desde: tuple[str, ...], hacia: E, ahora: datetime,
        motivo: str | None = None, **extra,
    ) -> bool:  # fmt: skip
        actual = self.obtener(pid)
        if actual is None or actual.navegador_id != navegador_id:
            return False
        return self._cambiar(pid, desde, hacia, ahora, motivo, **extra)

    def marcar_envio_pulsado(self, pid: int, navegador_id: int, ahora: datetime) -> bool:
        actual = self.obtener(pid)
        if actual is None or actual.navegador_id != navegador_id or actual.estado != E.EN_CURSO:
            return False
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE postulaciones SET envio_pulsado = 1, actualizada = ? WHERE id = ?",
                (a_texto(ahora), pid),
            )
            self.paso(cx, pid, "envio_pulsado", ahora, E.EN_CURSO)
        return True

    def registrar_paso(
        self, pid: int, navegador_id: int, paso: str, detalle, ahora: datetime
    ) -> bool:
        actual = self.obtener(pid)
        if actual is None or actual.navegador_id != navegador_id:
            return False
        with self.base.transaccion() as cx:
            self.paso(cx, pid, paso, ahora, detalle=detalle)
        return True

    def verificacion(self, pid: int, navegador_id: int, ahora: datetime) -> bool:
        """Captcha visible al usuario: la extensión espera que lo complete."""
        return self._cambiar_de_navegador(pid, navegador_id, (E.EN_CURSO,), E.VERIFICACION, ahora)

    def verificacion_resuelta(self, pid: int, navegador_id: int, ahora: datetime) -> bool:
        return self._cambiar_de_navegador(pid, navegador_id, (E.VERIFICACION,), E.EN_CURSO, ahora)

    def esperar_usuario(self, pid: int, navegador_id: int, ahora: datetime) -> bool:
        """Faltan datos: la extensión cerró la pestaña sin enviar y libera la postulación."""
        actual = self.obtener(pid)
        if actual is None or actual.navegador_id != navegador_id:
            return False
        return self._cambiar(
            pid, (E.EN_CURSO,), E.ESPERANDO_USUARIO, ahora, navegador_id=None, tomada_en=None
        )

    def terminar(
        self, pid: int, navegador_id: int, resultado: E, ahora: datetime, motivo: str | None = None
    ) -> Evento | None:
        """Resultado reportado por la extensión."""
        if resultado not in FINALES_EXTENSION:
            raise ValueError(f"resultado no permitido: {resultado}")
        actual = self.obtener(pid)
        if actual is None or actual.navegador_id != navegador_id:
            return None
        if actual.envio_pulsado and resultado in (E.ESPERANDO_SESION, E.CUENTA_DISTINTA):
            resultado = E.INCIERTA  # tras pulsar el envío nunca se reintenta
        extra = {"terminada_en": a_texto(ahora)}
        if resultado in (E.ESPERANDO_SESION, E.CUENTA_DISTINTA):
            extra = {"navegador_id": None, "tomada_en": None}
        if not self._cambiar(pid, ACTIVAS, resultado, ahora, motivo, **extra):
            return None
        return Evento("resultado", pid, actual.usuario_id, resultado, motivo)

    # --- respuestas del usuario y reanudaciones -----------------------------------------------

    def reanudar(self, pid: int, ahora: datetime, desde: tuple[str, ...]) -> bool:
        return self._cambiar(pid, desde, E.EN_COLA, ahora, navegador_id=None, tomada_en=None)

    def portales_actualizados(
        self, usuario_id: int, portales_listos: set[str], ahora: datetime
    ) -> list[int]:
        """Un latido con la sesión iniciada reactiva lo que esperaba sesión en ese portal."""
        reanudadas = []
        filas = self.base.cx.execute(
            "SELECT id, plataforma FROM postulaciones WHERE usuario_id = ? AND estado = ?",
            (usuario_id, E.ESPERANDO_SESION),
        ).fetchall()
        for f in filas:
            if f["plataforma"] in portales_listos and self.reanudar(
                f["id"], ahora, (E.ESPERANDO_SESION,)
            ):
                reanudadas.append(f["id"])
        filas = self.base.cx.execute(
            "SELECT id FROM postulaciones WHERE usuario_id = ? AND estado = ?",
            (usuario_id, E.ESPERANDO_NAVEGADOR),
        ).fetchall()
        for f in filas:
            if self.reanudar(f["id"], ahora, (E.ESPERANDO_NAVEGADOR,)):
                reanudadas.append(f["id"])
        return reanudadas

    def reintentar(self, pid: int, ahora: datetime) -> bool:
        """Vuelve a la cola una postulación terminada sin enviarse (nuevo toque ⚡)."""
        return self._cambiar(pid, REINTENTABLES, E.EN_COLA, ahora, "reintento",
                             navegador_id=None, tomada_en=None, terminada_en=None,
                             envio_pulsado=0)  # fmt: skip

    def a_respaldo(self, pid: int, ahora: datetime, motivo: str, desde: tuple[str, ...]) -> bool:
        return self._cambiar(pid, desde, E.RESPALDO, ahora, motivo, terminada_en=a_texto(ahora))

    # --- vigilancia periódica ------------------------------------------------------------------

    def vigilar(self, ahora: datetime) -> list[Evento]:
        """Plazos y navegadores caídos. Se llama cada minuto desde el servicio."""
        ej = self.config.ejecucion
        caido = timedelta(minutes=self.config.extension.navegador_caido_min)
        eventos: list[Evento] = []
        filas = self.base.cx.execute(
            "SELECT p.*, (SELECT MAX(n.ultimo_latido) FROM navegadores n "
            "WHERE n.usuario_id = p.usuario_id AND n.revocado = 0) AS latido_usuario, "
            "(SELECT n.ultimo_latido FROM navegadores n WHERE n.id = p.navegador_id) "
            "AS latido_navegador FROM postulaciones p WHERE p.estado NOT IN (?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?)",
            (E.ENVIADA, E.YA_POSTULADA, E.VACANTE_CERRADA, E.BLOQUEADA,
             E.FORMULARIO_DESCONOCIDO, E.INCIERTA, E.FALLIDA, E.RESPALDO, E.CANCELADA,
             E.COMPLETADO, E.CUENTA_DISTINTA, "x"),
        ).fetchall()  # fmt: skip
        for f in filas:
            p = Postulacion.de_fila(f)
            latido_usuario = de_texto(f["latido_usuario"])
            latido_navegador = de_texto(f["latido_navegador"])
            espera = ahora - p.actualizada

            def evento(tipo: str, estado: E, detalle: str | None = None, p=p) -> None:
                eventos.append(Evento(tipo, p.id, p.usuario_id, estado, detalle))

            if p.estado == E.EN_COLA and (latido_usuario is None or ahora - latido_usuario > caido):
                if self._cambiar(p.id, (E.EN_COLA,), E.ESPERANDO_NAVEGADOR, ahora):
                    evento("navegador_desconectado", E.ESPERANDO_NAVEGADOR)
            elif p.estado == E.ESPERANDO_NAVEGADOR and ahora - p.creada > timedelta(
                hours=ej.espera_navegador_h
            ):
                if self.a_respaldo(p.id, ahora, "navegador_desconectado", (E.ESPERANDO_NAVEGADOR,)):
                    evento("respaldo", E.RESPALDO, "navegador_desconectado")
            elif p.estado in ACTIVAS and (
                latido_navegador is None or ahora - latido_navegador > caido
            ):
                if p.envio_pulsado:
                    if self._cambiar(p.id, ACTIVAS, E.INCIERTA, ahora, "navegador_cerrado",
                                     terminada_en=a_texto(ahora)):  # fmt: skip
                        evento("resultado", E.INCIERTA, "navegador_cerrado")
                elif self.reanudar(p.id, ahora, ACTIVAS):
                    evento("reencolada", E.EN_COLA, "navegador_cerrado")
            elif p.estado == E.ESPERANDO_USUARIO and espera > timedelta(hours=ej.espera_usuario_h):
                if self.a_respaldo(p.id, ahora, "sin_respuesta", (E.ESPERANDO_USUARIO,)):
                    evento("respaldo", E.RESPALDO, "sin_respuesta")
            elif p.estado == E.ESPERANDO_SESION and espera > timedelta(hours=ej.espera_sesion_h):
                if self.a_respaldo(p.id, ahora, "sin_sesion", (E.ESPERANDO_SESION,)):
                    evento("respaldo", E.RESPALDO, "sin_sesion")
            elif p.estado == E.VERIFICACION and espera > timedelta(hours=ej.espera_verificacion_h):
                motivo = "verificacion_sin_resolver"
                if self._cambiar(p.id, (E.VERIFICACION,), E.BLOQUEADA, ahora, motivo,
                                 terminada_en=a_texto(ahora)):  # fmt: skip
                    evento("resultado", E.BLOQUEADA, motivo)
        return eventos

    def recuperar_al_arrancar(self, ahora: datetime) -> list[Evento]:
        """Tras un reinicio del servicio: lo que estaba activo se decide por envio_pulsado."""
        eventos = []
        filas = self.base.cx.execute(
            "SELECT * FROM postulaciones WHERE estado IN (?, ?, ?)", ACTIVAS
        ).fetchall()
        for f in filas:
            p = Postulacion.de_fila(f)
            if p.envio_pulsado:
                if self._cambiar(p.id, ACTIVAS, E.INCIERTA, ahora, "reinicio",
                                 terminada_en=a_texto(ahora)):  # fmt: skip
                    eventos.append(Evento("resultado", p.id, p.usuario_id, E.INCIERTA, "reinicio"))
            else:
                self.reanudar(p.id, ahora, ACTIVAS)
        return eventos
