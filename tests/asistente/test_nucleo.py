import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

pytest.importorskip("fpdf", reason="requiere uv sync --group asistente")
pytest.importorskip("cryptography", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import tarjeta_postulacion as tp  # noqa: E402
from buscador_vacantes.asistente import vinculos  # noqa: E402
from buscador_vacantes.asistente.campos import RESERVADO  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import E  # noqa: E402
from buscador_vacantes.asistente.cv_lectura import Formacion, Idioma, PerfilExtraido  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro  # noqa: E402
from buscador_vacantes.asistente.destinos_linkedin import Destino, guardar  # noqa: E402
from buscador_vacantes.asistente.detalle import Detalles, Ritmo  # noqa: E402
from buscador_vacantes.asistente.enlaces import id_corto  # noqa: E402
from buscador_vacantes.asistente.ia import crear_clientes  # noqa: E402
from buscador_vacantes.asistente.nucleo import Camino, Nucleo  # noqa: E402
from buscador_vacantes.asistente.pantalla import (  # noqa: E402
    Boton,
    Consulta,
    ConsultaReparacion,
    Peticion,
    Resumen,
    Sugerido,
)
from buscador_vacantes.asistente.respuestas import (  # noqa: E402
    REDACTAR,
    DatoFaltante,
    Origen,
    Pregunta,
    Respuesta,
    guardar_en_banco,
    normalizar_pregunta,
    recordar,
    sembrar_banco,
)
from buscador_vacantes.asistente.resumen_postulacion import DatosResumen  # noqa: E402
from buscador_vacantes.asistente.vacantes import Indice  # noqa: E402
from buscador_vacantes.comun.config import cargar_configuracion  # noqa: E402
from buscador_vacantes.comun.estado import Estado, a_texto  # noqa: E402
from buscador_vacantes.comun.modelo import Vacante  # noqa: E402

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parent.parent / "fixtures" / "detalle"
URL_CT = "https://co.computrabajo.com/ofertas-de-trabajo/oferta-1"
URL_LI = "https://co.linkedin.com/jobs/view/4475512580"
CT = "computrabajo"

PERFIL = PerfilExtraido(
    es_cv=True,
    nombre="Ana Pérez",
    ciudad="Bogotá",
    formacion=[Formacion(institucion="SENA", programa="ADSO", estado="En curso")],
    habilidades_tecnicas=["Python", "SQL", "Excel"],
    idiomas=[Idioma(idioma="Inglés", nivel="B1")],
)


class Mundo:
    def __init__(self, tmp_path):
        self.estado = Estado.abrir(tmp_path / "vacantes.db")
        for fuente, url in (("computrabajo", URL_CT), ("linkedin", URL_LI)):
            v = Vacante(fuente=fuente, id_fuente="1", titulo="Practicante de sistemas",
                        empresa="ACME", url=url, keyword="k")  # fmt: skip
            self.estado.registrar_vista(v, f"h{fuente}", momento=T0, enviada=True)
        configuracion = cargar_configuracion()
        self.base = BaseAsistente.abrir(tmp_path / "a.db")
        sembrar_banco(self.base, T0)
        self.ro = abrir_vacantes_ro(tmp_path / "vacantes.db")
        a = configuracion.asistente

        async def dormir(_):
            return None

        ritmo = Ritmo(0, reloj=lambda: 0, dormir=dormir)
        detalles = Detalles(self.base, self.ro, a.detalle, configuracion.red, ritmo=ritmo)
        ia = crear_clientes(a.ia, self.base, 60, reloj=lambda: T0)
        self.esperas = []  # lo que el núcleo esperó antes de reintentar con la IA

        async def esperar(segundos):
            self.esperas.append(segundos)

        async def sin_esperar(_segundos):
            return None

        for cliente in ia.values():  # los reintentos del propio cliente no esperan ni se cuentan
            cliente.dormir = sin_esperar
        self.nucleo = Nucleo(
            configuracion, self.base, Indice(self.base, self.ro, 90), detalles, ia,
            Cifrador(generar_clave()), tmp_path / "archivos", reloj=lambda: T0, dormir=esperar,
        )  # fmt: skip
        self.eventos = []

        async def notificar(e):
            self.eventos.append(e)

        self.nucleo.notificador = notificar
        self.usuario = self.nucleo.usuarios.crear(111, "Ana", T0)
        self.nucleo.usuarios.completar_alta(self.usuario)
        self.usuario = self.nucleo.usuarios.obtener(111)
        self.nucleo.guardar_perfil(self.usuario.id, PERFIL)
        self.nucleo.guardar_cuestionario(
            self.usuario.id,
            {"salario": "1300000", "correo": "ana@gmail.com", "telefono": "3105551234"},
        )

    def vincular(self):
        codigo = vinculos.crear_codigo(self.base, self.usuario.id, T0)
        vinculos.canjear(self.base, codigo, "Edge", "1.0.0", T0)

    def cerrar(self):
        self.ro.close()
        self.estado.cerrar()
        self.base.cerrar()


@pytest.fixture
def mundo(tmp_path):
    m = Mundo(tmp_path)
    yield m
    m.cerrar()


def test_toque_con_navegador_es_automatico(mundo):
    mundo.vincular()
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1"))
    assert toque.camino == Camino.AUTOMATICA and toque.postulacion.estado == E.EN_COLA
    otra = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1"))
    assert otra.camino == Camino.YA_EXISTE and otra.postulacion.id == toque.postulacion.id


def test_toque_sin_navegador_va_a_respaldo(mundo):
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1"))
    assert toque.camino == Camino.RESPALDO and toque.motivo == "sin_navegador"


def test_linkedin_va_a_respaldo(mundo):
    mundo.vincular()
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("linkedin:1"))
    # Reconocida, pero apagada hasta su piloto (change postular-linkedin)
    assert toque.vacante.plataforma == "linkedin"
    assert toque.camino == Camino.RESPALDO and toque.motivo == "plataforma_no_automatica"


def test_id_desconocido(mundo):
    assert mundo.nucleo.tocar(mundo.usuario, "inexistente1").camino == Camino.NO_DISPONIBLE


def publicar(mundo, fuente, id_fuente, url):
    """Publica una vacante en el canal (vacantes.db) y devuelve su id corto."""
    v = Vacante(fuente=fuente, id_fuente=id_fuente, titulo="Practicante de sistemas",
                empresa="ACME", url=url, keyword="k")  # fmt: skip
    mundo.estado.registrar_vista(v, f"h{fuente}{id_fuente}", momento=T0, enviada=True)
    return id_corto(f"{fuente}:{id_fuente}")


# Plataformas reconocidas por dominio; las pruebas de respaldo las apagan (automatica: false)
NUEVAS = {"elempleo": "https://www.elempleo.com/co/ofertas-trabajo/practicante-1886774213"}


@pytest.mark.parametrize("plataforma", list(NUEVAS))
def test_plataforma_nueva_sin_automatica_va_a_respaldo_sin_tarea(mundo, plataforma):
    mundo.vincular()
    mundo.nucleo.config.plataformas[plataforma].automatica = False
    id_ = publicar(mundo, plataforma, "1", NUEVAS[plataforma])
    toque = mundo.nucleo.tocar(mundo.usuario, id_)
    assert toque.vacante.plataforma == plataforma
    assert toque.camino == Camino.RESPALDO and toque.motivo == "plataforma_no_automatica"
    assert toque.postulacion.estado == E.RESPALDO
    listos = {"computrabajo", "magneto", plataforma}
    assert mundo.nucleo.cola.siguiente(mundo.usuario.id, listos, T0) is None


def test_vacante_indexada_antes_de_reconocer_el_dominio_toma_la_plataforma_del_enlace(mundo):
    mundo.vincular()
    mundo.nucleo.config.plataformas["elempleo"].automatica = False
    id_ = publicar(mundo, "elempleo", "3", NUEVAS["elempleo"])
    mundo.nucleo.indice.indexar(T0)
    # Así quedaron las filas indexadas cuando elempleo.com aún no estaba en PLATAFORMAS
    mundo.base.cx.execute("UPDATE vacantes SET plataforma = NULL WHERE id_corto = ?", (id_,))
    mundo.base.cx.commit()
    toque = mundo.nucleo.tocar(mundo.usuario, id_)
    assert toque.vacante.plataforma == "elempleo"
    assert toque.camino == Camino.RESPALDO and toque.motivo == "plataforma_no_automatica"


@pytest.mark.parametrize(
    ("url", "plataforma", "motivo"),
    [
        ("https://co.computrabajo.com/ofertas-de-trabajo/oferta-2", "computrabajo", None),
        ("https://www.magneto365.com/co/empleos/practicante-1-5-2", "magneto", None),
        (NUEVAS["elempleo"], "elempleo", None),
        ("https://empleos.cajadecompensacion.example/oferta/2", None, "plataforma_no_soportada"),
    ],
)
def test_plaza_del_spe_toma_la_plataforma_del_enlace(mundo, url, plataforma, motivo):
    mundo.vincular()
    vacante = mundo.nucleo.indice.resolver(publicar(mundo, "spe", "2", url), T0)
    assert vacante.fuente == "spe" and vacante.plataforma == plataforma
    assert mundo.nucleo.camino_automatico(mundo.usuario.id, vacante) == motivo


@respx.mock
def test_formulario_con_dato_faltante_pregunta_y_reanuda(mundo):
    respx.get(URL_CT).mock(
        return_value=httpx.Response(200, text=(FIXTURES / "computrabajo.html").read_text("utf-8"))
    )
    mundo.vincular()
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1"))
    pid = toque.postulacion.id
    navegador = mundo.base.cx.execute("SELECT id FROM navegadores").fetchone()[0]
    mundo.nucleo.cola.tomar(pid, navegador, T0)
    mundo.nucleo.cola.iniciar(pid, navegador, T0)
    p = mundo.nucleo.cola.obtener(pid)
    preguntas = [
        Pregunta("¿Cuál es tu aspiración salarial?"),
        Pregunta("¿Tienes licencia de conducción?", "opciones", ["Sí", "No"]),
    ]
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert [r.valor for r in resultado.respuestas] == ["1300000"]
    assert len(resultado.faltan) == 1
    pendientes = mundo.nucleo.pendientes(mundo.usuario.id)
    assert pendientes[0]["pregunta"] == "¿Tienes licencia de conducción?"
    assert any(e.get("tipo") == "preguntas_pendientes" for e in mundo.eventos)
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    assert mundo.nucleo.responder_pendiente(mundo.usuario.id, pendientes[0]["id"], "No")
    assert mundo.nucleo.cola.obtener(pid).estado == E.EN_COLA
    # La próxima vez la respuesta aprendida resuelve la pregunta y hay CV adaptado
    mundo.nucleo.cola.tomar(pid, navegador, T0 + timedelta(minutes=3))
    mundo.nucleo.cola.iniciar(pid, navegador, T0 + timedelta(minutes=3))
    p = mundo.nucleo.cola.obtener(pid)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert not resultado.faltan
    assert resultado.respuestas[1].texto == "No"
    assert resultado.cv is not None and resultado.cv.name == "CV_Ana_Perez.pdf"


