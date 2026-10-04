from pathlib import Path

import pytest
import yaml

from buscador_vacantes.config import RAIZ, ErrorConfiguracion, cargar_configuracion, cargar_secretos
from buscador_vacantes.modelo import Categoria

VARIABLES = (
    "ASISTENTE_BOT_TOKEN",
    "ASISTENTE_CLAVE_CIFRADO",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_CHAT_PRUEBA",
    "DEEPSEEK_API_KEY",
    "HEALTHCHECK_URL",
)


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    for nombre in VARIABLES:
        monkeypatch.delenv(nombre, raising=False)


@pytest.fixture
def config():
    return cargar_configuracion()


def escribir_config(tmp_path: Path, cambio) -> Path:
    datos = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    cambio(datos)
    ruta = tmp_path / "config.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return ruta


def escribir_env(tmp_path: Path, **valores) -> Path:
    ruta = tmp_path / ".env"
    ruta.write_text("".join(f"{k}={v}\n" for k, v in valores.items()), encoding="utf-8")
    return ruta


ENV_COMPLETO = {
    "TELEGRAM_BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
    "TELEGRAM_CHAT_ID": "-1004429829042",
    "DEEPSEEK_API_KEY": "sk-prueba",
    "HEALTHCHECK_URL": "https://hc-ping.com/uuid",
}


def test_config_inicial_carga(config):
    assert config.zona_horaria == "America/Bogota"
    assert config.fuentes["linkedin"].presupuesto == 3
    assert config.fuentes["computrabajo"].presupuesto == 8
    assert config.fuentes["computrabajo"].paginas_nucleo == 3
    assert config.fuentes["elempleo"].presupuesto == 5
    assert config.fuentes["magneto"].paginas_nucleo == 1
    assert config.fuentes["getonboard"].presupuesto == 5
    assert config.fuentes["sena"].activa is False
    assert config.banner.modo == "diario"
    assert config.ia.presupuesto_dia.clasificador == 300
    assert config.ia.presupuesto_dia.reportero == 20
    assert config.ia.presupuesto_dia.resumen == 3
    assert config.clasificador.politica_sin_ia == "descartar"


def test_palabras_clave_cubren_roles(config):
    assert "aprendiz SENA" in config.palabras_clave.nucleo
    roles = set(config.palabras_clave.cola_larga)
    assert {
        "desarrollo",
        "infraestructura",
        "redes",
        "bases_datos",
        "soporte",
        "datos",
        "qa",
        "ciberseguridad",
    } <= roles
    plana = config.palabras_clave.cola_larga_plana
    assert len(plana) == len(set(plana))
    assert "DBA junior" in plana


def test_nucleo_exclusivo_de_practicas(config):
    nucleo = config.palabras_clave.nucleo
    assert not [k for k in nucleo if "junior" in k.lower()]
    assert {"aprendiz SENA", "aprendiz ADSO", "practicante TI"} <= set(nucleo)
    assert not set(nucleo) & set(config.palabras_clave.cola_larga_plana)


def test_nucleo_ocupa_al_menos_la_mitad_del_presupuesto(config):
    for nombre, fuente in config.fuentes.items():
        if not fuente.activa or fuente.filtra_nivel:
            continue
        reservados = fuente.reservado_nucleo * fuente.paginas_nucleo
        assert reservados * 2 >= fuente.presupuesto, nombre


def test_fuente_spe(config):
    spe = config.fuentes["spe"]
    assert spe.activa and spe.filtra_nivel
    assert spe.presupuesto == 2
    assert "symplicity.com" in spe.opciones["dominios_con_login"]
    assert "spe" in config.filtros.ubicacion.fuentes_colombianas


def test_prompt_decide_practicas_de_otra_area(config):
    prompt = config.clasificador.prompt_sistema
    assert "Práctica de otra área" in prompt
    assert "funciones principales son de TI" in prompt


