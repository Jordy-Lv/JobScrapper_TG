"""Preferencias del usuario por portal: el engranaje de cada plataforma en la extensión.

Sin fila guardada rigen los valores por defecto: participa del modo automático del usuario, sin
afinidad mínima propia (usa la del usuario), avisa por Telegram las postulaciones que se
enviaron solas y no pide revisar las respuestas redactadas antes de enviarlas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.textos import NOMBRES_NIVEL_IA
from buscador_vacantes.comun.config import AsistenteNivelesIA
from buscador_vacantes.comun.estado import a_texto, de_texto
from buscador_vacantes.comun.fechas import ZONA

NIVELES_IA = tuple(NOMBRES_NIVEL_IA)  # ahorro, normal, maximo
NIVEL_IA_DEFECTO = "normal"


@dataclass
class PreferenciasPortal:
    automatico: bool = True
    umbral: int | None = None
    avisar: bool = True
    revisar_respuestas: bool = False


class Preferencias:
    def __init__(self, base: BaseAsistente) -> None:
        self.base = base

    # --- nivel de uso de IA (del usuario, no de un portal) -------------------------------

    def nivel_ia(self, usuario_id: int) -> str:
        fila = self.base.cx.execute(
            "SELECT nivel_ia FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        return fila["nivel_ia"] if fila and fila["nivel_ia"] in NIVELES_IA else NIVEL_IA_DEFECTO

    def fijar_nivel_ia(self, usuario_id: int, nivel: str) -> None:
        """Vale para las postulaciones que se encolen después: las que ya están en la cola o en
        curso conservan el nivel con que se encolaron."""
        if nivel not in NIVELES_IA:
            raise ValueError(f"nivel de IA desconocido: {nivel}")
        with self.base.transaccion() as cx:
            cx.execute("UPDATE usuarios SET nivel_ia = ? WHERE id = ?", (nivel, usuario_id))

    @staticmethod
    def nivel_guardado(guardado: str | None) -> str:
        """El nivel con que se encoló una postulación. Las anteriores al esquema 6 lo tienen en
        NULL y corren en Normal: ni el nivel que el usuario elija después ni uno que no tenían
        les cambia el consumo a mitad de camino."""
        return guardado if guardado in NIVELES_IA else NIVEL_IA_DEFECTO

    def nivel_bajado(self, usuario_id: int, ahora: datetime) -> str | None:
        """El nivel al que bajó la cuota agotada al usuario hoy, o None si no bajó (o ya venció)."""
        valor = self.base.kv_obtener(f"nivel_bajado:{usuario_id}")
        nivel, _, hasta = (valor or "").partition("|")
        vence = de_texto(hasta) if hasta else None
        return nivel if nivel in NIVELES_IA and vence is not None and ahora < vence else None

    def bajar_nivel(self, usuario_id: int, nivel: str, ahora: datetime) -> None:
        """Las postulaciones del usuario no pasan de `nivel` hasta que termine el día de
        Colombia (`nivel_bajado_hasta`). Nunca sube un nivel ya bajado."""
        actual = self.nivel_bajado(usuario_id, ahora)
        if nivel not in NIVELES_IA or (
            actual and NIVELES_IA.index(actual) <= NIVELES_IA.index(nivel)
        ):
            return
        manana = datetime.combine(
            ahora.astimezone(ZONA).date() + timedelta(days=1), time(0), tzinfo=ZONA
        )
        self.base.kv_guardar(f"nivel_bajado:{usuario_id}", f"{nivel}|{a_texto(manana)}")

    def nivel_efectivo(self, usuario_id: int, guardado: str | None, ahora: datetime) -> str:
        """El nivel con que corre una postulación: el que traía al encolar, o el menor al que
        bajó la cuota del usuario hoy."""
        nivel = self.nivel_guardado(guardado)
        bajado = self.nivel_bajado(usuario_id, ahora)
        if bajado and NIVELES_IA.index(bajado) < NIVELES_IA.index(nivel):
            return bajado
        return nivel

    # --- modo ensayo: llenar todo y detenerse antes de enviar -------------------------------

    def ensayo_usuario(self, usuario_id: int) -> bool:
        fila = self.base.cx.execute(
            "SELECT ensayo FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        return bool(fila and fila["ensayo"])

    def fijar_ensayo_usuario(self, usuario_id: int, activo: bool) -> None:
        with self.base.transaccion() as cx:
            cx.execute("UPDATE usuarios SET ensayo = ? WHERE id = ?", (int(activo), usuario_id))

    def plataformas_en_ensayo(self, configuradas: list[str]) -> dict[str, str | None]:
        """Plataforma → motivo (o None) de las que se ensayan para todos: las de la configuración
        (`asistente.ensayo.plataformas`) y las que el dueño o el vigía pusieron en ensayo."""
        en_ensayo: dict[str, str | None] = dict.fromkeys(configuradas)
        for f in self.base.cx.execute("SELECT plataforma, motivo FROM plataformas_en_ensayo"):
            en_ensayo[f["plataforma"]] = f["motivo"]
        return en_ensayo

    def poner_en_ensayo(self, plataforma: str, motivo: str | None, ahora: datetime) -> bool:
        """True si la plataforma no estaba ya en ensayo en la base."""
        with self.base.transaccion() as cx:
            cur = cx.execute(
                "INSERT OR IGNORE INTO plataformas_en_ensayo(plataforma, motivo, desde) "
                "VALUES (?, ?, ?)",
                (plataforma, motivo, a_texto(ahora)),
            )
        return bool(cur.rowcount)

    def quitar_de_ensayo(self, plataforma: str) -> bool:
        """Saca la plataforma del ensayo de la base (las de la configuración, se editan allá)."""
        with self.base.transaccion() as cx:
            cur = cx.execute(
                "DELETE FROM plataformas_en_ensayo WHERE plataforma = ?", (plataforma,)
            )
        return bool(cur.rowcount)

    def uso_ia_hoy(self, usuario_id: int, ahora: datetime) -> tuple[int, int]:
        """(llamadas, tokens) exitosos del día calendario de Colombia, como los cuenta el tope."""
        inicio = datetime.combine(ahora.astimezone(ZONA).date(), time(0), tzinfo=ZONA)
        fila = self.base.cx.execute(
            "SELECT COUNT(*), COALESCE(SUM(COALESCE(tokens_in, 0) + COALESCE(tokens_out, 0)), 0) "
            "FROM ia_uso WHERE usuario_id = ? AND ts >= ? AND ok = 1",
            (usuario_id, a_texto(inicio)),
        ).fetchone()
        return fila[0], fila[1]

    def resumen_nivel_ia(
        self, usuario_id: int, niveles: AsistenteNivelesIA, ahora: datetime
    ) -> dict:
        """Lo que muestran `/ia nivel` y el popup: nivel actual, consumo estimado por nivel y uso
        de hoy."""
        llamadas, tokens = self.uso_ia_hoy(usuario_id, ahora)
        return {
            "nivel": self.nivel_ia(usuario_id),
            "niveles": [
                {
                    "clave": clave,
                    "nombre": NOMBRES_NIVEL_IA[clave],
                    "llamadas_estimadas": getattr(niveles, clave).llamadas_estimadas,
                }
                for clave in NIVELES_IA
            ],
            "hoy": {"llamadas": llamadas, "tokens": tokens},
        }

    def obtener(self, usuario_id: int, plataforma: str) -> PreferenciasPortal:
        fila = self.base.cx.execute(
            "SELECT automatico, umbral, avisar, revisar_respuestas FROM preferencias_portal "
            "WHERE usuario_id = ? AND plataforma = ?",
            (usuario_id, plataforma),
        ).fetchone()
        if fila is None:
            return PreferenciasPortal()
        return PreferenciasPortal(
            bool(fila["automatico"]), fila["umbral"], bool(fila["avisar"]),
            bool(fila["revisar_respuestas"]),
        )  # fmt: skip

    def guardar(
        self,
        usuario_id: int,
        plataforma: str,
        ahora: datetime,
        *,
        automatico: bool,
        umbral: int | None,
        avisar: bool,
        revisar_respuestas: bool = False,
    ) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO preferencias_portal(usuario_id, plataforma, automatico, umbral, "
                "avisar, revisar_respuestas, actualizada) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(usuario_id, plataforma) DO UPDATE SET "
                "automatico = excluded.automatico, umbral = excluded.umbral, "
                "avisar = excluded.avisar, revisar_respuestas = excluded.revisar_respuestas, "
                "actualizada = excluded.actualizada",
                (
                    usuario_id,
                    plataforma,
                    int(automatico),
                    umbral,
                    int(avisar),
                    int(revisar_respuestas),
                    a_texto(ahora),
                ),  # fmt: skip
            )
