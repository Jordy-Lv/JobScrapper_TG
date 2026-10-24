import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

pytest.importorskip("pypdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import campos  # noqa: E402
from buscador_vacantes.asistente.campos import (
    RESERVADO,  # noqa: E402
    DatosUsuario,  # noqa: E402
)
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
    autorizacion_trabajo,
    datos_aprendidos,
    detectar_idioma,
    elegir_opcion,
    es_consentimiento,
    guardar_en_banco,
    normalizar_pregunta,
    recordar,
    recortar_a_limite,
    redactar_formulario,
    resolver,
    sembrar_banco,
    semilla,
    separar_preguntas,
)
from buscador_vacantes.comun.config import cargar_configuracion  # noqa: E402

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


def contexto(base, usuario_id=1, con_ia=True, datos=DATOS, plataforma=None, idioma=None,
             nivel="normal"):
    cliente = None
    config = cargar_configuracion().asistente
    config_niveles = config.niveles_ia
    if con_ia:
        cliente = ClienteIA(config.ia.proveedores["gemini"], base, 60, reloj=lambda: AHORA)
    return Contexto(base, usuario_id, datos, AHORA, cliente, "clave" if con_ia else None,
                    vacante="Practicante de desarrollo Python", plataforma=plataforma,
                    idioma=idioma, nivel=nivel,
                    clasificar_preguntas=getattr(config_niveles, nivel).clasificar_preguntas
                    )  # fmt: skip


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
    ruta = respx.post(URL_LITE).mock(return_value=gemini({"campo": "salario", "formato": "dato"}))
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


def campo_en_banco(base, texto):
    fila = base.cx.execute(
        "SELECT campo, parametro FROM banco_preguntas WHERE pregunta_norm = ?",
        (normalizar_pregunta(texto),),
    ).fetchone()
    return tuple(fila) if fila else None


