"""Destino de una vacante de LinkedIn: clasificarlo antes de abrirlo y compartirlo entre usuarios.

El destino lo lee la extensión con la sesión del usuario (el enlace `/safety/go`); aquí se limpia,
se sigue un acortador conocido, se clasifica por su dominio y se guarda. Lo que el bot no puede o no
debe hacer (mensajería, ATS con cuenta, inicios de sesión ajenos) va al respaldo sin abrir nada.
Solo se guarda la URL limpia del destino, que es pública, nunca datos de quien la resolvió.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.medicion_linkedin import familia_de, limpiar_destino
from buscador_vacantes.asistente.recetas import barrera_de, host_de
from buscador_vacantes.comun.config import AsistenteLinkedin, AsistenteMedicionLinkedin
from buscador_vacantes.comun.estado import a_texto, de_texto

MAX_SALTOS = 5  # redirecciones de acortadores que se siguen
MOTIVO_MENSAJERIA = "destino_mensajeria"
MOTIVO_CON_CUENTA = "ats_con_cuenta"
MOTIVO_OAUTH = "oauth"
# El motivo de una barrera aprendida (recetas.MOTIVOS_BARRERA) → el que ve el usuario
_MOTIVOS_BARRERA = {"mensajeria": MOTIVO_MENSAJERIA}


@dataclass(frozen=True)
class Destino:
    url: str  # limpia, tras seguir el acortador
    familia: str
    motivo: str | None = None  # None: se puede abrir; si no, va al respaldo por este motivo


def _del_host(host: str, patron: str) -> bool:
    return host == patron or host.endswith("." + patron)


def _coincide(url: str, entrada: str) -> bool:
    """La URL cae en la entrada: un esquema («mailto:»), un host o un host con ruta."""
    entrada = entrada.lower().strip()
    if entrada.endswith(":"):
        return url.lower().startswith(entrada)
    host_entrada, _, ruta_entrada = entrada.strip("/").partition("/")
    if not _del_host(host_de(url), host_entrada.removeprefix("www.")):
        return False
    return not ruta_entrada or urlparse(url).path.lower().lstrip("/").startswith(ruta_entrada)


def es_acortador(url: str, config: AsistenteLinkedin) -> bool:
    host = host_de(url)
    return any(_del_host(host, a.lower()) for a in config.acortadores)


async def seguir_acortadores(
    url: str,
    config: AsistenteLinkedin,
    ubicacion: Callable[[str], Awaitable[str | None]],
) -> str:
    """La URL final tras seguir las redirecciones de los acortadores de la configuración. Solo
    se pide la página de un acortador conocido (nunca un host arbitrario); `ubicacion` devuelve su
    cabecera `Location`, o None si no redirige o falla."""
    for _ in range(MAX_SALTOS):
        if not es_acortador(url, config):
            return url
        destino = await ubicacion(url)
        if not destino:
            return url
        url = urljoin(url, destino)
    return url


def clasificar(
    url: str,
    linkedin: AsistenteLinkedin,
    medicion: AsistenteMedicionLinkedin,
    base: BaseAsistente,
) -> Destino:
    """Mensajería, inicio de sesión ajeno, familia con cuenta o dominio barrera aprendido → respaldo
    con su motivo; cualquier otro → se abre, con su familia (`propio` si no es de ninguna)."""
    url = limpiar_destino(url)
    familia = familia_de(url, medicion.familias)
    if any(_coincide(url, e) for e in linkedin.mensajeria):
        return Destino(url, familia, MOTIVO_MENSAJERIA)
    if any(_coincide(url, e) for e in linkedin.hosts_prohibidos):
        return Destino(url, familia, MOTIVO_OAUTH)
    if familia in linkedin.familias_con_cuenta:
        return Destino(url, familia, MOTIVO_CON_CUENTA)
    if motivo := barrera_de(base, host_de(url)):
        return Destino(url, familia, _MOTIVOS_BARRERA.get(motivo, motivo))
    return Destino(url, familia)


def guardar(base: BaseAsistente, id_vacante: str, destino: Destino, ahora: datetime) -> None:
    """Guarda (o actualiza) el destino de la vacante para todos los usuarios."""
    ahora_txt = a_texto(ahora)
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO destinos_linkedin(id_vacante, destino, familia, resuelto, ultima_vez) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id_vacante) DO UPDATE SET "
            "destino = excluded.destino, familia = excluded.familia, "
            "resuelto = excluded.resuelto, ultima_vez = excluded.ultima_vez",
            (id_vacante, destino.url, destino.familia, ahora_txt, ahora_txt),
        )


def vigente(
    base: BaseAsistente, id_vacante: str, ahora: datetime, dias: int
) -> dict[str, str] | None:
    """El destino guardado de la vacante si se resolvió hace menos de `dias`, o None."""
    fila = base.cx.execute(
        "SELECT destino, familia, resuelto FROM destinos_linkedin WHERE id_vacante = ?",
        (id_vacante,),
    ).fetchone()
    if fila is None:
        return None
    resuelto = de_texto(fila["resuelto"])
    if resuelto is None or ahora - resuelto >= timedelta(days=dias):
        return None
    return {"destino": fila["destino"], "familia": fila["familia"]}


def usar(base: BaseAsistente, id_vacante: str, ahora: datetime) -> None:
    """Anota que el destino guardado se volvió a usar."""
    with base.transaccion() as cx:
        cx.execute(
            "UPDATE destinos_linkedin SET ultima_vez = ? WHERE id_vacante = ?",
            (a_texto(ahora), id_vacante),
        )
