import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

pytest.importorskip("pypdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import campos  # noqa: E402
from buscador_vacantes.asistente.campos import DatosUsuario  # noqa: E402
from buscador_vacantes.asistente.cv_lectura import (  # noqa: E402
    Formacion,
    Idioma,
    PerfilExtraido,
)
from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.asistente.ia import ClienteIA  # noqa: E402
from buscador_vacantes.asistente.respuestas import (  # noqa: E402
    Contexto,
    ErrorPegado,
    Origen,
    Pregunta,
    elegir_opcion,
    normalizar_pregunta,
    recordar,
    resolver,
    sembrar_banco,
    semilla,
    separar_preguntas,
)
from buscador_vacantes.config import cargar_configuracion  # noqa: E402

AHORA = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
URL_LITE = BASE_URL + "gemini-flash-lite-latest:generateContent"

PERFIL = PerfilExtraido(
    es_cv=True,
    nombre="Ana Pérez",
    ciudad="Bogotá",
    formacion=[
        Formacion(
            institucion="Universidad Nacional", programa="Ingeniería de Sistemas",
            semestre="6", estado="En curso",
        )
    ],
    habilidades_tecnicas=["Python", "SQL", "Excel avanzado"],
    idiomas=[Idioma(idioma="Inglés", nivel="B1")],
)  # fmt: skip
DATOS = DatosUsuario(
    PERFIL,
    {"salario": "1300000", "correo": "ana@gmail.com", "telefono": "3105551234",
     "documento": "1020345678"},
)  # fmt: skip


def gemini(contenido):
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(contenido)}]}}]}
    )


@pytest.fixture
def base(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "a.db")
    with base.transaccion() as cx:
        for i in (1, 2):
            cx.execute(
                "INSERT INTO usuarios(id, telegram_id, directorio, creado) VALUES (?, ?, ?, 'x')",
                (i, i, f"u{i}"),
            )
    sembrar_banco(base, AHORA)
    yield base
    base.cerrar()


def contexto(base, usuario_id=1, con_ia=True, datos=DATOS):
    cliente = None
    if con_ia:
        config = cargar_configuracion().asistente
        cliente = ClienteIA(config.ia.proveedores["gemini"], base, 60, reloj=lambda: AHORA)
    return Contexto(base, usuario_id, datos, AHORA, cliente, "clave" if con_ia else None,
                    vacante="Practicante de desarrollo Python")  # fmt: skip


def test_semilla_apunta_a_campos_del_catalogo():
    assert len(semilla()) >= 60
    for item in semilla():
        assert campos.es_campo_valido(item["campo"], item.get("parametro")), item


def test_conoce_segun_perfil_y_sinonimos():
    assert DATOS.valor("conoce", "python") == "Sí"
    assert DATOS.valor("conoce", "Excel") == "Sí"  # "Excel avanzado"
    assert DATOS.valor("conoce", "Docker") == "No"


def test_para_ia_sin_contacto():
    texto = json.dumps(DATOS.para_ia(), ensure_ascii=False)
    for dato in ("ana@gmail.com", "3105551234", "1020345678", "Ana Pérez"):
        assert dato not in texto