@respx.mock
def test_clasificacion_fuera_del_catalogo_queda_para_el_redactor(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(
        return_value=gemini({"campo": "color_favorito", "formato": "dato"})
    )
    texto = "¿Qué te motiva de este reto?"
    r = asyncio.run(resolver(Pregunta(texto), contexto(base)))
    assert r.redactar and not r.falta and r.valor is None
    assert ruta.call_count == 1  # solo clasificar: la redacción es por formulario
    assert campo_en_banco(base, texto) == ("redactar", None)


@respx.mock
def test_pregunta_compuesta_se_guarda_como_redactar(base):
    texto = (
        "¿Qué programa técnico o tecnológico estás estudiando relacionado con Sistemas o "
        "Informática y en qué institución?"
    )
    ruta = respx.post(URL_LITE).mock(
        return_value=gemini({"campo": "programa", "formato": "redactar"})
    )
    r = asyncio.run(resolver(Pregunta(texto), contexto(base, 1)))
    assert r.redactar and r.valor is None  # no se envía el programa pelado
    assert campo_en_banco(base, texto) == ("redactar", None)
    otro = asyncio.run(resolver(Pregunta(texto), contexto(base, 2)))
    assert otro.redactar and ruta.call_count == 1  # el banco evita volver a clasificar


@respx.mock
def test_dato_simple_se_guarda_con_su_campo(base):
    respx.post(URL_LITE).mock(return_value=gemini({"campo": "ciudad", "formato": "dato"}))
    texto = "Ciudad donde resides actualmente"
    r = asyncio.run(resolver(Pregunta(texto), contexto(base)))
    assert (r.valor, r.origen, r.redactar) == ("Bogotá", Origen.BANCO, False)
    assert campo_en_banco(base, texto) == ("ciudad", None)


@respx.mock
def test_opcion_exacta(base):
    pregunta = Pregunta(
        "Nivel de inglés", "opciones", ["Básico (A1-A2)", "Intermedio (B1)", "Avanzado (C1)"]
    )
    r = asyncio.run(resolver(pregunta, contexto(base)))
    assert r.opcion == 1 and r.texto == "Intermedio (B1)"


@respx.mock
@pytest.mark.parametrize("pregunta", [
    Pregunta("¿Cuántos proyectos personales tienes?", "numero"),
    Pregunta("¿Desde cuándo puedes empezar?", "fecha"),
])  # fmt: skip
def test_numero_y_fecha_sin_dato_nunca_van_al_redactor(base, pregunta):
    respx.post(URL_LITE).mock(return_value=gemini({"campo": None, "formato": "redactar"}))
    r = asyncio.run(resolver(pregunta, contexto(base)))
    assert r.falta and not r.redactar and r.opcion is None


@respx.mock
def test_opciones_sin_dato_conocido_van_al_redactor_para_elegir(base):
    respx.post(URL_LITE).mock(return_value=gemini({"campo": None, "formato": "redactar"}))
    pregunta = Pregunta("¿Confirmas tu participación en el proceso?", "opciones", ["Si", "No"])
    r = asyncio.run(resolver(pregunta, contexto(base)))
    assert r.redactar and not r.falta and r.opcion is None


@respx.mock
def test_dato_simple_conocido_no_llama_al_redactor(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    ctx = contexto(base)
    r = asyncio.run(resolver(Pregunta("Aspiración salarial", "numero"), ctx))
    ingles = Pregunta("¿Nivel de inglés?", "opciones", ["Básico", "Intermedio (B1)", "Avanzado"])
    r2 = asyncio.run(resolver(ingles, ctx))
    assert r.valor == "1300000" and r2.opcion == 1
    assert not r.redactar and not r2.redactar and ruta.call_count == 0


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


def test_aprendida_gana_a_una_pregunta_del_banco_sin_dato(base):
    pregunta = Pregunta(
        "¿Tienes experiencia en cuáles herramientas de RPA?",
        "opciones",
        ["UiPath", "Power Automate", "Tengo conocimiento en todas las anteriores"],
    )
    guardar_en_banco(base, normalizar_pregunta(pregunta.texto), "conoce", "UiPath", AHORA)
    antes = asyncio.run(resolver(pregunta, contexto(base, con_ia=False)))
    assert antes.redactar and antes.opcion is None  # el dato no calza: lo decidiría el redactor
    recordar(base, 1, pregunta.texto, "Tengo conocimiento en todas las anteriores", AHORA)
    r = asyncio.run(resolver(pregunta, contexto(base, con_ia=False)))
    assert not r.falta and (r.opcion, r.origen) == (2, Origen.APRENDIDA)


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


CONSENTIMIENTOS = [
    "¿Autorizas el tratamiento de tus datos personales?",
    "Acepto la política de tratamiento de datos de la empresa",
    "¿Aceptas los términos y condiciones?",
    "Autorizo el uso de mis datos (Habeas Data)",
]


@pytest.mark.parametrize("texto", CONSENTIMIENTOS)
def test_consentimiento_se_reconoce(texto):
    assert es_consentimiento(normalizar_pregunta(texto))


@pytest.mark.parametrize("texto", [
    "¿Tienes autorización para trabajar en Colombia?",
    "¿Tienes disponibilidad para trabajar de forma presencial?",
    "¿Cuál es tu aspiración salarial?",
])  # fmt: skip
def test_pregunta_normal_no_es_consentimiento(texto):
    assert not es_consentimiento(normalizar_pregunta(texto))


@respx.mock
@pytest.mark.parametrize("texto", CONSENTIMIENTOS)
def test_consentimiento_sin_respuesta_del_usuario_no_se_inventa(base, texto):
    ruta = respx.post(URL_LITE).mock(
        return_value=gemini({"respuesta": "Sí", "opcion": 0, "suficiente": True})
    )
    pregunta = Pregunta(texto, "opciones", ["Si", "No"])
    r = asyncio.run(resolver(pregunta, contexto(base)))
    assert r.falta and r.texto is None
    assert not ruta.called  # ni siquiera se le pregunta a la IA


@respx.mock
def test_consentimiento_aprendido_del_usuario_se_reutiliza(base):
    texto = "¿Autorizas el tratamiento de tus datos personales?"
    recordar(base, 1, texto, "No", AHORA)
    r = asyncio.run(resolver(Pregunta(texto, "opciones", ["Si", "No"]), contexto(base)))
    assert not r.falta and r.texto == "No" and r.origen == Origen.APRENDIDA


# --- redactor por formulario -------------------------------------------------------------

URL_REDACTAR = BASE_URL + "gemini-flash-latest:generateContent"
COMPUESTA = (
    "¿Qué programa técnico o tecnológico estás estudiando relacionado con Sistemas o "
    "Informática y en qué institución?"
)


def enviado(ruta, n=0):
    """Texto completo que se le mandó a la IA en la llamada n."""
    return ruta.calls[n].request.content.decode("utf-8")


@respx.mock
def test_redactor_responde_la_pregunta_compuesta_completa(base):
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [{
        "indice": 1,
        "respuesta": "Estudio Ingeniería de Sistemas en la Universidad Nacional, sexto semestre.",
    }]}))  # fmt: skip
    r = asyncio.run(redactar_formulario([Pregunta(COMPUESTA)], contexto(base)))
    assert r[0].valor.startswith("Estudio Ingeniería de Sistemas en la Universidad Nacional")
    assert r[0].faltan == []
    cuerpo = enviado(ruta)
    assert "Universidad Nacional" in cuerpo and "Practicante de desarrollo Python" in cuerpo
    assert "ana@gmail.com" not in cuerpo and "3105551234" not in cuerpo


