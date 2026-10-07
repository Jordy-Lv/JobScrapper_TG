import asyncio
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

pytest.importorskip("telegram", reason="requiere uv sync --group asistente")
fpdf = pytest.importorskip("fpdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import preguntas_tarjeta as pt  # noqa: E402
from buscador_vacantes.asistente import tarjeta_postulacion as tp  # noqa: E402
from buscador_vacantes.asistente import textos as t  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import E, Evento  # noqa: E402
from buscador_vacantes.asistente.conversacion import Conversacion, cb  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro  # noqa: E402
from buscador_vacantes.asistente.detalle import Detalles, Ritmo  # noqa: E402
from buscador_vacantes.asistente.enlaces import id_corto  # noqa: E402
from buscador_vacantes.asistente.ia import crear_clientes  # noqa: E402
from buscador_vacantes.asistente.membresia import Comprobador  # noqa: E402
from buscador_vacantes.asistente.nucleo import Nucleo  # noqa: E402
from buscador_vacantes.asistente.respuestas import sembrar_banco  # noqa: E402
from buscador_vacantes.asistente.usuarios import EstadoUsuario  # noqa: E402
from buscador_vacantes.asistente.vacantes import Indice  # noqa: E402
from buscador_vacantes.config import cargar_configuracion  # noqa: E402
from buscador_vacantes.estado import Estado, a_texto  # noqa: E402
from buscador_vacantes.modelo import Vacante  # noqa: E402

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
DUENO = 999
ANA, LUIS, EVA, EXTRANO = 111, 222, 333, 444
URL_LI = "https://co.linkedin.com/jobs/view/4475512580"
FIXTURE_LI = (Path(__file__).parent / "fixtures" / "detalle" / "linkedin.html").read_text("utf-8")
CLAVE = "AIzaSyClaveDePrueba1234567890"
MODELOS = "https://generativelanguage.googleapis.com/v1beta/models"


class SalidaFalsa:
    def __init__(self):
        self.mensajes = []  # (chat, texto, botones)
        self.ediciones = []
        self.botones_editados = {}  # mensaje → botones de su última edición
        self.documentos = []
        self.borrados = []
        self._id = 0

    async def enviar(self, chat_id, texto, botones=None):
        self._id += 1
        self.mensajes.append((chat_id, texto, botones))
        return self._id

    async def editar(self, chat_id, mensaje_id, texto, botones=None):
        self.ediciones.append((chat_id, mensaje_id, texto))
        self.botones_editados[mensaje_id] = botones

    async def documento(self, chat_id, ruta, texto=None):
        self.documentos.append((chat_id, Path(ruta).name))

    async def borrar(self, chat_id, mensaje_id):
        self.borrados.append((chat_id, mensaje_id))

    def de(self, chat):
        return [m[1] for m in self.mensajes if m[0] == chat]

    def ultimo(self, chat):
        return [m for m in self.mensajes if m[0] == chat][-1]


class BotGrupo:
    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status="left" if user_id == EXTRANO else "member", is_member=True)


@pytest.fixture
def mundo(tmp_path):
    estado = Estado.abrir(tmp_path / "vacantes.db")
    v = Vacante(fuente="linkedin", id_fuente="1", titulo="Practicante de sistemas",
                empresa="ACME", url=URL_LI, keyword="k")  # fmt: skip
    estado.registrar_vista(v, "h", momento=T0, enviada=True)
    configuracion = cargar_configuracion()
    configuracion.asistente.dueno_telegram_id = DUENO
    base = BaseAsistente.abrir(tmp_path / "a.db")
    sembrar_banco(base, T0)
    ro = abrir_vacantes_ro(tmp_path / "vacantes.db")
    a = configuracion.asistente

    async def dormir(_):
        return None

    detalles = Detalles(base, ro, a.detalle, configuracion.red,
                        ritmo=Ritmo(0, reloj=lambda: 0, dormir=dormir))  # fmt: skip
    nucleo = Nucleo(configuracion, base, Indice(base, ro, 90), detalles,
                    crear_clientes(a.ia, base, 60, reloj=lambda: T0),
                    Cifrador(generar_clave()), tmp_path / "archivos", reloj=lambda: T0)  # fmt: skip
    salida = SalidaFalsa()

    async def avisar(_):
        return None

    comprobador = Comprobador(BotGrupo(), -100, nucleo.usuarios, 10, avisar)
    conversacion = Conversacion(nucleo, salida, comprobador)
    nucleo.notificador = conversacion.notificar
    yield SimpleNamespace(n=nucleo, s=salida, c=conversacion, base=base, comprobador=comprobador)
    ro.close()
    estado.cerrar()
    base.cerrar()


def correr(coro):
    return asyncio.run(coro)


def pdf_cv():
    doc = fpdf.FPDF()
    doc.add_page()
    doc.set_font("helvetica", size=10)
    doc.multi_cell(0, 5, "Ana Perez\nTecnologo en ADSO - SENA\nPython, SQL\n" * 10)
    return bytes(doc.output())


MANUAL = ("Ana Pérez", "Tecnólogo en ADSO", "SENA", "Python, SQL, Excel", "Bogotá",
          "ana@gmail.com", "3105551234")  # fmt: skip


async def hasta_resumen(m, tid, *, payload=None):
    """Alta sin clave de Gemini (perfil con unas preguntas) hasta el resumen único."""
    c = m.c
    await c.al_iniciar(tid, "Ana", payload)
    await c.al_boton(tid, cb("politica", "si"))
    await c.al_boton(tid, cb("clave", "omitir"))
    await c.al_documento(tid, pdf_cv(), "cv.pdf")
    for respuesta in MANUAL:
        await c.al_texto(tid, respuesta)


async def responder_faltantes(m, tid):
    """Responde las preguntas de la tarjeta (botones o texto) y confirma el resumen."""
    for _ in range(2 * len(t.CUESTIONARIO)):
        estado = m.c._preguntas(m.n.usuarios.obtener(tid))
        if estado is None:
            return
        if estado.fase == pt.RESUMEN:
            await m.c.al_boton(tid, cb("cuest", "ok"))
            continue
        indice = estado.actual
        item = t.CUESTIONARIO[indice]
        if item.otro:  # botones de rango, pero la prueba escribe su propio valor
            await m.c.al_boton(tid, cb("cuest", indice, "otro"))
            await m.c.al_texto(tid, "1300000")
        elif item.opciones:
            await m.c.al_boton(tid, cb("cuest", indice, 0))
        elif item.opcional:
            await m.c.al_boton(tid, cb("cuest", indice, "omitir"))
        else:
            await m.c.al_texto(tid, "1300000")


async def alta_completa(m, tid, *, payload=None):
    """Camino corto: "Información correcta", solo las preguntas que faltan y vincula el navegador."""
    await hasta_resumen(m, tid, payload=payload)
    await m.c.al_boton(tid, cb("resumen", "ok"))
    await responder_faltantes(m, tid)
    await m.c.al_boton(tid, cb("vincular"))
    usuario = m.n.usuarios.obtener(tid)
    await m.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})
    await m.c.esperar_tareas()


def test_no_miembro_no_guarda_datos(mundo):
    correr(mundo.c.al_iniciar(EXTRANO, "X", None))
    assert mundo.s.de(EXTRANO) == [t.NO_MIEMBRO]
    assert mundo.n.usuarios.obtener(EXTRANO) is None


@respx.mock
def test_alta_desde_el_enlace_retoma_la_vacante(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    correr(alta_completa(mundo, ANA, payload="v_" + id_corto("linkedin:1")))
    usuario = mundo.n.usuarios.obtener(ANA)
    assert usuario.estado == EstadoUsuario.ACTIVO and usuario.vacante_pendiente is None
    mensajes = "\n".join(mundo.s.de(ANA))
    # con vacante pendiente no hay mensaje de cierre
    assert not any(m[1] == t.ALTA_LISTA for m in mundo.s.mensajes)
    assert "Practicante de sistemas" in mensajes and "Mensaje de presentación" in mensajes
    assert any(nombre.startswith("CV_") for _, nombre in mundo.s.documentos)
    datos = mundo.n.datos_usuario(usuario.id)
    assert datos.cuestionario["correo"] == "ana@gmail.com"
    assert datos.perfil.habilidades_tecnicas == ["Python", "SQL", "Excel"]
    # La aspiración salarial no estaba en el CV: se preguntó una vez al inicio
    assert datos.cuestionario["salario"] == "1300000"


def test_resumen_unico_con_dos_botones_y_sin_cuestionario(mundo):
    correr(hasta_resumen(mundo, ANA))
    _, texto, botones = mundo.s.ultimo(ANA)
    assert "Revisa tu información" in texto
    for dato in ("Ana Pérez", "ana@gmail.com", "3105551234", "Tecnólogo en ADSO", "Python"):
        assert dato in texto
    assert [b[1] for b in botones[0]] == [cb("resumen", "ok"), cb("resumen", "editar")]
    antes = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, cb("resumen", "ok")))
    correr(responder_faltantes(mundo, ANA))
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "navegador"
    # Un solo mensaje de preguntas (la tarjeta, que se edita) más el aviso previo y el del navegador
    textos = [m[1] for m in mundo.s.mensajes[antes:]]
    assert len(textos) == 3 and "Faltan" in textos[1]
    preguntadas = "\n".join(textos + [e[2] for e in mundo.s.ediciones])
    # Lo que el CV (o el perfil manual) ya respondió no se vuelve a preguntar
    for clave in ("nombre", "correo", "telefono", "ciudad"):
        item = next(i for i in t.CUESTIONARIO if i.clave == clave)
        assert t.e(item.pregunta) not in preguntadas
    # Sí se preguntan las que suelen pedir las vacantes y el CV no dice
    for clave in ("salario", "disponibilidad_inicio", "actualizar_cv_portal"):
        item = next(i for i in t.CUESTIONARIO if i.clave == clave)
        assert t.e(item.pregunta) in preguntadas