@respx.mock
def test_como_te_enteraste_y_autorizacion_para_trabajar_sin_ia(mundo):
    respx.get(URL_CT).mock(
        return_value=httpx.Response(200, text=(FIXTURES / "computrabajo.html").read_text("utf-8"))
    )
    mundo.vincular()
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1"))
    pid = toque.postulacion.id
    navegador = mundo.base.cx.execute("SELECT id FROM navegadores").fetchone()[0]
    mundo.nucleo.cola.tomar(pid, navegador, T0)
    mundo.nucleo.cola.iniciar(pid, navegador, T0)
    p = mundo.nucleo.cola.obtener(pid)
    preguntas = [
        Pregunta("How did you hear about this opportunity?", "opciones",
                 ["Indeed", "Computrabajo", "Other"]),
        Pregunta("Are you legally authorized to work in Colombia?", "opciones", ["Yes", "No"]),
    ]  # fmt: skip
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    # La fuente sale de la plataforma de la vacante; la autorización se le pregunta al usuario
    assert [(r.campo, r.texto) for r in resultado.respuestas] == [
        ("fuente_vacante", "Computrabajo")
    ]
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert pendiente["campo"] == "autorizacion_trabajo:colombia"
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    assert mundo.nucleo.responder_pendiente(mundo.usuario.id, pendiente["id"], "Sí")
    # La respuesta sirve para cualquier otra pregunta por Colombia, aunque la redacten distinto
    mundo.nucleo.cola.tomar(pid, navegador, T0 + timedelta(minutes=3))
    mundo.nucleo.cola.iniciar(pid, navegador, T0 + timedelta(minutes=3))
    p = mundo.nucleo.cola.obtener(pid)
    otra = Pregunta("Are you eligible to work legally in Colombia?", "opciones", ["Yes", "No"])
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, [otra]))
    assert not resultado.faltan and resultado.respuestas[0].texto == "Yes"
    assert mundo.nucleo.datos_usuario(mundo.usuario.id).cuestionario[
        "autorizacion_trabajo:colombia"
    ] == "Sí"


def test_clave_gemini_cifrada(mundo):
    mundo.nucleo.guardar_clave_gemini(mundo.usuario.id, "AIzaSecreta1234")
    fila = mundo.base.cx.execute("SELECT gemini_clave, gemini_ult4 FROM usuarios").fetchone()
    assert "AIzaSecreta" not in fila[0] and fila[1] == "1234"
    assert mundo.nucleo.clave_gemini(mundo.usuario.id) == "AIzaSecreta1234"
    mundo.nucleo.marcar_clave_invalida(mundo.usuario.id)
    assert mundo.nucleo.clave_gemini(mundo.usuario.id) is None


def test_modo_automatico_encola_por_umbral(mundo):
    mundo.vincular()
    mundo.nucleo.indice.indexar(T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE usuarios SET automatico_umbral = 0")
        cx.execute(
            "UPDATE vacantes SET requisitos_json = ? WHERE plataforma = 'computrabajo'",
            ('{"origen": "ia", "requisitos": {"obligatorios": ["Python"]}}',),
        )
    mundo.base.kv_guardar("automatico_hasta", "2000-01-01T00:00:00+00:00")
    nuevas = asyncio.run(mundo.nucleo.encolar_automaticos())
    assert [p.id_corto for p in nuevas] == [id_corto("computrabajo:1")]
    assert nuevas[0].origen == "automatico"


def test_preferencia_apaga_el_modo_automatico_en_un_portal(mundo):
    """El engranaje de la extensión puede excluir un portal del modo automático sin apagarlo
    para los demás ni para el toque ⚡ manual."""
    mundo.vincular()
    mundo.nucleo.indice.indexar(T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE usuarios SET automatico_umbral = 0")
        cx.execute(
            "UPDATE vacantes SET requisitos_json = ? WHERE plataforma = 'computrabajo'",
            ('{"origen": "ia", "requisitos": {"obligatorios": ["Python"]}}',),
        )
    mundo.nucleo.preferencias.guardar(
        mundo.usuario.id, "computrabajo", T0, automatico=False, umbral=None, avisar=True
    )
    mundo.base.kv_guardar("automatico_hasta", "2000-01-01T00:00:00+00:00")
    nuevas = asyncio.run(mundo.nucleo.encolar_automaticos())
    assert nuevas == []
    # El toque manual (⚡) sigue funcionando normalmente en ese portal
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1"))
    assert toque.camino == Camino.AUTOMATICA


def test_preferencia_de_afinidad_propia_prevalece_sobre_la_del_usuario(mundo):
    """Una afinidad mínima propia del portal reemplaza, solo ahí, la del usuario."""
    mundo.vincular()
    mundo.nucleo.indice.indexar(T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE usuarios SET automatico_umbral = 90")  # no alcanza con el perfil
        cx.execute(
            "UPDATE vacantes SET requisitos_json = ? WHERE plataforma = 'computrabajo'",
            ('{"origen": "ia", "requisitos": {"obligatorios": ["Python"]}}',),
        )
    mundo.nucleo.preferencias.guardar(
        mundo.usuario.id, "computrabajo", T0, automatico=True, umbral=0, avisar=True
    )
    mundo.base.kv_guardar("automatico_hasta", "2000-01-01T00:00:00+00:00")
    nuevas = asyncio.run(mundo.nucleo.encolar_automaticos())
    assert [p.id_corto for p in nuevas] == [id_corto("computrabajo:1")]


URL_MG = "https://www.magneto365.com/co/empleos/desarrollador-junior-erp-odoo-1100511"
ENCUESTA_MG = [
    "¿Tienes disponibilidad para trabajar de forma presencial?",
    "¿Autorizas el tratamiento de tus datos personales?",
]


def postulacion_magneto(mundo):
    """Postulación de Magneto en curso y su vacante indexada."""
    mundo.vincular()
    id_ = publicar(mundo, "magneto", "1", URL_MG)
    mundo.nucleo.indice.indexar(T0)
    pid = mundo.nucleo.tocar(mundo.usuario, id_).postulacion.id
    navegador = mundo.base.cx.execute("SELECT id FROM navegadores").fetchone()[0]
    mundo.nucleo.cola.tomar(pid, navegador, T0)
    mundo.nucleo.cola.iniciar(pid, navegador, T0)
    return mundo.nucleo.cola.obtener(pid), id_


def preguntas_magneto():
    """Como las lee la extensión: opciones Si/No, sin name, todas obligatorias."""
    return [Pregunta(t, "opciones", ["Si", "No"], True, None) for t in ENCUESTA_MG]


def test_encuesta_de_magneto_queda_guardada_y_llega_a_la_tarjeta(mundo):
    p, id_ = postulacion_magneto(mundo)
    for texto in ENCUESTA_MG:
        recordar(mundo.base, mundo.usuario.id, texto, "Si", T0)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas_magneto()))
    assert not resultado.faltan
    assert [r.opcion for r in resultado.respuestas] == [0, 0]
    filas = mundo.base.cx.execute(
        "SELECT pregunta, respuesta, origen FROM respuestas WHERE postulacion_id = ? ORDER BY id",
        (p.id,),
    ).fetchall()
    assert [(f["pregunta"], f["respuesta"], f["origen"]) for f in filas] == [
        (t, "Si", "aprendida") for t in ENCUESTA_MG
    ]
    resumen = DatosResumen(
        mundo.nucleo.indice.obtener(id_), "magneto", T0, respuestas=[dict(f) for f in filas],
        folio=f"P-{p.id}",
    )  # fmt: skip
    datos = tp.Datos(pid=p.id, titulo="Desarrollador junior", empresa="ACME",
                     plataforma="magneto", url=URL_MG, resumen=resumen)  # fmt: skip
    card = tp.Card(fase=tp.CONFIRMADA)
    assert "Encuesta de 2" in tp.texto(card, datos)
    botones = tp.botones(card, datos, lambda *partes: "cb:" + ":".join(map(str, partes)))
    assert "Respuestas" in [texto for fila in botones for texto, _ in fila]


def test_magneto_sin_encuesta_se_muestra_como_sin_encuesta(mundo):
    p, id_ = postulacion_magneto(mundo)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, []))
    assert not resultado.faltan and not resultado.respuestas
    resumen = DatosResumen(mundo.nucleo.indice.obtener(id_), "magneto", T0)
    datos = tp.Datos(pid=p.id, titulo="Desarrollador junior", empresa="ACME",
                     plataforma="magneto", url=URL_MG, resumen=resumen)  # fmt: skip
    card = tp.Card(fase=tp.CONFIRMADA)
    assert "Sin encuesta" in tp.texto(card, datos)
    botones = tp.botones(card, datos, lambda *partes: "cb:" + ":".join(map(str, partes)))
    assert "Respuestas" not in [texto for fila in botones for texto, _ in fila]


def test_consentimiento_de_magneto_sin_respuesta_espera_al_usuario(mundo):
    p, _ = postulacion_magneto(mundo)
    recordar(mundo.base, mundo.usuario.id, ENCUESTA_MG[0], "Si", T0)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas_magneto()))
    assert [r.pregunta.texto for r in resultado.faltan] == [ENCUESTA_MG[1]]
    pendientes = mundo.nucleo.pendientes(mundo.usuario.id)
    assert [x["pregunta"] for x in pendientes] == [ENCUESTA_MG[1]]
    assert any(e.get("tipo") == "preguntas_pendientes" for e in mundo.eventos)


# --- redactor por formulario -----------------------------------------------------------------

URL_REDACTAR = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
)
ABIERTAS = [
    "¿Qué programa estás estudiando y en qué institución?",
    "¿Por qué te interesa esta vacante?",
    "Cuéntanos de un proyecto del que estés orgulloso",
]
INSTITUCION = {"pregunta": "¿En qué institución estudias?", "sugerencias": ["SENA", "ITM"]}


def gemini(contenido):
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(contenido)}]}}]}
    )


def redactadas(*respuestas):
    return gemini({"respuestas": list(respuestas)})


def en_curso(mundo, con_ia=True):
    """Postulación de Computrabajo con el CV ya preparado y las preguntas abiertas en el banco."""
    mundo.vincular()
    if con_ia:
        mundo.nucleo.guardar_clave_gemini(mundo.usuario.id, "clave")
    for texto in ABIERTAS:
        guardar_en_banco(mundo.base, normalizar_pregunta(texto), REDACTAR, None, T0)
    pid = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1")).postulacion.id
    cv = mundo.nucleo.archivos / "cv.pdf"
    cv.parent.mkdir(parents=True, exist_ok=True)
    cv.write_bytes(b"%PDF")
    mundo.base.cx.execute("UPDATE postulaciones SET cv_archivo = ? WHERE id = ?", (str(cv), pid))
    mundo.base.cx.commit()
    return pid


def tomar(mundo, pid, minutos=0):
    navegador = mundo.base.cx.execute("SELECT id FROM navegadores").fetchone()[0]
    momento = T0 + timedelta(minutes=minutos)
    mundo.nucleo.cola.tomar(pid, navegador, momento)
    mundo.nucleo.cola.iniciar(pid, navegador, momento)
    return mundo.nucleo.cola.obtener(pid), navegador


def formulario():
    return [Pregunta(t) for t in ABIERTAS] + [Pregunta("¿Cuál es tu aspiración salarial?")]


def filas_respuestas(mundo, pid):
    return mundo.base.cx.execute(
        "SELECT pregunta, respuesta, origen, estado FROM respuestas WHERE postulacion_id = ? "
        "ORDER BY id",
        (pid,),
    ).fetchall()