@respx.mock
def test_varias_preguntas_en_una_sola_llamada(base):
    preguntas = [Pregunta(f"Pregunta abierta {n}") for n in range(1, 5)]
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [
        {"indice": n, "respuesta": f"Respuesta {n}."} for n in range(1, 5)
    ]}))  # fmt: skip
    r = asyncio.run(redactar_formulario(preguntas, contexto(base)))
    assert ruta.call_count == 1
    assert [r[i].valor for i in range(4)] == [f"Respuesta {n}." for n in range(1, 5)]
    assert all(f"{n}. Pregunta abierta {n}" in enviado(ruta) for n in range(1, 5))


@respx.mock
def test_dato_faltante_vuelve_con_sugerencias_limpias(base):
    respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [{
        "indice": 1, "respuesta": None,
        "faltan": [{"pregunta": "¿En qué institución estudias?",
                    "sugerencias": ["SENA", "sena", "Universidad Nacional", "x" * 60, "ITM",
                                    "Otra"]}],
    }]}))  # fmt: skip
    r = asyncio.run(redactar_formulario([Pregunta(COMPUESTA)], contexto(base)))
    assert r[0].valor is None
    [falta] = r[0].faltan
    assert falta.pregunta == "¿En qué institución estudias?"
    assert falta.sugerencias == ["SENA", "Universidad Nacional", "x" * 40, "ITM"]


@respx.mock
def test_datos_aprendidos_y_reservado_llegan_al_redactor(base):
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO pendientes_usuario(usuario_id, pregunta, pregunta_norm, tipo, creada) "
            "VALUES (1, '¿En qué institución estudias?', ?, 'dato', 'x'), "
            "(1, '¿Cuál es tu estrato?', ?, 'dato', 'x')",
            (normalizar_pregunta("¿En qué institución estudias?"),
             normalizar_pregunta("¿Cuál es tu estrato?")),
        )  # fmt: skip
    recordar(base, 1, "¿En qué institución estudias?", "SENA", AHORA)
    recordar(base, 1, "¿Cuál es tu estrato?", RESERVADO, AHORA)
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": []}))
    asyncio.run(redactar_formulario([Pregunta(COMPUESTA, maximo=150)], contexto(base)))
    cuerpo = enviado(ruta)
    assert "¿En qué institución estudias? → SENA" in cuerpo
    assert "¿Cuál es tu estrato? → (prefiere no decirlo)" in cuerpo
    assert RESERVADO not in cuerpo
    assert "(máximo 150 caracteres)" in cuerpo


def test_datos_aprendidos_sin_contacto_y_con_tope(base):
    recordar(base, 1, "¿Cuál es tu número de documento?", "1020345678", AHORA)
    guardar_en_banco(base, normalizar_pregunta("¿Cuál es tu número de documento?"),
                     "documento", None, AHORA)  # fmt: skip
    for n in range(45):
        recordar(base, 1, f"Pregunta de formulario {n}", f"respuesta {n}", AHORA)
    aprendidos = datos_aprendidos(base, 1)
    assert len(aprendidos) == 40
    assert all("1020345678" not in r for _, r in aprendidos)


@respx.mock
def test_respuesta_fuera_de_indice_se_ignora(base):
    respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [
        {"indice": 7, "respuesta": "No existe."},
        {"indice": 0, "respuesta": "Tampoco."},
        {"indice": 1, "respuesta": "Sí existe."},
    ]}))  # fmt: skip
    r = asyncio.run(redactar_formulario([Pregunta("¿Por qué te interesa?")], contexto(base)))
    assert list(r) == [0] and r[0].valor == "Sí existe."


@respx.mock
def test_falla_de_ia_devuelve_none(base):
    respx.post(url__startswith=BASE_URL).mock(return_value=httpx.Response(500))
    ctx = contexto(base)
    ctx.cliente.dormir = lambda _s: asyncio.sleep(0)
    assert asyncio.run(redactar_formulario([Pregunta("¿Por qué te interesa?")], ctx)) is None
    sin_ia = contexto(base, con_ia=False)
    assert asyncio.run(redactar_formulario([Pregunta("¿Por qué?")], sin_ia)) is None


