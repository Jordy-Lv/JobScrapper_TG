import asyncio

import pytest

pytest.importorskip("pypdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente.pantalla import (  # noqa: E402
    AccionPagina,
    Boton,
    Consulta,
    DecisionPagina,
    ElementoResumen,
    Peticion,
    Reparacion,
    Resumen,
    acciones_validas,
    decidir,
    texto_consulta,
)
from buscador_vacantes.asistente.recetas import BotonReceta  # noqa: E402
from buscador_vacantes.asistente.respuestas import Pregunta  # noqa: E402

BOTONES = [Boton(indice=0, texto="Compartir"), Boton(indice=1, texto="Quick apply", clase="enviar")]
RESUMEN = Resumen(
    elementos=[
        ElementoResumen(indice=0, rol="button", texto="Quick apply"),
        ElementoResumen(indice=1, rol="combobox", texto="País"),
        ElementoResumen(indice=2, rol="button", texto="Cerrar"),
    ],
    encabezados=["Backend Engineer"],
    avisos=["Faltan campos obligatorios"],
)


def decision(acciones, **extra):
    return DecisionPagina.model_validate({"clase": "intermedia", "acciones": acciones, **extra})


def test_decision_valida_conserva_sus_acciones():
    d = decision([
        {"accion": "avanzar", "indice": 1},
        {"accion": "esperar"},
        {"accion": "elegir", "indice": 1, "opcion": "Colombia"},
    ], motivo="Detalle")  # fmt: skip
    assert [(a.accion, a.indice, a.opcion) for a in d.acciones] == [
        ("avanzar", 1, None), ("esperar", None, None), ("elegir", 1, "Colombia"),
    ]  # fmt: skip
    assert d.motivo == "Detalle"


def test_accion_fuera_de_la_lista_se_descarta_sin_tumbar_la_decision():
    d = decision([
        {"accion": "borrar_cuenta", "indice": 0},
        {"accion": "cerrar_modal", "indice": 2},  # solo vale en la reparación
        {"accion": "avanzar", "indice": 1},
        "avanzar",
        {"indice": 1},
    ])  # fmt: skip
    assert [a.accion for a in d.acciones] == ["avanzar"]


def test_indice_mal_formado_se_descarta():
    d = decision([
        {"accion": "avanzar", "indice": -1},
        {"accion": "avanzar", "indice": "1"},
        {"accion": "avanzar", "indice": True},
        {"accion": "elegir", "indice": 1, "opcion": 7},
        {"accion": "avanzar", "indice": 0},
    ])  # fmt: skip
    assert [(a.accion, a.indice) for a in d.acciones] == [("avanzar", 0)]


def test_decision_recorta_lo_que_se_pasa_de_largo():
    d = decision([{"accion": "esperar"}] * 9 + [{"accion": "avanzar", "indice": 0}],
                 motivo="x " * 400)  # fmt: skip
    assert len(d.acciones) == 5 and len(d.motivo) <= 300
    largo = decision([{"accion": "elegir", "indice": 1, "opcion": "o" * 500}])
    assert len(largo.acciones[0].opcion) == 100


def test_clase_fuera_de_la_lista_si_es_un_error():
    with pytest.raises(ValueError):
        DecisionPagina.model_validate({"clase": "pagar", "acciones": []})


def test_acciones_que_no_son_lista_quedan_vacias():
    assert decision("avanzar").acciones == []
    assert decision(None).acciones == []


def test_reparacion_acepta_cerrar_modal_y_trae_diagnostico():
    r = Reparacion.model_validate({
        "clase": "formulario",
        "acciones": [{"accion": "cerrar_modal", "indice": 2}, {"accion": "inventada", "indice": 0}],
        "motivo": "Un modal tapa el botón",
        "diagnostico": "El botón cambió de texto  a «Postular ahora»",
    })  # fmt: skip
    assert [a.accion for a in r.acciones] == ["cerrar_modal"]
    assert r.diagnostico == "El botón cambió de texto a «Postular ahora»"
    assert Reparacion.model_validate({"clase": "desconocida"}).diagnostico == ""