@respx.mock
def test_una_sola_llamada_redacta_todas_las_abiertas(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    ruta = respx.post(URL_REDACTAR).mock(return_value=redactadas(
        {"indice": 1, "respuesta": "Estudio ADSO en el SENA."},
        {"indice": 2, "respuesta": "Quiero aplicar Python en un equipo real."},
        {"indice": 3, "respuesta": "Hice un inventario en Django."},
    ))  # fmt: skip
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert ruta.call_count == 1 and not resultado.faltan and not resultado.revisar
    assert [(r.valor, r.origen) for r in resultado.respuestas] == [
        ("Estudio ADSO en el SENA.", Origen.IA),
        ("Quiero aplicar Python en un equipo real.", Origen.IA),
        ("Hice un inventario en Django.", Origen.IA),
        ("1300000", Origen.PERFIL),
    ]
    assert {f["estado"] for f in filas_respuestas(mundo, pid)} == {"enviada"}
    assert "aspiración salarial" not in ruta.calls[0].request.content.decode("utf-8")


@respx.mock
def test_dato_faltante_se_pregunta_y_la_segunda_pasada_solo_redacta_eso(mundo):
    pid = en_curso(mundo)
    p, navegador = tomar(mundo, pid)
    # Dos preguntas piden el mismo dato: se pregunta una sola vez
    preguntas = formulario() + [Pregunta("Institución y programa que cursas")]
    guardar_en_banco(mundo.base, normalizar_pregunta(preguntas[-1].texto), REDACTAR, None, T0)
    ruta = respx.post(URL_REDACTAR).mock(return_value=redactadas(
        {"indice": 1, "respuesta": None, "faltan": [INSTITUCION]},
        {"indice": 2, "respuesta": "Quiero aplicar Python."},
        {"indice": 3, "respuesta": "Hice un inventario."},
        {"indice": 4, "respuesta": None, "faltan": [INSTITUCION]},
    ))  # fmt: skip
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert len(resultado.faltan) == 2
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert (pendiente["pregunta"], pendiente["tipo"]) == ("¿En qué institución estudias?", "dato")
    assert json.loads(pendiente["opciones_json"]) == ["SENA", "ITM"]
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    assert mundo.nucleo.responder_pendiente(mundo.usuario.id, pendiente["id"], "SENA")
    assert mundo.nucleo.cola.obtener(pid).estado == E.EN_COLA
    # Segunda pasada: se reutiliza lo redactado y solo se redacta lo que faltaba
    ruta.return_value = redactadas(
        {"indice": 1, "respuesta": "Estudio ADSO en el SENA."},
        {"indice": 2, "respuesta": "Curso ADSO en el SENA."},
    )
    p, _ = tomar(mundo, pid, 3)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert not resultado.faltan and ruta.call_count == 2
    cuerpo = ruta.calls[-1].request.content.decode("utf-8")
    assert "¿En qué institución estudias? → SENA" in cuerpo
    assert ABIERTAS[1] not in cuerpo and ABIERTAS[2] not in cuerpo
    assert [r.valor for r in resultado.respuestas] == [
        "Estudio ADSO en el SENA.", "Quiero aplicar Python.", "Hice un inventario.", "1300000",
        "Curso ADSO en el SENA.",
    ]  # fmt: skip
    assert mundo.nucleo.pendientes(mundo.usuario.id) == []
    assert len(filas_respuestas(mundo, pid)) == 5  # una fila por pregunta, sin duplicados


def test_sin_ia_las_preguntas_de_texto_van_a_la_card_como_formulario(mundo):
    pid = en_curso(mundo, con_ia=False)
    p, _ = tomar(mundo, pid)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert [r.pregunta.texto for r in resultado.faltan] == ABIERTAS
    pendientes = mundo.nucleo.pendientes(mundo.usuario.id)
    assert [(x["pregunta"], x["tipo"]) for x in pendientes] == [(t, "formulario") for t in ABIERTAS]


@respx.mock
def test_falla_de_ia_al_redactar_no_pierde_la_postulacion(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    respx.post(url__startswith="https://generativelanguage").mock(
        return_value=gemini({"no": "cumple"})
    )
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert [r.pregunta.texto for r in resultado.faltan] == ABIERTAS
    assert {x["tipo"] for x in mundo.nucleo.pendientes(mundo.usuario.id)} == {"formulario"}


@respx.mock
def test_dato_reservado_que_la_ia_vuelve_a_pedir_pasa_a_pregunta_del_formulario(mundo):
    pid = en_curso(mundo)
    p, navegador = tomar(mundo, pid)
    ruta = respx.post(URL_REDACTAR).mock(return_value=redactadas(
        {"indice": 1, "respuesta": None, "faltan": [INSTITUCION]},
    ))  # fmt: skip
    preguntas = [Pregunta(ABIERTAS[0])]
    asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    assert mundo.nucleo.responder_pendiente(mundo.usuario.id, pendiente["id"], RESERVADO)
    p, _ = tomar(mundo, pid, 3)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert "(prefiere no decirlo)" in ruta.calls[-1].request.content.decode("utf-8")
    assert [r.pregunta.texto for r in resultado.faltan] == [ABIERTAS[0]]
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert (pendiente["pregunta"], pendiente["tipo"]) == (ABIERTAS[0], "formulario")
    datos = mundo.nucleo.datos_usuario(mundo.usuario.id)
    assert RESERVADO not in json.dumps(datos.para_ia(), ensure_ascii=False)


# --- revisión antes de enviar ------------------------------------------------------------


def revisar_en_computrabajo(mundo, encendida=True):
    mundo.nucleo.preferencias.guardar(mundo.usuario.id, "computrabajo", T0, automatico=True,
                                      umbral=None, avisar=True,
                                      revisar_respuestas=encendida)  # fmt: skip


@respx.mock
def test_revision_encendida_espera_y_lo_aprobado_se_envia_sin_ia(mundo):
    pid = en_curso(mundo)
    revisar_en_computrabajo(mundo)
    p, navegador = tomar(mundo, pid)
    ruta = respx.post(URL_REDACTAR).mock(return_value=redactadas(
        {"indice": 1, "respuesta": "Estudio ADSO en el SENA."},
        {"indice": 2, "respuesta": "Quiero aplicar Python."},
    ))  # fmt: skip
    preguntas = [Pregunta(ABIERTAS[0]), Pregunta(ABIERTAS[1]), Pregunta("Aspiración salarial")]
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert resultado.revisar and resultado.cv is None
    assert any(e.get("tipo") == "revision_respuestas" for e in mundo.eventos)
    revision = mundo.nucleo.respuestas_en_revision(pid)
    assert [(r["respuesta"], r["estado"]) for r in revision] == [
        ("Estudio ADSO en el SENA.", "propuesta"), ("Quiero aplicar Python.", "propuesta"),
    ]  # fmt: skip
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    # Corregir: el texto del usuario reemplaza la redacción tal cual
    assert mundo.nucleo.corregir_respuesta(mundo.usuario.id, revision[1]["id"], "Me gusta.") == pid
    assert mundo.nucleo.corregir_respuesta(999, revision[1]["id"], "otro") is None
    assert mundo.nucleo.aprobar_respuestas(mundo.usuario.id, pid)
    assert mundo.nucleo.cola.obtener(pid).estado == E.EN_COLA
    p, _ = tomar(mundo, pid, 3)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert ruta.call_count == 1 and not resultado.revisar and resultado.cv is not None
    assert [(r.valor, r.origen) for r in resultado.respuestas] == [
        ("Estudio ADSO en el SENA.", Origen.IA), ("Me gusta.", Origen.USUARIO),
        ("1300000", Origen.PERFIL),
    ]  # fmt: skip


@respx.mock
def test_revision_apagada_envia_sin_esperar(mundo):
    pid = en_curso(mundo)
    revisar_en_computrabajo(mundo, encendida=False)
    p, _ = tomar(mundo, pid)
    respx.post(URL_REDACTAR).mock(return_value=redactadas({"indice": 1, "respuesta": "Sí."}))
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, [Pregunta(ABIERTAS[1])]))
    assert not resultado.revisar and resultado.cv is not None
    assert not any(e.get("tipo") == "revision_respuestas" for e in mundo.eventos)


def test_revision_encendida_sin_redacciones_no_espera(mundo):
    pid = en_curso(mundo)
    revisar_en_computrabajo(mundo)
    p, _ = tomar(mundo, pid)
    preguntas = [Pregunta("Aspiración salarial"), Pregunta("Ciudad de residencia")]
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert not resultado.revisar and not resultado.faltan


# --- por qué una postulación en cola no sale ---------------------------------------------------


def latido_guardado(mundo, portales, momento=T0, version="1.4.0"):
    with mundo.base.transaccion() as cx:
        cx.execute(
            "UPDATE navegadores SET ultimo_latido = ?, version = ?, portales_json = ?",
            (a_texto(momento), version, json.dumps(portales)),
        )


def en_cola_magneto(mundo):
    mundo.vincular()
    mundo.nucleo.cargar_selectores()
    id_ = publicar(mundo, "magneto", "1", URL_MG)
    mundo.nucleo.indice.indexar(T0)
    return mundo.nucleo.tocar(mundo.usuario, id_).postulacion.id


def test_espera_reproduce_la_postulacion_43_magneto_sin_sesion(mundo):
    mundo.nucleo.config.extension.version_minima = "1.0.0"
    pid = en_cola_magneto(mundo)
    latido_guardado(mundo, {
        "magneto": {"estado": "sin_sesion", "motivo": "enlace_ingresar", "cuenta": "ok"},
        "_pausado": False,
    })  # fmt: skip
    resultado = mundo.nucleo.espera(pid)
    assert resultado.codigo == "sin_sesion" and resultado.plataforma == "magneto"


def test_espera_se_resuelve_al_iniciar_sesion(mundo):
    mundo.nucleo.config.extension.version_minima = "1.0.0"
    pid = en_cola_magneto(mundo)
    latido_guardado(mundo, {"magneto": {"estado": "listo", "cuenta": "ok"}, "_pausado": False})
    assert mundo.nucleo.espera(pid) is None


def test_espera_sin_latido_reciente_y_con_navegador_revocado(mundo):
    pid = en_cola_magneto(mundo)
    latido_guardado(mundo, {}, momento=T0 - timedelta(hours=1))
    assert mundo.nucleo.espera(pid).codigo == "sin_latido"
    vinculos.revocar(mundo.base, mundo.usuario.id)
    assert mundo.nucleo.espera(pid).codigo == "sin_navegador"


def test_espera_plataforma_apagada_se_explica_aunque_el_portal_este_listo(mundo):
    mundo.nucleo.config.extension.version_minima = "1.0.0"
    pid = en_cola_magneto(mundo)
    latido_guardado(mundo, {"magneto": {"estado": "listo", "cuenta": "ok"}, "_pausado": False})
    mundo.nucleo.config.plataformas["magneto"].automatica = False
    assert mundo.nucleo.espera(pid).codigo == "plataforma_apagada"


def test_espera_solo_aplica_a_lo_que_esta_en_cola(mundo):
    pid = en_cola_magneto(mundo)
    assert mundo.nucleo.espera(99999) is None
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = 'enviada' WHERE id = ?", (pid,))
    assert mundo.nucleo.espera(pid) is None


# --- opciones en la misma llamada: Magneto y elempleo -------------------------------------------

URL_CLASIFICAR = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-flash-lite-latest:generateContent"
)


def con_cv(mundo, pid):
    cv = mundo.nucleo.archivos / f"cv{pid}.pdf"
    cv.parent.mkdir(parents=True, exist_ok=True)
    cv.write_bytes(b"%PDF")
    mundo.base.cx.execute("UPDATE postulaciones SET cv_archivo = ? WHERE id = ?", (str(cv), pid))
    mundo.base.cx.commit()


