"""elempleo en el servidor: selectores, nota obligatoria, bloqueos y cuenta asociada.

El flujo en el navegador se prueba en test_extension.py (pruebas `test_elempleo_*`).
"""

import json
from datetime import UTC, datetime

import pytest

pytest.importorskip("cryptography", reason="requiere uv sync --group asistente")
pytest.importorskip("fastapi", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import textos as t  # noqa: E402
from buscador_vacantes.asistente.api import campos_obligatorios  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cuentas_portal import CuentasPortal, EstadoCuenta  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.comun import config as cfg  # noqa: E402

SELECTORES = cfg.RAIZ / "assets" / "asistente" / "selectores"
AHORA = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
# Acciones que motor.js y servicio.js saben ejecutar
ACCIONES = {"detectar", "esperar", "clic", "enviar", "ir", "formulario", "llenar",
            "cv_liberar", "cv_subir", "cv_verificar", "confirmar"}  # fmt: skip


def selectores(plataforma: str) -> dict:
    return json.loads((SELECTORES / f"{plataforma}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("archivo", sorted(SELECTORES.glob("*.json")), ids=lambda p: p.stem)
def test_los_pasos_usan_acciones_y_textos_conocidos(archivo):
    sel = json.loads(archivo.read_text(encoding="utf-8"))
    for paso in sel["postular"]:
        assert paso["accion"] in ACCIONES, paso
        for caso in paso.get("casos", []):
            if "texto" in caso:
                assert sel["textos"].get(caso["texto"]), (paso["nombre"], caso["texto"])
            motivo = caso.get("motivo")
            if caso["resultado"] == "bloqueada" and motivo and motivo.startswith("portal_"):
                assert motivo in t.BLOQUEOS_PORTAL, motivo


def test_elempleo_postula_en_perfil_multiple_y_omite_el_video():
    sel = selectores("elempleo")
    assert sel["cv"]["modo"] == "perfil_multiple"
    pasos = {p["nombre"]: p for p in sel["postular"]}
    # El video de V-Prez se omite y nunca se pulsa "Continuar proceso" (graba su imagen)
    todo = json.dumps(sel["postular"])
    assert "btnSkipVprez" in todo and "btnRedirectVprez" not in todo
    assert pasos["omitir_video"]["opcional"] and pasos["omitir_video_tras_enviar"]["opcional"]
    # El clic que puede enviar la postulación queda registrado antes de pulsarlo
    assert pasos["aplicar"]["envia"]
    assert pasos["cv_subir"]["accion"] == "cv_subir" and pasos["cv_verificar"]
    assert list(pasos).index("cv_subir") < list(pasos).index("enviar")


def test_la_nota_de_presentacion_de_elempleo_es_obligatoria():
    """Si la IA no la redacta, el servidor la pregunta por la card en vez de enviarla vacía."""
    assert campos_obligatorios(("1", selectores("elempleo"))) == {"ApplicationNote"}
    assert campos_obligatorios(("1", selectores("computrabajo"))) == set()
    assert campos_obligatorios(None) == set()


def test_bloqueo_por_hoja_de_vida_incompleta_explica_que_hacer():
    texto = t.BLOQUEOS_PORTAL["portal_perfil_incompleto"].format(portal="elempleo")
    assert "elempleo" in texto and "Hoja de vida" in texto


@pytest.fixture
def cuentas(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "asistente.db")
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO usuarios(telegram_id, directorio, creado) VALUES (1, 'u', ?)",
            (AHORA.isoformat(),),
        )
    yield CuentasPortal(base, Cifrador(generar_clave()))
    base.cerrar()


def test_cuenta_de_elempleo_primero_se_confirma(cuentas):
    v = cuentas.verificar(1, "elempleo", "ana.perez@example.com", AHORA)
    assert (v.estado, v.nuevo) == (EstadoCuenta.POR_CONFIRMAR, True)
    cuentas.confirmar(1, "elempleo", AHORA)
    assert cuentas.verificar(1, "elempleo", "ana.perez@example.com", AHORA).estado == "ok"


def test_otra_cuenta_de_elempleo_no_postula_y_se_avisa_enmascarada(cuentas):
    cuentas.verificar(1, "elempleo", "ana.perez@example.com", AHORA)
    cuentas.confirmar(1, "elempleo", AHORA)
    v = cuentas.verificar(1, "elempleo", "otra.persona@example.com", AHORA)
    assert v.estado == EstadoCuenta.DISTINTA
    assert v.encontrado_oculto == "o***@example.com"


def test_sin_correo_legible_de_elempleo(cuentas):
    assert cuentas.verificar(1, "elempleo", None, AHORA).estado == EstadoCuenta.SIN_CORREO
