import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

pytest.importorskip("fpdf", reason="requiere uv sync --group asistente")
pytest.importorskip("cryptography", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import vinculos  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import E  # noqa: E402
from buscador_vacantes.asistente.cv_lectura import Formacion, Idioma, PerfilExtraido  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro  # noqa: E402
from buscador_vacantes.asistente.detalle import Detalles, Ritmo  # noqa: E402
from buscador_vacantes.asistente.enlaces import id_corto  # noqa: E402
from buscador_vacantes.asistente.gemini import ClienteGemini  # noqa: E402
from buscador_vacantes.asistente.nucleo import Camino, Nucleo  # noqa: E402
from buscador_vacantes.asistente.respuestas import Pregunta, sembrar_banco  # noqa: E402
from buscador_vacantes.asistente.vacantes import Indice  # noqa: E402
from buscador_vacantes.config import cargar_configuracion  # noqa: E402
from buscador_vacantes.estado import Estado  # noqa: E402
from buscador_vacantes.modelo import Vacante  # noqa: E402

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "detalle"
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
        gemini = ClienteGemini(a.gemini, self.base, 60, reloj=lambda: T0)
        self.nucleo = Nucleo(
            configuracion, self.base, Indice(self.base, self.ro, 90), detalles, gemini,
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
def test_paquete_de_respaldo_sin_ia(mundo):
    respx.get(URL_LI).mock(
        return_value=httpx.Response(200, text=(FIXTURES / "linkedin.html").read_text("utf-8"))
    )
    toque = mundo.nucleo.tocar(mundo.usuario, id_corto("linkedin:1"))
    paquete = asyncio.run(
        mundo.nucleo.armar_paquete(mundo.usuario, toque.vacante, toque.postulacion.id, toque.motivo)
    )
    assert paquete.cv.is_file() and paquete.cv.read_bytes().startswith(b"%PDF")
    assert "Practicante de sistemas" in paquete.carta
    assert paquete.contacto["Correo"] == "ana@gmail.com"
    textos = {r.pregunta.texto: r.texto for r in paquete.respuestas}
    assert textos["¿Cuál es tu aspiración salarial?"] == "1300000"


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