@respx.mock
def test_encuesta_de_magneto_la_elige_el_redactor_y_el_consentimiento_va_a_la_card(mundo):
    p, _ = postulacion_magneto(mundo)
    mundo.nucleo.guardar_clave_gemini(mundo.usuario.id, "clave")
    con_cv(mundo, p.id)
    respx.post(URL_CLASIFICAR).mock(return_value=gemini({"campo": None, "formato": "redactar"}))
    ruta = respx.post(URL_REDACTAR).mock(return_value=redactadas({"indice": 1, "opcion": 0}))
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas_magneto()))
    assert ruta.call_count == 1
    assert [(r.pregunta.texto, r.texto, r.origen) for r in resultado.respuestas] == [
        (ENCUESTA_MG[0], "Si", Origen.IA)
    ]
    assert "tratamiento" not in ruta.calls[0].request.content.decode("utf-8")
    assert [r.pregunta.texto for r in resultado.faltan] == [ENCUESTA_MG[1]]  # la decide el usuario
    # Con el consentimiento respondido, la segunda pasada reutiliza la opción sin llamar a la IA
    navegador = mundo.base.cx.execute("SELECT id FROM navegadores").fetchone()[0]
    mundo.nucleo.cola.esperar_usuario(p.id, navegador, T0)
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert mundo.nucleo.responder_pendiente(mundo.usuario.id, pendiente["id"], "Si")
    p, _ = tomar(mundo, p.id, 3)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas_magneto()))
    assert ruta.call_count == 1 and not resultado.faltan
    assert [(r.opcion, r.origen) for r in resultado.respuestas] == [
        (0, Origen.IA), (0, Origen.APRENDIDA),
    ]  # fmt: skip


@respx.mock
def test_opcion_invalida_de_la_ia_va_a_la_card_con_sus_opciones(mundo):
    p, _ = postulacion_magneto(mundo)
    mundo.nucleo.guardar_clave_gemini(mundo.usuario.id, "clave")
    respx.post(URL_CLASIFICAR).mock(return_value=gemini({"campo": None, "formato": "redactar"}))
    respx.post(URL_REDACTAR).mock(return_value=redactadas({"indice": 1, "opcion": 9}))
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas_magneto()[:1]))
    assert [r.pregunta.texto for r in resultado.faltan] == [ENCUESTA_MG[0]]
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert pendiente["tipo"] == "formulario"
    assert json.loads(pendiente["opciones_json"]) == ["Si", "No"]


URL_EE = NUEVAS["elempleo"]


@respx.mock
def test_cuestionario_de_elempleo_se_redacta_en_una_sola_llamada(mundo):
    mundo.vincular()
    mundo.nucleo.guardar_clave_gemini(mundo.usuario.id, "clave")
    id_ = publicar(mundo, "elempleo", "9", URL_EE)
    mundo.nucleo.indice.indexar(T0)
    pid = mundo.nucleo.tocar(mundo.usuario, id_).postulacion.id
    con_cv(mundo, pid)
    p, _ = tomar(mundo, pid)
    abiertas = ["¿Por qué quieres trabajar con nosotros?", "Describe tu experiencia con SQL"]
    for texto in abiertas:
        guardar_en_banco(mundo.base, normalizar_pregunta(texto), REDACTAR, None, T0)
    cerrada = "¿Cuentas con disponibilidad inmediata?"
    guardar_en_banco(mundo.base, normalizar_pregunta(cerrada), REDACTAR, None, T0)
    # Como las lee la extensión en /co/JobOffers/Questionnaires: textarea [n].OpenAnswer
    preguntas = [Pregunta(t, nombre=f"[{n}].OpenAnswer", maximo=2000)
                 for n, t in enumerate(abiertas)]  # fmt: skip
    preguntas.append(Pregunta(cerrada, "opciones", ["Sí", "No"], nombre="[2].IsCloseAnswer"))
    ruta = respx.post(URL_REDACTAR).mock(return_value=redactadas(
        {"indice": 1, "respuesta": "Me interesa su equipo de datos."},
        {"indice": 2, "respuesta": "Uso SQL en proyectos del SENA."},
        {"indice": 3, "opcion": 0},
    ))  # fmt: skip
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert ruta.call_count == 1 and not resultado.faltan and resultado.cv is not None
    assert [(r.texto, r.origen) for r in resultado.respuestas] == [
        ("Me interesa su equipo de datos.", Origen.IA),
        ("Uso SQL en proyectos del SENA.", Origen.IA),
        ("Sí", Origen.IA),
    ]
    assert "(máximo 2000 caracteres)" in ruta.calls[0].request.content.decode("utf-8")


# --- árbitro de pantallas (entender_pagina) ---------------------------------------------------

URL_ENTENDER = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
)


def consulta_de_pantalla():
    peticion = Peticion(
        "desconocida", None, "en", "https://empresa.co/jobs/1?token=SECRETO",
        [Pregunta("City")], [Boton(indice=0, texto="Quick apply")], None,
        Resumen(encabezados=["Backend Engineer"]), None, False,
    )  # fmt: skip
    return Consulta(peticion)


@respx.mock
def test_arbitro_de_pantalla_usa_la_clave_del_usuario_y_valida_el_esquema(mundo):
    pid = en_curso(mundo)
    p = mundo.nucleo.cola.obtener(pid)
    ruta = respx.post(URL_ENTENDER).mock(return_value=gemini({
        "clase": "intermedia",
        "acciones": [{"accion": "borrar", "indice": 0}, {"accion": "avanzar", "indice": 0}],
        "motivo": "Hay que avanzar",
    }))  # fmt: skip
    decision = asyncio.run(mundo.nucleo.arbitrar_pantalla(p, consulta_de_pantalla()))
    assert decision.clase == "intermedia"
    assert [(a.accion, a.indice) for a in decision.acciones] == [("avanzar", 0)]
    assert ruta.call_count == 1
    cuerpo = ruta.calls[0].request.content.decode("utf-8")
    assert "Backend Engineer" in cuerpo and "Quick apply" in cuerpo
    assert "SECRETO" not in cuerpo and "ana@gmail.com" not in cuerpo
    uso = mundo.base.cx.execute("SELECT tarea, ok FROM ia_uso").fetchall()
    assert [tuple(f) for f in uso] == [("entender_pagina", 1)]


def test_arbitro_de_pantalla_sin_clave_devuelve_none(mundo):
    pid = en_curso(mundo, con_ia=False)
    p = mundo.nucleo.cola.obtener(pid)
    assert asyncio.run(mundo.nucleo.arbitrar_pantalla(p, consulta_de_pantalla())) is None


@respx.mock
def test_arbitro_de_pantalla_con_falla_de_la_ia_devuelve_none(mundo):
    pid = en_curso(mundo)
    p = mundo.nucleo.cola.obtener(pid)
    respx.post(url__startswith="https://generativelanguage").mock(
        return_value=gemini({"clase": "inventada"})
    )
    assert asyncio.run(mundo.nucleo.arbitrar_pantalla(p, consulta_de_pantalla())) is None


# --- reparación de un paso fallido (reparar_flujo) --------------------------------------------

URL_REPARAR = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
)


def consulta_de_reparacion():
    return ConsultaReparacion(consulta_de_pantalla().peticion, "clic:postular", "no se encontró")


REPARACION = {
    "clase": "formulario",
    "acciones": [{"accion": "cerrar_modal", "indice": 0}, {"accion": "tocar_todo", "indice": 0}],
    "motivo": "Un aviso tapa el botón",
    "diagnostico": "El aviso de cookies cubre el botón",
}


@respx.mock
def test_reparar_usa_la_clave_del_usuario_y_registra_su_uso(mundo):
    pid = en_curso(mundo)
    p = mundo.nucleo.cola.obtener(pid)
    ruta = respx.post(URL_REPARAR).mock(return_value=gemini(REPARACION))
    r = asyncio.run(mundo.nucleo.reparar_pantalla(p, consulta_de_reparacion()))
    assert [(a.accion, a.indice) for a in r.acciones] == [("cerrar_modal", 0)]
    assert r.diagnostico == "El aviso de cookies cubre el botón"
    cuerpo = ruta.calls[0].request.content.decode("utf-8")
    assert "clic:postular" in cuerpo and "ana@gmail.com" not in cuerpo
    uso = mundo.base.cx.execute("SELECT usuario_id, tarea FROM ia_uso").fetchall()
    assert [tuple(f) for f in uso] == [(mundo.usuario.id, "reparar_flujo")]


@respx.mock
def test_reparar_sin_clave_del_usuario_y_clave_duenio_apagada_es_sin_ia(mundo):
    pid = en_curso(mundo, con_ia=False)
    p = mundo.nucleo.cola.obtener(pid)
    duenio = mundo.nucleo.usuarios.crear(999, "Dueño", T0)
    mundo.nucleo.guardar_clave_gemini(duenio.id, "clave_duenio")
    mundo.nucleo.config.dueno_telegram_id = 999
    ruta = respx.post(url__startswith="https://generativelanguage").mock(
        return_value=gemini(REPARACION)
    )
    assert asyncio.run(mundo.nucleo.reparar_pantalla(p, consulta_de_reparacion())) is None
    assert ruta.call_count == 0  # la clave del dueño no se toca si no se activó


@respx.mock
def test_reparar_con_clave_duenio_usa_la_del_dueno_y_queda_a_su_nombre(mundo):
    pid = en_curso(mundo, con_ia=False)
    p = mundo.nucleo.cola.obtener(pid)
    duenio = mundo.nucleo.usuarios.crear(999, "Dueño", T0)
    mundo.nucleo.guardar_clave_gemini(duenio.id, "clave_duenio")
    mundo.nucleo.config.dueno_telegram_id = 999
    mundo.nucleo.config.autorreparacion.clave_duenio = True
    ruta = respx.post(URL_REPARAR).mock(return_value=gemini(REPARACION))
    r = asyncio.run(mundo.nucleo.reparar_pantalla(p, consulta_de_reparacion()))
    assert r is not None and ruta.call_count == 1
    assert ruta.calls[0].request.headers["x-goog-api-key"] == "clave_duenio"
    uso = mundo.base.cx.execute("SELECT usuario_id, tarea FROM ia_uso").fetchall()
    assert [tuple(f) for f in uso] == [(duenio.id, "reparar_flujo")]


@respx.mock
def test_reparar_prefiere_la_clave_del_usuario_aunque_este_la_del_dueno(mundo):
    pid = en_curso(mundo)
    p = mundo.nucleo.cola.obtener(pid)
    duenio = mundo.nucleo.usuarios.crear(999, "Dueño", T0)
    mundo.nucleo.guardar_clave_gemini(duenio.id, "clave_duenio")
    mundo.nucleo.config.dueno_telegram_id = 999
    mundo.nucleo.config.autorreparacion.clave_duenio = True
    ruta = respx.post(URL_REPARAR).mock(return_value=gemini(REPARACION))
    asyncio.run(mundo.nucleo.reparar_pantalla(p, consulta_de_reparacion()))
    assert ruta.calls[0].request.headers["x-goog-api-key"] == "clave"


# --- dominios barrera y parches en los selectores (6.3) -------------------------------------