def test_indices_se_validan_contra_la_pantalla_enviada():
    acciones = [
        AccionPagina(accion="avanzar", indice=1),  # botón que existe
        AccionPagina(accion="enviar", indice=9),  # botón inexistente
        AccionPagina(accion="elegir", indice=1, opcion="Colombia"),  # elemento del resumen
        AccionPagina(accion="elegir", indice=8, opcion="Colombia"),  # elemento inexistente
        AccionPagina(accion="elegir", indice=1),  # sin opción no hay qué elegir
        AccionPagina(accion="avanzar", indice=2),  # el índice 2 es del resumen, no un botón
        AccionPagina(accion="esperar"),
    ]
    validas = acciones_validas(acciones, BOTONES, RESUMEN)
    assert [(a.accion, a.indice) for a in validas] == [
        ("avanzar", 1), ("elegir", 1), ("esperar", None),
    ]  # fmt: skip


def test_cerrar_modal_solo_sobre_un_elemento_del_resumen():
    r = Reparacion.model_validate({"clase": "formulario", "acciones": [
        {"accion": "cerrar_modal", "indice": 2}, {"accion": "cerrar_modal", "indice": 5},
        {"accion": "cerrar_modal"},
    ]})  # fmt: skip
    assert [a.indice for a in acciones_validas(r.acciones, BOTONES, RESUMEN)] == [2]


def test_accion_pagina_directa_exige_indice_no_negativo():
    with pytest.raises(ValueError):
        AccionPagina(accion="avanzar", indice=-1)


def test_texto_de_la_consulta_trae_la_pagina_y_nunca_la_consulta_de_la_url():
    peticion = Peticion(
        "desconocida", "sin_botones", "en", "https://empresa.co/jobs/1?token=SECRETO#paso",
        [Pregunta("City", "texto", obligatoria=False)], BOTONES + [
            Boton(indice=2, texto="Apply with LinkedIn", clase="nunca", oauth=True)
        ], None, RESUMEN, None, False,
    )  # fmt: skip
    texto = texto_consulta(Consulta(peticion))
    assert "https://empresa.co/jobs/1" in texto and "SECRETO" not in texto
    assert "encabezados: Backend Engineer" in texto
    assert "avisos: Faltan campos obligatorios" in texto
    assert "- City (texto, opcional)" in texto
    assert "1. Quick apply [button clase=enviar]" in texto
    assert "2. Apply with LinkedIn [button clase=nunca oauth]" in texto
    assert "1. combobox: País" in texto


def test_acciones_ya_construidas_se_conservan():
    d = DecisionPagina(clase="intermedia", acciones=[AccionPagina(accion="avanzar", indice=1)])
    assert [(a.accion, a.indice) for a in d.acciones] == [("avanzar", 1)]


# --- el botón de la receta cuando las reglas dudan ---------------------------------------------


def peticion_con_receta(botones, receta_boton):
    return Peticion(
        "formulario", None, "en", "https://empresa.co/apply", [], botones, None, RESUMEN, None,
        False, receta_boton,
    )  # fmt: skip


def decidir_sin_ia(peticion):
    async def resolver(preguntas):
        raise AssertionError("no hay campos que resolver")

    async def arbitrar(consulta):
        raise AssertionError("la receta decide: no se consulta al árbitro")

    return asyncio.run(decidir(peticion, resolver, arbitrar))


def test_la_receta_elige_el_boton_cuando_las_reglas_no_sugieren_ninguno():
    botones = [Boton(indice=0, texto="Back", clase="avanzar"),
               Boton(indice=1, texto="Submit application", clase="enviar")]  # fmt: skip
    d = decidir_sin_ia(peticion_con_receta(botones, BotonReceta(texto="submit  Application")))
    assert d.accion == {"tipo": "enviar", "indice": 1}


def test_la_receta_no_pulsa_un_boton_sin_clase_ni_uno_prohibido():
    sin_clase = [Boton(indice=0, texto="Submit application")]
    prohibido = [Boton(indice=0, texto="Submit application", clase="nunca")]
    otro_texto = [Boton(indice=0, texto="Enviar solicitud", clase="enviar")]
    for botones in (sin_clase, prohibido, otro_texto):
        peticion = peticion_con_receta(botones, BotonReceta(texto="Submit application"))
        with pytest.raises(AssertionError, match="árbitro"):  # sigue el camino de siempre
            decidir_sin_ia(peticion)
