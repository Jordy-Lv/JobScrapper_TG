import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from buscador_vacantes.estado import Estado, a_texto
from buscador_vacantes.migrar_historial import clave_desde_registro, fecha_descubrimiento, migrar
from buscador_vacantes.normalizar import huella

FIXTURE = Path(__file__).parent / "fixtures" / "historial_hermes.json"
AHORA = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


@pytest.mark.parametrize(
    ("registro", "esperada"),
    [
        ({"url": "https://co.linkedin.com/jobs/view/pasante-de-sistemas-at-holcim-colombia-4436768819"},
         ("linkedin", "4436768819")),
        ({"url": "https://www.linkedin.com/jobs/view/4429879165"}, ("linkedin", "4429879165")),
        ({"url": "https://co.linkedin.com/jobs/view/practicante-de-an%C3%A1lisis-at-siigo-4454811779"},
         ("linkedin", "4454811779")),
        ({"url": "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-en-cali-da9fa8cf8e67e33b61373e686dcf3405"},
         ("computrabajo", "DA9FA8CF8E67E33B61373E686DCF3405")),
        ({"url": "https://www.elempleo.com/co/ofertas-trabajo/analista-de-pruebas-junior-1886742826"},
         ("elempleo", "1886742826")),
        ({"url": "https://www.getonbrd.com/jobs/junior-backend-engineer-krunchbox-santiago"},
         ("getonboard", "junior-backend-engineer-krunchbox-santiago")),
        ({"url": "https://remoteOK.com/remote-jobs/remote-junior-designer-1135514"},
         ("remoteok", "1135514")),
        ({"url": "", "raw_job_id": "gob-qa-junior-bc-tecnologia-santiago"},
         ("getonboard", "qa-junior-bc-tecnologia-santiago")),
        ({"url": "https://otro.sitio/oferta", "raw_job_id": "magneto-7"}, ("hermes", "magneto-7")),
        ({"cargo": "Sin datos"}, None),
    ],
)  # fmt: skip
def test_clave_desde_registro(registro, esperada):
    assert clave_desde_registro(registro) == esperada


def test_migracion_importa_y_es_idempotente(estado):
    total = len(json.loads(FIXTURE.read_text(encoding="utf-8"))["vacantes"])
    primera = migrar(estado, FIXTURE, AHORA)
    assert primera.leidas == total
    assert primera.omitidas == 1  # el registro sin URL ni id
    assert primera.importadas == total - 1
    assert estado.contar_vistas() == total - 1
    assert estado.contar_vistas(enviadas=True) == total - 1
    assert estado.inicializada()

    segunda = migrar(estado, FIXTURE, AHORA)
    assert segunda.importadas == 0
    assert segunda.ya_existian == total - 1
    assert estado.contar_vistas() == total - 1


def test_vacante_migrada_no_se_vuelve_a_publicar(estado):
    migrar(estado, FIXTURE, AHORA)
    # Misma oferta de LinkedIn vista ahora con la URL canónica
    assert estado.ya_vista("linkedin:4436768819", "otra-huella")
    # Misma vacante en otra fuente, por huella de cargo + empresa
    registro = next(
        r
        for r in json.loads(FIXTURE.read_text(encoding="utf-8"))["vacantes"]
        if "holcim" in r.get("url", "")
    )
    otra = huella(registro["cargo"], registro["empresa"], "computrabajo:XYZ")
    assert estado.ya_vista("computrabajo:XYZ", otra)


def test_fecha_de_envio_es_la_de_hermes(estado):
    assert fecha_descubrimiento({"descubierto_en": "2026-08-16T15:47:42.311939"}, AHORA).month == 8
    assert fecha_descubrimiento({"fecha_descubrimiento": "2026-09-01 10:00:00"}, AHORA).day == 1
    assert fecha_descubrimiento({"fecha": "Hace 3 días"}, AHORA) == AHORA - timedelta(days=2)
    migrar(estado, FIXTURE, AHORA)
    # Nada de lo migrado cae en la ventana de 24 h del resumen diario
    desde = a_texto(AHORA - timedelta(hours=24))
    recientes = estado.cx.execute(
        "SELECT COUNT(*) FROM vistas WHERE enviada_en >= ?", (desde,)
    ).fetchone()[0]
    assert recientes == 0
