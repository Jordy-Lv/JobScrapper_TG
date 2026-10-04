"""Publicación de vacantes: banner según el modo, envío por mensajes y marca de enviadas."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from buscador_vacantes import config as cfg
from buscador_vacantes.estado import Estado
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.formato import componer
from buscador_vacantes.modelo import Vacante
from buscador_vacantes.notificador_telegram import Notificador

log = logging.getLogger(__name__)

PAUSA_ENTRE_MENSAJES_S = 1.0


@dataclass
class Rechazo:
    descripcion: str
    codigo: int | None
    claves: list[str]


@dataclass
class ResultadoPublicacion:
    mensajes_enviados: int = 0
    enviadas: list[str] = field(default_factory=list)
    no_enviadas: list[str] = field(default_factory=list)
    rechazos: list[Rechazo] = field(default_factory=list)
    banner_enviado: bool = False
    error_banner: str | None = None


def _clave_banner(prueba: bool) -> str:
    return "ultimo_banner_prueba" if prueba else "ultimo_banner"


def _debe_enviar_banner(banner: cfg.Banner, estado: Estado, hoy: str, prueba: bool) -> bool:
    if banner.modo == "nunca":
        return False
    if banner.modo == "siempre":
        return True
    return estado.kv_obtener(_clave_banner(prueba)) != hoy


def publicar(
    candidatas: list[tuple[Vacante, str]],
    notificador: Notificador,
    estado: Estado,
    banner: cfg.Banner,
    chat_id: str,
    ahora: datetime,
    *,
    prueba: bool = False,
    raiz: Path = Path("."),
    dormir: Callable[[float], None] = time.sleep,
    bot_asistente: str | None = None,
) -> ResultadoPublicacion:
    """Envía las vacantes (con su huella). Cada vacante se marca solo si su mensaje se confirma.

    En modo prueba los envíos no cuentan como enviados al canal real y los fallos no se
    reintentan desde la cola del canal.
    """
    resultado = ResultadoPublicacion()
    if not candidatas:
        return resultado
    por_clave = {vacante.clave: (vacante, huella) for vacante, huella in candidatas}

    hoy = ahora.astimezone(ZONA).date().isoformat()
    if _debe_enviar_banner(banner, estado, hoy, prueba):
        envio = notificador.enviar_foto(chat_id, raiz / banner.imagen)
        if envio.ok:
            resultado.banner_enviado = True
            estado.kv_guardar(_clave_banner(prueba), hoy)
        else:
            # El banner es decorativo: su fallo no impide publicar ni abre fallo_envio
            log.warning("No se pudo enviar el banner: %s", envio.error)
            resultado.error_banner = envio.error

    mensajes = componer([v for v, _ in candidatas], ahora, bot_asistente=bot_asistente)
    for numero, mensaje in enumerate(mensajes):
        if numero or resultado.banner_enviado:
            dormir(PAUSA_ENTRE_MENSAJES_S)
        envio = notificador.enviar_mensaje(chat_id, mensaje.texto)
        if envio.ok:
            resultado.mensajes_enviados += 1
            for clave in mensaje.claves:
                vacante, huella = por_clave[clave]
                estado.registrar_vista(vacante, huella, momento=ahora, enviada=True, prueba=prueba)
                if not prueba:
                    estado.quitar_por_enviar(clave)
                resultado.enviadas.append(clave)
        else:
            log.error(
                "Telegram rechazó un mensaje con %s vacantes: %s", len(mensaje.claves), envio.error
            )
            resultado.rechazos.append(Rechazo(envio.error or "error", envio.codigo, mensaje.claves))
            for clave in mensaje.claves:
                vacante, huella = por_clave[clave]
                if not prueba:
                    estado.guardar_por_enviar(vacante, huella, ahora)
                resultado.no_enviadas.append(clave)
    return resultado