@respx.mock
def test_redaccion_larga_se_recorta_al_maximo(base):
    largo = "Me interesa la vacante por el equipo. " * 10
    respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [
        {"indice": 1, "respuesta": largo},
    ]}))  # fmt: skip
    r = asyncio.run(redactar_formulario([Pregunta("¿Por qué?", maximo=150)], contexto(base)))
    assert len(r[0].valor) <= 150 and r[0].valor.endswith(".")


def test_recortar_a_limite():
    assert recortar_a_limite("Hola. Mundo grande", 10) == "Hola."
    assert recortar_a_limite("¿Sí? Claro que sí", 12) == "¿Sí?"
    assert recortar_a_limite("Estudio sistemas en el SENA", 16) == "Estudio sistemas"
    assert recortar_a_limite("Uno, dos tres", 5) == "Uno"
    assert recortar_a_limite("sinespacios", 4) == "sine"
    assert recortar_a_limite("Texto corto", None) == "Texto corto"
    assert recortar_a_limite("Texto corto", 100) == "Texto corto"


@respx.mock
def test_redactor_elige_opciones_en_la_misma_llamada(base):
    preguntas = [
        Pregunta("¿Confirmas tu participación en el proceso?", "opciones", ["Si", "No"]),
        Pregunta("¿Por qué te interesa?"),
        Pregunta("¿Prefieres trabajo en equipo?", "opciones", ["Si", "No"]),
    ]
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [
        {"indice": 1, "opcion": 0, "respuesta": "Sí, confirmo"},
        {"indice": 2, "respuesta": "Quiero crecer en desarrollo."},
        {"indice": 3, "opcion": 5},
    ]}))  # fmt: skip
    r = asyncio.run(redactar_formulario(preguntas, contexto(base)))
    assert ruta.call_count == 1
    assert (r[0].opcion, r[0].valor) == (0, None)  # en opciones nunca se envía texto
    assert r[1].valor == "Quiero crecer en desarrollo." and r[1].opcion is None
    assert r[2].opcion is None  # fuera de rango: se ignora
    assert "[opciones: 0) Si · 1) No]" in enviado(ruta)


def texto_enviado(ruta, n=0):
    """Los textos de la llamada n con sus saltos de línea reales (el cuerpo viaja como JSON)."""
    def textos(valor):
        if isinstance(valor, str):
            yield valor
        elif isinstance(valor, dict):
            for v in valor.values():
                yield from textos(v)
        elif isinstance(valor, list):
            for v in valor:
                yield from textos(v)

    return "\n".join(textos(json.loads(enviado(ruta, n))))


# --- campos por autocomplete y por name/id -----------------------------------------------------

DATOS_AMPLIADOS = DatosUsuario(
    PERFIL,
    {"salario": "2500000", "correo": "ana@gmail.com", "telefono": "3105551234",
     "nombre": "Ana María Pérez Gómez", "pais": "Colombia"},
)  # fmt: skip