def abrir_preguntas(mundo):
    """Alta hasta la primera pregunta de la tarjeta (el documento, que es opcional)."""
    correr(hasta_resumen(mundo, ANA))
    correr(mundo.c.al_boton(ANA, cb("resumen", "ok")))
    return mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))


def responder_hasta_resumen(mundo):
    async def flujo():
        while (est := mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))).fase != pt.RESUMEN:
            item = t.CUESTIONARIO[est.actual]
            if item.opciones:
                await mundo.c.al_boton(ANA, cb("cuest", est.actual, 0))
            elif item.opcional:
                await mundo.c.al_boton(ANA, cb("cuest", est.actual, "omitir"))
            else:
                await mundo.c.al_texto(ANA, "x")

    correr(flujo())


def botones_tarjeta(mundo):
    return mundo.s.botones_editados[mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)).mensaje_id]


def datos_ana(mundo):
    return mundo.n.datos_usuario(mundo.n.usuarios.obtener(ANA).id).cuestionario


def test_preguntas_en_una_sola_tarjeta_que_se_edita(mundo):
    estado = abrir_preguntas(mundo)
    assert estado.mensaje_id and estado.fase == pt.PREGUNTANDO
    enviados = len(mundo.s.mensajes)
    primera = mundo.s.ultimo(ANA)[1]
    assert primera.startswith("<b>Faltan")
    responder_hasta_resumen(mundo)
    assert len(mundo.s.mensajes) == enviados  # ninguna pregunta salió como mensaje nuevo
    assert len(mundo.s.ediciones) >= 3
    assert all(e[1] == estado.mensaje_id for e in mundo.s.ediciones)
    assert "Revisa tus respuestas" in mundo.s.ediciones[-1][2]
    ultima_antes = [e[2] for e in mundo.s.ediciones if e[2].startswith("<b>Última")]
    assert len(ultima_antes) == 1


def test_estado_de_la_tarjeta_va_a_la_base(mundo):
    estado = abrir_preguntas(mundo)
    usuario = mundo.n.usuarios.obtener(ANA)
    estado.fase, estado.editando = pt.RESUMEN, True
    mundo.c._guardar_preguntas(usuario, estado)
    assert mundo.c._preguntas(usuario) == estado
    mundo.c._guardar_preguntas(usuario, None)
    assert mundo.c._preguntas(usuario) is None


def test_salario_con_botones_de_rango_y_otro_valor(mundo):
    indice = next(i for i, it in enumerate(t.CUESTIONARIO) if it.clave == "salario")
    abrir_preguntas(mundo)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))  # el documento es opcional
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)).actual == indice
    etiquetas = [b[0] for fila in botones_tarjeta(mundo) for b in fila]
    assert etiquetas == [*t.CUESTIONARIO[indice].opciones, "✏️ Otro valor"]
    enviados = len(mundo.s.mensajes)
    # «Otro valor» no guarda nada: la tarjeta pide el número, con «Volver», sin mensajes extra
    correr(mundo.c.al_boton(ANA, cb("cuest", indice, "otro")))
    assert len(mundo.s.mensajes) == enviados
    assert "Escribe el valor" in mundo.s.ediciones[-1][2]
    assert botones_tarjeta(mundo) == [[("↩️ Volver", cb("cuest", "volver"))]]
    assert not datos_ana(mundo).get("salario")
    # Volver regresa a las opciones; un botón guarda el número, no la etiqueta
    correr(mundo.c.al_boton(ANA, cb("cuest", "volver")))
    assert "Escribe el valor" not in mundo.s.ediciones[-1][2]
    correr(mundo.c.al_boton(ANA, cb("cuest", indice, 0)))
    assert datos_ana(mundo)["salario"] == str(t.SMMLV)


def test_otro_valor_borra_lo_escrito_y_valida_el_numero(mundo):
    indice = next(i for i, it in enumerate(t.CUESTIONARIO) if it.clave == "salario")
    abrir_preguntas(mundo)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))
    correr(mundo.c.al_boton(ANA, cb("cuest", indice, "otro")))
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.al_texto(ANA, "mucho", mensaje_id=501))  # no es un número
    assert mundo.s.borrados == [(ANA, 501)]
    assert "Escribe solo el número" in mundo.s.ediciones[-1][2]
    assert not datos_ana(mundo).get("salario")
    correr(mundo.c.al_texto(ANA, "$2.200.000", mensaje_id=502))
    assert mundo.s.borrados == [(ANA, 501), (ANA, 502)]
    assert datos_ana(mundo)["salario"] == "2200000"
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)).fase == pt.PREGUNTANDO
    assert "Escribe solo el número" not in mundo.s.ediciones[-1][2]
    assert len(mundo.s.mensajes) == enviados


def test_documento_escrito_se_guarda_y_se_borra_del_chat(mundo):
    abrir_preguntas(mundo)
    correr(mundo.c.al_texto(ANA, " 1012345678 ", mensaje_id=77))
    assert datos_ana(mundo)["documento"] == "1012345678"
    assert mundo.s.borrados == [(ANA, 77)]


def test_si_no_se_puede_borrar_la_respuesta_igual_queda_guardada(mundo):
    abrir_preguntas(mundo)

    async def borrar(chat, mensaje):
        raise RuntimeError("Message can't be deleted")

    mundo.s.borrar = borrar
    correr(mundo.c.al_texto(ANA, "1012345678", mensaje_id=77))
    assert datos_ana(mundo)["documento"] == "1012345678"
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)).actual != 3


def test_texto_fuera_de_turno_se_borra_sin_guardarse(mundo):
    abrir_preguntas(mundo)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))
    estado = mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))
    item = t.CUESTIONARIO[estado.actual]
    assert item.opciones  # la pregunta se contesta con botones: el texto no cuenta
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.al_texto(ANA, "hola", mensaje_id=88))
    assert mundo.s.borrados == [(ANA, 88)]
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)) == estado
    assert not datos_ana(mundo).get(item.clave)
    assert len(mundo.s.mensajes) == enviados


def test_resumen_confirmar_cierra_la_tarjeta_y_sigue_con_el_navegador(mundo):
    abrir_preguntas(mundo)
    responder_hasta_resumen(mundo)
    resumen = mundo.s.ediciones[-1][2]
    assert "• Documento: —" in resumen and "• Aspiración salarial:" in resumen
    assert [b[1] for b in botones_tarjeta(mundo)[0]] == [cb("cuest", "ok"), cb("cuest", "editar")]
    mid = mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)).mensaje_id
    correr(mundo.c.al_boton(ANA, cb("cuest", "ok")))
    assert mundo.s.ediciones[-1][2] == pt.CIERRE and mundo.s.botones_editados[mid] is None
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "navegador"
    assert "navegador" in mundo.s.ultimo(ANA)[1].lower()
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)) is None
    assert mundo.c._esperando(mundo.n.usuarios.obtener(ANA)) is None
    # Un toque viejo sobre la tarjeta ya cerrada no cambia nada
    mensajes = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))
    correr(mundo.c.al_boton(ANA, cb("cuest", "ok")))
    assert len(mundo.s.mensajes) == mensajes and not datos_ana(mundo).get("documento")


def test_toque_de_una_pregunta_vieja_no_guarda_y_repinta_la_vigente(mundo):
    abrir_preguntas(mundo)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))  # documento contestado
    estado = mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))
    ediciones = len(mundo.s.ediciones)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))  # botón de la pregunta anterior
    correr(mundo.c.al_boton(ANA, cb("cuest", "ok")))  # y el Confirmar aún no existe
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)) == estado
    assert len(mundo.s.ediciones) == ediciones + 2


def test_editar_una_respuesta_con_boton_y_volver_al_resumen(mundo):
    abrir_preguntas(mundo)
    responder_hasta_resumen(mundo)
    indice = next(i for i, it in enumerate(t.CUESTIONARIO) if it.clave == "disponibilidad_inicio")
    assert datos_ana(mundo)["disponibilidad_inicio"] == "Inmediata"
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, cb("cuest", "editar")))
    assert "¿Cuál respuesta quieres corregir?" in mundo.s.ediciones[-1][2]
    # Volver sin elegir deja todo igual
    correr(mundo.c.al_boton(ANA, cb("cuest", "volver")))
    assert "Revisa tus respuestas" in mundo.s.ediciones[-1][2]
    correr(mundo.c.al_boton(ANA, cb("cuest", "editar")))
    correr(mundo.c.al_boton(ANA, cb("cuest", "campo", indice)))
    assert "Editando" in mundo.s.ediciones[-1][2]
    correr(mundo.c.al_boton(ANA, cb("cuest", indice, 2)))  # «En 1 mes»
    assert datos_ana(mundo)["disponibilidad_inicio"] == "En 1 mes"
    assert "• Cuándo empiezas: En 1 mes" in mundo.s.ediciones[-1][2]
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)).fase == pt.RESUMEN
    assert len(mundo.s.mensajes) == enviados


def test_editar_el_documento_con_texto_vuelve_al_resumen(mundo):
    abrir_preguntas(mundo)
    responder_hasta_resumen(mundo)
    assert not datos_ana(mundo).get("documento")
    correr(mundo.c.al_boton(ANA, cb("cuest", "editar")))
    correr(mundo.c.al_boton(ANA, cb("cuest", "campo", 3)))
    correr(mundo.c.al_texto(ANA, "1012345678", mensaje_id=91))
    assert datos_ana(mundo)["documento"] == "1012345678"
    assert mundo.s.borrados == [(ANA, 91)]
    assert "• Documento: 1012345678" in mundo.s.ediciones[-1][2]
    # Omitirlo al corregir borra la respuesta anterior
    correr(mundo.c.al_boton(ANA, cb("cuest", "editar")))
    correr(mundo.c.al_boton(ANA, cb("cuest", "campo", 3)))
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))
    assert not datos_ana(mundo).get("documento")
    assert "• Documento: —" in mundo.s.ediciones[-1][2]