def test_vacante_de_un_dominio_barrera_va_al_respaldo_sin_abrir_la_pagina(mundo):
    from buscador_vacantes.asistente.recetas import marcar_barrera, quitar_barrera

    mundo.vincular()
    marcar_barrera(mundo.base, "co.computrabajo.com", "ats_con_cuenta", T0)
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("computrabajo:1"))
    assert toque.camino == Camino.RESPALDO and toque.motivo == "ats_con_cuenta"
    assert toque.postulacion.estado == E.RESPALDO and toque.postulacion.motivo == "ats_con_cuenta"
    # El dueño quita el dominio y la siguiente vacante vuelve a ir sola
    assert quitar_barrera(mundo.base, "co.computrabajo.com")
    otra = mundo.nucleo.tocar(mundo.usuario, id_corto("linkedin:1"))
    assert otra.motivo != "ats_con_cuenta"


def test_los_selectores_llevan_los_parches_antepuestos_y_otra_version(mundo):
    from buscador_vacantes.asistente.recetas import proponer_parche, resultado_parches

    contenido = {"postular": [{"nombre": "aplicar", "accion": "ir", "selector": ["a.viejo"]}]}
    with mundo.base.transaccion() as cx:
        cx.execute(
            "INSERT INTO selectores(plataforma, version, contenido_json, cargado_en) "
            "VALUES ('computrabajo', '2026.10.06-2', ?, 'x')",
            (json.dumps(contenido),),
        )
    assert mundo.nucleo.selectores("computrabajo") == ("2026.10.06-2", contenido)
    pid = proponer_parche(mundo.base, "computrabajo", "aplicar", "a.nuevo", T0)
    version, parchado = mundo.nucleo.selectores("computrabajo")
    assert version == f"2026.10.06-2+p{pid}"
    assert parchado["postular"][0]["selector"] == ["a.nuevo", "a.viejo"]
    # Descartado, vuelven los selectores revisados y la versión original
    resultado_parches(mundo.base, [pid], False, T0)
    assert mundo.nucleo.selectores("computrabajo") == ("2026.10.06-2", contenido)
    assert mundo.nucleo.selectores("magneto") is None


# --- nivel Máximo: calidad de las respuestas y carta (6.8) --------------------------------------

URL_REVISOR = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
)


def en_curso_maximo(mundo, con_ia=True):
    mundo.nucleo.preferencias.fijar_nivel_ia(mundo.usuario.id, "maximo")  # antes de encolar
    return en_curso(mundo, con_ia)


def respuestas_revisadas(mundo, pid):
    filas = mundo.base.cx.execute(
        "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? "
        "AND paso = 'respuestas_revisadas'",
        (pid,),
    ).fetchall()
    return [f["detalle"] for f in filas]


@respx.mock
def test_maximo_redacta_dos_veces_y_el_revisor_final_ajusta_antes_de_enviar(mundo):
    pid = en_curso_maximo(mundo)
    p, _ = tomar(mundo, pid)
    redactor = respx.post(URL_REDACTAR).mock(side_effect=[
        redactadas(
            {"indice": 1, "respuesta": "Estudio ADSO en el SENA."},
            {"indice": 2, "respuesta": "Quiero aplicar Python en un equipo real."},
            {"indice": 3, "respuesta": "Hice un inventario en Django."},
        ),
        redactadas(  # segunda versión, solo de las largas: motivación y proyecto
            {"indice": 1, "respuesta": "Busco crecer aplicando Python con gente más senior."},
            {"indice": 2, "respuesta": "Construí un inventario con Django y SQL."},
        ),
    ])  # fmt: skip
    revisor = respx.post(URL_REVISOR).mock(return_value=gemini({"veredictos": [
        {"indice": 1, "veredicto": "ok"},
        {"indice": 2, "veredicto": "elegir", "eleccion": 2},
        {"indice": 3, "veredicto": "corregir", "texto": "Hice un inventario con Django y SQL."},
    ]}))  # fmt: skip
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert redactor.call_count == 2 and revisor.call_count == 1
    assert not resultado.faltan
    assert [r.valor for r in resultado.respuestas] == [
        "Estudio ADSO en el SENA.",
        "Busco crecer aplicando Python con gente más senior.",
        "Hice un inventario con Django y SQL.",
        "1300000",
    ]
    assert respuestas_revisadas(mundo, pid) == ["2"]
    # De las respuestas, el revisor solo ve las redactadas por la IA: no el dato simple (salario)
    # ni el contacto del usuario
    enviado = revisor.calls[0].request.content.decode("utf-8")
    assert "Pregunta: ¿Cuál es tu aspiración salarial" not in enviado
    assert "Respuesta: 1300000" not in enviado
    assert "ana@gmail.com" not in enviado and "3105551234" not in enviado
    assert "Estudio ADSO" in enviado and "Segunda versión" in enviado


@respx.mock
def test_maximo_dato_dudoso_del_revisor_se_pregunta_en_la_card(mundo):
    pid = en_curso_maximo(mundo)
    p, _ = tomar(mundo, pid)
    respx.post(URL_REDACTAR).mock(side_effect=[
        redactadas({"indice": 1, "respuesta": "Tengo tres años de experiencia en Python."}),
        redactadas({"indice": 1, "respuesta": "Llevo tres años programando en Python."}),
    ])  # fmt: skip
    respx.post(URL_REVISOR).mock(return_value=gemini({"veredictos": [{
        "indice": 1, "veredicto": "preguntar",
        "faltan": [{"pregunta": "¿Cuántos años de experiencia tienes?",
                    "sugerencias": ["1 año", "Sin experiencia"]}],
    }]}))  # fmt: skip
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, [Pregunta(ABIERTAS[1])]))
    assert [r.pregunta.texto for r in resultado.faltan] == [ABIERTAS[1]]
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert (pendiente["pregunta"], pendiente["tipo"]) == (
        "¿Cuántos años de experiencia tienes?", "dato"
    )
    assert respuestas_revisadas(mundo, pid) == ["1"]


@respx.mock
def test_maximo_nunca_afirma_un_requisito_de_la_vacante_que_el_perfil_no_tiene(mundo):
    pid = en_curso_maximo(mundo)
    p, _ = tomar(mundo, pid)
    mundo.base.cx.execute(
        "UPDATE vacantes SET requisitos_json = ? WHERE id_corto = ?",
        (json.dumps({"requisitos": {"obligatorios": ["Python", "Kubernetes"], "deseables": []}}),
         p.id_corto),
    )  # fmt: skip
    mundo.base.cx.commit()
    redactor = respx.post(URL_REDACTAR).mock(side_effect=[
        redactadas({"indice": 1, "respuesta": "Domino Kubernetes y Python."}),
        redactadas({"indice": 1, "respuesta": "He operado clústeres de Kubernetes."}),
    ])  # fmt: skip
    respx.post(URL_REVISOR).mock(return_value=gemini({"veredictos": []}))
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, [Pregunta(ABIERTAS[1])]))
    enviado = redactor.calls[0].request.content.decode("utf-8")
    assert "Kubernetes (obligatorio)" in enviado and "Python (obligatorio)" in enviado
    assert [r.pregunta.texto for r in resultado.faltan] == [ABIERTAS[1]]  # se pregunta al usuario
    assert not resultado.respuestas


@respx.mock
def test_normal_no_hace_doble_redaccion_ni_revisa(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    redactor = respx.post(URL_REDACTAR).mock(return_value=redactadas(
        {"indice": 1, "respuesta": "Estudio ADSO en el SENA."},
        {"indice": 2, "respuesta": "Quiero aplicar Python."},
        {"indice": 3, "respuesta": "Hice un inventario."},
    ))  # fmt: skip
    revisor = respx.post(URL_REVISOR).mock(return_value=gemini({"veredictos": []}))
    asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert redactor.call_count == 1 and revisor.call_count == 0
    assert respuestas_revisadas(mundo, pid) == []


def archivo(texto, obligatoria=True):
    return Pregunta(texto, "archivo", obligatoria=obligatoria)


def pdf_guardado(mundo, tipo, contenido=b"%PDF-1.4 del usuario"):
    return mundo.nucleo.documentos.guardar(mundo.usuario, tipo, tipo, contenido, T0)


@respx.mock
def test_maximo_adjunta_una_carta_en_pdf_si_es_opcional(mundo):
    pid = en_curso_maximo(mundo)
    p, _ = tomar(mundo, pid)
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini(
        {"carta": "Me interesa la vacante y estudio Ingeniería de Sistemas."}
    ))
    paquete = asyncio.run(
        mundo.nucleo.documentos_pantalla(p, [archivo("Cover letter (optional)", False)])
    )
    nombre, contenido = paquete.documentos["carta"]
    assert set(paquete.documentos) == {"carta"} and not paquete.faltan
    assert nombre == "Carta_Ana_Perez.pdf" and contenido.startswith(b"%PDF")
    # Se reutiliza: una segunda pantalla con el mismo campo no vuelve a llamar a la IA
    asyncio.run(mundo.nucleo.documentos_pantalla(p, [archivo("Carta de presentación", False)]))
    assert ruta.call_count == 1