def test_areas_cubren_categorias(config):
    categorias = {area.categoria for area in config.filtros.areas}
    esperadas = set(Categoria) - {Categoria.PRACTICAS, Categoria.OTROS_TI}
    assert categorias == esperadas


def test_campo_invalido_indica_el_campo(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["fuentes"]["linkedin"].update(presupuesto="tres"))
    with pytest.raises(ErrorConfiguracion) as error:
        cargar_configuracion(ruta)
    assert "fuentes.linkedin.presupuesto" in str(error.value)


def test_campo_desconocido_es_error(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["banner"].update(mdo="diario"))
    with pytest.raises(ErrorConfiguracion) as error:
        cargar_configuracion(ruta)
    assert "banner.mdo" in str(error.value)


def test_modo_banner_invalido(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["banner"].update(modo="semanal"))
    with pytest.raises(ErrorConfiguracion, match="banner.modo"):
        cargar_configuracion(ruta)


def test_reserva_mayor_que_presupuesto(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["fuentes"]["linkedin"].update(reservado_nucleo=9))
    with pytest.raises(ErrorConfiguracion, match="reservado_nucleo"):
        cargar_configuracion(ruta)


def test_paginas_del_nucleo_cuentan_en_el_presupuesto(tmp_path):
    ruta = escribir_config(
        tmp_path,
        lambda d: d["fuentes"]["computrabajo"].update(
            presupuesto=8, reservado_nucleo=3, paginas_nucleo=3
        ),
    )
    with pytest.raises(ErrorConfiguracion, match="paginas_nucleo"):
        cargar_configuracion(ruta)


def test_archivo_inexistente(tmp_path):
    with pytest.raises(ErrorConfiguracion, match="No existe"):
        cargar_configuracion(tmp_path / "nada.yaml")


def test_secretos_completos(tmp_path, config):
    secretos = cargar_secretos(config, escribir_env(tmp_path, **ENV_COMPLETO))
    assert secretos.telegram_chat_id == "-1004429829042"
    assert secretos.deepseek_api_key == "sk-prueba"
    assert "sk-prueba" in secretos.valores()


def test_secreto_faltante(tmp_path, config):
    valores = dict(ENV_COMPLETO)
    del valores["DEEPSEEK_API_KEY"]
    with pytest.raises(ErrorConfiguracion) as error:
        cargar_secretos(config, escribir_env(tmp_path, **valores))
    assert "DEEPSEEK_API_KEY" in str(error.value)
    assert "TELEGRAM_CHAT_ID" not in str(error.value)


def test_dry_run_no_exige_secretos(tmp_path):
    # Sin token de Hermes: en el PC real ~/.hermes/.env sí existe
    sin_hermes = {"archivo": str(tmp_path / "no-hermes.env"), "variable": "TELEGRAM_BOT_TOKEN"}
    config = cargar_configuracion(
        escribir_config(tmp_path, lambda d: d["telegram"].update(token_hermes=sin_hermes))
    )
    secretos = cargar_secretos(config, tmp_path / "no-existe.env", exigir_envio=False)
    assert secretos.telegram_bot_token is None


def test_chat_prueba_exigido(tmp_path, config):
    with pytest.raises(ErrorConfiguracion, match="TELEGRAM_CHAT_PRUEBA"):
        cargar_secretos(config, escribir_env(tmp_path, **ENV_COMPLETO), exigir_chat_prueba=True)


def test_token_desde_configuracion_de_hermes(tmp_path):
    env_hermes = tmp_path / "hermes.env"
    env_hermes.write_text("OTRA=1\nTELEGRAM_BOT_TOKEN=999:token-de-hermes\n", encoding="utf-8")
    ruta = escribir_config(
        tmp_path,
        lambda d: d["telegram"].update(
            token_hermes={"archivo": str(env_hermes), "variable": "TELEGRAM_BOT_TOKEN"}
        ),
    )
    config = cargar_configuracion(ruta)
    valores = dict(ENV_COMPLETO)
    del valores["TELEGRAM_BOT_TOKEN"]
    secretos = cargar_secretos(config, escribir_env(tmp_path, **valores))
    assert secretos.telegram_bot_token == "999:token-de-hermes"


