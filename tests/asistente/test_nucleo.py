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
)
from buscador_vacantes.asistente.respuestas import (  # noqa: E402
    REDACTAR,
    Origen,
    Pregunta,
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
        self.nucleo = Nucleo(
            configuracion, self.base, Indice(self.base, self.ro, 90), detalles, ia,
            Cifrador(generar_clave()), tmp_path / "archivos", reloj=lambda: T0,
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
    assert toque.camino == Camino.RESPALDO and toque.motivo == "plataforma_no_soportada"


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