def test_corregir_y_volver_con_el_boton_del_resumen(mundo):
    abrir_preguntas(mundo)
    responder_hasta_resumen(mundo)
    correr(mundo.c.al_boton(ANA, cb("cuest", "editar")))
    correr(mundo.c.al_boton(ANA, cb("cuest", "campo", 3)))
    correr(mundo.c.al_boton(ANA, cb("cuest", "volver")))  # sin responder
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)).fase == pt.RESUMEN
    assert not datos_ana(mundo).get("documento")


def test_editar_recorre_secciones_enfoque_y_cuestionario(mundo):
    async def editar():
        c = mundo.c
        await hasta_resumen(mundo, ANA)
        await c.al_boton(ANA, cb("resumen", "editar"))
        for seccion in ("formacion", "experiencia", "proyectos", "habilidades", "idiomas"):
            await c.al_boton(ANA, cb("seccion", seccion, "ok"))
        await c.al_boton(ANA, cb("enfoque", "ok"))

    correr(editar())
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "cuestionario:0"
    assert t.CUESTIONARIO[0].pregunta in mundo.s.de(ANA)[-1]


@respx.mock
def test_la_clave_se_borra_del_chat_y_se_guarda_cifrada(mundo):
    respx.get(MODELOS).mock(return_value=httpx.Response(200, json={"models": []}))
    correr(mundo.c.al_iniciar(ANA, "Ana", None))
    correr(mundo.c.al_boton(ANA, cb("politica", "si")))
    correr(mundo.c.al_texto(ANA, CLAVE, mensaje_id=77))
    assert mundo.s.borrados == [(ANA, 77)]
    assert mundo.n.clave_gemini(mundo.n.usuarios.obtener(ANA).id) == CLAVE
    assert CLAVE not in "\n".join(mundo.s.de(ANA))
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "cv"


@respx.mock
def test_clave_invalida(mundo):
    respx.get(MODELOS).mock(return_value=httpx.Response(400, json={}))
    correr(mundo.c.al_iniciar(ANA, "Ana", None))
    correr(mundo.c.al_boton(ANA, cb("politica", "si")))
    correr(mundo.c.al_texto(ANA, "mala", mensaje_id=5))
    assert "no es válida" in mundo.s.de(ANA)[-1]
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "clave"


def test_no_acepta_la_politica_borra_todo(mundo):
    correr(mundo.c.al_iniciar(ANA, "Ana", None))
    correr(mundo.c.al_boton(ANA, cb("politica", "no")))
    assert mundo.n.usuarios.obtener(ANA) is None


def test_cuestionario_se_retoma_tras_reinicio(mundo):
    abrir_preguntas(mundo)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))
    estado = mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))
    enviados = len(mundo.s.mensajes)
    # Un servicio nuevo (reinicio) repinta la misma tarjeta en la pregunta en que iba
    otra = Conversacion(mundo.n, mundo.s, mundo.comprobador)
    correr(otra.al_iniciar(ANA, "Ana", None))
    assert len(mundo.s.mensajes) == enviados
    assert mundo.s.ediciones[-1][1] == estado.mensaje_id
    assert t.e(t.CUESTIONARIO[estado.actual].pregunta) in mundo.s.ediciones[-1][2]
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)) == estado


def test_reinicio_en_el_resumen_repinta_el_resumen(mundo):
    abrir_preguntas(mundo)
    responder_hasta_resumen(mundo)
    otra = Conversacion(mundo.n, mundo.s, mundo.comprobador)
    correr(otra.al_comando(ANA, "estado", []))  # cualquier comando durante el alta
    assert "Revisa tus respuestas" in mundo.s.ediciones[-1][2]
    assert [b[1] for b in botones_tarjeta(mundo)[0]] == [cb("cuest", "ok"), cb("cuest", "editar")]


def test_si_la_tarjeta_fue_borrada_se_envia_una_nueva_con_el_estado(mundo):
    abrir_preguntas(mundo)
    correr(mundo.c.al_boton(ANA, cb("cuest", 3, "omitir")))
    estado = mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))

    async def editar(chat, mensaje, texto, botones=None):
        raise RuntimeError("Message to edit not found")

    mundo.s.editar = editar
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, cb("cuest", estado.actual, 0)))
    assert len(mundo.s.mensajes) == enviados + 1
    nuevo = mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))
    assert nuevo.mensaje_id == mundo.s._id and nuevo.mensaje_id != estado.mensaje_id
    assert nuevo.actual != estado.actual


def test_el_comando_cuestionario_usa_la_tarjeta(mundo):
    correr(alta_completa(mundo, ANA))
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.al_comando(ANA, "cuestionario", []))
    assert len(mundo.s.mensajes) == enviados + 1
    estado = mundo.c._preguntas(mundo.n.usuarios.obtener(ANA))
    assert estado.indices == list(range(len(t.CUESTIONARIO))) and estado.mensaje_id
    correr(mundo.c.al_texto(ANA, "Ana María Pérez", mensaje_id=12))
    assert datos_ana(mundo)["nombre"] == "Ana María Pérez"
    assert mundo.s.borrados == [(ANA, 12)] and len(mundo.s.mensajes) == enviados + 1
    responder_hasta_resumen(mundo)
    assert len(mundo.s.mensajes) == enviados + 1
    paso = mundo.n.usuarios.obtener(ANA).paso_alta
    correr(mundo.c.al_boton(ANA, cb("cuest", "ok")))  # fuera del alta solo se cierra la tarjeta
    assert mundo.s.ediciones[-1][2] == pt.CIERRE and len(mundo.s.mensajes) == enviados + 1
    assert mundo.n.usuarios.obtener(ANA).paso_alta == paso
    assert mundo.c._preguntas(mundo.n.usuarios.obtener(ANA)) is None


def test_dato_pedido_por_un_formulario_queda_en_el_perfil(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), "computrabajo", T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = 'esperando_usuario' WHERE id = ?", (p.id,))
        cx.execute(
            "INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, pregunta_norm, "
            "campo, creada) VALUES (?, ?, 'Pretensión salarial', 'pretension salarial', "
            "'salario', 'x')",
            (usuario.id, p.id),
        )
    correr(mundo.c.notificar({"tipo": "preguntas_pendientes", "usuario_id": usuario.id}))
    correr(mundo.c.al_texto(ANA, "1300000"))
    assert mundo.n.datos_usuario(usuario.id).cuestionario["salario"] == "1300000"


def test_comando_de_admin_ajeno_es_desconocido(mundo):
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_comando(ANA, "usuarios", []))
    assert mundo.s.de(ANA)[-1].startswith("No conozco ese comando")


def test_dueno_ve_usuarios_con_auditoria(mundo):
    correr(alta_completa(mundo, DUENO))
    correr(mundo.c.al_comando(DUENO, "usuarios", []))
    assert "<b>Usuarios</b>" in mundo.s.de(DUENO)[-1]
    assert mundo.base.cx.execute("SELECT accion FROM auditoria").fetchone()[0] == "listar_usuarios"


@respx.mock
def test_detalle_muestra_pasos_respuestas_y_cv(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    datos = mundo.n.datos_usuario(usuario.id)
    mundo.n.guardar_cuestionario(usuario.id, {**datos.cuestionario, "salario": "1300000"})

    async def tocar():
        await mundo.c.procesar_toque(usuario, id_corto("linkedin:1"))
        await mundo.c.esperar_tareas()

    correr(tocar())
    mundo.s.documentos.clear()
    correr(mundo.c.al_comando(ANA, "detalle", ["1"]))
    texto = mundo.s.de(ANA)[-1]
    assert "Pasos" in texto and "Preguntas y respuestas" in texto
    assert mundo.s.documentos and mundo.s.documentos[0][1].startswith("CV_")


def test_borrarme(mundo):
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_comando(ANA, "borrarme", []))
    assert "elimínalo desde Telegram" in mundo.s.mensajes[-1][1]
    correr(mundo.c.al_boton(ANA, cb("borrarme")))
    assert mundo.n.usuarios.obtener(ANA) is None


def test_resultado_enviado_edita_la_card_sin_mensajes_nuevos(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), None, T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET mensaje_id = 42 WHERE id = ?", (p.id,))
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    assert any(m == 42 and "confirmó tu postulación" in texto for _, m, texto in mundo.s.ediciones)
    assert "¿Cómo te fue?" in mundo.s.ediciones[-1][2]
    assert len(mundo.s.mensajes) == enviados