@respx.mock
def test_first_name_con_given_name_se_llena_sin_ia(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    ctx = contexto(base, datos=DATOS_AMPLIADOS)
    r = asyncio.run(resolver(Pregunta("First Name", nombre="first_name",
                                      autocomplete="given-name"), ctx))  # fmt: skip
    assert (r.valor, r.origen, r.campo) == ("Ana María", Origen.PERFIL, "nombre_pila")
    assert ruta.call_count == 0


@respx.mock
@pytest.mark.parametrize(
    ("pregunta", "campo", "valor"),
    [
        # el autocomplete manda aunque la etiqueta no esté en el banco
        (Pregunta("Your legal first name, as on your passport", autocomplete="given-name"),
         "nombre_pila", "Ana María"),
        (Pregunta("Surname(s)", autocomplete="section-work family-name"), "apellido",
         "Pérez Gómez"),
        (Pregunta("Where do you reside?", autocomplete="country-name"), "pais", "Colombia"),
        (Pregunta("Full legal name", autocomplete="name"), "nombre", "Ana María Pérez Gómez"),
        # tokens de name o id, en cualquier convención
        (Pregunta("Campo 1", nombre="job_application[first_name]"), "nombre_pila", "Ana María"),
        (Pregunta("Campo 2", nombre="candidateLastName"), "apellido", "Pérez Gómez"),
        (Pregunta("Campo 3", nombre="legalNameSection_firstName"), "nombre_pila", "Ana María"),
        (Pregunta("Campo 4", nombre="_systemfield_name"), "nombre", "Ana María Pérez Gómez"),
        (Pregunta("Campo 5", nombre="country"), "pais", "Colombia"),
    ],
)  # fmt: skip
def test_autocomplete_y_name_se_resuelven_antes_del_banco_y_sin_ia(base, pregunta, campo, valor):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    r = asyncio.run(resolver(pregunta, contexto(base, datos=DATOS_AMPLIADOS)))
    assert (r.campo, r.valor, r.origen) == (campo, valor, Origen.PERFIL)
    assert ruta.call_count == 0


def test_codigo_de_pais_del_telefono_no_es_el_pais(base):
    ctx = contexto(base, con_ia=False, datos=DATOS_AMPLIADOS)
    r = asyncio.run(resolver(Pregunta("Prefix", nombre="phone_country_code"), ctx))
    assert r.campo == "telefono"  # lo gana el teléfono
    r = asyncio.run(resolver(Pregunta("Prefijo", nombre="country_code"), ctx))
    assert r.falta and r.campo is None


def test_campo_por_autocomplete_sin_dato_se_pregunta_una_vez(base):
    sin_nombre = DatosUsuario(PerfilExtraido(es_cv=True), {})
    r = asyncio.run(resolver(Pregunta("Anything", autocomplete="family-name"),
                             contexto(base, con_ia=False, datos=sin_nombre)))  # fmt: skip
    assert r.falta and r.campo == "apellido"


def test_autocomplete_de_pais_elige_la_opcion_del_select(base):
    pregunta = Pregunta("Country", "opciones", ["Argentina", "Colombia (+57)", "Perú"],
                        autocomplete="country")  # fmt: skip
    r = asyncio.run(resolver(pregunta, contexto(base, con_ia=False, datos=DATOS_AMPLIADOS)))
    assert r.opcion == 1


# --- banco en inglés y portugués ----------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    ("texto", "campo", "valor"),
    [
        ("Pretensão salarial", "salario", "2500000"),
        ("Qual é a sua pretensão salarial?", "salario", "2500000"),
        ("What are your monthly pay expectations in Colombian Pesos?", "salario", "2500000"),
        ("Expected salary", "salario", "2500000"),
        ("First Name", "nombre_pila", "Ana María"),
        ("Last name", "apellido", "Pérez Gómez"),
        ("Sobrenome", "apellido", "Pérez Gómez"),
        ("Country", "pais", "Colombia"),
        ("Current city", "ciudad", "Bogotá"),
        ("Cidade de residência", "ciudad", "Bogotá"),
        ("Please list your current cumulative GPA.", "promedio", None),
        ("LinkedIn Profile", "enlace_linkedin", None),
    ],
)  # fmt: skip
def test_banco_reconoce_formulaciones_en_ingles_y_portugues(base, texto, campo, valor):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    r = asyncio.run(resolver(Pregunta(texto), contexto(base, datos=DATOS_AMPLIADOS)))
    assert r.campo == campo
    assert (r.valor == valor) if valor else r.falta  # sin el dato en el perfil se pregunta
    assert ruta.call_count == 0


