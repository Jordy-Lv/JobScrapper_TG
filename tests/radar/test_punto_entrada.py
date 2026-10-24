import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
import yaml

from buscador_vacantes.comun.config import RAIZ
from buscador_vacantes.comun.estado import Estado, a_texto, vacante_a_json
from buscador_vacantes.comun.modelo import Vacante
from buscador_vacantes.radar.corrida import main


def test_punto_entrada_de_la_raiz_muestra_la_ayuda():
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "buscador.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "usage: buscador.py" in resultado.stdout
    assert "--dry-run" in resultado.stdout


def test_raiz_es_la_del_repositorio():
    assert (RAIZ / "config.yaml").is_file()
    assert (RAIZ / "buscador.py").is_file()


# --- buscador.py diagnosticar ---------------------------------------------------------------

AHORA_DIAG = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)
URL_CT = "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-aprendiz-sena-AB12"


def _vacante(titulo, id_fuente, url=URL_CT, fuente="computrabajo", keyword="aprendiz sena"):
    return Vacante(
        fuente=fuente, id_fuente=id_fuente, titulo=titulo, empresa="Acme S.A.S.", url=url,
        keyword=keyword, ubicacion="Cartagena", modalidad="Presencial",
    )  # fmt: skip


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base de estado en disco y el config.yaml que apunta a ella."""
    ruta_base = tmp_path / "vacantes.db"
    datos = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))
    datos["rutas"]["base_datos"] = str(ruta_base)
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(datos), encoding="utf-8")
    monkeypatch.setenv("BUSCADOR_SIN_CONFIG_LOCAL", "1")
    estado = Estado.abrir(ruta_base)
    yield estado, config
    estado.cerrar()


def _diagnosticar(config, consulta, capsys):
    codigo = main(["--config", str(config), "diagnosticar", consulta])
    return codigo, capsys.readouterr().out


def test_diagnosticar_vacante_publicada(base, capsys):
    estado, config = base
    v = _vacante("Aprendiz SENA Sistemas", "AB12")
    estado.registrar_vista(v, "h1", momento=AHORA_DIAG, enviada=True)
    codigo, salida = _diagnosticar(config, URL_CT + "?utm=correo", capsys)
    assert codigo == 0
    assert "[vistas]" in salida
    assert "publicada en el canal el 2026-10-24 10:00" in salida


def test_diagnosticar_vacante_descartada_por_reglas(base, capsys):
    estado, config = base
    v = _vacante("Aprendiz SENA Contable", "AB12")
    estado.registrar_descarte(v, "h1", "reglas", "no_ti", "práctica sin TI", AHORA_DIAG)
    estado.registrar_descarte(v, "h1", "reglas", "no_ti", "práctica sin TI", AHORA_DIAG)
    codigo, salida = _diagnosticar(config, URL_CT, capsys)
    assert codigo == 0
    assert "rechazada por las reglas (etapa «reglas»)" in salida
    assert "Motivo: no_ti — práctica sin TI" in salida
    assert "Palabra clave que la trajo: aprendiz sena" in salida
    assert "Vista 2 veces" in salida


def test_diagnosticar_vacante_pendiente_de_ia_por_titulo(base, capsys):
    estado, config = base
    v = _vacante("Aprendiz de Soporte", "ZZ9", url="https://co.computrabajo.com/otra")
    with estado.transaccion() as cx:
        cx.execute(
            "INSERT INTO pendientes(huella, vacante_json, desde) VALUES (?, ?, ?)",
            ("h2", vacante_a_json(v), a_texto(AHORA_DIAG)),
        )
    codigo, salida = _diagnosticar(config, "aprendiz de SOPORTE", capsys)
    assert codigo == 0
    assert "[pendientes]" in salida
    assert "dudosa, esperando la respuesta de la IA desde el 2026-10-24 10:00" in salida


def test_diagnosticar_vacante_nunca_vista_resume_los_intentos(base, capsys):
    estado, config = base
    ahora = datetime.now(UTC)
    with estado.transaccion() as cx:
        cx.executemany(
            "INSERT INTO intentos(ts, fuente, keyword, status, items) VALUES (?, ?, ?, 200, ?)",
            [
                (a_texto(ahora), "computrabajo", "aprendiz sena", 25),
                (a_texto(ahora), "computrabajo", "aprendiz sena", 10),
                (a_texto(ahora - timedelta(days=10)), "computrabajo", "pasante", 40),
                (a_texto(ahora), "linkedin", "practicante", 5),
            ],
        )
    codigo, salida = _diagnosticar(config, URL_CT, capsys)
    assert codigo == 0
    assert "nunca recibió esta vacante" in salida
    assert "aprendiz sena: 2 peticiones, 35 resultados" in salida
    assert "pasante" not in salida  # fuera de los últimos 3 días
    assert "practicante" not in salida  # otra fuente


def test_diagnosticar_no_escribe_en_la_base(base, capsys):
    estado, config = base
    antes = estado.cx.execute("PRAGMA data_version").fetchone()[0]
    _diagnosticar(config, URL_CT, capsys)
    assert estado.cx.execute("PRAGMA data_version").fetchone()[0] == antes


# --- buscador.py diagnosticar --evaluar ---------------------------------------------------------


def test_evaluar_aprendiz_sena_se_acepta_como_practica(base, capsys):
    _, config = base
    codigo = main(
        ["--config", str(config), "diagnosticar", "--evaluar",
         "--titulo", "Aprendiz SENA Tecnólogo ADSO", "--empresa", "Acme",
         "--ubicacion", "Cartagena", "--modalidad", "Presencial"]
    )  # fmt: skip
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "Veredicto de las reglas: aceptar" in salida
    assert "Categoría: practicas" in salida
    assert "Guardarraíl de prácticas: no la cambia" in salida


def test_evaluar_exige_titulo(base, capsys):
    _, config = base
    assert main(["--config", str(config), "diagnosticar", "--evaluar"]) == 2
    assert "Uso:" in capsys.readouterr().err


@respx.mock
def test_evaluar_con_ia_no_toca_la_cache_real(base, capsys, tmp_path):
    estado, config = base
    env = tmp_path / ".env"
    env.write_text("DEEPSEEK_API_KEY=sk-clave-de-prueba-123456\n", encoding="utf-8")
    respuesta = {"vacantes": [{"id": 0, "aceptar": True, "categoria": "soporte", "motivo": "TI"}]}
    respx.get("https://api.deepseek.com/user/balance").mock(
        return_value=httpx.Response(
            200, json={"balance_infos": [{"currency": "USD", "total_balance": "10.00"}]}
        )
    )
    ruta = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(respuesta)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
    )
    codigo = main(
        ["--config", str(config), "--env", str(env), "diagnosticar", "--evaluar", "--con-ia",
         "--titulo", "Auxiliar logístico", "--empresa", "Acme", "--ubicacion", "Cartagena",
         "--modalidad", "Presencial", "--descripcion", "Manejo de sistemas de inventario"]
    )  # fmt: skip
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "Veredicto de las reglas: dudosa" in salida
    assert "IA: aceptar" in salida
    assert "no se guardó en la caché" in salida
    assert ruta.called
    for tabla in ("clasificaciones", "pendientes", "ia_uso"):
        assert estado.cx.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0
