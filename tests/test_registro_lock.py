import logging
from datetime import date, timedelta

import pytest

import registro
from lock import CorridaActiva, Lock

TOKEN = "123456789:AAFakeTokenFakeTokenFakeTokenFake12"


@pytest.fixture(autouse=True)
def restaurar_logging():
    raiz = logging.getLogger()
    previos, nivel = list(raiz.handlers), raiz.level
    yield
    for handler in list(raiz.handlers):
        raiz.removeHandler(handler)
        handler.close()
    for handler in previos:
        raiz.addHandler(handler)
    raiz.setLevel(nivel)


def test_retencion_borra_log_de_hace_15_dias(tmp_path):
    hoy = date(2026, 10, 3)
    viejo = tmp_path / f"{(hoy - timedelta(days=15)).isoformat()}.log"
    limite = tmp_path / f"{(hoy - timedelta(days=14)).isoformat()}.log"
    otro = tmp_path / "notas.txt"
    for archivo in (viejo, limite, otro):
        archivo.write_text("x")
    borrados = registro.limpiar_logs(tmp_path, 14, hoy)
    assert borrados == [viejo]
    assert not viejo.exists()
    assert limite.exists() and otro.exists()


def test_token_no_aparece_en_el_log(tmp_path):
    ruta = registro.configurar(tmp_path, 14, secretos=["sk-clave-secreta-deepseek", TOKEN])
    log = logging.getLogger("prueba")
    log.info("Enviando a https://api.telegram.org/bot%s/sendMessage", TOKEN)
    log.info("Clave sk-clave-secreta-deepseek y otra sk-desconocida1234567")
    try:
        raise RuntimeError(f"fallo con {TOKEN}")
    except RuntimeError:
        log.exception("Error")
    for handler in logging.getLogger().handlers:
        handler.flush()
    contenido = ruta.read_text(encoding="utf-8")
    assert TOKEN not in contenido
    assert "sk-clave-secreta-deepseek" not in contenido
    assert "sk-desconocida1234567" not in contenido
    assert "bot***/sendMessage" in contenido
    assert "Error" in contenido


def test_log_por_dia(tmp_path):
    ruta = registro.configurar(tmp_path, 14)
    assert ruta.parent == tmp_path
    assert ruta.name.endswith(".log")
    date.fromisoformat(ruta.stem)


def test_segundo_lock_falla_de_inmediato(tmp_path):
    ruta = tmp_path / "data" / "buscador.lock"
    with Lock(ruta):
        with pytest.raises(CorridaActiva):
            with Lock(ruta):
                pass
    with Lock(ruta):
        pass
