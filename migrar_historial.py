"""Importa historial_vacantes.json de Hermes como vacantes ya enviadas (idempotente)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from estado import Estado, ahora_utc
from fechas import ZONA
from modelo import Vacante
from normalizar import huella

log = logging.getLogger(__name__)

_NUMERO_FINAL = re.compile(r"(\d{6,})/?$")
_HEX_FINAL = re.compile(r"([A-Fa-f0-9]{32})/?$")
_SLUG_GETONBOARD = re.compile(r"/jobs/([^/?#]+)")


# Sin fecha de descubrimiento, la vacante se fecha antes de la ventana del resumen diario
# para que la migración no aparezca como "enviadas hoy"
ANTIGUEDAD_SIN_FECHA = timedelta(days=2)


def fecha_descubrimiento(registro: dict, momento: datetime) -> datetime:
    for campo in ("descubierto_en", "fecha_descubrimiento"):
        texto = (registro.get(campo) or "").strip()
        if not texto:
            continue
        try:
            fecha = datetime.fromisoformat(texto)
        except ValueError:
            continue
        fecha = fecha if fecha.tzinfo else fecha.replace(tzinfo=ZONA)
        if fecha <= momento:
            return fecha
    return momento - ANTIGUEDAD_SIN_FECHA


@dataclass
class ResultadoMigracion:
    leidas: int = 0
    importadas: int = 0
    ya_existian: int = 0
    omitidas: int = 0


def clave_desde_registro(registro: dict) -> tuple[str, str] | None:
    """Deriva (fuente, id_nativo) de la URL, con el mismo id que producen las fuentes nuevas."""
    url = (registro.get("url") or "").strip()
    dominio = urlparse(url).netloc.lower()
    ruta = unquote(urlparse(url).path)
    if "linkedin.com" in dominio and (m := _NUMERO_FINAL.search(ruta)):
        return "linkedin", m.group(1)
    if "computrabajo" in dominio and (m := _HEX_FINAL.search(ruta)):
        return "computrabajo", m.group(1).upper()
    if "elempleo.com" in dominio and (m := _NUMERO_FINAL.search(ruta)):
        return "elempleo", m.group(1)
    if "getonbrd.com" in dominio and (m := _SLUG_GETONBOARD.search(ruta)):
        return "getonboard", m.group(1)
    if "remoteok.com" in dominio and (m := _NUMERO_FINAL.search(ruta)):
        return "remoteok", m.group(1)

    crudo = str(registro.get("raw_job_id") or "").strip()
    if crudo.startswith("gob-"):
        return "getonboard", crudo[4:]
    if crudo:
        return "hermes", crudo
    return None


def migrar(estado: Estado, ruta: Path | str, momento: datetime | None = None) -> ResultadoMigracion:
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    registros = datos.get("vacantes", []) if isinstance(datos, dict) else datos
    momento = momento or ahora_utc()
    resultado = ResultadoMigracion(leidas=len(registros))
    for registro in registros:
        if not isinstance(registro, dict):
            resultado.omitidas += 1
            continue
        clave = clave_desde_registro(registro)
        if clave is None:
            resultado.omitidas += 1
            log.warning("Registro sin URL ni id, omitido: %s", registro.get("cargo"))
            continue
        fuente, id_fuente = clave
        vacante = Vacante(
            fuente=fuente,
            id_fuente=id_fuente,
            titulo=(registro.get("cargo") or "").strip(),
            empresa=(registro.get("empresa") or registro.get("company") or "").strip(),
            url=(registro.get("url") or "").strip(),
            keyword="hermes",
        )
        existe = estado.cx.execute(
            "SELECT 1 FROM vistas WHERE clave = ?", (vacante.clave,)
        ).fetchone()
        if existe:
            resultado.ya_existian += 1
            continue
        estado.registrar_vista(
            vacante,
            huella(vacante.titulo, vacante.empresa, vacante.clave),
            momento=fecha_descubrimiento(registro, momento),
            enviada=True,
        )
        resultado.importadas += 1
    estado.marcar_inicializada(momento)
    log.info(
        "Migración: %s leídas, %s importadas, %s ya existían, %s omitidas",
        resultado.leidas,
        resultado.importadas,
        resultado.ya_existian,
        resultado.omitidas,
    )
    return resultado