@respx.mock
def test_nivel_de_ingles_con_opciones_en_ingles(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    pregunta = Pregunta("What is your English level?", "opciones",
                        ["A1", "A2", "B1 - Intermediate", "B2", "C1"])  # fmt: skip
    r = asyncio.run(resolver(pregunta, contexto(base)))
    assert r.opcion == 2 and ruta.call_count == 0


def test_semilla_corrige_el_campo_de_una_fila_ya_sembrada(base):
    norma = normalizar_pregunta("Perfil de LinkedIn")
    with base.transaccion() as cx:
        cx.execute("UPDATE banco_preguntas SET campo = 'enlace_portafolio' "
                   "WHERE pregunta_norm = ?", (norma,))  # fmt: skip
    assert campo_en_banco(base, "Perfil de LinkedIn") == ("enlace_portafolio", None)
    assert sembrar_banco(base, AHORA) == 0  # nada nuevo que agregar
    assert campo_en_banco(base, "Perfil de LinkedIn") == ("enlace_linkedin", None)


def test_semilla_no_pisa_lo_que_clasifico_la_ia(base):
    guardar_en_banco(base, normalizar_pregunta("Pregunta nueva de la IA"), "ciudad", None, AHORA)
    sembrar_banco(base, AHORA)
    assert campo_en_banco(base, "Pregunta nueva de la IA") == ("ciudad", None)


# --- datos de postulación ampliados ---------------------------------------------------------------


@respx.mock
def test_como_te_enteraste_se_responde_con_la_plataforma(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    pregunta = Pregunta("How did you hear about this opportunity?", "opciones",
                        ["Indeed", "LinkedIn", "Referral", "Other"])  # fmt: skip
    r = asyncio.run(resolver(pregunta, contexto(base, plataforma="linkedin")))
    assert (r.opcion, r.origen, r.campo) == (1, Origen.PERFIL, "fuente_vacante")
    abierta = asyncio.run(resolver(Pregunta("¿Cómo te enteraste de esta oferta?"),
                                   contexto(base, plataforma="computrabajo")))  # fmt: skip
    assert abierta.valor == "Computrabajo"
    assert ruta.call_count == 0


def test_fuente_sin_plataforma_o_sin_opcion_que_calce(base):
    sin = asyncio.run(resolver(Pregunta("How did you hear about us?"),
                               contexto(base, con_ia=False)))  # fmt: skip
    assert sin.falta  # sin plataforma no se inventa la fuente
    otras = Pregunta("How did you hear about us?", "opciones", ["Referral", "Job board"])
    r = asyncio.run(resolver(otras, contexto(base, con_ia=False, plataforma="linkedin")))
    assert r.redactar and r.opcion is None  # la opción no calza: elige el redactor


COLOMBIA = "Are you legally authorized to work in Colombia?"


def test_autorizacion_para_trabajar_se_pregunta_una_vez_por_pais(base):
    pregunta = Pregunta(COLOMBIA, "opciones", ["Yes", "No"])
    antes = asyncio.run(resolver(pregunta, contexto(base, con_ia=False)))
    assert antes.falta and antes.campo == "autorizacion_trabajo:colombia"
    guardado = DatosUsuario(PERFIL, {"autorizacion_trabajo:colombia": "Sí"})
    otra_redaccion = Pregunta("Are you eligible to work legally in Colombia?", "opciones",
                              ["Yes", "No"])  # fmt: skip
    for p in (pregunta, otra_redaccion):
        r = asyncio.run(resolver(p, contexto(base, con_ia=False, datos=guardado)))
        assert (r.opcion, r.origen) == (0, Origen.PERFIL)
    otro_pais = Pregunta("Are you legally authorized to work in Mexico?", "opciones", ["Yes", "No"])
    r = asyncio.run(resolver(otro_pais, contexto(base, con_ia=False, datos=guardado)))
    assert r.falta and r.campo == "autorizacion_trabajo:mexico"


@pytest.mark.parametrize(("texto", "esperado"), [
    ("Are you legally authorized to work in Colombia?", ("autorizacion_trabajo", "Colombia")),
    ("¿Tienes autorización para trabajar en Colombia?", ("autorizacion_trabajo", "Colombia")),
    ("Você tem autorização para trabalhar na Colômbia?", ("autorizacion_trabajo", "Colombia")),
    ("Are you authorized to work in the U.S.?", ("autorizacion_trabajo", "Estados Unidos")),
    # sin país conocido o la pregunta contraria: no se contesta con este dato
    ("Are you legally authorized to work in Narnia?", None),
    ("Will you require sponsorship to work in Colombia?", None),
    ("¿Requieres patrocinio de visa para trabajar en Estados Unidos?", None),
    ("¿Tienes disponibilidad para trabajar en Colombia?", None),
])  # fmt: skip
def test_autorizacion_trabajo_reconoce_pais_y_descarta_patrocinio(texto, esperado):
    assert autorizacion_trabajo(normalizar_pregunta(texto)) == esperado


def test_autorizacion_aprendida_manda_sobre_la_regla(base):
    recordar(base, 1, COLOMBIA, "No", AHORA)
    r = asyncio.run(resolver(Pregunta(COLOMBIA, "opciones", ["Yes", "No"]),
                             contexto(base, con_ia=False)))  # fmt: skip
    assert (r.opcion, r.origen) == (1, Origen.APRENDIDA)


@pytest.mark.parametrize(("tipo", "texto", "ayuda", "esperado"), [
    ("texto", "Expected salary", "Please include currency", "COP 2.500.000"),
    ("texto", "Pretensão salarial", "Informe a moeda", "COP 2.500.000"),
    ("texto", "Aspiración salarial", "Indica la moneda", "COP 2.500.000"),
    ("numero", "Expected salary", "Please include currency", "2500000"),  # un número no lleva texto
    ("texto", "Expected salary", None, "2500000"),
])  # fmt: skip
def test_salario_con_moneda_cuando_la_pregunta_la_pide(base, tipo, texto, ayuda, esperado):
    r = asyncio.run(resolver(Pregunta(texto, tipo, ayuda=ayuda),
                             contexto(base, con_ia=False, datos=DATOS_AMPLIADOS)))  # fmt: skip
    assert r.campo == "salario" and r.valor == esperado


@respx.mock
def test_salario_con_la_moneda_en_la_misma_pregunta(base):
    respx.post(URL_LITE).mock(return_value=gemini({"campo": "salario", "formato": "dato"}))
    texto = "What is your expected monthly salary? Please include currency"
    r = asyncio.run(resolver(Pregunta(texto), contexto(base, datos=DATOS_AMPLIADOS)))
    assert (r.campo, r.valor) == ("salario", "COP 2.500.000")


def test_salario_en_dolares_nunca_manda_la_cifra_en_pesos(base):
    pregunta = Pregunta("What are your salary expectations in USD?",
                        ayuda="Please include currency")
    sin = asyncio.run(resolver(pregunta, contexto(base, con_ia=False, datos=DATOS_AMPLIADOS)))
    assert sin.falta and sin.campo == "salario_usd"
    con = DatosUsuario(PERFIL, {"salario": "2500000", "salario_usd": "1500"})
    r = asyncio.run(resolver(pregunta, contexto(base, con_ia=False, datos=con)))
    assert r.valor == "USD 1.500" and r.campo == "salario_usd"
    libre = Pregunta("Salary expectations (USD)")
    assert asyncio.run(resolver(libre, contexto(base, con_ia=False, datos=con))).valor == "1500"


def test_promedio_se_pregunta_y_se_elige_el_rango(base):
    pregunta = Pregunta("Please list your current cumulative GPA.", "opciones",
                        ["Below 3.5", "3.5 - 4.0", "4.0 - 4.5", "4.5 - 5.0"])  # fmt: skip
    assert asyncio.run(resolver(pregunta, contexto(base, con_ia=False))).falta
    con = DatosUsuario(PERFIL, {"promedio": "4.2"})
    r = asyncio.run(resolver(pregunta, contexto(base, con_ia=False, datos=con)))
    assert r.opcion == 2


def test_si_no_en_texto_libre_va_en_el_idioma_del_formulario(base):
    ingles = Pregunta("Are you currently studying?", idioma="en")
    portugues = Pregunta("Você estuda atualmente?", idioma="pt")
    espanol = Pregunta("¿Estudias actualmente?")
    ctx = contexto(base, con_ia=False)
    assert asyncio.run(resolver(ingles, ctx)).valor == "Yes"
    assert asyncio.run(resolver(portugues, ctx)).valor == "Sim"
    assert asyncio.run(resolver(espanol, ctx)).valor == "Sí"


@pytest.mark.parametrize("texto", [
    "I agree to the privacy policy",
    "Do you consent to the processing of your personal data? (GDPR)",
    "I have read and accept the Terms and Conditions",
    "Eu concordo com a política de privacidade",
    "Sí, he leído y acepto la declaración de privacidad del candidato.",
])  # fmt: skip
@respx.mock
def test_consentimiento_en_ingles_y_portugues_no_se_inventa(base, texto):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    assert es_consentimiento(normalizar_pregunta(texto))
    r = asyncio.run(resolver(Pregunta(texto, "opciones", ["Yes", "No"]), contexto(base)))
    assert r.falta and not ruta.called


# --- idioma del formulario -----------------------------------------------------------------------


@pytest.mark.parametrize(("textos", "declarado", "esperado"), [
    (["First Name", "Last Name"], None, "en"),
    (["Tell us a bit about your background in Technical Support"], "en", "en"),
    (["Nombre", "¿Cuál es tu aspiración salarial?", "Tienes experiencia?"], "es", "es"),
    (["¿Cuál es tu aspiración salarial?", "¿Tienes disponibilidad de horario?"], "en", "es"),
    (["Qual é a sua pretensão salarial?", "Você tem experiência?"], "es", "pt"),
    (["Why are you interested in this role?", "What is your salary?"], "es", "en"),
    (["Email", "Phone"], "en", "en"),  # sin palabras que decidan: el declarado
    (["Email", "Skype"], None, "es"),  # nada que decida: español
    (["Name", "Nombre"], "en-US", "en"),  # una palabra no basta para llevar la contraria
])  # fmt: skip
def test_detectar_idioma(textos, declarado, esperado):
    preguntas = [Pregunta(t, idioma=declarado) for t in textos]
    assert detectar_idioma(preguntas) == esperado


@respx.mock
def test_formulario_en_ingles_se_redacta_en_ingles(base):
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [
        {"indice": 1, "respuesta": "I have two years of experience in technical support."},
    ]}))  # fmt: skip
    pregunta = Pregunta("Tell us a bit about your background in Technical Support", idioma="en",
                        ayuda="Two or three sentences is enough")  # fmt: skip
    r = asyncio.run(redactar_formulario([pregunta], contexto(base)))
    assert r[0].valor.startswith("I have two years")
    cuerpo = texto_enviado(ruta)
    assert "<<<DATOS idioma\ninglés\nDATOS>>>" in cuerpo
    assert "idioma indicado en «idioma»" in cuerpo
    assert "[ayuda: Two or three sentences is enough]" in cuerpo
    assert "ana@gmail.com" not in cuerpo


