import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

pytest.importorskip("pypdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente.afinidad import (  # noqa: E402
    Requisitos,
    calcular_afinidad,
    obtener_requisitos,
    requisitos_por_diccionario,
)
from buscador_vacantes.asistente.cv_lectura import PerfilExtraido, Proyecto  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.asistente.ia import ClienteIA  # noqa: E402
from buscador_vacantes.asistente.tecnologias import diccionario  # noqa: E402
from buscador_vacantes.config import cargar_configuracion  # noqa: E402

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"

PERFIL = PerfilExtraido(
    es_cv=True,
    habilidades_tecnicas=["JS", "Python 3", "Excel avanzado", "Trabajo en equipo"],
    proyectos=[Proyecto(nombre="API", tecnologias=["Django", "PostgreSQL"])],
)


def test_diccionario_canonicas_y_sinonimos():
    d = diccionario()
    assert d.canonica("js") == "JavaScript"
    assert d.canonica("Postgres") == "PostgreSQL"
    assert d.son_sinonimos("JS", "JavaScript")
    assert not d.son_sinonimos("Java", "JavaScript")
    assert len(d.categorias) >= 200


def test_buscar_en_texto_sin_falsos_positivos():
    texto = (
        "Empresa XYZ S.A.S. busca practicante con conocimientos en Python, SQL Server y "
        "Power BI. Deseable C# y .NET. Ir al trabajo en Go-Kart no aplica."
    )
    encontradas = diccionario().buscar(texto)
    assert encontradas[:3] == ["Python", "SQL Server", "Power BI"]
    assert "C#" in encontradas and ".NET" in encontradas
    assert "SAS" not in encontradas and "Go" not in encontradas


def test_afinidad_porcentaje_esperado():
    requisitos = Requisitos(obligatorios=["Python", "SQL", "Git"], deseables=["Django", "AWS"])
    # Python ✓ (2), SQL ✗, Git ✗, Django ✓ (1), AWS ✗  →  3 / 8
    afinidad = calcular_afinidad(requisitos, PERFIL)
    assert afinidad.porcentaje == 38
    assert afinidad.cumple == ["Python", "Django"]
    assert afinidad.faltan == ["SQL", "Git", "AWS"]


def test_sinonimos_cumplen():
    requisitos = Requisitos(obligatorios=["JavaScript", "Postgres", "Excel"])
    assert calcular_afinidad(requisitos, PERFIL).porcentaje == 100


def test_requisito_fuera_del_diccionario_por_texto():
    requisitos = Requisitos(obligatorios=["Trabajo en equipo", "Contabilidad"])
    afinidad = calcular_afinidad(requisitos, PERFIL)
    assert afinidad.cumple == ["Trabajo en equipo"] and afinidad.faltan == ["Contabilidad"]


def test_sin_requisitos_no_hay_afinidad():
    assert calcular_afinidad(Requisitos(), PERFIL) is None


def test_respaldo_por_diccionario():
    requisitos = requisitos_por_diccionario("Se requiere manejo de Excel, SQL y Python.")
    assert requisitos.obligatorios == ["Excel", "SQL", "Python"]


@pytest.fixture
def base(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "a.db")
    with base.transaccion() as cx:
        cx.execute("INSERT INTO usuarios(id, telegram_id, directorio, creado) VALUES (1,1,'u','x')")
        cx.execute(
            "INSERT INTO vacantes(id_corto, clave, fuente, url, indexada_en) "
            "VALUES ('abc', 'computrabajo:1', 'computrabajo', 'https://x', 'x')"
        )
    yield base
    base.cerrar()


@respx.mock
def test_requisitos_con_ia_se_comparten_en_cache(base):
    config = cargar_configuracion().asistente
    cliente = ClienteIA(
        config.ia.proveedores["gemini"], base, 60, reloj=lambda: datetime(2026, 10, 4, tzinfo=UTC)
    )
    ruta = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps({"obligatorios": ["Python"]})}]}}
                ]
            },
        )
    )
    texto = "Practicante con Python"
    primero = asyncio.run(
        obtener_requisitos(base, "abc", texto, cliente=cliente, clave="k1", usuario_id=1)
    )
    segundo = asyncio.run(
        obtener_requisitos(base, "abc", texto, cliente=cliente, clave="k2", usuario_id=1)
    )
    assert primero.obligatorios == segundo.obligatorios == ["Python"]
    assert ruta.call_count == 1
    asyncio.run(cliente.cerrar())


def test_requisitos_sin_ia_usan_diccionario(base):
    requisitos = asyncio.run(obtener_requisitos(base, "abc", "Manejo de SQL y Git"))
    assert requisitos.obligatorios == ["SQL", "Git"]