def test_cuenta_por_confirmar_muestra_el_correo_y_botones(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    aviso = {"tipo": "cuenta_por_confirmar", "usuario_id": usuario.id,
             "plataforma": "computrabajo", "asociado": "ana@gmail.com"}  # fmt: skip
    correr(mundo.c.notificar(aviso))
    chat, mensaje, texto = mundo.s.ediciones[-1]
    botones = mundo.s.botones_editados[mensaje]
    assert "Conexión con tus portales" in texto
    assert "Computrabajo</b>: sesión iniciada con <b>ana@gmail.com</b>" in texto
    assert botones[0][0][1] == cb("cuenta", "computrabajo", "si")
    assert botones[0][1][1] == cb("cuenta", "computrabajo", "no")


@respx.mock
def test_tres_usuarios_simultaneos_sin_mezclarse(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    for tid in (ANA, LUIS, EVA):
        correr(alta_completa(mundo, tid))

    async def todos():
        usuarios = [mundo.n.usuarios.obtener(tid) for tid in (ANA, LUIS, EVA)]
        await asyncio.gather(*(mundo.c.procesar_toque(u, id_corto("linkedin:1")) for u in usuarios))
        await mundo.c.esperar_tareas()

    correr(todos())
    for tid in (ANA, LUIS, EVA):
        assert any("Practicante de sistemas" in m for m in mundo.s.de(tid))
    filas = mundo.base.cx.execute("SELECT usuario_id FROM postulaciones").fetchall()
    assert len(filas) == 3 and len({f[0] for f in filas}) == 3


def test_limite_de_mensajes_por_minuto(mundo):
    correr(alta_completa(mundo, ANA))
    antes = len(mundo.s.de(ANA))
    for _ in range(40):
        correr(mundo.c.al_comando(ANA, "ayuda", []))
    assert len(mundo.s.de(ANA)) - antes <= mundo.n.config.topes.mensajes_min


def test_preguntas_pendientes_con_botones_y_reanudacion(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), "computrabajo", T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = 'esperando_usuario' WHERE id = ?", (p.id,))
        cx.execute(
            "INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, pregunta_norm, "
            "opciones_json, creada) VALUES (?, ?, '¿Tienes moto?', 'tienes moto', "
            "'[\"Sí\", \"No\"]', 'x')",
            (usuario.id, p.id),
        )
    correr(mundo.c.notificar({"tipo": "preguntas_pendientes", "usuario_id": usuario.id}))
    _, texto, botones = mundo.s.ultimo(ANA)
    assert "Pregunta rápida" in texto and "¿Tienes moto?" in texto
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, botones[1][0][1]))
    assert mundo.n.cola.obtener(p.id).estado == E.EN_COLA
    assert len(mundo.s.mensajes) == enviados  # la card vuelve a «En cola»: sin «Gracias» aparte
    _, mensaje, texto = mundo.s.ediciones[-1]
    assert "En cola" in texto and mundo.s.botones_editados[mensaje] is None


def test_pdf_cv_es_valido():
    assert io.BytesIO(pdf_cv()).read(4) == b"%PDF"


@respx.mock
def test_gemini_saturado_reintenta_solo_el_cv(mundo):
    respx.get(MODELOS).mock(return_value=httpx.Response(200, json={"models": []}))
    respuestas = iter(
        [httpx.Response(503, json={})] * 9
        + [
            httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": (
                    '{"es_cv": true, "nombre": "Ana Pérez", "habilidades_tecnicas": ["Python"]}'
                )}]}}]},
            )
        ]
    )  # fmt: skip
    respx.post(url__startswith=MODELOS + "/").mock(side_effect=lambda _: next(respuestas))
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)

    mundo.c.dormir = dormir
    mundo.n.ia["gemini"].dormir = dormir

    async def flujo():
        c = mundo.c
        await c.al_iniciar(ANA, "Ana", None)
        await c.al_boton(ANA, cb("politica", "si"))
        await c.al_texto(ANA, CLAVE, mensaje_id=1)
        await c.al_documento(ANA, pdf_cv(), "cv.pdf")
        await c.esperar_tareas()

    correr(flujo())
    mensajes = mundo.s.de(ANA)
    assert any("muy ocupados" in m for m in mensajes)
    assert not any("Armemos tu perfil" in m for m in mensajes)
    assert 120 in esperas
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "resumen"
    assert "Revisa tu información" in mensajes[-1]


def _subir_cv_con_fallo(mundo, efecto):
    """Sube el CV con Gemini fallando con ``efecto``; devuelve la ruta mockeada de generación."""
    respx.get(MODELOS).mock(return_value=httpx.Response(200, json={"models": []}))
    ruta = respx.post(url__startswith=MODELOS + "/").mock(side_effect=efecto)

    async def dormir(segundos):
        return None

    mundo.c.dormir = dormir
    mundo.n.ia["gemini"].dormir = dormir

    async def flujo():
        c = mundo.c
        await c.al_iniciar(ANA, "Ana", None)
        await c.al_boton(ANA, cb("politica", "si"))
        await c.al_texto(ANA, CLAVE, mensaje_id=1)
        await c.al_documento(ANA, pdf_cv(), "cv.pdf")

    correr(flujo())
    return ruta


def _etiquetas(botones):
    return [b[0] for fila in botones for b in fila]


@respx.mock
def test_cv_sin_contacto_reintenta_y_pregunta_que_hacer(mundo):
    def caida(_):
        raise httpx.ConnectError("sin red")

    ruta = _subir_cv_con_fallo(mundo, caida)
    assert ruta.call_count >= 3
    _, texto, botones = mundo.s.ultimo(ANA)
    assert "No logré conectarme con Gemini" in texto
    assert "3 intentos" in texto
    etiquetas = _etiquetas(botones)
    assert any("a mano" in e for e in etiquetas)
    assert any("Seguir intentando" in e for e in etiquetas)
    assert not any("API key" in e for e in etiquetas)
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "cv"


@respx.mock
def test_cv_con_cuota_llena_ofrece_cambiar_clave_o_esperar(mundo):
    _subir_cv_con_fallo(mundo, lambda _: httpx.Response(429, json={}))
    _, texto, botones = mundo.s.ultimo(ANA)
    assert "cuota" in texto
    etiquetas = _etiquetas(botones)
    assert any("a mano" in e for e in etiquetas)
    assert any("Seguir intentando" in e for e in etiquetas)
    assert any("Cambiar API key" in e for e in etiquetas)
    assert any("restablezca" in e for e in etiquetas)


@respx.mock
def test_cv_cambiar_clave_retoma_la_lectura(mundo):
    estado = {"falla": True}

    def generar(_):
        if estado["falla"]:
            return httpx.Response(429, json={})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": (
                '{"es_cv": true, "nombre": "Ana Pérez", "habilidades_tecnicas": ["Python"]}'
            )}]}}]},
        )  # fmt: skip

    _subir_cv_con_fallo(mundo, generar)
    estado["falla"] = False

    async def cambiar():
        await mundo.c.al_boton(ANA, cb("cv", "clave"))
        await mundo.c.al_texto(ANA, "AIzaOtraClave1234567890", mensaje_id=2)

    correr(cambiar())
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "resumen"


@respx.mock
def test_cv_avisar_cuando_vuelva_la_cuota(mundo):
    estado = {"falla": True}

    def generar(_):
        if estado["falla"]:
            return httpx.Response(429, json={})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": (
                '{"es_cv": true, "nombre": "Ana Pérez", "habilidades_tecnicas": ["Python"]}'
            )}]}}]},
        )  # fmt: skip

    _subir_cv_con_fallo(mundo, generar)
    pausas = []

    async def dormir(segundos):
        pausas.append(segundos)
        if len(pausas) == 2:  # la cuota vuelve tras el segundo aviso
            estado["falla"] = False

    mundo.c.dormir = dormir

    async def flujo():
        await mundo.c.al_boton(ANA, cb("cv", "avisar"))
        await mundo.c.esperar_tareas()

    correr(flujo())
    assert pausas == [mundo.c.ESPERA_CUOTA_CV_S] * 2
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "resumen"


# --- botón ⚡ en los mensajes del canal ----------------------------------------------------


def test_toque_en_el_canal_postula_al_usuario_registrado(mundo):
    correr(alta_completa(mundo, ANA))
    mundo.n.indice.indexar(T0)

    async def tocar():
        r = await mundo.c.al_toque_canal(ANA, id_corto("linkedin:1"))
        await mundo.c.esperar_tareas()
        return r

    r = correr(tocar())
    usuario = mundo.n.usuarios.obtener(ANA)
    fila = mundo.base.cx.execute(
        "SELECT id_corto FROM postulaciones WHERE usuario_id = ?", (usuario.id,)
    ).fetchone()
    assert fila["id_corto"] == id_corto("linkedin:1")
    assert r.url is None and r.texto  # aviso sobre el canal, sin abrir el bot
    # Un segundo toque no duplica: avisa que ya la tiene
    r2 = correr(mundo.c.al_toque_canal(ANA, id_corto("linkedin:1")))
    assert r2.texto.startswith("Ya la tienes")
    total = mundo.base.cx.execute("SELECT COUNT(*) FROM postulaciones").fetchone()[0]
    assert total == 1


def test_toque_en_el_canal_sin_registro_abre_el_bot_con_la_vacante(mundo):
    r = correr(mundo.c.al_toque_canal(ANA, id_corto("linkedin:1")))
    assert r.url.endswith(f"?start=v_{id_corto('linkedin:1')}")
    assert not mundo.base.cx.execute("SELECT COUNT(*) FROM postulaciones").fetchone()[0]


def test_toque_en_el_canal_con_postulaciones_en_pausa(mundo):
    correr(alta_completa(mundo, ANA))
    mundo.n.indice.indexar(T0)
    correr(mundo.c.al_comando(ANA, "pausa", []))
    r = correr(mundo.c.al_toque_canal(ANA, id_corto("linkedin:1")))
    assert r.alerta and "pausa" in r.texto