def test_env_del_proyecto_tiene_prioridad(tmp_path, config, monkeypatch):
    # En el PC el shell exporta la DEEPSEEK_API_KEY de Hermes: no debe pisar la del .env
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-de-otro-programa")
    secretos = cargar_secretos(config, escribir_env(tmp_path, **ENV_COMPLETO))
    assert secretos.deepseek_api_key == ENV_COMPLETO["DEEPSEEK_API_KEY"]


def test_variable_de_entorno_si_el_env_no_la_trae(tmp_path, config, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100999")
    valores = dict(ENV_COMPLETO)
    del valores["TELEGRAM_CHAT_ID"]
    secretos = cargar_secretos(config, escribir_env(tmp_path, **valores))
    assert secretos.telegram_chat_id == "-100999"


def test_resumen_no_exige_healthcheck(tmp_path, config):
    valores = dict(ENV_COMPLETO)
    del valores["HEALTHCHECK_URL"]
    ruta = escribir_env(tmp_path, **valores)
    with pytest.raises(ErrorConfiguracion, match="HEALTHCHECK_URL"):
        cargar_secretos(config, ruta)
    assert cargar_secretos(config, ruta, exigir_salud=False).healthcheck_url is None


# --- Asistente de postulación ---


def test_asistente_por_defecto_desactivado(config):
    asistente = config.asistente
    assert asistente is not None
    assert asistente.activo is False
    assert asistente.enlace_canal is False
    assert set(asistente.plataformas) == {"computrabajo", "magneto"}
    assert set(asistente.gemini.tareas) == {
        "leer_cv",
        "requisitos",
        "adaptar_cv",
        "carta",
        "responder",
        "clasificar_pregunta",
    }


def test_asistente_tope_negativo(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["asistente"]["topes"].update(usuario_dia=-1))
    with pytest.raises(ErrorConfiguracion, match="asistente.topes.usuario_dia"):
        cargar_configuracion(ruta)


def test_asistente_tarea_gemini_sin_modelo(tmp_path):
    ruta = escribir_config(
        tmp_path, lambda d: d["asistente"]["gemini"]["tareas"]["carta"].pop("modelo")
    )
    with pytest.raises(ErrorConfiguracion, match="asistente.gemini.tareas.carta.modelo"):
        cargar_configuracion(ruta)


def test_asistente_tarea_gemini_faltante(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["asistente"]["gemini"]["tareas"].pop("leer_cv"))
    with pytest.raises(ErrorConfiguracion, match="leer_cv"):
        cargar_configuracion(ruta)


def test_asistente_enlace_sin_activo(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["asistente"].update(enlace_canal=True))
    with pytest.raises(ErrorConfiguracion, match="enlace_canal requiere activo"):
        cargar_configuracion(ruta)


def test_asistente_activo_exige_bot_y_dueno(tmp_path):
    ruta = escribir_config(tmp_path, lambda d: d["asistente"].update(activo=True))
    with pytest.raises(ErrorConfiguracion, match="bot_usuario"):
        cargar_configuracion(ruta)


def test_asistente_pausa_invertida(tmp_path):
    ruta = escribir_config(
        tmp_path,
        lambda d: d["asistente"]["ejecucion"].update(pausa_s={"min": 100, "max": 10}),
    )
    with pytest.raises(ErrorConfiguracion, match="asistente.ejecucion.pausa_s"):
        cargar_configuracion(ruta)


def test_secretos_del_asistente(tmp_path, config):
    env = escribir_env(tmp_path, ASISTENTE_BOT_TOKEN="123:abc", ASISTENTE_CLAVE_CIFRADO="k" * 44)
    secretos = cargar_secretos(config, env, exigir_envio=False)
    assert secretos.asistente_bot_token == "123:abc"
    assert "123:abc" in secretos.valores()