@respx.mock
def test_normal_deja_vacia_la_carta_opcional(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    ruta = respx.post(URL_REDACTAR).mock(return_value=gemini({"carta": "Hola."}))
    paquete = asyncio.run(
        mundo.nucleo.documentos_pantalla(p, [archivo("Cover letter (optional)", False)])
    )
    assert paquete.documentos == {} and not paquete.faltan and ruta.call_count == 0


@respx.mock
def test_la_carta_obligatoria_se_redacta_en_cualquier_nivel_y_el_cv_no_es_carta(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    respx.post(URL_REDACTAR).mock(return_value=gemini({"carta": "Me interesa la vacante."}))
    sin_carta = asyncio.run(mundo.nucleo.documentos_pantalla(p, [archivo("Resume/CV")]))
    assert sin_carta.documentos == {}
    paquete = asyncio.run(mundo.nucleo.documentos_pantalla(p, [archivo("Cover letter")]))
    assert set(paquete.documentos) == {"carta"}


def test_carta_sin_ia_usa_el_mensaje_basico_con_datos_del_perfil(mundo):
    pid = en_curso_maximo(mundo, con_ia=False)
    p, _ = tomar(mundo, pid)
    paquete = asyncio.run(mundo.nucleo.documentos_pantalla(p, [archivo("Cover letter", True)]))
    assert paquete.documentos["carta"][1].startswith(b"%PDF")


@respx.mock
def test_el_certificado_de_notas_del_usuario_va_en_el_campo_de_notas(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    pdf_guardado(mundo, "certificado_notas", b"%PDF-1.4 mis notas")
    ruta = respx.post(url__startswith="https://generativelanguage").mock(
        return_value=gemini({})
    )
    transcript = "Please upload a copy of your unofficial university transcripts."
    paquete = asyncio.run(
        mundo.nucleo.documentos_pantalla(p, [archivo("Resume/CV"), archivo(transcript)])
    )
    assert set(paquete.documentos) == {"certificado_notas"} and not paquete.faltan
    nombre, contenido = paquete.documentos["certificado_notas"]
    assert nombre == "Notas_Ana_Perez.pdf" and contenido == b"%PDF-1.4 mis notas"
    assert ruta.call_count == 0 and mundo.nucleo.pendientes(mundo.usuario.id) == []


@respx.mock
def test_la_carta_guardada_por_el_usuario_manda_sobre_la_redactada(mundo):
    pid = en_curso_maximo(mundo)
    p, _ = tomar(mundo, pid)
    pdf_guardado(mundo, "carta", b"%PDF-1.4 mi carta")
    ruta = respx.post(url__startswith="https://generativelanguage").mock(
        return_value=gemini({"carta": "No debería usarse."})
    )
    paquete = asyncio.run(mundo.nucleo.documentos_pantalla(p, [archivo("Cover letter", False)]))
    assert paquete.documentos["carta"][1] == b"%PDF-1.4 mi carta" and ruta.call_count == 0


def test_documento_obligatorio_sin_guardar_queda_pendiente_y_la_postulacion_espera(mundo):
    pid = en_curso(mundo)
    p, navegador = tomar(mundo, pid)
    notas = archivo("Please upload a copy of your unofficial university transcripts.")
    paquete = asyncio.run(mundo.nucleo.documentos_pantalla(p, [archivo("Resume/CV"), notas]))
    assert paquete.documentos == {} and [q.texto for q in paquete.faltan] == [notas.texto]
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert (pendiente["tipo"], pendiente["campo"], pendiente["postulacion_id"]) == (
        "documento", "certificado_notas", pid
    )
    aviso = {"tipo": "preguntas_pendientes", "usuario_id": mundo.usuario.id, "postulacion_id": pid}
    assert aviso in mundo.eventos
    # Otra pasada de la misma pantalla no repite la pregunta
    asyncio.run(mundo.nucleo.documentos_pantalla(p, [notas]))
    assert len(mundo.nucleo.pendientes(mundo.usuario.id)) == 1
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    # Con el documento guardado la postulación vuelve a la cola
    pdf_guardado(mundo, "certificado_notas")
    assert mundo.nucleo.documento_recibido(mundo.usuario.id, pendiente["id"]) is True
    assert mundo.nucleo.cola.obtener(pid).estado == E.EN_COLA
    assert mundo.nucleo.pendientes(mundo.usuario.id) == []
    assert mundo.nucleo.documento_recibido(mundo.usuario.id, pendiente["id"]) is False


def test_dejar_el_documento_obligatorio_manda_la_vacante_al_respaldo(mundo):
    pid = en_curso(mundo)
    p, navegador = tomar(mundo, pid)
    asyncio.run(mundo.nucleo.documentos_pantalla(p, [archivo("Transcript")]))
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert mundo.nucleo.documento_a_respaldo(mundo.usuario.id, pendiente["id"]) == pid
    assert mundo.nucleo.cola.obtener(pid).estado == E.RESPALDO
    assert mundo.nucleo.pendientes(mundo.usuario.id) == []
    assert mundo.nucleo.documento_a_respaldo(mundo.usuario.id, pendiente["id"]) is None


# --- esquema anticipado (7.3) ---------------------------------------------------------------


def test_esquema_de_la_vacante_se_guarda_y_los_campos_mal_formados_se_ignoran(mundo):
    mundo.nucleo.indice.indexar(T0)
    corta = id_corto("computrabajo:1")
    assert mundo.nucleo.indice.obtener(corta).esquema is None
    mundo.nucleo.indice.guardar_esquema(corta, [
        {"texto": "¿Cuál es tu aspiración salarial?", "nombre": "q1", "maximo": 20},
        {"nombre": "sin_texto"},  # mal formado: no tiene etiqueta
        {"texto": "Ciudad", "tipo": "texto", "obligatoria": False},
    ])  # fmt: skip
    preguntas = mundo.nucleo.esquema_de(mundo.nucleo.indice.obtener(corta))
    assert [(p.texto, p.nombre, p.obligatoria) for p in preguntas] == [
        ("¿Cuál es tu aspiración salarial?", "q1", True), ("Ciudad", None, False),
    ]
    mundo.nucleo.indice.guardar_esquema(corta, None)
    assert mundo.nucleo.indice.obtener(corta).esquema is None
    assert mundo.nucleo.esquema_de(None) == []


def test_anticipar_el_esquema_resuelve_todo_y_deja_las_respuestas_guardadas(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    mundo.nucleo.indice.guardar_esquema(p.id_corto, [
        {"texto": "¿Cuál es tu aspiración salarial?", "nombre": "q_salario"},
        {"texto": "Resume", "tipo": "archivo"},
    ])  # fmt: skip
    vacante = mundo.nucleo.indice.obtener(p.id_corto)
    assert asyncio.run(mundo.nucleo.anticipar_esquema(p, vacante)) is True
    assert mundo.nucleo.esquema_resuelto(p) == {"q_salario": "1300000"}  # el CV va aparte
    assert mundo.nucleo.pendientes(mundo.usuario.id) == []


def test_anticipar_el_esquema_con_un_dato_que_falta_deja_la_pregunta_y_devuelve_false(mundo):
    pid = en_curso(mundo, con_ia=False)
    p, _ = tomar(mundo, pid)
    mundo.nucleo.indice.guardar_esquema(p.id_corto, [
        {"texto": "¿Cuál es tu aspiración salarial?", "nombre": "q_salario"},
        {"texto": "¿Tienes experiencia con Docker?", "nombre": "q_docker"},
    ])  # fmt: skip
    vacante = mundo.nucleo.indice.obtener(p.id_corto)
    assert asyncio.run(mundo.nucleo.anticipar_esquema(p, vacante)) is False
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert pendiente["pregunta"] == "¿Tienes experiencia con Docker?"
    assert mundo.nucleo.esquema_resuelto(p) == {"q_salario": "1300000"}


def test_vacante_sin_esquema_se_da_por_resuelta(mundo):
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    vacante = mundo.nucleo.indice.obtener(p.id_corto)
    assert asyncio.run(mundo.nucleo.anticipar_esquema(p, vacante)) is True
    assert mundo.nucleo.esquema_resuelto(p) == {}


# --- destino de LinkedIn: acortadores y esquema del destino (postular-linkedin, 4.1) ---------


@respx.mock
def test_resolver_redireccion_sigue_solo_los_acortadores_conocidos(mundo):
    corto = respx.get("https://grnh.se/abc").mock(
        return_value=httpx.Response(
            301, headers={"location": "https://job-boards.greenhouse.io/prueba/jobs/1"}
        )
    )
    final = respx.get("https://job-boards.greenhouse.io/prueba/jobs/1")
    assert asyncio.run(mundo.nucleo.resolver_redireccion("https://grnh.se/abc")) == (
        "https://job-boards.greenhouse.io/prueba/jobs/1"
    )
    assert corto.called and not final.called  # el destino no se pide: solo se clasifica
    ajeno = respx.get("https://acme.com/empleo")
    assert asyncio.run(mundo.nucleo.resolver_redireccion("https://acme.com/empleo")) == (
        "https://acme.com/empleo"
    )
    assert not ajeno.called  # un host que no es acortador nunca se pide


@respx.mock
def test_resolver_redireccion_encadena_saltos_y_tolera_errores(mundo):
    respx.get("https://bit.ly/x").mock(
        return_value=httpx.Response(302, headers={"location": "https://ai-job.link/y"})
    )
    respx.get("https://ai-job.link/y").mock(
        return_value=httpx.Response(302, headers={"location": "https://wa.me/573001112233"})
    )
    assert asyncio.run(mundo.nucleo.resolver_redireccion("https://bit.ly/x")) == (
        "https://wa.me/573001112233"
    )
    respx.get("https://t.co/z").mock(side_effect=httpx.ConnectTimeout("lenta"))
    assert asyncio.run(mundo.nucleo.resolver_redireccion("https://t.co/z")) == "https://t.co/z"


@respx.mock
def test_preparar_esquema_lee_el_formulario_lo_guarda_y_lo_resuelve(mundo):
    datos = json.loads((FIXTURES.parent / "ats" / "greenhouse_trabajo.json").read_text("utf-8"))
    respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/4100100").mock(
        return_value=httpx.Response(200, json=datos)
    )
    pid = en_curso(mundo, con_ia=False)
    p, _ = tomar(mundo, pid)
    url = "https://job-boards.greenhouse.io/prueba/jobs/4100100"
    # Faltan datos del usuario (certificado, promedio…): la card los pregunta
    assert asyncio.run(mundo.nucleo.preparar_esquema(p, "greenhouse", url)) is False
    esquema = mundo.nucleo.indice.obtener(p.id_corto).esquema
    assert "question_9001" in {c["nombre"] for c in esquema}
    assert mundo.nucleo.pendientes(mundo.usuario.id)


@respx.mock
def test_preparar_esquema_sin_lector_o_con_api_caida_deja_el_motor_leer_la_pagina(mundo):
    respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/4100100").mock(
        return_value=httpx.Response(503)
    )
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    mundo.nucleo.indice.guardar_esquema(p.id_corto, [{"texto": "Vieja", "nombre": "q"}])
    url = "https://job-boards.greenhouse.io/prueba/jobs/4100100"
    assert asyncio.run(mundo.nucleo.preparar_esquema(p, "greenhouse", url)) is True
    assert mundo.nucleo.indice.obtener(p.id_corto).esquema is None  # no deja el de otro destino
    assert asyncio.run(mundo.nucleo.preparar_esquema(p, "propio", "https://acme.com/e")) is True


# --- camino de LinkedIn al tocar ⚡ (postular-linkedin, 4.2) --------------------------------------

ID_LI = id_corto("linkedin:1")
DESTINO_ACME = Destino("https://acme.com/empleo/7", "propio")


def linkedin_listo(mundo, *, aceptar=True):
    """Navegador vinculado, LinkedIn encendida y, si se pide, el riesgo aceptado."""
    mundo.vincular()
    mundo.nucleo.config.plataformas["linkedin"].automatica = True
    if aceptar:
        version = mundo.nucleo.config.linkedin.riesgo_version
        mundo.nucleo.linkedin.aceptar(mundo.usuario.id, version, T0)


def permiso_externo(mundo, estado="listo"):
    mundo.base.cx.execute(
        "UPDATE navegadores SET portales_json = ?", (json.dumps({"externa": {"estado": estado}}),)
    )
    mundo.base.cx.commit()


def test_linkedin_sin_aceptar_ofrece_el_riesgo_y_no_encola_nada(mundo):
    linkedin_listo(mundo, aceptar=False)
    toque = mundo.nucleo.tocar(mundo.usuario, ID_LI)
    assert (toque.camino, toque.motivo) == (Camino.ACEPTAR_RIESGO, "linkedin_sin_aceptar")
    assert toque.postulacion is None
    assert mundo.nucleo.cola.de_usuario(mundo.usuario.id, ID_LI) is None


def test_aceptar_el_riesgo_guarda_version_y_fecha_y_encola(mundo):
    linkedin_listo(mundo, aceptar=False)
    toque = mundo.nucleo.aceptar_riesgo_linkedin(mundo.usuario, ID_LI)
    assert toque.camino == Camino.AUTOMATICA and toque.postulacion.estado == E.EN_COLA
    estado = mundo.nucleo.linkedin.estado(mundo.usuario.id)
    assert (estado.version, estado.aceptado_en) == (1, T0)
    assert estado.sencilla and estado.externas


def test_una_version_nueva_del_texto_del_riesgo_se_vuelve_a_pedir(mundo):
    linkedin_listo(mundo)
    mundo.nucleo.config.linkedin.riesgo_version = 2
    assert mundo.nucleo.tocar(mundo.usuario, ID_LI).camino == Camino.ACEPTAR_RIESGO


def test_solo_paquete_va_al_respaldo_y_la_misma_vacante_vuelve_a_ofrecer_el_riesgo(mundo):
    linkedin_listo(mundo, aceptar=False)
    toque = mundo.nucleo.solo_paquete_linkedin(mundo.usuario, ID_LI)
    assert (toque.camino, toque.motivo) == (Camino.RESPALDO, "linkedin_sin_aceptar")
    assert toque.postulacion.estado == E.RESPALDO
    otra = mundo.nucleo.tocar(mundo.usuario, ID_LI)  # no queda como «ya la tienes»
    assert (otra.camino, otra.postulacion.id) == (Camino.ACEPTAR_RIESGO, toque.postulacion.id)
    aceptada = mundo.nucleo.aceptar_riesgo_linkedin(mundo.usuario, ID_LI)
    assert aceptada.camino == Camino.AUTOMATICA  # el mismo registro vuelve a la cola
    assert aceptada.postulacion.id == toque.postulacion.id
    assert aceptada.postulacion.estado == E.EN_COLA


def test_con_los_dos_interruptores_apagados_va_al_respaldo(mundo):
    linkedin_listo(mundo)
    mundo.nucleo.linkedin.fijar(mundo.usuario.id, sencilla=False, externas=False)
    toque = mundo.nucleo.tocar(mundo.usuario, ID_LI)
    assert (toque.camino, toque.motivo) == (Camino.RESPALDO, "linkedin_apagado")


def test_con_un_solo_interruptor_apagado_se_encola_y_se_decide_al_conocer_el_tipo(mundo):
    linkedin_listo(mundo)
    mundo.nucleo.linkedin.fijar(mundo.usuario.id, externas=False)
    assert mundo.nucleo.tocar(mundo.usuario, ID_LI).camino == Camino.AUTOMATICA


def test_el_destino_guardado_se_clasifica_al_tocar(mundo):
    linkedin_listo(mundo)
    permiso_externo(mundo)
    guardar(mundo.base, ID_LI, Destino("https://acme.wd3.myworkdayjobs.com/x/job/1", "workday",
                                       "ats_con_cuenta"), T0)
    toque = mundo.nucleo.tocar(mundo.usuario, ID_LI)
    assert (toque.camino, toque.motivo) == (Camino.RESPALDO, "ats_con_cuenta")


def test_el_destino_guardado_respeta_las_externas_apagadas_y_el_permiso(mundo):
    linkedin_listo(mundo)
    guardar(mundo.base, ID_LI, DESTINO_ACME, T0)
    sin_permiso = mundo.nucleo.tocar(mundo.usuario, ID_LI)
    assert (sin_permiso.camino, sin_permiso.motivo) == (Camino.RESPALDO, "sin_permiso_externo")
    mundo.base.cx.execute("DELETE FROM postulaciones")
    permiso_externo(mundo, "sin_permiso")  # la extensión lo reporta, pero sin concederlo
    assert mundo.nucleo.tocar(mundo.usuario, ID_LI).motivo == "sin_permiso_externo"
    mundo.base.cx.execute("DELETE FROM postulaciones")
    permiso_externo(mundo)
    mundo.nucleo.linkedin.fijar(mundo.usuario.id, externas=False)
    assert mundo.nucleo.tocar(mundo.usuario, ID_LI).motivo == "linkedin_apagado"
    mundo.base.cx.execute("DELETE FROM postulaciones")
    mundo.nucleo.linkedin.fijar(mundo.usuario.id, externas=True)
    assert mundo.nucleo.tocar(mundo.usuario, ID_LI).camino == Camino.AUTOMATICA


def test_un_destino_viejo_se_ignora_y_se_abre_linkedin_de_nuevo(mundo):
    linkedin_listo(mundo)
    guardar(mundo.base, ID_LI, Destino("https://wa.me/573001112233", "propio", "x"),
            T0 - timedelta(days=8))
    assert mundo.nucleo.tocar(mundo.usuario, ID_LI).camino == Camino.AUTOMATICA


def test_pausar_linkedin_guarda_las_horas_de_la_configuracion(mundo):
    linkedin_listo(mundo)
    assert mundo.nucleo.pausar_linkedin(mundo.usuario.id) == T0 + timedelta(hours=24)
    assert mundo.nucleo.linkedin.pausado_hasta(mundo.usuario.id, T0) is not None


def retenida_de_linkedin(mundo):
    """Postulación de LinkedIn con destino guardado, retenida mientras se resuelve de antemano."""
    linkedin_listo(mundo)
    permiso_externo(mundo)
    return mundo.nucleo.tocar(mundo.usuario, ID_LI).postulacion


@respx.mock
def test_anticipar_destino_confirma_que_sigue_abierta_y_deja_salir_la_postulacion(mundo):
    guardar(mundo.base, ID_LI, DESTINO_ACME, T0 - timedelta(days=1))
    respx.get(URL_LI).mock(
        return_value=httpx.Response(200, text=(FIXTURES / "linkedin.html").read_text("utf-8"))
    )
    p = retenida_de_linkedin(mundo)
    vacante = mundo.nucleo.indice.obtener(ID_LI)
    assert mundo.nucleo.requiere_anticipo(p, vacante)
    mundo.nucleo.cola.retener(p.id, T0)
    assert asyncio.run(mundo.nucleo.anticipar_destino(p, vacante)) == "resuelto"
    fila = mundo.base.cx.execute("SELECT ultima_vez FROM destinos_linkedin").fetchone()
    assert fila["ultima_vez"] == a_texto(T0)  # el uso queda anotado


@respx.mock
def test_anticipar_destino_de_una_vacante_cerrada_la_cierra_sin_abrir_nada(mundo):
    guardar(mundo.base, ID_LI, DESTINO_ACME, T0 - timedelta(days=1))
    respx.get(URL_LI).mock(
        return_value=httpx.Response(
            200, text="<html><body><main><h1>No longer accepting applications</h1></main></body>"
        )
    )
    p = retenida_de_linkedin(mundo)
    vacante = mundo.nucleo.indice.obtener(ID_LI)
    mundo.nucleo.cola.retener(p.id, T0)
    assert asyncio.run(mundo.nucleo.anticipar_destino(p, vacante)) == "cerrada"
    assert mundo.nucleo.cola.obtener(p.id).estado == E.VACANTE_CERRADA


@respx.mock
def test_anticipar_destino_lee_el_formulario_del_destino_y_pregunta_lo_que_falta(mundo):
    destino = "https://job-boards.greenhouse.io/prueba/jobs/4100100"
    guardar(mundo.base, ID_LI, Destino(destino, "greenhouse"), T0 - timedelta(days=1))
    respx.get(URL_LI).mock(
        return_value=httpx.Response(200, text=(FIXTURES / "linkedin.html").read_text("utf-8"))
    )
    datos = json.loads((FIXTURES.parent / "ats" / "greenhouse_trabajo.json").read_text("utf-8"))
    respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/4100100").mock(
        return_value=httpx.Response(200, json=datos)
    )
    p = retenida_de_linkedin(mundo)
    vacante = mundo.nucleo.indice.obtener(ID_LI)
    mundo.nucleo.cola.retener(p.id, T0)
    assert asyncio.run(mundo.nucleo.anticipar_destino(p, vacante)) == "faltan"
    assert mundo.nucleo.pendientes(mundo.usuario.id)


def test_sin_destino_guardado_el_anticipo_es_el_del_esquema_de_la_vacante(mundo):
    linkedin_listo(mundo)
    p = mundo.nucleo.tocar(mundo.usuario, ID_LI).postulacion
    vacante = mundo.nucleo.indice.obtener(ID_LI)
    assert not mundo.nucleo.requiere_anticipo(p, vacante)
    assert asyncio.run(mundo.nucleo.anticipar_destino(p, vacante)) == "resuelto"


# --- vigía: ensayo diario de cada plataforma en el navegador del dueño -------------------------


def vigia_listo(mundo, hora="10:00"):
    """El dueño es el usuario del mundo, con navegador vinculado y selectores cargados."""
    mundo.nucleo.config.dueno_telegram_id = mundo.usuario.telegram_id
    mundo.nucleo.config.vigia.activo = True
    mundo.nucleo.config.vigia.hora = hora
    mundo.nucleo.cargar_selectores()
    mundo.nucleo.indice.indexar(T0)
    mundo.vincular()
    return mundo.nucleo


def test_el_vigia_encola_un_ensayo_por_plataforma_y_una_sola_vez_al_dia(mundo):
    nucleo = vigia_listo(mundo)
    [p] = nucleo.programar_vigia(T0)  # solo Computrabajo tiene una vacante en el índice
    assert p.tipo == "vigia" and p.plataforma == CT and p.estado == E.EN_COLA
    assert p.usuario_id == mundo.usuario.id and p.origen == "vigia"
    assert nucleo.en_ensayo(p)  # el vigía nunca envía
    assert nucleo.programar_vigia(T0 + timedelta(minutes=1)) == []
    # Al otro día no hay otra vacante distinta: no repite la de ayer
    assert nucleo.programar_vigia(T0 + timedelta(days=1)) == []


def test_el_vigia_respeta_la_hora_la_ventana_y_el_interruptor(mundo):
    nucleo = vigia_listo(mundo, hora="05:30")  # T0 son las 10:00: fuera de la ventana de 3 h
    assert nucleo.programar_vigia(T0) == []
    assert nucleo.programar_vigia(T0 - timedelta(hours=9)) == []  # 20:00 de ayer en Bogotá
    nucleo.config.vigia.hora = "09:00"
    assert len(nucleo.programar_vigia(T0)) == 1  # 10:00, a una hora de la prevista
    nucleo.config.vigia.activo = False
    assert nucleo.programar_vigia(T0 + timedelta(days=1)) == []


def test_el_vigia_necesita_el_navegador_del_dueno(mundo):
    nucleo = mundo.nucleo
    nucleo.config.vigia.activo = True
    nucleo.config.vigia.hora = "10:00"
    nucleo.cargar_selectores()
    nucleo.config.dueno_telegram_id = mundo.usuario.telegram_id
    assert nucleo.programar_vigia(T0) == []  # sin navegador vinculado
    nucleo.config.dueno_telegram_id = 5
    mundo.vincular()
    assert nucleo.programar_vigia(T0) == []  # el dueño no está registrado


def test_el_vigia_elige_una_vacante_reciente_abierta_y_que_el_dueno_no_tenga(mundo):
    nucleo = vigia_listo(mundo)
    corto = id_corto("computrabajo:1")
    uid = mundo.usuario.id
    assert nucleo.vacante_para_vigia(uid, CT, T0).id_corto == corto
    # Ya la tiene en la cola
    nucleo.cola.encolar(uid, corto, CT, T0)
    assert nucleo.vacante_para_vigia(uid, CT, T0) is None
    with mundo.base.transaccion() as cx:
        cx.execute("DELETE FROM postulaciones")
        cx.execute("UPDATE vacantes SET estado_pagina = 'cerrada' WHERE id_corto = ?", (corto,))
    assert nucleo.vacante_para_vigia(uid, CT, T0) is None  # cerrada
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE vacantes SET estado_pagina = 'ok' WHERE id_corto = ?", (corto,))
    assert nucleo.vacante_para_vigia(uid, CT, T0 + timedelta(days=4)) is None  # muy vieja
    assert nucleo.vacante_para_vigia(uid, CT, T0 + timedelta(days=2)).id_corto == corto
    assert nucleo.vacante_para_vigia(uid, "magneto", T0) is None  # sin vacantes de otra plataforma


def test_una_postulacion_real_pasa_antes_que_el_vigia_y_lo_reemplaza_si_es_la_misma(mundo):
    nucleo = vigia_listo(mundo)
    [vigia] = nucleo.programar_vigia(T0)
    assert nucleo.cola.de_usuario(mundo.usuario.id, vigia.id_corto) is None  # no cuenta como suya
    toque = nucleo.tocar(mundo.usuario, vigia.id_corto)
    assert toque.camino == Camino.AUTOMATICA and toque.postulacion.tipo == "postular"
    assert nucleo.cola.obtener(vigia.id) is None  # el ensayo cedió el lugar
    # Con las dos en la cola, la real sale primero
    nucleo.config.vigia.hora = "10:00"
    publicar(mundo, "computrabajo", "2", "https://co.computrabajo.com/ofertas-de-trabajo/oferta-2")
    otro = nucleo.cola.encolar_vigia(
        mundo.usuario.id, id_corto("computrabajo:2"), CT, T0 - timedelta(minutes=5)
    )
    assert otro is not None
    siguiente = nucleo.cola.siguiente(mundo.usuario.id, {CT}, T0)
    assert siguiente.id == toque.postulacion.id


@pytest.mark.parametrize(
    ("estado", "motivo", "resultado", "en_ensayo"),
    [
        (E.ENSAYADA, "boton:Aplicar", "ok", False),
        (E.FORMULARIO_DESCONOCIDO, "no apareció el botón", "fallo", True),
        (E.FALLIDA, None, "fallo", True),
        (E.FORMULARIO_DESCONOCIDO, "ats_con_cuenta", "omitida", False),
        (E.BLOQUEADA, "captcha_visible", "bloqueada", False),
        (E.VACANTE_CERRADA, None, "omitida", False),
        (E.RESPALDO, "navegador_desconectado", "omitida", False),
    ],
)
def test_el_resultado_del_vigia_solo_pone_en_ensayo_lo_que_fallo_sin_reparar(
    mundo, estado, motivo, resultado, en_ensayo
):
    nucleo = vigia_listo(mundo)
    [p] = nucleo.programar_vigia(T0)
    assert nucleo.cerrar_vigia(p, estado, motivo) == resultado
    assert (CT in nucleo.preferencias.plataformas_en_ensayo([])) is en_ensayo


def test_un_ensayo_del_vigia_que_se_reparo_no_pone_la_plataforma_en_ensayo(mundo):
    nucleo = vigia_listo(mundo)
    [p] = nucleo.programar_vigia(T0)
    with mundo.base.transaccion() as cx:
        nucleo.cola.paso(cx, p.id, "respaldo_generico", T0, detalle="paso 2")
    assert nucleo.cerrar_vigia(p, E.ENSAYADA, "boton:Aplicar") == "reparado"
    assert nucleo.preferencias.plataformas_en_ensayo([]) == {}


AVAL = ("¿Cuentas con el aval por parte de tu institución educativa para iniciar proceso de "
        "prácticas de inmediato?")  # fmt: skip


@respx.mock
def test_pregunta_de_si_o_no_en_texto_queda_pendiente_con_botones_y_recuerda_el_aval(mundo):
    pid = en_curso(mundo, con_ia=False)
    p, navegador = tomar(mundo, pid)
    preguntas = [
        Pregunta(AVAL),
        Pregunta("¿Por qué te interesa esta vacante?"),
        Pregunta("¿Tienes licencia de conducción?", "opciones", ["Sí", "No", "En trámite"]),
    ]
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, preguntas))
    assert len(resultado.faltan) == 3
    pendientes = {x["pregunta"]: x for x in mundo.nucleo.pendientes(mundo.usuario.id)}
    aval = pendientes[AVAL]
    assert (aval["tipo"], json.loads(aval["opciones_json"])) == ("si_no", ["Sí", "No"])
    assert aval["campo"] == "aval_institucion"
    abierta = pendientes["¿Por qué te interesa esta vacante?"]
    assert (abierta["tipo"], json.loads(abierta["opciones_json"])) == ("formulario", [])
    licencia = pendientes["¿Tienes licencia de conducción?"]
    assert json.loads(licencia["opciones_json"]) == ["Sí", "No", "En trámite"]
    assert licencia["tipo"] == "formulario"  # con opciones del portal no cambia
    # Responder el aval lo guarda en el cuestionario y se usa con otra redacción de la pregunta
    mundo.nucleo.cola.esperar_usuario(pid, navegador, T0)
    mundo.nucleo.responder_pendiente(mundo.usuario.id, aval["id"], "Sí")
    assert mundo.nucleo.datos_usuario(mundo.usuario.id).cuestionario["aval_institucion"] == "Sí"
    otra = Pregunta("¿Tienes aval de tu universidad para hacer prácticas?")
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, [otra]))
    assert not resultado.faltan and resultado.respuestas[0].texto == "Sí"