@respx.mock
def test_formulario_en_espanol_declarado_en_ingles_se_redacta_en_espanol(base):
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": []}))
    preguntas = [Pregunta("¿Por qué te interesa esta vacante?", idioma="en"),
                 Pregunta("¿Cuál es tu experiencia con soporte técnico?", idioma="en")]  # fmt: skip
    asyncio.run(redactar_formulario(preguntas, contexto(base)))
    assert "<<<DATOS idioma\nespañol\nDATOS>>>" in texto_enviado(ruta)


@respx.mock
def test_idioma_del_contexto_manda_sobre_las_etiquetas(base):
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": []}))
    asyncio.run(redactar_formulario([Pregunta("Motivación")], contexto(base, idioma="pt")))
    assert "<<<DATOS idioma\nportugués\nDATOS>>>" in texto_enviado(ruta)


# --- niveles de IA ---------------------------------------------------------------------------


@respx.mock
def test_ahorro_no_clasifica_con_ia_las_preguntas_nuevas_van_a_la_card(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(
        return_value=gemini({"campo": "salario", "formato": "dato"})
    )
    pregunta = Pregunta("¿Cuál es tu pretensión económica mensual?")
    r = asyncio.run(resolver(pregunta, contexto(base, nivel="ahorro")))
    assert r.falta and not r.redactar
    assert ruta.call_count == 0
    ia = base.cx.execute("SELECT COUNT(*) FROM banco_preguntas WHERE origen = 'ia'").fetchone()
    assert ia[0] == 0  # lo que no se clasificó no entra al banco


@respx.mock
def test_ahorro_sigue_resolviendo_con_datos_banco_y_lo_aprendido_sin_ia(base):
    ruta = respx.post(url__startswith=BASE_URL).mock(return_value=gemini({}))
    r = asyncio.run(
        resolver(Pregunta("¿Cuál es tu aspiración salarial?"), contexto(base, nivel="ahorro"))
    )
    assert (r.valor, r.origen) == ("1300000", Origen.PERFIL)
    assert ruta.call_count == 0


@respx.mock
def test_ahorro_si_redacta_las_preguntas_abiertas_con_una_llamada_al_modelo_ligero(base):
    ligero = respx.post(URL_LITE).mock(return_value=gemini({"respuestas": [
        {"indice": 1, "respuesta": "Me interesa por el equipo y el stack."}
    ]}))  # fmt: skip
    configurado = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": []}))
    r = asyncio.run(
        redactar_formulario([Pregunta(COMPUESTA)], contexto(base, nivel="ahorro"))
    )
    assert r[0].valor == "Me interesa por el equipo y el stack."
    assert (ligero.call_count, configurado.call_count) == (1, 0)


@respx.mock
def test_normal_clasifica_con_ia_y_redacta_con_el_modelo_configurado(base):
    clasifica = respx.post(URL_LITE).mock(
        return_value=gemini({"campo": "salario", "formato": "dato"})
    )
    r = asyncio.run(
        resolver(Pregunta("¿Cuál es tu pretensión económica mensual?"), contexto(base))
    )
    assert r.origen == Origen.BANCO and clasifica.call_count == 1
    configurado = respx.post(URL_REDACTAR).mock(return_value=gemini({"respuestas": [
        {"indice": 1, "respuesta": "Estudio Ingeniería de Sistemas."}
    ]}))  # fmt: skip
    asyncio.run(redactar_formulario([Pregunta(COMPUESTA)], contexto(base)))
    assert configurado.call_count == 1