@respx.mock
def test_pregunta_conocida_sin_ia(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    r = asyncio.run(resolver(Pregunta("¿Cuál es tu aspiración salarial?"), contexto(base)))
    assert (r.valor, r.origen, r.campo) == ("1300000", Origen.PERFIL, "salario")
    assert ruta.call_count == 0


@respx.mock
def test_pregunta_nueva_se_clasifica_una_vez_para_todos(base):
    ruta = respx.post(URL_LITE).mock(return_value=gemini({"campo": "salario", "abierta": False}))
    pregunta = Pregunta("¿Cuál es tu pretensión económica mensual?")
    r1 = asyncio.run(resolver(pregunta, contexto(base, 1)))
    otro = DatosUsuario(PERFIL, {"salario": "1500000"})
    r2 = asyncio.run(resolver(pregunta, contexto(base, 2, datos=otro)))
    assert (r1.valor, r1.origen) == ("1300000", Origen.BANCO)
    assert (r2.valor, r2.origen) == ("1500000", Origen.PERFIL)
    assert ruta.call_count == 1
    fila = base.cx.execute(
        "SELECT campo, origen FROM banco_preguntas WHERE pregunta_norm = ?",
        (normalizar_pregunta(pregunta.texto),),
    ).fetchone()
    assert tuple(fila) == ("salario", "ia")


@respx.mock
def test_clasificacion_fuera_del_catalogo_se_redacta(base):
    respx.post(URL_LITE).mock(
        side_effect=[
            gemini({"campo": "color_favorito", "abierta": False}),
            gemini({"respuesta": "Me interesa aplicar Python en proyectos reales.",
                    "suficiente": True}),
        ]
    )  # fmt: skip
    r = asyncio.run(resolver(Pregunta("¿Qué te motiva de este reto?"), contexto(base)))
    assert r.origen == Origen.IA and "Python" in r.valor
    assert (
        base.cx.execute(
            "SELECT COUNT(*) FROM banco_preguntas WHERE campo = 'color_favorito'"
        ).fetchone()[0]
        == 0
    )


@respx.mock
def test_opcion_exacta(base):
    pregunta = Pregunta(
        "Nivel de inglés", "opciones", ["Básico (A1-A2)", "Intermedio (B1)", "Avanzado (C1)"]
    )
    r = asyncio.run(resolver(pregunta, contexto(base)))
    assert r.opcion == 1 and r.texto == "Intermedio (B1)"


@respx.mock
def test_ia_solo_elige_indices_validos(base):
    respx.post(URL_LITE).mock(
        side_effect=[
            gemini({"campo": None, "abierta": True}),
            gemini({"opcion": 7, "suficiente": True}),
        ]
    )
    pregunta = Pregunta("¿Qué área prefieres?", "opciones", ["Backend", "Frontend"])
    r = asyncio.run(resolver(pregunta, contexto(base)))
    assert r.falta and r.opcion is None


@respx.mock
def test_dato_inexistente_no_se_inventa(base):
    respx.post(URL_LITE).mock(
        side_effect=[
            gemini({"campo": None, "abierta": False}),
            gemini({"respuesta": None, "suficiente": False}),
        ]
    )
    r = asyncio.run(resolver(Pregunta("¿Tienes licencia de conducción B1?"), contexto(base)))
    assert r.falta and r.valor is None


def test_sin_ia_lo_desconocido_queda_falta(base):
    r = asyncio.run(resolver(Pregunta("¿Tienes moto?"), contexto(base, con_ia=False)))
    assert r.falta


def test_aprendida_se_reutiliza(base):
    recordar(base, 1, "¿Tienes licencia de conducción B1?", "No", AHORA)
    r = asyncio.run(
        resolver(Pregunta("Tienes licencia de conducción B1"), contexto(base, con_ia=False))
    )
    assert (r.valor, r.origen) == ("No", Origen.APRENDIDA)
    r2 = asyncio.run(
        resolver(
            Pregunta("¿Tienes licencia de conducción B1?", "opciones", ["Sí", "No"]),
            contexto(base, con_ia=False),
        )
    )
    assert r2.opcion == 1


def test_campos_estandar_sin_ia(base):
    ctx = contexto(base, con_ia=False)
    correo = asyncio.run(resolver(Pregunta("Escribe aquí", "correo"), ctx))
    telefono = asyncio.run(resolver(Pregunta("Dato", nombre="phone_number"), ctx))
    nombre = asyncio.run(resolver(Pregunta("Nombre completo"), ctx))
    assert correo.valor == "ana@gmail.com"
    assert telefono.valor == "3105551234"
    assert nombre.valor == "Ana Pérez"


@pytest.mark.parametrize(
    ("valor", "opciones", "esperado"),
    [
        ("Sí", ["No", "Si"], 1),
        ("No", ["Sí, tengo", "No tengo"], 1),
        ("1300000", ["Menos de $1.000.000", "$1.000.000 - $1.500.000", "Más de $1.500.000"], 1),
        ("2000000", ["Menos de $1.000.000", "$1.000.000 - $1.500.000", "Más de $1.500.000"], 2),
        ("6", ["1 a 4", "5 a 8", "9 o más"], 1),
        ("B1", ["A2", "B1 - Intermedio", "C1"], 1),
        ("Marte", ["Bogotá", "Medellín"], None),
    ],
)
def test_elegir_opcion(valor, opciones, esperado):
    assert elegir_opcion(valor, opciones) == esperado


def test_separar_preguntas_pegadas():
    texto = (
        "1. ¿Cuál es tu aspiración salarial?\n"
        "¿Tienes computador propio?\n"
        "- Sí\n"
        "- No\n"
        "Nivel de inglés: Básico / Intermedio / Avanzado\n"
    )
    preguntas = separar_preguntas(texto)
    assert [p.texto for p in preguntas] == [
        "1. ¿Cuál es tu aspiración salarial?",
        "¿Tienes computador propio?",
        "Nivel de inglés",
    ]
    assert preguntas[1].opciones == ["Sí", "No"]
    assert preguntas[2].opciones == ["Básico", "Intermedio", "Avanzado"]


def test_limites_de_preguntas_pegadas():
    with pytest.raises(ErrorPegado, match="máximo 15"):
        separar_preguntas("\n".join(f"¿Pregunta {i}?" for i in range(16)))
    with pytest.raises(ErrorPegado, match="4000"):
        separar_preguntas("x" * 4001)
