from datetime import datetime

import pytest

from buscador_vacantes import corrida as buscador
from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.ia_cliente import RespuestaIA
from buscador_vacantes.incidentes import TIPOS
from buscador_vacantes.simulacion import NotificadorConsola, simular, validar_objetivo

AHORA = datetime(2026, 10, 3, 10, 0, tzinfo=ZONA)


@pytest.fixture
def config():
    return cargar_configuracion()


def correr(config, objetivo, falla=None):
    salida = []
    simular(objetivo, config, NotificadorConsola(salida.append), "-100PRUEBA", buscador.FUENTES,
            falla_ia=falla, ahora=AHORA)  # fmt: skip
    return "\n".join(salida)


@pytest.mark.parametrize("tipo", [t for t in TIPOS if t != "fallo_envio"])
def test_cada_tipo_con_api_caida(config, tipo):
    texto = correr(config, f"linkedin:{tipo}", "api_caida")
    assert f"🚨 Incidente: LinkedIn · {tipo}" in texto
    assert "Diagnóstico IA no disponible (motivo: error del servidor (HTTP 503))" in texto
    assert "-100PRUEBA" in texto


def test_saldo_bajo(config):
    texto = correr(config, "magneto:captcha", "saldo_bajo")
    assert "motivo: saldo bajo" in texto and "💳 Saldo DeepSeek bajo: $0.42" in texto


def test_fallo_envio_y_red(config):
    assert "Telegram · fallo_envio" in correr(config, "telegram:fallo_envio", "api_caida")
    assert "⚠️ El PC estuvo sin internet de 08:20 a 10:00" in correr(config, "red:sin_conexion")


def test_diagnostico_ia_simulado(config, monkeypatch):
    diagnostico = {"diagnosticos": [{
        "fuente": "computrabajo", "tipo": "cambio_html", "severidad": "media",
        "causa_probable": "Cambió el HTML", "evidencia_clave": "0 items con 200",
        "accion_recomendada": "Actualizar selectores", "requiere_intervencion": True,
        "sugerencia_tecnica": "section.offer-card"}]}  # fmt: skip
    monkeypatch.setattr(
        "buscador_vacantes.simulacion.FALLAS_IA", {"fija": RespuestaIA(True, diagnostico)}
    )
    texto = correr(config, "computrabajo:cambio_html", "fija")
    assert "<b>Incidente: Computrabajo · cambio_html</b> (severidad media)" in texto
    assert "<pre>section.offer-card</pre>" in texto


def test_no_toca_el_estado_real(config, tmp_path, monkeypatch):
    real = cargar_configuracion().rutas.base_datos
    antes = real.exists() and real.stat().st_mtime
    correr(config, "linkedin:bloqueo", "api_caida")
    assert (real.exists() and real.stat().st_mtime) == antes


@pytest.mark.parametrize("objetivo", ["linkedin:inventado", "noexiste:bloqueo", "linkedin",
                                      "linkedin:fallo_envio"])  # fmt: skip
def test_objetivo_invalido(config, objetivo):
    with pytest.raises(ValueError):
        validar_objetivo(objetivo, config)


def test_cli_simulacion_en_consola(capsys):
    codigo = buscador.main(["--simular-incidente", "elempleo:error_servidor",
                            "--simular-falla-ia", "api_caida", "--dry-run"])  # fmt: skip
    assert codigo == 0
    assert "elempleo · error_servidor" in capsys.readouterr().out
    assert buscador.main(["--simular-incidente", "x:y", "--dry-run"]) == 2