@respx.mock
def test_dato_de_si_o_no_sin_sugerencias_recibe_los_botones(mundo):
    pid = en_curso(mundo)
    mundo.nucleo._crear_pendientes(
        mundo.usuario.id, pid,
        [Respuesta(Pregunta("Motivación"), falta=True,
                   datos=[DatoFaltante(pregunta="¿Tienes moto propia?", sugerencias=[]),
                          DatoFaltante(pregunta="¿Dónde vives?", sugerencias=[])])],
    )  # fmt: skip
    por_pregunta = {x["pregunta"]: x for x in mundo.nucleo.pendientes(mundo.usuario.id)}
    moto = por_pregunta["¿Tienes moto propia?"]
    assert (moto["tipo"], json.loads(moto["opciones_json"])) == ("dato", ["Sí", "No"])
    assert json.loads(por_pregunta["¿Dónde vives?"]["opciones_json"]) == []


@respx.mock
@pytest.mark.parametrize("plataforma", ["computrabajo", "magneto"])
def test_motor_generico_y_formulario_clasico_esperan_con_el_pendiente_si_no(mundo, plataforma):
    from buscador_vacantes.asistente.pantalla import decidir

    pid = en_curso(mundo, con_ia=False)
    mundo.base.cx.execute("UPDATE postulaciones SET plataforma = ? WHERE id = ?", (plataforma, pid))
    mundo.base.cx.commit()
    p, _ = tomar(mundo, pid)
    peticion = Peticion(
        "intermedia", None, "es", "https://empresa.co/jobs/1", [Pregunta(AVAL)],
        [Boton(indice=0, texto="Siguiente")], None, Resumen(encabezados=["Practicante"]), None,
        False,
    )  # fmt: skip
    # Motor genérico (/pantalla): la pregunta de texto de sí o no espera al usuario
    resolver = lambda q: mundo.nucleo.resolver_formulario(p, q)  # noqa: E731
    decision = asyncio.run(decidir(peticion, resolver, None))
    assert decision.esperar_usuario
    [pendiente] = mundo.nucleo.pendientes(mundo.usuario.id)
    assert (pendiente["tipo"], json.loads(pendiente["opciones_json"])) == ("si_no", ["Sí", "No"])
    # Formulario clásico (/formulario): el mismo resultado, sin repetir la pregunta
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, [Pregunta(AVAL)]))
    assert [r.pregunta.texto for r in resultado.faltan] == [AVAL]
    assert len(mundo.nucleo.pendientes(mundo.usuario.id)) == 1


