import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

pytest.importorskip("fpdf", reason="requiere uv sync --group asistente")
pytest.importorskip("cryptography", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import tarjeta_postulacion as tp  # noqa: E402
from buscador_vacantes.asistente import vinculos  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import E  # noqa: E402
from buscador_vacantes.asistente.cv_lectura import Formacion, Idioma, PerfilExtraido  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro  # noqa: E402
from buscador_vacantes.asistente.detalle import Detalles, Ritmo  # noqa: E402
from buscador_vacantes.asistente.enlaces import id_corto  # noqa: E402
from buscador_vacantes.asistente.ia import crear_clientes  # noqa: E402
from buscador_vacantes.asistente.nucleo import Camino, Nucleo  # noqa: E402
from buscador_vacantes.asistente.respuestas import Pregunta, recordar, sembrar_banco  # noqa: E402
from buscador_vacantes.asistente.resumen_postulacion import DatosResumen  # noqa: E402
from buscador_vacantes.asistente.vacantes import Indice  # noqa: E402
from buscador_vacantes.comun.config import cargar_configuracion  # noqa: E402
from buscador_vacantes.comun.estado import Estado  # noqa: E402
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


# Plataformas reconocidas por dominio que aún no postulan solas (automatica: false)
NUEVAS = {"elempleo": "https://www.elempleo.com/co/ofertas-trabajo/practicante-1886774213"}


@pytest.mark.parametrize("plataforma", list(NUEVAS))
def test_plataforma_nueva_sin_automatica_va_a_respaldo_sin_tarea(mundo, plataforma):
    mundo.vincular()
    id_ = publicar(mundo, plataforma, "1", NUEVAS[plataforma])
    toque = mundo.nucleo.tocar(mundo.usuario, id_)
    assert toque.vacante.plataforma == plataforma
    assert toque.camino == Camino.RESPALDO and toque.motivo == "plataforma_no_automatica"
    assert toque.postulacion.estado == E.RESPALDO
    listos = {"computrabajo", "magneto", plataforma}
    assert mundo.nucleo.cola.siguiente(mundo.usuario.id, listos, T0) is None


def test_vacante_indexada_antes_de_reconocer_el_dominio_toma_la_plataforma_del_enlace(mundo):
    mundo.vincular()
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
        (NUEVAS["elempleo"], "elempleo", "plataforma_no_automatica"),
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