def test_avisar_apagado_silencia_solo_la_automatica(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    mundo.n.preferencias.guardar(
        usuario.id, "computrabajo", T0, automatico=True, umbral=None, avisar=False
    )
    # Una postulación automática no avisa
    auto, _ = mundo.n.cola.encolar(
        usuario.id, id_corto("computrabajo:1"), "computrabajo", T0, origen="automatico"
    )
    antes = len(mundo.s.de(ANA))
    correr(mundo.c.notificar(Evento("resultado", auto.id, usuario.id, E.ENVIADA)))
    assert len(mundo.s.de(ANA)) == antes
    # Un toque manual sigue avisando, aunque el portal tenga el aviso apagado
    manual, _ = mundo.n.cola.encolar(
        usuario.id, id_corto("computrabajo:2"), "computrabajo", T0, origen="boton"
    )
    correr(mundo.c.notificar(Evento("resultado", manual.id, usuario.id, E.ENVIADA)))
    assert "confirmó tu postulación" in mundo.s.de(ANA)[-1]


def postulacion_enviada_con_datos(mundo):
    """Postulación de Ana a la vacante de LinkedIn con ficha, respuestas y CV adjunto."""
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), None, T0)
    cv = mundo.n.cv_base_de(usuario, mundo.n.datos_usuario(usuario.id))
    ficha = '{"salario": "$ 1.423.500 mensual", "ubicacion": "Medellín, Antioquia"}'
    requisitos = (
        '{"origen": "ia", "requisitos": {"obligatorios": ["Sistemas", "Redes"], '
        '"deseables": [], "palabras_clave": [], "nivel": "Practicante", "modalidad": "Presencial"}}'
    )
    with mundo.base.transaccion() as cx:
        cx.execute(
            "UPDATE vacantes SET detalle = ?, ficha_json = ?, requisitos_json = ? "
            "WHERE id_corto = ?",
            ("Buscamos practicante para soporte de equipos. Horario de lunes a viernes.",
             ficha, requisitos, id_corto("linkedin:1")),
        )  # fmt: skip
        cx.execute(
            "UPDATE postulaciones SET mensaje_id = 42, afinidad = 60, cv_archivo = ?, "
            "terminada_en = ? WHERE id = ?",
            (str(cv), T0.isoformat(), p.id),
        )
        cx.executemany(
            "INSERT INTO respuestas(postulacion_id, campo, pregunta, respuesta, origen) "
            "VALUES (?, ?, ?, ?, ?)",
            [(p.id, "institucion", "¿En qué institución estudias?", "SENA", "perfil"),
             (p.id, None, "¿Por qué te interesa?", "Quiero aprender soporte.", "ia")],
        )  # fmt: skip
    mundo.n.cola.registrar_paso(p.id, None, "cv_adjunto", cv.name, T0)
    return usuario, p, cv


def card_de(mundo, mensaje=42):
    """Texto y botones de la última edición de la card (la fixture ya le dio el mensaje 42)."""
    texto = next(e[2] for e in reversed(mundo.s.ediciones) if e[1] == mensaje)
    return texto, mundo.s.botones_editados[mensaje]


def test_tarjeta_corta_con_botones_al_confirmar_la_postulacion(mundo):
    usuario, p, cv = postulacion_enviada_con_datos(mundo)
    mundo.s.documentos.clear()
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    texto, botones = card_de(mundo)
    assert "Practicante de sistemas</b>\nACME\n" in texto
    assert "Encuesta de 2 · CV adaptado adjunto</blockquote>" in texto
    assert botones == [[
        ("Respuestas", cb("res", p.id, "r")),
        ("De qué trata", cb("res", p.id, "d")),
        ("Ver vacante", "url:" + URL_LI),
    ], [
        ("Entrevista", cb("seg", p.id, "entrevista")),
        ("Rechazada", cb("seg", p.id, "rechazada")),
    ]]  # fmt: skip
    assert "¿Cómo te fue?" in texto
    assert mundo.s.documentos == [(ANA, cv.name)]
    assert len(mundo.s.mensajes) == enviados  # todo en la misma card


def test_botones_de_la_tarjeta_muestran_respuestas_y_descripcion(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.al_boton(ANA, cb("res", p.id, "r")))
    respuestas = mundo.s.de(ANA)[-1]
    assert "<b>SENA</b> 👤" in respuestas and "¿Por qué te interesa?" in respuestas
    assert "🤖 redactada con IA" in respuestas
    correr(mundo.c.al_boton(ANA, cb("res", p.id, "d")))
    trata = mundo.s.de(ANA)[-1]
    for esperado in ("Medellín, Antioquia", "$ 1.423.500 mensual", "soporte de equipos",
                     "Piden: Sistemas, Redes", "Tu afinidad: 60 %"):  # fmt: skip
        assert esperado in trata, esperado
    # Los botones de otra persona no muestran nada
    antes = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(LUIS, cb("res", p.id, "r")))
    assert len(mundo.s.mensajes) == antes


def test_tarjeta_sin_adjunto_dice_hdv_del_perfil_y_no_manda_pdf(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    with mundo.base.transaccion() as cx:
        cx.execute("DELETE FROM postulacion_pasos WHERE paso = 'cv_adjunto'")
    mundo.s.documentos.clear()
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    assert "HdV del perfil" in card_de(mundo)[0]
    assert not mundo.s.documentos


def test_bloqueo_del_portal_explica_que_hacer_sin_paquete(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), "computrabajo", T0)
    antes = len(mundo.s.de(ANA))
    ev = Evento("resultado", p.id, usuario.id, E.BLOQUEADA, "portal_correo_incorrecto")
    correr(mundo.c.notificar(ev))
    correr(mundo.c.esperar_tareas())
    chat, texto, botones = mundo.s.ultimo(ANA)
    assert "no puede enviarte correos" in texto and "Computrabajo" in texto
    assert "No envié nada todavía" in texto
    assert botones == [[("Reintentar", cb("rei", p.id))]]
    assert len(mundo.s.de(ANA)) == antes + 1  # solo la card: sin aviso aparte ni paquete
    assert not any("paquete" in m for m in mundo.s.de(ANA)[antes:])
    assert not mundo.s.de(DUENO)  # no es un formulario roto: no se avisa al dueño


def test_sin_confirmacion_igual_envia_la_tarjeta_con_las_respuestas(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.INCIERTA)))
    texto, botones = card_de(mundo)
    assert "no mostró la confirmación" in texto and "Encuesta de 2" in texto
    assert botones[0][0] == ("Respuestas", cb("res", p.id, "r"))
    correr(mundo.c.al_boton(ANA, cb("res", p.id, "r")))
    assert "<b>SENA</b>" in card_de(mundo)[0]


# --- mensajes de los botones del resumen: se borran solos y no se pueden repetir ----------------


def tocar_resumen(mundo, pid, parte):
    return correr(mundo.c.al_boton(ANA, cb("res", pid, parte)))