# --- la IA falla de forma temporal: se reintenta antes de preguntar ---------------------------


def con_ia_que_se_recupera(mundo, ok_desde):
    """Responde 503 hasta la espera número `ok_desde` del núcleo y bien después."""
    buenas = redactadas(
        {"indice": 1, "respuesta": "Estudio ADSO en el SENA."},
        {"indice": 2, "respuesta": "Quiero aplicar Python."},
        {"indice": 3, "respuesta": "Hice un inventario."},
    )  # fmt: skip

    def responder(_peticion):
        return buenas if len(mundo.esperas) >= ok_desde else httpx.Response(503, json={})

    return respx.post(url__startswith="https://generativelanguage").mock(side_effect=responder)


@respx.mock
def test_ia_saturada_que_se_recupera_se_resuelve_sin_preguntar_al_usuario(mundo):
    mundo.nucleo.config.formulario_ia.esperas_s = [30, 60, 120]
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    con_ia_que_se_recupera(mundo, ok_desde=1)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert not resultado.faltan and len(resultado.respuestas) == 4
    assert [r.origen for r in resultado.respuestas[:3]] == [Origen.IA] * 3
    assert 30 in mundo.esperas and 60 not in mundo.esperas  # solo hizo falta el primer reintento
    assert mundo.nucleo.pendientes(mundo.usuario.id) == []
    pasos = mundo.base.cx.execute(
        "SELECT 1 FROM postulacion_pasos WHERE postulacion_id = ? AND paso = 'ia_no_respondio'",
        (pid,),
    ).fetchall()
    assert pasos == []


@respx.mock
def test_ia_saturada_siempre_agota_las_esperas_y_pregunta_al_usuario(mundo):
    mundo.nucleo.config.formulario_ia.esperas_s = [30, 60]
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    con_ia_que_se_recupera(mundo, ok_desde=10**6)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert len(resultado.faltan) == 3  # las tres abiertas; el salario sí se resolvió
    assert [e for e in mundo.esperas if e in (30, 60)] == [30, 60]
    assert len(mundo.nucleo.pendientes(mundo.usuario.id)) == 3
    paso = mundo.base.cx.execute(
        "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? "
        "AND paso = 'ia_no_respondio'", (pid,),
    ).fetchone()  # fmt: skip
    assert json.loads(paso["detalle"]) == [normalizar_pregunta(t) for t in ABIERTAS]


@respx.mock
def test_sin_clave_de_ia_no_espera_ni_reintenta(mundo):
    mundo.nucleo.config.formulario_ia.esperas_s = [30, 60]
    pid = en_curso(mundo, con_ia=False)
    p, _ = tomar(mundo, pid)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert len(resultado.faltan) == 3 and mundo.esperas == []
    assert mundo.base.cx.execute(
        "SELECT 1 FROM postulacion_pasos WHERE paso = 'ia_no_respondio'"
    ).fetchall() == []


@respx.mock
def test_cuota_agotada_no_espera_ni_reintenta(mundo):
    mundo.nucleo.config.formulario_ia.esperas_s = [30, 60]
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    respx.post(url__startswith="https://generativelanguage").mock(
        return_value=httpx.Response(429, json={})
    )
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert len(resultado.faltan) == 3 and 30 not in mundo.esperas and 60 not in mundo.esperas


@respx.mock
def test_esperas_vacias_desactivan_el_reintento(mundo):
    mundo.nucleo.config.formulario_ia.esperas_s = []
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    ruta = con_ia_que_se_recupera(mundo, ok_desde=10**6)
    resultado = asyncio.run(mundo.nucleo.resolver_formulario(p, formulario()))
    assert len(resultado.faltan) == 3 and mundo.esperas == []
    llamadas = ruta.call_count
    assert llamadas >= 1


@respx.mock
def test_motor_generico_tambien_reintenta_con_la_ia_saturada(mundo):
    from buscador_vacantes.asistente.pantalla import decidir

    mundo.nucleo.config.formulario_ia.esperas_s = [30, 60]
    pid = en_curso(mundo)
    p, _ = tomar(mundo, pid)
    con_ia_que_se_recupera(mundo, ok_desde=1)
    peticion = Peticion(
        "intermedia", None, "es", "https://empresa.co/jobs/1", [Pregunta(ABIERTAS[1])],
        [Boton(indice=0, texto="Siguiente", clase="avanzar")], Sugerido(indice=0, accion="avanzar"),
        Resumen(encabezados=["Practicante"]), None, False,
    )  # fmt: skip
    resolver = lambda q: mundo.nucleo.resolver_formulario(p, q)  # noqa: E731
    decision = asyncio.run(decidir(peticion, resolver, None))
    assert not decision.esperar_usuario and mundo.esperas == [30]
