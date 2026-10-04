"""Subcomandos `buscador.py asistente …`.

Las dependencias del asistente (grupo `asistente` de uv) se importan aquí dentro, para que el
buscador funcione sin ellas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from buscador_vacantes import config as cfg

INSTALAR = "Faltan las dependencias del asistente. Instálalas con:\n  uv sync --group asistente"


def agregar_subcomandos(sub: argparse._SubParsersAction) -> None:
    asistente = sub.add_parser("asistente", help="asistente de postulación (ver README)")
    acciones = asistente.add_subparsers(dest="accion", required=True)
    acciones.add_parser(
        "generar-clave", help="genera una clave maestra para ASISTENTE_CLAVE_CIFRADO"
    )
    rotar = acciones.add_parser(
        "rotar-clave",
        help="vuelve a cifrar los datos con una clave nueva (generada antes con generar-clave)",
    )
    rotar.add_argument("--nueva", required=True, help="la clave maestra nueva")


def ejecutar(args: argparse.Namespace) -> int:
    try:
        from buscador_vacantes.asistente import cifrado
        from buscador_vacantes.asistente.datos import BaseAsistente
    except ImportError:
        print(INSTALAR, file=sys.stderr)
        return 2

    if args.accion == "generar-clave":
        print(cifrado.generar_clave())
        print(
            "Guárdala en .env como ASISTENTE_CLAVE_CIFRADO y respáldala en un lugar seguro: "
            "si se pierde, los usuarios deben registrar de nuevo su clave de Gemini.",
            file=sys.stderr,
        )
        return 0

    try:
        config = cfg.cargar_configuracion(args.config)
        secretos = cfg.cargar_secretos(config, args.env, exigir_envio=False)
        if config.asistente is None:
            raise cfg.ErrorConfiguracion("config.yaml no tiene la sección asistente")
        base = BaseAsistente.abrir(_ruta(config.asistente.base_datos))
        try:
            if args.accion == "rotar-clave":
                total = cifrado.rotar(base, secretos.asistente_clave_cifrado, args.nueva)
                print(
                    f"Rotados {total} valores. Reemplaza ASISTENTE_CLAVE_CIFRADO en .env por la "
                    "clave nueva y reinicia el servicio del asistente."
                )
                return 0
        finally:
            base.cerrar()
    except cfg.ErrorConfiguracion as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 2


def _ruta(ruta: Path) -> Path:
    ruta = ruta.expanduser()
    return ruta if ruta.is_absolute() else cfg.RAIZ / ruta