def test_el_mensaje_del_boton_trae_el_aviso_de_borrado_y_queda_anotado(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    assert tocar_resumen(mundo, p.id, "r") is None
    texto = mundo.s.de(ANA)[-1]
    assert "Tus respuestas" in texto and "🕒 Se borra solo en 25 s" in texto
    filas = mundo.base.cx.execute("SELECT clave, borrar_en FROM mensajes_efimeros").fetchall()
    assert [f["clave"] for f in filas] == [f"res:{p.id}:r"]


def test_mientras_sigue_en_pantalla_volver_a_tocar_no_lo_repite(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    tocar_resumen(mundo, p.id, "r")
    enviados = len(mundo.s.mensajes)
    aviso = tocar_resumen(mundo, p.id, "r")
    assert "Ya lo tienes arriba" in aviso and "25 s" in aviso
    assert len(mundo.s.mensajes) == enviados
    # El otro botón es independiente
    assert tocar_resumen(mundo, p.id, "d") is None
    assert len(mundo.s.mensajes) == enviados + 1


def test_dos_toques_a_la_vez_envian_una_sola_vez(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)

    async def doble():
        return await asyncio.gather(
            mundo.c.al_boton(ANA, cb("res", p.id, "r")), mundo.c.al_boton(ANA, cb("res", p.id, "r"))
        )

    avisos = correr(doble())
    assert sorted(a is None for a in avisos) == [False, True]
    assert sum("Tus respuestas" in m for m in mundo.s.de(ANA)) == 1


def test_al_cumplirse_el_tiempo_se_borra_y_se_puede_pedir_otra_vez(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    tocar_resumen(mundo, p.id, "r")
    ids = [i for i in range(1, mundo.s._id + 1)]
    # Reinicio del servicio o paso del tiempo: el barrido borra lo vencido
    assert correr(mundo.c.borrar_vencidos(T0 + timedelta(seconds=10))) == 0
    assert correr(mundo.c.borrar_vencidos(T0 + timedelta(seconds=26))) == 1
    assert mundo.s.borrados == [(ANA, ids[-1])]
    assert mundo.base.cx.execute("SELECT COUNT(*) FROM mensajes_efimeros").fetchone()[0] == 0
    assert tocar_resumen(mundo, p.id, "r") is None  # ya se puede pedir de nuevo


def test_el_borrado_programado_corre_solo_tras_la_espera(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    esperas = []

    async def dormir(segundos):
        esperas.append(segundos)

    mundo.c.dormir = dormir

    async def flujo():
        await mundo.c.al_boton(ANA, cb("res", p.id, "r"))
        await asyncio.gather(*mundo.c._borrados)

    correr(flujo())
    assert esperas == [25] and len(mundo.s.borrados) == 1


def test_si_el_mensaje_ya_no_existe_el_borrado_no_falla(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    tocar_resumen(mundo, p.id, "r")

    async def borrar(chat, mensaje):
        raise RuntimeError("Message to delete not found")

    mundo.s.borrar = borrar
    assert correr(mundo.c.borrar_vencidos(T0 + timedelta(seconds=60))) == 0
    assert mundo.base.cx.execute("SELECT COUNT(*) FROM mensajes_efimeros").fetchone()[0] == 0


def test_el_tiempo_de_lectura_crece_con_el_texto_y_tiene_tope(mundo):
    espera = mundo.c._espera_lectura
    assert espera(["corto"]) == 25
    assert espera(["<b>x</b>" + "a" * 700]) == 50
    assert espera(["a" * 100000]) == 120


def test_tope_de_toques_por_minuto_protege_el_chat(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    mundo.n.config.mensajes_efimeros.max_por_min = 1
    tocar_resumen(mundo, p.id, "r")
    enviados = len(mundo.s.mensajes)
    assert "muy rápido" in tocar_resumen(mundo, p.id, "d")
    assert len(mundo.s.mensajes) == enviados


def test_progreso_un_solo_mensaje_que_avanza_de_etapa_y_se_detiene(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    mundo.c.intervalo_animacion = 0.01

    async def correr_progreso():
        base = {"postulacion_id": p.id, "usuario_id": usuario.id}
        await mundo.c.notificar({"tipo": "postulando", **base})
        await mundo.c.notificar({"tipo": "paso", "paso": "llenado", **base})
        await asyncio.sleep(0.05)
        await mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA))

    correr(correr_progreso())
    textos = [e[2] for e in mundo.s.ediciones if e[1] == 42]
    assert any("⠋ <b>Abriendo la oferta…</b>" in x for x in textos)
    assert any("✓ Preparando tu hoja de vida" in x and "Respondiendo el formulario…" in x
               for x in textos)  # fmt: skip
    assert "confirmó tu postulación" in textos[-1]
    assert p.id not in mundo.c._animaciones


def test_paso_cv_con_botones_adjuntar_y_desde_cero_proximamente(mundo):
    correr(alta_completa(mundo, ANA))
    _, texto, botones = next(m for m in mundo.s.mensajes if "Paso 3 de 5" in m[1])
    assert botones == [[("✍️ Crearla desde cero", cb("cvopc", "cero")),
                        ("📎 Adjuntar mi CV", cb("cvopc", "adjuntar"))]]  # fmt: skip
    correr(mundo.c.al_boton(ANA, cb("cvopc", "cero")))
    assert "Próximamente" in mundo.s.de(ANA)[-1]
    correr(mundo.c.al_boton(ANA, cb("cvopc", "adjuntar")))
    assert "Adjunta aquí tu hoja de vida" in mundo.s.de(ANA)[-1]


def test_modalidad_se_pregunta_segun_la_ciudad_del_usuario(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    datos = mundo.n.datos_usuario(usuario.id)
    cuestionario = datos.cuestionario
    cuestionario["ciudad"] = "Cali"
    mundo.n.guardar_cuestionario(usuario.id, cuestionario)
    indice = next(i for i, x in enumerate(t.CUESTIONARIO) if x.clave == "modalidades")
    correr(mundo.c._iniciar_preguntas(usuario, [indice]))
    _, texto, botones = mundo.s.mensajes[-1]
    assert "Vives en Cali" in texto
    assert [b[0] for b in botones[0]] == ["Presencial en Cali", "Híbrido y remoto", "Cualquiera"]
    correr(mundo.c.al_boton(ANA, cb("cuest", indice, 0)))
    assert mundo.n.datos_usuario(usuario.id).cuestionario["modalidades"] == "Presencial en Cali"


def test_al_vincular_el_navegador_el_alta_termina_sin_boton_terminar(mundo):
    mundo.n.enlace_grupo = "https://t.me/+abc"

    async def flujo():
        await hasta_resumen(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("resumen", "ok"))
        await responder_faltantes(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("vincular"))
        usuario = mundo.n.usuarios.obtener(ANA)
        assert usuario.estado == EstadoUsuario.ALTA
        await mundo.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado != EstadoUsuario.ALTA
    assert not any("Cuando termines" in m[1] for m in mundo.s.mensajes)
    tarjetas = [m for m in mundo.s.mensajes if "Conexión con tus portales" in m[1]]
    assert len(tarjetas) == 1 and "✓ Navegador vinculado" in tarjetas[0][1]
    assert t.ALTA_LISTA not in mundo.s.ediciones[-1][2]  # la tarjeta ya no repite el cierre
    cierres = [m for m in mundo.s.mensajes if m[1] == t.ALTA_LISTA]  # mensaje nuevo: sí avisa
    assert len(cierres) == 1 and "grupo" in cierres[0][1] and "⚡ Postularme" in cierres[0][1]
    assert cierres[0][2] == [[("👥 Ir al grupo", "url:https://t.me/+abc")]]


def test_el_cierre_del_alta_sin_enlace_al_grupo_no_lleva_boton(mundo):
    mundo.n.enlace_grupo = None

    async def flujo():
        await hasta_resumen(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("resumen", "ok"))
        await responder_faltantes(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("vincular"))
        usuario = mundo.n.usuarios.obtener(ANA)
        await mundo.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})

    correr(flujo())
    cierres = [m for m in mundo.s.mensajes if m[1] == t.ALTA_LISTA]
    assert len(cierres) == 1 and cierres[0][2] is None


@respx.mock
def test_start_con_el_navegador_ya_vinculado_cierra_el_alta_y_retoma_la_vacante(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))

    async def flujo():
        await hasta_resumen(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("resumen", "ok"))
        await responder_faltantes(mundo, ANA)
        usuario = mundo.n.usuarios.obtener(ANA)
        with mundo.n.base.transaccion() as cx:  # navegador vinculado con el alta sin cerrar
            cx.execute(
                "INSERT INTO navegadores(usuario_id, token_hash, creado, ultimo_latido) "
                "VALUES (?, 'h', 'x', 'x')",
                (usuario.id,),
            )
        assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ALTA
        await mundo.c.al_iniciar(ANA, "Ana", "v_" + id_corto("linkedin:1"))
        await mundo.c.esperar_tareas()

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ACTIVO
    mensajes = "\n".join(mundo.s.de(ANA))
    assert "Conexión con tus portales" in mensajes and "✓ Navegador vinculado" in mensajes
    assert "Paso 5 de 5" not in mensajes.split("Conexión con tus portales")[-1]
    assert "Practicante de sistemas" in mensajes


async def vincular_navegador(m, tid):
    """Alta hasta el paso del navegador; la prueba vincula con el evento de la API."""
    await m.c.al_boton(tid, cb("resumen", "ok"))
    await responder_faltantes(m, tid)
    await m.c.al_boton(tid, cb("vincular"))
    usuario = m.n.usuarios.obtener(tid)
    with m.n.base.transaccion() as cx:
        cx.execute(
            "INSERT INTO navegadores(usuario_id, token_hash, creado, ultimo_latido) "
            "VALUES (?, 'h', 'x', 'x')",
            (usuario.id,),
        )
    await m.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})
    await m.c.esperar_tareas()
    return m.n.usuarios.obtener(tid)


def test_vincular_con_navegador_ya_vinculado_avisa_y_no_genera_codigo(mundo):
    def codigos():
        return mundo.n.base.cx.execute("SELECT COUNT(*) FROM codigos_vinculo").fetchone()[0]

    async def flujo():
        await hasta_resumen(mundo, ANA)
        await vincular_navegador(mundo, ANA)
        with mundo.n.base.transaccion() as cx:
            cx.execute(
                "UPDATE navegadores SET creado = ?, ultimo_latido = ?, nombre = 'Edge'",
                (a_texto(mundo.n.ahora()),) * 2,
            )
        antes, mensajes = codigos(), len(mundo.s.mensajes)
        await mundo.c.al_comando(ANA, "vincular", [])
        await mundo.c.al_boton(ANA, cb("vincular"))  # botón de un mensaje viejo
        return antes, mensajes

    antes, mensajes = correr(flujo())
    nuevos = mundo.s.mensajes[mensajes:]
    assert len(nuevos) == 2
    assert all("Dispositivo ya vinculado" in m[1] for m in nuevos)
    assert all("/navegadores" in m[1] for m in nuevos)
    assert codigos() == antes
    assert not any("🔗 Vincular mi navegador" in str(m) for m in nuevos)


def test_vincular_sin_navegador_sigue_ofreciendo_el_enlace(mundo):
    async def flujo():
        await hasta_resumen(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("resumen", "ok"))
        await responder_faltantes(mundo, ANA)
        antes = len(mundo.s.mensajes)
        await mundo.c.al_boton(ANA, cb("vincular"))
        return antes

    antes = correr(flujo())
    assert not any("Dispositivo ya vinculado" in m[1] for m in mundo.s.mensajes[antes:])


def aviso_cuenta(usuario, plataforma, correo, tipo="cuenta_por_confirmar"):
    return {"tipo": tipo, "usuario_id": usuario.id, "plataforma": plataforma, "asociado": correo}


def kv_tarjeta(mundo, usuario):
    return mundo.n.base.kv_obtener(f"tarjeta:{usuario.id}")


def test_cuentas_se_confirman_en_la_misma_tarjeta_sin_mensajes_nuevos(mundo):
    async def flujo():
        await hasta_resumen(mundo, ANA)
        usuario = await vincular_navegador(mundo, ANA)
        await mundo.c.notificar(aviso_cuenta(usuario, "computrabajo", "ana@gmail.com"))
        enviados = len(mundo.s.mensajes)
        await mundo.c.al_boton(ANA, cb("cuenta", "computrabajo", "si"))
        assert len(mundo.s.mensajes) == enviados  # confirmar solo edita la tarjeta

    correr(flujo())
    id_tarjeta = next(i for i, m in enumerate(mundo.s.mensajes, 1) if "Conexión" in m[1])
    chat, mensaje, texto = mundo.s.ediciones[-1]
    assert mensaje == id_tarjeta and "✓ Computrabajo · ana@gmail.com" in texto
    assert mundo.s.botones_editados[mensaje] is None  # ya no queda nada por confirmar
    assert not any("quedó asociada" in m[1] or "Sesión iniciada" in m[1] for m in mundo.s.mensajes)


def test_cancelar_la_cuenta_deja_la_linea_pendiente_en_la_tarjeta(mundo):
    async def flujo():
        await hasta_resumen(mundo, ANA)
        usuario = await vincular_navegador(mundo, ANA)
        await mundo.c.notificar(aviso_cuenta(usuario, "magneto", "otra@gmail.com"))
        await mundo.c.al_boton(ANA, cb("cuenta", "magneto", "no"))

    correr(flujo())
    assert "· Magneto: inicia sesión con tu cuenta" in mundo.s.ediciones[-1][2]


@respx.mock
def test_la_vacante_del_alta_se_postula_dentro_de_la_misma_tarjeta(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    mundo.c.intervalo_animacion = 0.01
    mundo.n.camino_automatico = lambda *_: None  # la vacante de la prueba es de LinkedIn

    async def flujo():
        await hasta_resumen(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        usuario = await vincular_navegador(mundo, ANA)
        fila = mundo.n.base.cx.execute("SELECT id, mensaje_id FROM postulaciones").fetchone()
        base = {"postulacion_id": fila["id"], "usuario_id": usuario.id}
        await mundo.c.notificar({"tipo": "postulando", **base})
        await mundo.c.notificar(aviso_cuenta(usuario, "computrabajo", "ana@gmail.com"))
        await asyncio.sleep(0.05)  # la animación sigue editando con los botones puestos
        con_botones = mundo.s.botones_editados[fila["mensaje_id"]]
        await mundo.c.al_boton(ANA, cb("cuenta", "computrabajo", "si"))
        await mundo.c.notificar({"tipo": "paso", "paso": "llenado", **base})
        await asyncio.sleep(0.05)
        await mundo.c.notificar(Evento("resultado", fila["id"], usuario.id, E.ENVIADA))
        return usuario, fila, con_botones

    usuario, fila, con_botones = correr(flujo())
    assert con_botones[0][0][1] == cb("cuenta", "computrabajo", "si")
    textos = [e[2] for e in mundo.s.ediciones if e[1] == fila["mensaje_id"]]
    assert any("✓ Navegador vinculado" in x and "Abriendo la oferta" in x for x in textos)
    assert any("✓ Computrabajo · ana@gmail.com" in x and "Respondiendo el formulario…" in x
               for x in textos)  # fmt: skip
    assert "confirmó tu postulación" in textos[-1] and "Conexión" not in textos[-1]
    assert not kv_tarjeta(mundo, usuario)
    # Un solo mensaje para todo el proceso: nada de avisos sueltos de cuenta ni de alta
    todos = "\n".join(mundo.s.de(ANA))
    assert "Sesión iniciada" not in todos and "quedó asociada" not in todos
    assert t.ALTA_LISTA not in todos


def test_si_la_tarjeta_fue_borrada_se_envia_una_nueva(mundo):
    async def flujo():
        await hasta_resumen(mundo, ANA)
        usuario = await vincular_navegador(mundo, ANA)

        async def editar(chat, mensaje, texto, botones=None):
            raise RuntimeError("Message to edit not found")

        mundo.s.editar = editar
        aviso = aviso_cuenta(usuario, "computrabajo", "ana@gmail.com", "portal_listo")
        await mundo.c.notificar(aviso)
        return usuario

    usuario = correr(flujo())
    chat, texto, _ = mundo.s.ultimo(ANA)
    assert "✓ Computrabajo · ana@gmail.com" in texto
    assert f'"mensaje_id": {len(mundo.s.mensajes)}' in kv_tarjeta(mundo, usuario)


# --- la card única de una postulación, de punta a punta -----------------------------------------


def preparar_toque(mundo, *, automatico=True):
    """Alta completa de Ana, vacante indexada y el portal de la prueba como automático."""
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    correr(alta_completa(mundo, ANA))
    mundo.n.indice.indexar(T0)
    if automatico:
        mundo.n.camino_automatico = lambda *_: None  # la vacante de la prueba es de LinkedIn
    return mundo.n.usuarios.obtener(ANA)


def tocar(mundo, usuario):
    """Toque ⚡ y espera a las tareas de fondo. Devuelve (pid, mensajes nuevos de Ana)."""

    async def flujo():
        toque = await mundo.c.procesar_toque(usuario, id_corto("linkedin:1"))
        await mundo.c.esperar_tareas()
        return toque

    antes = len(mundo.s.mensajes)
    toque = correr(flujo())
    return toque.postulacion.id, mundo.s.mensajes[antes:]


def card_guardada(mundo, pid):
    return tp.Card.de_texto(mundo.base.kv_obtener(f"card:{pid}"))


def nuevos(mundo, desde):
    return [m for m in mundo.s.mensajes[desde:] if m[0] == ANA]


# --- nacimiento y reintento ---------------------------------------------------------------


@respx.mock
def test_el_toque_crea_una_sola_card_y_guarda_su_estado(mundo):
    usuario = preparar_toque(mundo)
    antes = len(mundo.s.mensajes)

    async def flujo():  # sin esperar las tareas de fondo: solo lo que produce el toque
        return await mundo.c.procesar_toque(usuario, id_corto("linkedin:1"))

    toque = correr(flujo())
    pid = toque.postulacion.id
    enviados = nuevos(mundo, antes)
    assert len(enviados) == 1
    assert "Practicante de sistemas" in enviados[0][1] and "En cola" in enviados[0][1]
    card = card_guardada(mundo, pid)
    assert card.fase == tp.EN_COLA and card.mensaje_id == mundo.s._id
    fila = mundo.base.cx.execute("SELECT mensaje_id FROM postulaciones WHERE id = ?", (pid,))
    assert fila.fetchone()["mensaje_id"] == card.mensaje_id


@respx.mock
def test_tocar_otra_vez_repinta_la_misma_card_sin_mensajes_nuevos(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    antes = len(mundo.s.mensajes)
    pid2, enviados = tocar(mundo, usuario)
    assert pid2 == pid and not enviados and len(mundo.s.mensajes) == antes


@respx.mock
def test_reintentar_reusa_la_card_y_no_envia_otra(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    bloqueo = Evento("resultado", pid, usuario.id, E.BLOQUEADA, "portal_correo_incorrecto")
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = 'bloqueada' WHERE id = ?", (pid,))
    correr(mundo.c.notificar(bloqueo))
    assert card_guardada(mundo, pid).fase == tp.BLOQUEO
    antes = len(mundo.s.mensajes)

    async def reintentar():
        aviso = await mundo.c.al_boton(ANA, cb("rei", pid))
        await mundo.c.esperar_tareas()
        return aviso

    assert "Reintentando" in correr(reintentar())
    assert len(mundo.s.mensajes) == antes  # no se envió otra card ni «En cola» suelto
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    card = card_guardada(mundo, pid)
    assert card.fase == tp.EN_COLA and card.mensaje_id == mensaje
    texto, botones = card_de(mundo, mensaje)
    assert "En cola" in texto and botones is None


def test_reintentar_sobre_una_card_confirmada_no_reencola_nada(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    antes = len(mundo.s.mensajes)
    assert correr(mundo.c.al_boton(ANA, cb("rei", p.id))) is None
    assert len(mundo.s.mensajes) == antes
    assert mundo.n.cola.obtener(p.id).estado == E.EN_COLA  # estado de la fixture: no se tocó
    assert "confirmó tu postulación" in card_de(mundo)[0]


@respx.mock
def test_card_borrada_se_envia_una_nueva_con_el_estado_actual(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)

    async def editar(chat, mensaje, texto, botones=None):
        raise RuntimeError("Message to edit not found")

    mundo.s.editar = editar
    correr(mundo.c.notificar(Evento("resultado", pid, usuario.id, E.ESPERANDO_SESION)))
    chat, texto, _ = mundo.s.ultimo(ANA)
    assert "Inicia sesión" in texto
    assert card_guardada(mundo, pid).mensaje_id == mundo.s._id


# --- conexión y progreso ----------------------------------------------------------------------


@respx.mock
def test_la_cuenta_por_confirmar_se_pinta_en_la_card_en_curso(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    antes = len(mundo.s.mensajes)
    correr(mundo.c.notificar(aviso_cuenta(usuario, "computrabajo", "ana@gmail.com")))
    texto, botones = card_de(mundo, mensaje)
    assert "Conexión con tus portales" in texto and "En cola" in texto
    assert "sesión iniciada con <b>ana@gmail.com</b>" in texto
    assert botones == [[
        ("Confirmar Computrabajo", cb("cuenta", "computrabajo", "si")),
        ("Cancelar", cb("cuenta", "computrabajo", "no")),
    ]]  # fmt: skip
    correr(mundo.c.al_boton(ANA, cb("cuenta", "computrabajo", "si")))
    texto, botones = card_de(mundo, mensaje)
    assert "✓ Computrabajo · ana@gmail.com" in texto and botones is None
    assert len(mundo.s.mensajes) == antes


@respx.mock
def test_cuenta_distinta_ofrece_sus_dos_botones_en_la_card(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    aviso = aviso_cuenta(usuario, "computrabajo", "ana@gmail.com", "cuenta_distinta")
    aviso["encontrado"] = "l***@hotmail.com"
    correr(mundo.c.notificar(aviso))
    texto, botones = card_de(mundo, mensaje)
    assert "⚠️" in texto and "No postularé con ella" in texto
    assert [b[0] for b in botones[0]] == ["Es mi cuenta nueva", "No es mía"]


@respx.mock
def test_el_progreso_edita_la_card_y_se_vuelve_a_poner_tras_la_verificacion(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    base = {"postulacion_id": pid, "usuario_id": usuario.id}
    antes = len(mundo.s.mensajes)

    async def flujo():
        await mundo.c.notificar({"tipo": "postulando", **base})
        await mundo.c.notificar({"tipo": "paso", "paso": "cv_subir", **base})
        await mundo.c.notificar({"tipo": "verificacion", **base})
        assert card_guardada(mundo, pid).fase == tp.VERIFICACION
        await mundo.c.notificar({"tipo": "paso", "paso": "llenado", **base})
        assert card_guardada(mundo, pid).fase == tp.PROGRESO
        await mundo.c._detener_progreso(pid)

    correr(flujo())
    textos = [e[2] for e in mundo.s.ediciones if e[1] == mensaje]
    assert any("verificación" in x for x in textos)
    assert "✓ Preparando tu hoja de vida" in textos[-1]
    assert "Respondiendo el formulario…" in textos[-1]
    assert len(mundo.s.mensajes) == antes


@respx.mock
def test_sesion_espera_de_navegador_y_cierre_van_en_la_misma_card(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET plataforma = 'computrabajo' WHERE id = ?", (pid,))
    antes = len(mundo.s.mensajes)

    correr(mundo.c.notificar(Evento("navegador_desconectado", pid, usuario.id,
                                    E.ESPERANDO_NAVEGADOR)))  # fmt: skip
    assert "Se enviará cuando abras tu navegador" in card_de(mundo, mensaje)[0]

    correr(mundo.c.notificar(Evento("resultado", pid, usuario.id, E.ESPERANDO_SESION)))
    texto, botones = card_de(mundo, mensaje)
    assert "Inicia sesión en Computrabajo en tu navegador y sigo solo" in texto
    assert botones == [[("Crear cuenta", "url:https://co.computrabajo.com/")]]

    correr(mundo.c.notificar(Evento("resultado", pid, usuario.id, E.VACANTE_CERRADA)))
    texto, botones = card_de(mundo, mensaje)
    assert "Vacante cerrada" in texto
    assert botones == [[("Ver vacante", "url:" + URL_LI)]]
    assert len(mundo.s.mensajes) == antes


@respx.mock
def test_un_toque_viejo_de_respuestas_repinta_la_card_vigente(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    antes = len(mundo.s.mensajes)
    assert correr(mundo.c.al_boton(ANA, cb("res", pid, "r"))) is None
    assert len(mundo.s.mensajes) == antes
    assert card_guardada(mundo, pid).fase == tp.EN_COLA


# --- preguntas ----------------------------------------------------------------------------------


def pendiente(mundo, usuario, pid, pregunta, norma, opciones="[]"):
    with mundo.base.transaccion() as cx:
        cx.execute(
            "INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, pregunta_norm, "
            "opciones_json, creada) VALUES (?, ?, ?, ?, ?, 'x')",
            (usuario.id, pid, pregunta, norma, opciones),
        )


def esperando_usuario(mundo, pid):
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = 'esperando_usuario' WHERE id = ?", (pid,))


def preguntar(mundo, usuario):
    correr(mundo.c.notificar({"tipo": "preguntas_pendientes", "usuario_id": usuario.id}))


@respx.mock
def test_pregunta_de_texto_libre_borra_lo_escrito_y_la_card_vuelve_a_la_cola(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    esperando_usuario(mundo, pid)
    pendiente(mundo, usuario, pid, "¿Por qué te interesa?", "por que te interesa")
    preguntar(mundo, usuario)
    texto, botones = card_de(mundo, mensaje)
    assert "Pregunta rápida" in texto and "Escribe tu respuesta." in texto and botones is None
    assert "(1 de 1)" not in texto
    antes = len(mundo.s.mensajes)
    correr(mundo.c.al_texto(ANA, "Quiero aprender soporte", 77))
    assert (ANA, 77) in mundo.s.borrados
    assert len(mundo.s.mensajes) == antes
    assert mundo.n.pendientes(usuario.id) == []
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    assert "En cola" in card_de(mundo, mensaje)[0]
    assert card_guardada(mundo, pid).fase == tp.EN_COLA


@respx.mock
def test_varias_preguntas_avanzan_en_la_misma_card(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    esperando_usuario(mundo, pid)
    pendiente(mundo, usuario, pid, "¿Tienes moto?", "tienes moto", '["Sí", "No"]')
    pendiente(mundo, usuario, pid, "¿Por qué te interesa?", "por que te interesa")
    preguntar(mundo, usuario)
    texto, botones = card_de(mundo, mensaje)
    assert "Pregunta rápida (1 de 2)" in texto and "¿Tienes moto?" in texto
    antes = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, botones[0][0][1]))
    texto, botones = card_de(mundo, mensaje)
    assert "Pregunta rápida (2 de 2)" in texto and "¿Por qué te interesa?" in texto
    assert mundo.n.cola.obtener(pid).estado == E.ESPERANDO_USUARIO
    correr(mundo.c.al_texto(ANA, "Me gusta el soporte", 78))
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    assert len(mundo.s.mensajes) == antes


@respx.mock
def test_texto_fuera_de_turno_no_cambia_la_card_ni_responde(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    esperando_usuario(mundo, pid)
    pendiente(mundo, usuario, pid, "¿Tienes moto?", "tienes moto", '["Sí", "No"]')
    preguntar(mundo, usuario)
    mensajes, ediciones = len(mundo.s.mensajes), len(mundo.s.ediciones)
    correr(mundo.c.al_texto(ANA, "hola", 88))  # la card espera un botón, no texto
    assert (ANA, 88) in mundo.s.borrados
    assert len(mundo.s.mensajes) == mensajes and len(mundo.s.ediciones) == ediciones
    assert len(mundo.n.pendientes(usuario.id)) == 1


# --- respaldo -----------------------------------------------------------------------------------


@respx.mock
def test_respaldo_manual_la_card_resume_y_el_paquete_va_aparte(mundo):
    usuario = preparar_toque(mundo, automatico=False)
    pid, enviados = tocar(mundo, usuario)
    cards = [m for m in enviados if "No puedo postularla sola" in m[1]]
    assert len(cards) == 1 and enviados[0] is cards[0]
    assert "esta plataforma todavía no admite postulación automática" in cards[0][1]
    assert [[texto for texto, _ in fila] for fila in cards[0][2]] == [
        ["Ver vacante", "Pegar preguntas"], ["Ya me postulé", "No me interesa"],
    ]  # fmt: skip
    textos = [m[1] for m in enviados]
    assert not any("Cuando termines" in x or "Te preparo el paquete" in x for x in textos)
    assert any("Mensaje de presentación" in x for x in textos)  # el paquete sigue llegando
    assert mundo.s.documentos  # con su CV adaptado
    assert card_guardada(mundo, pid).fase == tp.RESPALDO


@respx.mock
def test_respaldo_sin_navegador_ofrece_vincularlo_en_la_misma_card(mundo):
    usuario = preparar_toque(mundo, automatico=False)
    mundo.n.camino_automatico = lambda *_: "sin_navegador"
    pid, enviados = tocar(mundo, usuario)
    card = enviados[0]
    assert "Falta vincular tu navegador." in card[1]
    assert card[2][0][0] == ("Vincular navegador", cb("vincular"))


@respx.mock
def test_marcar_el_seguimiento_del_respaldo_deja_el_visto_en_la_card(mundo):
    usuario = preparar_toque(mundo, automatico=False)
    pid, enviados = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    assert correr(mundo.c.al_boton(ANA, cb("seg", pid, "postulada"))) == "Anotado ✅"
    texto, botones = card_de(mundo, mensaje)
    assert botones[1][0] == ("✓ Ya me postulé", cb("seg", pid, "postulada"))
    assert botones[1][1] == ("No me interesa", cb("seg", pid, "descartada"))


def test_el_aviso_al_dueno_del_formulario_desconocido_se_mantiene(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    ev = Evento("resultado", p.id, usuario.id, E.FORMULARIO_DESCONOCIDO)
    correr(mundo.c.notificar(ev))
    correr(mundo.c.esperar_tareas())
    assert any("Postulación" in m for m in mundo.s.de(DUENO))
    assert "formulario" in card_de(mundo)[0]


# --- confirmación, vistas y seguimiento ----------------------------------------------------------


def test_respuestas_y_de_que_trata_son_vistas_de_la_card_con_volver(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    principal = card_de(mundo)[0]
    antes = len(mundo.s.mensajes)

    assert correr(mundo.c.al_boton(ANA, cb("res", p.id, "r"))) is None
    texto, botones = card_de(mundo)
    assert "Tus respuestas" in texto and "<b>SENA</b> 👤" in texto
    assert botones == [[("Volver", cb("res", p.id, "v"))]]

    correr(mundo.c.al_boton(ANA, cb("res", p.id, "d")))
    texto, _ = card_de(mundo)
    assert "Medellín, Antioquia" in texto and "soporte de equipos" in texto

    correr(mundo.c.al_boton(ANA, cb("res", p.id, "v")))
    assert card_de(mundo)[0] == principal
    assert len(mundo.s.mensajes) == antes  # ningún mensaje efímero
    assert not mundo.base.cx.execute("SELECT 1 FROM mensajes_efimeros").fetchall()


def test_vista_de_respuestas_muy_larga_se_recorta_sin_mensajes_nuevos(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    with mundo.base.transaccion() as cx:
        cx.executemany(
            "INSERT INTO respuestas(postulacion_id, campo, pregunta, respuesta, origen) "
            "VALUES (?, NULL, ?, ?, 'ia')",
            [(p.id, f"¿Pregunta larga {i}?", "x" * 450) for i in range(30)],
        )
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    antes = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, cb("res", p.id, "r")))
    texto, _ = card_de(mundo)
    assert len(texto) <= tp.MAX_TEXTO and texto.endswith("…")
    assert len(mundo.s.mensajes) == antes


def test_el_seguimiento_se_marca_en_la_card_y_se_puede_cambiar(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    antes = len(mundo.s.mensajes)
    assert correr(mundo.c.al_boton(ANA, cb("seg", p.id, "entrevista"))) == "Anotado ✅"
    texto, botones = card_de(mundo)
    assert [b[0] for b in botones[1]] == ["✓ Entrevista", "Rechazada"]
    assert "¿Cómo te fue?" not in texto
    correr(mundo.c.al_boton(ANA, cb("seg", p.id, "rechazada")))
    assert [b[0] for b in card_de(mundo)[1][1]] == ["Entrevista", "✓ Rechazada"]
    fila = mundo.base.cx.execute("SELECT seguimiento FROM postulaciones WHERE id = ?", (p.id,))
    assert fila.fetchone()["seguimiento"] == "rechazada"
    assert len(mundo.s.mensajes) == antes


def test_seguimiento_de_otra_persona_no_cambia_nada(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    ediciones = len(mundo.s.ediciones)
    asyncio.run(mundo.c.al_boton(ANA + 1, cb("seg", p.id, "oferta")))
    fila = mundo.base.cx.execute("SELECT seguimiento FROM postulaciones WHERE id = ?", (p.id,))
    assert fila.fetchone()["seguimiento"] is None
    assert len(mundo.s.ediciones) == ediciones
