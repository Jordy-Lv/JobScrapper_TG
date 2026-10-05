"""Subcomandos `buscador.py asistente …`.

Las dependencias del asistente (grupo `asistente` de uv) se importan aquí dentro, para que el
buscador funcione sin ellas.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from buscador_vacantes import config as cfg
from buscador_vacantes import registro

INSTALAR = "Faltan las dependencias del asistente. Instálalas con:\n  uv sync --group asistente"


def agregar_subcomandos(sub: argparse._SubParsersAction) -> None:
    asistente = sub.add_parser("asistente", help="asistente de postulación (ver README)")
    acciones = asistente.add_subparsers(dest="accion", required=True)
    acciones.add_parser("servicio", help="bot, API y tareas periódicas (lo ejecuta systemd)")
    acciones.add_parser(
        "generar-clave", help="genera una clave maestra para ASISTENTE_CLAVE_CIFRADO"
    )
    rotar = acciones.add_parser(
        "rotar-clave",
        help="vuelve a cifrar los datos con una clave nueva (generada antes con generar-clave)",
    )
    rotar.add_argument("--nueva", required=True, help="la clave maestra nueva")
    enlace = acciones.add_parser("enlace", help="muestra el enlace ⚡ de una vacante (pruebas)")
    enlace.add_argument("clave", help="clave de la vacante, p. ej. computrabajo:ABC123")
    selectores = acciones.add_parser("selectores", help="selectores de los portales")
    selectores.add_argument("operacion", choices=["recargar"])
    paquete = acciones.add_parser(
        "empaquetar-extension", help="arma el .zip de la extensión para la tienda de Edge"
    )
    paquete.add_argument("--destino", default="dist", help="carpeta de salida (por defecto dist)")


def empaquetar_extension(origen: Path, destino: Path) -> Path:
    """Zip con manifest.json en la raíz, en orden fijo y sin archivos ocultos."""
    import json
    import zipfile

    version = json.loads((origen / "manifest.json").read_text(encoding="utf-8"))["version"]
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / f"asistente-postulacion-{version}.zip"
    archivos = sorted(
        p for p in origen.rglob("*")
        if p.is_file() and not any(parte.startswith(".") for parte in p.relative_to(origen).parts)
    )  # fmt: skip
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for archivo in archivos:
            info = zipfile.ZipInfo(archivo.relative_to(origen).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, archivo.read_bytes())
    return salida


def ejecutar(args: argparse.Namespace) -> int:
    if args.accion == "empaquetar-extension":
        salida = empaquetar_extension(cfg.RAIZ / "extension", Path(args.destino))
        print(f"Paquete listo: {salida}")
        return 0
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
        if args.accion == "enlace":
            from buscador_vacantes.asistente.enlaces import enlace

            print(enlace(config.asistente.bot_usuario or "<bot>", args.clave))
            return 0
        if args.accion == "servicio":
            return _servicio(config, secretos)
        base = BaseAsistente.abrir(_ruta(config.asistente.base_datos))
        try:
            if args.accion == "rotar-clave":
                total = cifrado.rotar(base, secretos.asistente_clave_cifrado, args.nueva)
                print(
                    f"Rotados {total} valores. Reemplaza ASISTENTE_CLAVE_CIFRADO en .env por la "
                    "clave nueva y reinicia el servicio del asistente."
                )
                return 0
            if args.accion == "selectores":
                from buscador_vacantes.asistente.servicio import construir_nucleo

                nucleo = construir_nucleo(config, secretos)
                print(f"Selectores cargados: {nucleo.cargar_selectores()}")
                return 0
        finally:
            base.cerrar()
    except cfg.ErrorConfiguracion as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 2


def _servicio(config: cfg.Configuracion, secretos: cfg.Secretos) -> int:
    asistente = config.asistente
    if not asistente.activo:
        print("El asistente está desactivado (asistente.activo: false).")
        return 0
    if not secretos.asistente_bot_token:
        raise cfg.ErrorConfiguracion("Falta ASISTENTE_BOT_TOKEN en .env")
    try:
        from buscador_vacantes.asistente.servicio import Servicio
    except ImportError:
        print(INSTALAR, file=sys.stderr)
        return 2
    registro.configurar(
        _ruta(config.rutas.logs) / "asistente", config.registro.retencion_dias,
        secretos.valores(), config.zona_horaria,
    )  # fmt: skip
    servicio = Servicio(config, secretos)
    asyncio.run(servicio.ejecutar())
    return 0


def _ruta(ruta: Path) -> Path:
    ruta = ruta.expanduser()
    return ruta if ruta.is_absolute() else cfg.RAIZ / ruta
