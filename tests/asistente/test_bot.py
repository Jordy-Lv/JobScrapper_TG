import asyncio
import dataclasses
import io
import json
import re
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
from buscador_vacantes.asistente import vinculos  # noqa: E402
from buscador_vacantes.asistente.campos import RESERVADO  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import E, Evento  # noqa: E402
from buscador_vacantes.asistente.conversacion import Conversacion, cb  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro  # noqa: E402
from buscador_vacantes.asistente.detalle import Detalles, Ritmo  # noqa: E402
from buscador_vacantes.asistente.enlaces import id_corto  # noqa: E402
from buscador_vacantes.asistente.ia import crear_clientes  # noqa: E402
from buscador_vacantes.asistente.membresia import Comprobador  # noqa: E402
from buscador_vacantes.asistente.nucleo import Camino, Nucleo  # noqa: E402
from buscador_vacantes.asistente.recetas import (  # noqa: E402
    barrera_de,
    marcar_barrera,
    proponer_parche,
)
from buscador_vacantes.asistente.respuestas import (  # noqa: E402
    Pregunta,
    aprendida,
    normalizar_pregunta,
    sembrar_banco,
)
from buscador_vacantes.asistente.usuarios import EstadoUsuario  # noqa: E402
from buscador_vacantes.asistente.vacantes import Indice  # noqa: E402
from buscador_vacantes.comun.config import cargar_configuracion  # noqa: E402
from buscador_vacantes.comun.estado import Estado, a_texto  # noqa: E402
from buscador_vacantes.comun.modelo import Vacante  # noqa: E402

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
DUENO = 999
ANA, LUIS, EVA, EXTRANO = 111, 222, 333, 444
URL_LI = "https://co.linkedin.com/jobs/view/4475512580"
FIXTURE_LI = (Path(__file__).parent.parent / "fixtures" / "detalle" / "linkedin.html").read_text(
    "utf-8"
)
CLAVE = "AIzaSyClaveDePrueba1234567890"
MODELOS = "https://generativelanguage.googleapis.com/v1beta/models"


class SalidaFalsa:
    def __init__(self):
        self.mensajes = []  # (chat, texto, botones)
        self.ediciones = []
        self.botones_editados = {}  # mensaje → botones de su última edición
        self.documentos = []
        self.borrados = []
        self.efectos = {}  # mensaje → efecto con el que se envió
        self._id = 0

    async def enviar(self, chat_id, texto, botones=None, efecto=None):
        self._id += 1
        self.mensajes.append((chat_id, texto, botones))
        if efecto:
            self.efectos[self._id] = efecto
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
    configuracion.asistente.cuenta_regresiva_segundos = 0  # las pruebas de la cuenta la activan
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
    """Camino corto: "Información correcta", solo las preguntas que faltan y vincula el navegador"""
    await hasta_resumen(m, tid, payload=payload)
    await m.c.al_boton(tid, cb("resumen", "ok"))
    await responder_faltantes(m, tid)
    await m.c.al_boton(tid, cb("vincular"))
    usuario = m.n.usuarios.obtener(tid)
    await m.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})
    await omitir_plataformas(m, tid)
    await m.c.esperar_tareas()


async def omitir_plataformas(m, tid):
    """Cierra el paso de plataformas del alta si sigue abierto (las pruebas que no lo ejercitan)."""
    if m.n.usuarios.obtener(tid).paso_alta == "plataformas":
        await m.c.al_boton(tid, cb("omitir_plat"))


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
    assert "Mensaje de presentación" not in mensajes and "Respuestas típicas" not in mensajes
    assert not mundo.s.documentos  # LinkedIn no se postula sola y ya no se envía paquete
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


def test_detalle_muestra_pasos_respuestas_y_cv(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    mundo.s.documentos.clear()
    correr(mundo.c.al_comando(ANA, "detalle", [str(p.id)]))
    texto = mundo.s.de(ANA)[-1]
    assert "Pasos" in texto and "Preguntas y respuestas" in texto
    assert mundo.s.documentos and mundo.s.documentos[0][1].startswith("CV_")


def test_borrarme(mundo):
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_comando(ANA, "borrarme", []))
    assert "elimínalo desde Telegram" in mundo.s.mensajes[-1][1]
    correr(mundo.c.al_boton(ANA, cb("borrarme")))
    assert mundo.n.usuarios.obtener(ANA) is None


PDF = b"%PDF-1.4 certificado de notas de Ana"


def botones_enviados(mundo, chat=ANA):
    return [b for fila in (mundo.s.ultimo(chat)[2] or []) for b in fila]


def test_documentos_vacio_ofrece_subir_y_la_ayuda_lo_menciona(mundo):
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_comando(ANA, "documentos", []))
    assert "No tienes documentos guardados" in mundo.s.mensajes[-1][1]
    assert ("➕ Subir un documento", cb("doc", "subir")) in botones_enviados(mundo)
    assert "/documentos" in t.AYUDA


def test_subir_un_documento_con_tipo_listarlo_y_borrarlo(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    correr(mundo.c.al_boton(ANA, cb("doc", "subir")))
    assert t.DOCUMENTOS_ELEGIR_TIPO in mundo.s.mensajes[-1][1]
    correr(mundo.c.al_boton(ANA, cb("doc", "tipo", "certificado_notas")))
    assert "Envíame el PDF" in mundo.s.mensajes[-1][1]
    correr(mundo.c.al_documento(ANA, PDF, "notas.pdf"))
    assert "Guardé tu documento" in mundo.s.mensajes[-1][1]
    [doc] = mundo.n.documentos.listar(usuario.id)
    assert (doc.tipo, doc.etiqueta, doc.bytes) == (
        "certificado_notas", "Certificado de notas", len(PDF)
    )
    assert mundo.n.documentos.leer(doc) == PDF
    # El archivo en disco está cifrado: no es el PDF en claro ni lo contiene
    en_disco = doc.ruta.read_bytes()
    assert not en_disco.startswith(b"%PDF") and b"certificado de notas" not in en_disco
    correr(mundo.c.al_comando(ANA, "documentos", []))
    assert "Certificado de notas" in mundo.s.mensajes[-1][1]
    correr(mundo.c.al_boton(ANA, cb("doc", "borrar", doc.id)))
    assert mundo.n.documentos.listar(usuario.id) == [] and not doc.ruta.exists()
    assert "No tienes documentos guardados" in mundo.s.mensajes[-1][1]


def test_documento_de_tipo_otro_pide_nombre_y_uno_nuevo_reemplaza_al_del_mismo_tipo(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    correr(mundo.c.al_boton(ANA, cb("doc", "tipo", "otro")))
    assert "¿Cómo se llama" in mundo.s.mensajes[-1][1]
    correr(mundo.c.al_texto(ANA, "Certificado  de inglés"))
    correr(mundo.c.al_documento(ANA, PDF, "ingles.pdf"))
    [otro] = mundo.n.documentos.listar(usuario.id)
    assert (otro.tipo, otro.etiqueta) == ("otro", "Certificado de inglés")
    for contenido in (PDF, PDF + b" v2"):  # subir otra vez el mismo tipo lo reemplaza
        correr(mundo.c.al_boton(ANA, cb("doc", "tipo", "carta")))
        correr(mundo.c.al_documento(ANA, contenido, "carta.pdf"))
    cartas = [d for d in mundo.n.documentos.listar(usuario.id) if d.tipo == "carta"]
    assert len(cartas) == 1 and mundo.n.documentos.leer(cartas[0]) == PDF + b" v2"
    assert len(mundo.n.documentos.listar(usuario.id)) == 2


def test_documento_que_no_es_pdf_o_es_muy_grande_se_rechaza(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    correr(mundo.c.al_boton(ANA, cb("doc", "tipo", "portafolio")))
    correr(mundo.c.al_documento(ANA, b"no soy un pdf", "x.pdf"))
    assert "no es un PDF" in mundo.s.mensajes[-1][1]
    grande = b"%PDF" + b"0" * int(mundo.c.config.cv.max_mb * 1024 * 1024)
    correr(mundo.c.al_documento(ANA, grande, "x.pdf"))
    assert "supera" in mundo.s.mensajes[-1][1]
    assert mundo.n.documentos.listar(usuario.id) == []


def test_documentos_son_del_usuario_y_se_borran_con_la_cuenta(mundo):
    correr(alta_completa(mundo, ANA))
    correr(alta_completa(mundo, LUIS))
    ana, luis = mundo.n.usuarios.obtener(ANA), mundo.n.usuarios.obtener(LUIS)
    doc = mundo.n.documentos.guardar(ana, "carta", "Carta", PDF, T0)
    assert mundo.n.documentos.obtener(luis.id, doc.id) is None
    correr(mundo.c.al_boton(LUIS, cb("doc", "borrar", doc.id)))  # no es suyo: no se borra
    assert mundo.n.documentos.obtener(ana.id, doc.id) is not None
    correr(mundo.c.al_boton(ANA, cb("borrarme")))
    assert not doc.ruta.exists()
    assert mundo.base.cx.execute("SELECT COUNT(*) FROM documentos_usuario").fetchone()[0] == 0


def test_documento_enviado_sin_pedirlo_no_se_guarda(mundo):
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_documento(ANA, PDF, "x.pdf"))
    assert "usa /perfil" in mundo.s.mensajes[-1][1]
    assert mundo.n.documentos.listar(mundo.n.usuarios.obtener(ANA).id) == []


def test_limite_de_documentos_por_usuario(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    for n in range(10):
        mundo.n.documentos.guardar(usuario, "otro", f"Doc {n}", PDF, T0)
    correr(mundo.c.al_boton(ANA, cb("doc", "tipo", "portafolio")))
    correr(mundo.c.al_documento(ANA, PDF, "x.pdf"))
    assert "Ya tienes 10 documentos" in mundo.s.mensajes[-1][1]


def esperando_documento(mundo):
    """Postulación con card 42 que espera el certificado de notas que pide el formulario."""
    usuario, p = encolar_con_card_42(mundo)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = ? WHERE id = ?",
                   (E.ESPERANDO_USUARIO.value, p.id))  # fmt: skip
    notas = Pregunta("Please upload a copy of your unofficial university transcripts.", "archivo")
    mundo.n._crear_pendientes_documento(usuario.id, p.id, [notas])
    correr(mundo.c.notificar({"tipo": "preguntas_pendientes", "usuario_id": usuario.id,
                              "postulacion_id": p.id}))  # fmt: skip
    return usuario, p


def test_documento_obligatorio_se_pide_en_la_card_y_al_enviarlo_la_postulacion_sigue(mundo):
    usuario, p = esperando_documento(mundo)
    texto = [e[2] for e in mundo.s.ediciones if e[1] == 42][-1]
    assert "Documento necesario" in texto and "transcripts" in texto
    botones = [b for fila in mundo.s.botones_editados[42] for b in fila]
    assert [b[0] for b in botones][:2] == [tp.BOTON_ENVIAR_DOCUMENTO, tp.BOTON_DOCUMENTO_RESPALDO]
    correr(mundo.c.al_documento(ANA, PDF, "notas.pdf"))  # el PDF que esperaba la card
    [doc] = mundo.n.documentos.listar(usuario.id)
    assert doc.tipo == "certificado_notas" and mundo.n.documentos.leer(doc) == PDF
    assert mundo.n.pendientes(usuario.id) == []
    assert mundo.n.cola.obtener(p.id).estado == E.EN_COLA


def test_el_boton_enviar_documento_vuelve_a_pedir_el_pdf(mundo):
    usuario, p = esperando_documento(mundo)
    pendiente = mundo.n.pendientes(usuario.id)[0]
    mundo.c._esperar(usuario, None)  # se perdió la espera
    correr(mundo.c.al_boton(ANA, cb("docp", pendiente["id"])))
    assert "Envíame el PDF" in mundo.s.mensajes[-1][1]
    correr(mundo.c.al_documento(ANA, PDF, "notas.pdf"))
    assert mundo.n.cola.obtener(p.id).estado == E.EN_COLA


def test_dejar_el_documento_en_respaldo_cierra_la_card_con_documento_faltante(mundo):
    usuario, p = esperando_documento(mundo)
    pendiente = mundo.n.pendientes(usuario.id)[0]
    correr(mundo.c.al_boton(ANA, cb("docr", pendiente["id"])))
    assert mundo.n.cola.obtener(p.id).estado == E.RESPALDO
    assert mundo.n.pendientes(usuario.id) == []
    assert mundo.n.documentos.listar(usuario.id) == []
    visto = " ".join(m[1] for m in mundo.s.mensajes[-3:])
    visto += " ".join(e[2] for e in mundo.s.ediciones)
    assert "documento obligatorio" in visto


def encolar_con_card_42(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), None, T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET mensaje_id = 42 WHERE id = ?", (p.id,))
    return usuario, p


def test_resultado_enviado_reemplaza_la_card_por_una_con_confeti(mundo):
    usuario, p = encolar_con_card_42(mundo)
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    assert len(mundo.s.mensajes) == enviados + 1  # una sola card nueva, no un aviso aparte
    nuevo = mundo.s._id
    texto = mundo.s.ultimo(ANA)[1]
    assert "✅ <b>Postulación enviada</b>" in texto and "confirmó tu postulación" in texto
    assert "Folio P-" in texto and "100 %" in texto and "¿Cómo te fue?" not in texto
    assert mundo.s.efectos == {nuevo: t.EFECTO_CONFETI}
    assert (ANA, 42) in mundo.s.borrados
    assert not any(m == 42 for _, m, _ in mundo.s.ediciones)
    assert f'"mensaje_id": {nuevo}' in mundo.n.base.kv_obtener(f"card:{p.id}")
    assert mundo.c._mensaje_de(p.id) == nuevo


def test_el_confeti_se_entrega_aunque_no_se_pueda_borrar_la_card_vieja(mundo):
    usuario, p = encolar_con_card_42(mundo)

    async def no_borra(chat, mensaje):
        raise RuntimeError("message to delete not found")

    mundo.s.borrar = no_borra
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    assert mundo.s.efectos == {mundo.s._id: t.EFECTO_CONFETI}
    assert f'"mensaje_id": {mundo.s._id}' in mundo.n.base.kv_obtener(f"card:{p.id}")


def test_las_vistas_despues_del_confeti_editan_sin_repetir_el_efecto(mundo):
    usuario, p = encolar_con_card_42(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    nuevo, enviados = mundo.s._id, len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, cb("res", p.id, "r")))
    assert "Tus respuestas" in mundo.s.ediciones[-1][2] and mundo.s.ediciones[-1][1] == nuevo
    correr(mundo.c.al_boton(ANA, cb("res", p.id, "v")))
    assert "Postulación enviada" in mundo.s.ediciones[-1][2]
    assert len(mundo.s.mensajes) == enviados and list(mundo.s.efectos) == [nuevo]


def test_resultado_incierto_edita_la_card_en_el_lugar_sin_confeti(mundo):
    usuario, p = encolar_con_card_42(mundo)
    enviados = len(mundo.s.mensajes)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.INCIERTA)))
    assert any(
        m == 42 and "no mostró la confirmación" in texto for _, m, texto in mundo.s.ediciones
    )
    assert len(mundo.s.mensajes) == enviados and not mundo.s.efectos
    assert (ANA, 42) not in mundo.s.borrados


def test_confirmada_calcula_la_duracion_desde_que_se_tomo(mundo):
    usuario, p = encolar_con_card_42(mundo)
    with mundo.base.transaccion() as cx:
        cx.execute(
            "UPDATE postulaciones SET tomada_en = ?, terminada_en = ? WHERE id = ?",
            (a_texto(T0), a_texto(T0 + timedelta(seconds=75)), p.id),
        )
    datos, _ = mundo.c._datos_resumen(mundo.n.cola.obtener(p.id))
    assert datos.duracion_s == 75 and datos.folio == f"P-{p.id}"
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET tomada_en = NULL WHERE id = ?", (p.id,))
    datos, _ = mundo.c._datos_resumen(mundo.n.cola.obtener(p.id))
    assert datos.duracion_s is None


def test_resumen_cuenta_que_la_cuota_bajo_el_nivel_de_la_postulacion(mundo):
    usuario, p = encolar_con_card_42(mundo)
    assert mundo.c._datos_resumen(mundo.n.cola.obtener(p.id))[0].nivel_bajado is None
    with mundo.base.transaccion() as cx:
        for detalle in ("maximo>normal", "maximo>ahorro"):  # la cuota siguió agotándose
            cx.execute(
                "INSERT INTO postulacion_pasos(postulacion_id, ts, paso, estado, detalle) "
                "VALUES (?, ?, 'nivel_bajado', 'ok', ?)",
                (p.id, a_texto(T0), detalle),
            )
    datos, _ = mundo.c._datos_resumen(mundo.n.cola.obtener(p.id))
    assert datos.nivel_bajado == "ahorro"


def test_resumen_cuenta_las_respuestas_que_ajusto_el_revisor(mundo):
    usuario, p = encolar_con_card_42(mundo)
    with mundo.base.transaccion() as cx:
        for n in ("2", "1", "x"):  # dos pasadas del formulario; un detalle ajeno se ignora
            cx.execute(
                "INSERT INTO postulacion_pasos(postulacion_id, ts, paso, estado, detalle) "
                "VALUES (?, ?, 'respuestas_revisadas', 'ok', ?)",
                (p.id, a_texto(T0), n),
            )
    datos, _ = mundo.c._datos_resumen(mundo.n.cola.obtener(p.id))
    assert datos.revisadas == 3


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


def test_ia_nivel_muestra_los_tres_niveles_con_su_consumo_y_el_uso_de_hoy(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    with mundo.base.transaccion() as cx:
        cx.executemany(
            "INSERT INTO ia_uso(usuario_id, ts, tarea, ok, tokens_in, tokens_out) "
            "VALUES (?, ?, 'redactar', ?, ?, ?)",
            [
                (usuario.id, a_texto(T0), 1, 1000, 234),
                (usuario.id, a_texto(T0), 1, 500, 66),
                (usuario.id, a_texto(T0), 0, 900, 0),  # fallida: no cuenta
                (usuario.id, a_texto(T0 - timedelta(days=1)), 1, 5000, 5000),  # de ayer
            ],
        )
    correr(mundo.c.al_comando(ANA, "ia", ["nivel"]))
    _, texto, botones = mundo.s.ultimo(ANA)
    niveles = mundo.n.config.niveles_ia
    for nombre, nivel in (("Ahorro", niveles.ahorro), ("Normal", niveles.normal),
                          ("Máximo", niveles.maximo)):  # fmt: skip
        assert f"<b>{nombre}</b> · ~{nivel.llamadas_estimadas} llamadas por postulación" in texto
    assert "Hoy llevas 2 llamadas y 1800 tokens" in texto
    # Normal es el nivel por defecto y es el único marcado
    assert "✅ <b>Normal</b>" in texto
    assert "✅ <b>Ahorro</b>" not in texto and "✅ <b>Máximo</b>" not in texto
    assert [(b[0][0], b[0][1]) for b in botones] == [
        ("Ahorro", cb("ia", "ahorro")), ("✅ Normal", cb("ia", "normal")),
        ("Máximo", cb("ia", "maximo")),
    ]  # fmt: skip


def test_ia_nivel_cambia_el_nivel_y_lo_marca(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    assert mundo.n.preferencias.nivel_ia(usuario.id) == "normal"
    aviso = correr(mundo.c.al_boton(ANA, cb("ia", "maximo")))
    assert aviso == "Nivel Máximo"
    assert mundo.n.preferencias.nivel_ia(usuario.id) == "maximo"
    _, texto, botones = mundo.s.ultimo(ANA)
    assert "✅ <b>Máximo</b>" in texto and "✅ <b>Normal</b>" not in texto
    assert botones[2][0][0] == "✅ Máximo"
    # Un nivel que no existe no cambia nada
    assert correr(mundo.c.al_boton(ANA, cb("ia", "enorme"))) is None
    assert mundo.n.preferencias.nivel_ia(usuario.id) == "maximo"
    correr(mundo.c.al_comando(ANA, "ia", ["otra"]))
    assert "/ia nivel" in mundo.s.ultimo(ANA)[1]


def test_cambiar_el_nivel_no_afecta_una_postulacion_en_curso(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    antes, _ = mundo.n.cola.encolar(usuario.id, id_corto("computrabajo:1"), "computrabajo", T0)
    assert antes.nivel_ia == "normal"  # copiado del usuario al encolar
    # La postulación sale: se toma y arranca con el nivel con que se encoló
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = ? WHERE id = ?", (E.EN_CURSO, antes.id))
    correr(mundo.c.al_boton(ANA, cb("ia", "ahorro")))
    despues, _ = mundo.n.cola.encolar(usuario.id, id_corto("computrabajo:2"), "computrabajo", T0)
    correr(mundo.c.al_boton(ANA, cb("ia", "maximo")))
    siguiente, _ = mundo.n.cola.encolar(usuario.id, id_corto("computrabajo:3"), "computrabajo", T0)
    perfil = mundo.n.cola.encolar_completar_perfil(usuario.id, "computrabajo", T0)
    nivel = lambda pid: mundo.n.cola.obtener(pid).nivel_ia  # noqa: E731
    assert nivel(antes.id) == "normal"  # la que ya estaba en curso no cambió
    assert nivel(despues.id) == "ahorro"
    assert nivel(siguiente.id) == "maximo"
    assert nivel(perfil) == "maximo"
    # Un toque repetido sobre una vacante ya encolada devuelve la existente, sin tocar su nivel
    repetida, creada = mundo.n.cola.encolar(
        usuario.id, id_corto("computrabajo:1"), "computrabajo", T0
    )
    assert not creada and repetida.nivel_ia == "normal"


def test_la_ayuda_menciona_ia_nivel(mundo):
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_comando(ANA, "ayuda", []))
    assert "/ia nivel" in mundo.s.ultimo(ANA)[1]


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


def card_de(mundo, mensaje=None):
    """Texto y botones actuales de la card: la fixture le dio el mensaje 42 y, al confirmarse,
    la card pasa a un mensaje nuevo (con confeti) que se edita desde ahí."""
    mensaje = mensaje or max(mundo.s.efectos, default=42)
    texto = next((e[2] for e in reversed(mundo.s.ediciones) if e[1] == mensaje), None)
    if texto is not None:
        return texto, mundo.s.botones_editados[mensaje]
    _, texto, botones = mundo.s.mensajes[mensaje - 1]  # enviada y sin editar
    return texto, botones


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
        ("Generar guía para entrevista", cb("guia", p.id)),
    ]]  # fmt: skip
    assert "¿Cómo te fue?" not in texto
    assert mundo.s.documentos == [(ANA, cv.name)]
    assert len(mundo.s.mensajes) == enviados + 1  # solo la card nueva, con el confeti
    assert mundo.s.efectos == {mundo.s._id: t.EFECTO_CONFETI}


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


def test_portal_que_no_proceso_aplicar_ofrece_reintentar_sin_avisar_al_dueno(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), "magneto", T0)
    ev = Evento("resultado", p.id, usuario.id, E.FORMULARIO_DESCONOCIDO, "aplicar_sin_efecto")
    correr(mundo.c.notificar(ev))
    correr(mundo.c.esperar_tareas())
    chat, texto, botones = mundo.s.ultimo(ANA)
    assert "Magneto no cargó la postulación" in texto and "No envié nada todavía" in texto
    assert botones == [[("Reintentar", cb("rei", p.id))]]
    assert not mundo.s.de(DUENO)  # el portal falló, no el formulario: no se avisa al dueño


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
    assert p.id not in mundo.c._animaciones
    porcentajes = [int(m.group(1)) for x in textos if (m := re.search(r"(\d+) %", x))]
    assert porcentajes and porcentajes == sorted(porcentajes) and porcentajes[-1] <= 99
    assert all("~" in x and "░" in x for x in textos)
    assert (ANA, 42) in mundo.s.borrados
    assert "Postulación enviada" in mundo.s.ultimo(ANA)[1] and mundo.s.efectos


def test_paso_cv_con_botones_adjuntar_y_desde_cero_proximamente(mundo):
    correr(alta_completa(mundo, ANA))
    _, texto, botones = next(m for m in mundo.s.mensajes if "Paso 3 de 6" in m[1])
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


async def hasta_navegador(mundo, tid, *, payload=None):
    """Alta hasta el paso del navegador (sin vincularlo)."""
    await hasta_resumen(mundo, tid, payload=payload)
    await mundo.c.al_boton(tid, cb("resumen", "ok"))
    await responder_faltantes(mundo, tid)


async def avisar_vinculado(mundo, tid):
    usuario = mundo.n.usuarios.obtener(tid)
    await mundo.c.al_boton(tid, cb("vincular"))
    await mundo.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})
    return usuario


def vacante_de_portal(mundo, plataforma):
    """La vacante de la prueba es de LinkedIn: el índice la entrega como del portal dado."""
    original = mundo.n.indice.resolver

    def resolver(corto, ahora):
        vacante = original(corto, ahora)
        return dataclasses.replace(vacante, plataforma=plataforma) if vacante else vacante

    mundo.n.indice.resolver = resolver


def tarjetas_de_conexion(mundo):
    return [m for m in mundo.s.mensajes if "Conexión con tus portales" in m[1]]


def test_al_vincular_el_navegador_el_alta_pasa_al_paso_de_plataformas(mundo):
    mundo.n.enlace_grupo = "https://t.me/+abc"

    async def flujo():
        await hasta_navegador(mundo, ANA)
        await avisar_vinculado(mundo, ANA)

    correr(flujo())
    usuario = mundo.n.usuarios.obtener(ANA)
    assert usuario.estado == EstadoUsuario.ALTA and usuario.paso_alta == "plataformas"
    assert not any(m[1] == t.ALTA_LISTA for m in mundo.s.mensajes)  # el alta sigue abierta
    tarjetas = tarjetas_de_conexion(mundo)
    assert len(tarjetas) == 1
    _, texto, botones = tarjetas[0]
    assert "Paso 6 de 6" in texto and "✓ Navegador vinculado" in texto
    for portal in ("🔵 Computrabajo", "🟢 Magneto", "🩵 elempleo"):
        assert f"· {portal}: inicia sesión" in texto
    assert botones == [[("Omitir por ahora", cb("omitir_plat"))]]


@respx.mock
def test_al_vincular_con_vacante_de_un_portal_automatico_no_arranca_la_postulacion(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    vacante_de_portal(mundo, "magneto")

    async def flujo():
        await hasta_navegador(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        await avisar_vinculado(mundo, ANA)
        await mundo.c.esperar_tareas()

    correr(flujo())
    usuario = mundo.n.usuarios.obtener(ANA)
    assert usuario.estado == EstadoUsuario.ALTA
    assert usuario.vacante_pendiente == id_corto("linkedin:1")
    assert postulaciones(mundo) == []
    texto = tarjetas_de_conexion(mundo)[0][1]
    assert "Tu vacante es de <b>Magneto</b>" in texto
    assert "👉 <b>🟢 Magneto</b>: inicia sesión" in texto
    assert "· 🔵 Computrabajo (opcional): inicia sesión" in texto


def test_sin_vacante_basta_confirmar_una_cuenta_y_cierra_con_el_mensaje_al_grupo(mundo):
    mundo.n.enlace_grupo = "https://t.me/+abc"

    async def flujo():
        await hasta_navegador(mundo, ANA)
        usuario = await avisar_vinculado(mundo, ANA)
        await mundo.c.notificar(aviso_cuenta(usuario, "computrabajo", "ana@gmail.com"))
        assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ALTA  # por confirmar
        await mundo.c.al_boton(ANA, cb("cuenta", "computrabajo", "si"))

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ACTIVO
    cierres = [m for m in mundo.s.mensajes if m[1] == t.ALTA_LISTA]
    assert len(cierres) == 1 and cierres[0][2] == [[("👥 Ir al grupo", "url:https://t.me/+abc")]]
    ultima = mundo.s.ediciones[-1][2]
    assert "Paso 6" not in ultima and "Omitir" not in str(mundo.s.botones_editados)
    assert "✓ 🔵 Computrabajo" in ultima and "Magneto" not in ultima  # sin los portales sembrados


def test_el_aviso_de_portal_listo_tambien_cumple_el_paso(mundo):
    async def flujo():
        await hasta_navegador(mundo, ANA)
        usuario = await avisar_vinculado(mundo, ANA)
        await mundo.c.notificar(aviso_cuenta(usuario, "elempleo", "ana@gmail.com", "portal_listo"))

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ACTIVO
    assert any(m[1] == t.ALTA_LISTA for m in mundo.s.mensajes)


def test_el_aviso_de_perfil_incompleto_tambien_cumple_el_paso(mundo):
    async def flujo():
        await hasta_navegador(mundo, ANA)
        usuario = await avisar_vinculado(mundo, ANA)
        await mundo.c.notificar(
            aviso_cuenta(usuario, "magneto", "ana@gmail.com", "portal_incompleto")
        )

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ACTIVO


@respx.mock
def test_con_vacante_solo_cuenta_la_plataforma_de_la_vacante(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    mundo.n.camino_automatico = lambda *_: None
    vacante_de_portal(mundo, "elempleo")

    async def flujo():
        await hasta_navegador(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        usuario = await avisar_vinculado(mundo, ANA)
        await mundo.c.notificar(aviso_cuenta(usuario, "magneto", "ana@gmail.com", "portal_listo"))
        await mundo.c.esperar_tareas()
        otra = (mundo.n.usuarios.obtener(ANA).estado, postulaciones(mundo))
        await mundo.c.notificar(aviso_cuenta(usuario, "elempleo", "ana@gmail.com", "portal_listo"))
        await mundo.c.esperar_tareas()
        return otra

    estado_antes, antes = correr(flujo())
    assert estado_antes == EstadoUsuario.ALTA and antes == []  # otra plataforma: sigue abierto
    usuario = mundo.n.usuarios.obtener(ANA)
    assert usuario.estado == EstadoUsuario.ACTIVO and usuario.vacante_pendiente is None
    assert len(postulaciones(mundo)) == 1  # la de la plataforma esperada arranca
    assert not any(m[1] == t.ALTA_LISTA for m in mundo.s.mensajes)


@respx.mock
def test_omitir_con_vacante_cierra_el_alta_y_encola_la_vacante(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    mundo.n.camino_automatico = lambda *_: None
    vacante_de_portal(mundo, "magneto")

    async def flujo():
        await hasta_navegador(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        await avisar_vinculado(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("omitir_plat"))
        await mundo.c.esperar_tareas()

    correr(flujo())
    usuario = mundo.n.usuarios.obtener(ANA)
    assert usuario.estado == EstadoUsuario.ACTIVO and usuario.vacante_pendiente is None
    assert len(postulaciones(mundo)) == 1
    assert not any(m[1] == t.ALTA_LISTA for m in mundo.s.mensajes)


def test_el_cierre_del_alta_sin_enlace_al_grupo_no_lleva_boton(mundo):
    mundo.n.enlace_grupo = None

    async def flujo():
        await hasta_navegador(mundo, ANA)
        await avisar_vinculado(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("omitir_plat"))

    correr(flujo())
    cierres = [m for m in mundo.s.mensajes if m[1] == t.ALTA_LISTA]
    assert len(cierres) == 1 and cierres[0][2] is None


def test_omitir_sin_vacante_cierra_el_alta_con_el_mensaje_al_grupo(mundo):
    async def flujo():
        await hasta_navegador(mundo, ANA)
        await avisar_vinculado(mundo, ANA)
        await mundo.c.al_boton(ANA, cb("omitir_plat"))
        await mundo.c.al_boton(ANA, cb("omitir_plat"))  # un botón viejo ya no hace nada

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ACTIVO
    assert len([m for m in mundo.s.mensajes if m[1] == t.ALTA_LISTA]) == 1


@respx.mock
def test_el_paso_se_salta_si_la_cuenta_esperada_ya_tenia_la_sesion_abierta(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    mundo.n.camino_automatico = lambda *_: None
    vacante_de_portal(mundo, "magneto")
    portales = json.dumps({"magneto": {"estado": "listo", "cuenta": "ok"}})

    async def flujo():
        await hasta_navegador(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        usuario = mundo.n.usuarios.obtener(ANA)
        with mundo.n.base.transaccion() as cx:  # reinstalación: el latido ya reportó la sesión
            cx.execute(
                "INSERT INTO navegadores(usuario_id, token_hash, creado, ultimo_latido, "
                "portales_json) VALUES (?, 'h', 'x', 'x', ?)",
                (usuario.id, portales),
            )
        await mundo.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})
        await mundo.c.esperar_tareas()

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ACTIVO
    assert len(postulaciones(mundo)) == 1


@respx.mock
def test_la_sesion_cerrada_en_el_ultimo_latido_no_salta_el_paso(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    vacante_de_portal(mundo, "magneto")
    portales = json.dumps({"magneto": {"estado": "sin_sesion", "cuenta": "ok"}})

    async def flujo():
        await hasta_navegador(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        usuario = mundo.n.usuarios.obtener(ANA)
        with mundo.n.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO navegadores(usuario_id, token_hash, creado, ultimo_latido, "
                "portales_json) VALUES (?, 'h', 'x', 'x', ?)",
                (usuario.id, portales),
            )
        await mundo.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id})

    correr(flujo())
    assert mundo.n.usuarios.obtener(ANA).estado == EstadoUsuario.ALTA


@respx.mock
def test_el_paso_se_salta_si_la_plataforma_de_la_vacante_no_es_automatica(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    vacante_de_portal(mundo, "magneto")
    mundo.n.config.plataformas["magneto"].automatica = False

    async def flujo():
        await hasta_navegador(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        await avisar_vinculado(mundo, ANA)
        await mundo.c.esperar_tareas()

    correr(flujo())
    usuario = mundo.n.usuarios.obtener(ANA)
    assert usuario.estado == EstadoUsuario.ACTIVO and usuario.vacante_pendiente is None
    assert len(postulaciones(mundo)) == 1  # sigue su camino de respaldo


@respx.mock
def test_start_durante_el_paso_reenvia_la_tarjeta_y_avisa_que_la_vacante_sigue_guardada(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    vacante_de_portal(mundo, "magneto")
    corta = id_corto("linkedin:1")

    async def flujo():
        await hasta_navegador(mundo, ANA, payload="v_" + corta)
        await avisar_vinculado(mundo, ANA)
        antes = len(mundo.s.mensajes)
        anterior = mundo.n.base.kv_obtener(f"tarjeta:{mundo.n.usuarios.obtener(ANA).id}")
        await mundo.c.al_iniciar(ANA, "Ana", "v_" + corta)
        return antes, json.loads(anterior)["mensaje_id"]

    antes, mensaje_anterior = correr(flujo())
    nuevos_ = mundo.s.mensajes[antes:]
    assert len(nuevos_) == 2
    assert "sigue guardada" in nuevos_[0][1]
    assert "Paso 6 de 6" in nuevos_[1][1]  # la tarjeta nueva queda al final
    assert (ANA, mensaje_anterior) in mundo.s.borrados
    usuario = mundo.n.usuarios.obtener(ANA)
    assert usuario.vacante_pendiente == corta and usuario.paso_alta == "plataformas"
    guardada = json.loads(mundo.n.base.kv_obtener(f"tarjeta:{usuario.id}"))
    assert guardada["mensaje_id"] != mensaje_anterior


@respx.mock
def test_start_durante_el_paso_tolera_no_poder_borrar_la_tarjeta_anterior(mundo):
    vacante_de_portal(mundo, "magneto")

    async def borrar(*_):
        raise RuntimeError("mensaje demasiado viejo")

    mundo.s.borrar = borrar

    async def flujo():
        await hasta_navegador(mundo, ANA)
        await avisar_vinculado(mundo, ANA)
        await mundo.c.al_iniciar(ANA, "Ana", None)

    correr(flujo())
    assert len(tarjetas_de_conexion(mundo)) == 2
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "plataformas"


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
    assert "Paso 5 de 6" not in mensajes.split("Conexión con tus portales")[-1]
    assert "Mensaje de presentación" not in mensajes  # ya no se envía paquete


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
    await omitir_plataformas(m, tid)
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
    assert mensaje == id_tarjeta and "✓ 🔵 Computrabajo · ana@gmail.com" in texto
    assert mundo.s.botones_editados[mensaje] is None  # ya no queda nada por confirmar
    assert not any("quedó asociada" in m[1] or "Sesión iniciada" in m[1] for m in mundo.s.mensajes)


def test_cancelar_la_cuenta_deja_la_linea_pendiente_en_la_tarjeta(mundo):
    async def flujo():
        await hasta_resumen(mundo, ANA)
        usuario = await vincular_navegador(mundo, ANA)
        await mundo.c.notificar(aviso_cuenta(usuario, "magneto", "otra@gmail.com"))
        await mundo.c.al_boton(ANA, cb("cuenta", "magneto", "no"))

    correr(flujo())
    assert "· 🟢 Magneto: inicia sesión con tu cuenta" in mundo.s.ediciones[-1][2]


@respx.mock
def test_la_vacante_del_alta_se_postula_dentro_de_la_misma_tarjeta(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    mundo.c.intervalo_animacion = 0.01
    mundo.n.camino_automatico = lambda *_: None  # la vacante de la prueba es de LinkedIn

    async def flujo():
        await hasta_resumen(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        usuario = await vincular_navegador(mundo, ANA)
        fila = mundo.n.base.cx.execute("SELECT id, mensaje_id FROM postulaciones").fetchone()
        de_plataforma(mundo, fila["id"], "computrabajo")  # el bloque muestra solo su portal
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
    assert any("✓ 🔵 Computrabajo · ana@gmail.com" in x and "Respondiendo el formulario…" in x
               for x in textos)  # fmt: skip
    final = mundo.s.ultimo(ANA)[1]  # la confirmación llega como la card nueva, con confeti
    assert "confirmó tu postulación" in final and "Conexión" not in final
    assert (ANA, fila["mensaje_id"]) in mundo.s.borrados
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
    assert "✓ 🔵 Computrabajo · ana@gmail.com" in texto
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


SALARIO = {"texto": "¿Cuál es tu aspiración salarial?", "nombre": "q_salario"}
DOCKER = {"texto": "¿Tienes experiencia con Docker?", "nombre": "q_docker", "tipo": "opciones",
          "opciones": ["Sí", "No"]}  # fmt: skip


def con_esquema(mundo, *campos):
    mundo.n.indice.guardar_esquema(id_corto("linkedin:1"), list(campos))


@respx.mock
def test_esquema_anticipado_resuelto_sale_a_la_cola_con_las_respuestas_para_la_extension(mundo):
    usuario = preparar_toque(mundo)
    con_esquema(mundo, SALARIO)
    pid, _ = tocar(mundo, usuario)
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA and mundo.n.pendientes(usuario.id) == []
    resuelto = mundo.n.esquema_resuelto(mundo.n.cola.obtener(pid))
    assert resuelto == {"q_salario": "1300000"}


@respx.mock
def test_esquema_anticipado_con_un_dato_que_falta_pregunta_en_la_card_antes_de_encolar(mundo):
    usuario = preparar_toque(mundo)
    con_esquema(mundo, SALARIO, DOCKER)

    async def flujo():
        toque = await mundo.c.procesar_toque(usuario, id_corto("linkedin:1"))
        # Aún sin esperar al resto: la extensión no puede tomarla mientras se resuelve el formulario
        retenida = mundo.n.cola.obtener(toque.postulacion.id).estado
        await mundo.c.esperar_tareas()
        return toque, retenida

    toque, retenida = correr(flujo())
    pid = toque.postulacion.id
    assert retenida == E.ESPERANDO_USUARIO
    assert mundo.n.cola.obtener(pid).estado == E.ESPERANDO_USUARIO
    [pendiente] = mundo.n.pendientes(usuario.id)
    assert pendiente["pregunta"] == DOCKER["texto"] and pendiente["postulacion_id"] == pid
    assert card_guardada(mundo, pid).fase == tp.PREGUNTA
    # El usuario responde en la card y la postulación sale a la cola
    correr(mundo.c.al_boton(ANA, cb("pend", pendiente["id"], 0)))
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    assert mundo.n.esquema_resuelto(mundo.n.cola.obtener(pid)) == {
        "q_salario": "1300000", "q_docker": "Sí",
    }


@respx.mock
def test_vacante_sin_esquema_se_encola_como_siempre(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    assert mundo.n.esquema_resuelto(mundo.n.cola.obtener(pid)) == {}


def de_plataforma(mundo, pid, plataforma):
    """La vacante de la prueba es de LinkedIn: la postulación pasa a ser del portal dado."""
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET plataforma = ? WHERE id = ?", (plataforma, pid))


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
    de_plataforma(mundo, pid, "computrabajo")
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
    assert "✓ 🔵 Computrabajo · ana@gmail.com" in texto and botones is None
    assert len(mundo.s.mensajes) == antes


@respx.mock
def test_cuenta_distinta_ofrece_sus_dos_botones_en_la_card(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    de_plataforma(mundo, pid, "computrabajo")
    mensaje = card_guardada(mundo, pid).mensaje_id
    aviso = aviso_cuenta(usuario, "computrabajo", "ana@gmail.com", "cuenta_distinta")
    aviso["encontrado"] = "l***@hotmail.com"
    correr(mundo.c.notificar(aviso))
    texto, botones = card_de(mundo, mensaje)
    assert "⚠️" in texto and "No postularé con ella" in texto
    assert [b[0] for b in botones[0]] == ["Es mi cuenta nueva", "No es mía"]


# --- conexión limitada al portal de la vacante ---------------------------------------------


def ediciones_de(mundo, mensaje):
    return [e for e in mundo.s.ediciones if e[1] == mensaje]


@respx.mock
def test_vacante_de_magneto_con_computrabajo_confirmado_no_lo_menciona(mundo):
    usuario = preparar_toque(mundo)
    aviso = aviso_cuenta(usuario, "computrabajo", "ana@gmail.com", "portal_listo")
    correr(mundo.c.notificar(aviso))
    pid, _ = tocar(mundo, usuario)
    de_plataforma(mundo, pid, "magneto")
    mensaje = card_guardada(mundo, pid).mensaje_id
    correr(mundo.c.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario.id}))
    texto, botones = card_de(mundo, mensaje)
    assert "Conexión con tus portales" in texto
    assert "· 🟢 Magneto: inicia sesión con tu cuenta en ese navegador" in texto
    assert "Computrabajo" not in texto and botones is None


@respx.mock
def test_cuenta_por_confirmar_del_mismo_portal_va_en_la_card(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    de_plataforma(mundo, pid, "magneto")
    mensaje = card_guardada(mundo, pid).mensaje_id
    antes = len(mundo.s.mensajes)
    correr(mundo.c.notificar(aviso_cuenta(usuario, "magneto", "ana@magneto.co")))
    texto, botones = card_de(mundo, mensaje)
    assert "<b>🟢 Magneto</b>: sesión iniciada con <b>ana@magneto.co</b>" in texto
    assert botones == [[
        ("Confirmar Magneto", cb("cuenta", "magneto", "si")),
        ("Cancelar", cb("cuenta", "magneto", "no")),
    ]]  # fmt: skip
    assert len(mundo.s.mensajes) == antes


@respx.mock
def test_aviso_de_otro_portal_con_la_card_abierta_va_a_un_mensaje_aparte(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    de_plataforma(mundo, pid, "magneto")
    mensaje = card_guardada(mundo, pid).mensaje_id
    correr(mundo.c.notificar(aviso_cuenta(usuario, "magneto", "ana@magneto.co")))
    ediciones_card = len(ediciones_de(mundo, mensaje))
    antes = len(mundo.s.mensajes)

    correr(mundo.c.notificar(aviso_cuenta(usuario, "computrabajo", "ana@gmail.com")))
    assert len(ediciones_de(mundo, mensaje)) == ediciones_card  # la card no cambia
    (chat, texto, botones), = mundo.s.mensajes[antes:]  # fmt: skip
    aparte = mundo.s._id
    assert "Conexión con tus portales" in texto
    assert "<b>🔵 Computrabajo</b>: sesión iniciada con <b>ana@gmail.com</b>" in texto
    assert "Magneto" not in texto
    assert botones == [[
        ("Confirmar Computrabajo", cb("cuenta", "computrabajo", "si")),
        ("Cancelar", cb("cuenta", "computrabajo", "no")),
    ]]  # fmt: skip
    assert mundo.base.kv_obtener(f"tarjeta_otros:{usuario.id}") == str(aparte)

    # Confirmar desde el mensaje aparte lo edita en su sitio, sin tocar la card ni enviar otro
    correr(mundo.c.al_boton(ANA, cb("cuenta", "computrabajo", "si")))
    assert len(mundo.s.mensajes) == antes + 1
    assert len(ediciones_de(mundo, mensaje)) == ediciones_card
    texto, botones = card_de(mundo, aparte)
    assert "✓ 🔵 Computrabajo · ana@gmail.com" in texto and botones is None
    texto, botones = card_de(mundo, mensaje)
    assert "Confirmar Magneto" in botones[0][0][0]  # la card conserva lo suyo

    # Al soltar la card, el mensaje aparte deja de editarse
    correr(mundo.c.notificar(Evento("resultado", pid, usuario.id, E.ENVIADA)))
    assert not mundo.base.kv_obtener(f"tarjeta_otros:{usuario.id}")


@respx.mock
def test_sin_card_abierta_la_tarjeta_muestra_todos_los_portales(mundo):
    usuario = preparar_toque(mundo)
    correr(
        mundo.c.notificar(aviso_cuenta(usuario, "computrabajo", "ana@gmail.com", "portal_listo"))
    )
    correr(mundo.c.notificar(aviso_cuenta(usuario, "magneto", "ana@magneto.co")))
    texto, botones = mundo.s.ediciones[-1][2], mundo.s.botones_editados[mundo.s.ediciones[-1][1]]
    assert "✓ 🔵 Computrabajo · ana@gmail.com" in texto
    assert "<b>🟢 Magneto</b>: sesión iniciada con <b>ana@magneto.co</b>" in texto
    assert botones[0][0] == ("Confirmar Magneto", cb("cuenta", "magneto", "si"))
    assert not mundo.base.kv_obtener(f"tarjeta_otros:{usuario.id}")


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
def test_respaldo_manual_solo_muestra_la_card_sin_paquete(mundo):
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
    assert not any("Mensaje de presentación" in x or "Respuestas típicas" in x for x in textos)
    assert not mundo.s.documentos  # sin CV adaptado: solo se postula de forma automática
    assert len(enviados) == 1  # nada más que la card
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
    assert "¿Cómo te fue?" not in texto
    correr(mundo.c.al_boton(ANA, cb("seg", p.id, "rechazada")))
    fila = mundo.base.cx.execute("SELECT seguimiento FROM postulaciones WHERE id = ?", (p.id,))
    assert fila.fetchone()["seguimiento"] == "rechazada"
    assert len(mundo.s.mensajes) == antes


def test_generar_guia_avisa_en_un_mensaje_aparte_que_viene_pronto(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    antes = len(mundo.s.mensajes)
    correr(mundo.c.al_boton(ANA, cb("guia", p.id)))
    assert len(mundo.s.mensajes) == antes + 1
    assert "próximamente" in mundo.s.ultimo(ANA)[1]


def test_seguimiento_de_otra_persona_no_cambia_nada(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    ediciones = len(mundo.s.ediciones)
    asyncio.run(mundo.c.al_boton(ANA + 1, cb("seg", p.id, "oferta")))
    fila = mundo.base.cx.execute("SELECT seguimiento FROM postulaciones WHERE id = ?", (p.id,))
    assert fila.fetchone()["seguimiento"] is None
    assert len(mundo.s.ediciones) == ediciones


def test_el_boton_cerrar_borra_ya_el_mensaje_efimero_y_libera_el_boton(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    tocar_resumen(mundo, p.id, "r")
    _, _, botones = mundo.s.ultimo(ANA)
    assert botones == [[("Cerrar", cb("cerrar", "res", p.id, "r"))]]
    id_mensaje = mundo.s._id
    correr(mundo.c.al_boton(ANA, botones[0][0][1]))
    assert mundo.s.borrados == [(ANA, id_mensaje)]
    assert mundo.base.cx.execute("SELECT COUNT(*) FROM mensajes_efimeros").fetchone()[0] == 0
    assert tocar_resumen(mundo, p.id, "r") is None  # ya se puede volver a pedir
    correr(mundo.c.al_boton(LUIS, cb("cerrar", "res", p.id, "r")))  # otra persona: nada
    assert len(mundo.s.borrados) == 1


def test_botones_de_proveedores_paginan_de_cuatro_en_cuatro():
    from buscador_vacantes.asistente.conversacion import botones_proveedores

    p0, p1 = botones_proveedores(0), botones_proveedores(1)
    assert len(p0) == 5 and p0[-1] == [("Siguiente ➡️", cb("provpag", 1))]
    assert p0[0][0][1] == cb("prov", "gemini")
    assert len(p1) == 3 and p1[-1] == [("⬅️ Anterior", cb("provpag", 0))]


# --- cuenta regresiva antes de encolar -----------------------------------------------------


INTERVALO_CUENTA = 1.0


class RelojManual:
    """La cuenta espera aquí: cada ``avanzar`` deja pasar un segundo de la cuenta."""

    def __init__(self):
        self.cola = asyncio.Queue()

    async def dormir(self, segundos):
        if segundos != INTERVALO_CUENTA:  # otras esperas del bot (CV, cuota) no se controlan
            return
        await self.cola.get()

    async def avanzar(self, segundos=1):
        for _ in range(segundos):
            self.cola.put_nowait(None)
            for _ in range(10):
                await asyncio.sleep(0)


def con_cuenta(mundo, segundos=3):
    mundo.n.config.cuenta_regresiva_segundos = segundos
    reloj = RelojManual()
    mundo.c.dormir = reloj.dormir
    return reloj


def postulaciones(mundo):
    return mundo.n.base.cx.execute("SELECT id, mensaje_id FROM postulaciones").fetchall()


def ultimo_texto(mundo, mensaje):
    return ediciones_de(mundo, mensaje)[-1][2]


def botones_de(mundo, mensaje):
    return [texto for fila in mundo.s.botones_editados.get(mensaje) or [] for texto, _ in fila]


@respx.mock
def test_la_cuenta_pinta_la_card_y_no_encola_hasta_terminar(mundo):
    usuario = preparar_toque(mundo)
    reloj = con_cuenta(mundo, 3)
    corta = id_corto("linkedin:1")

    async def flujo():
        antes = len(mundo.s.mensajes)
        toque = await mundo.c.procesar_toque(usuario, corta)
        nuevos = mundo.s.mensajes[antes:]
        mensaje = mundo.s._id
        assert toque.camino == Camino.EN_CUENTA and len(nuevos) == 1
        texto, botones = nuevos[0][1], nuevos[0][2]
        assert "Practicante de sistemas" in texto and "Postulando en 3 s" in texto
        assert botones == [[("Cancelar", cb("cancel", corta))]]
        assert postulaciones(mundo) == []
        await reloj.avanzar(1)
        assert "Postulando en 2 s" in ultimo_texto(mundo, mensaje) and postulaciones(mundo) == []
        await reloj.avanzar(1)
        assert "Postulando en 1 s" in ultimo_texto(mundo, mensaje) and postulaciones(mundo) == []
        await reloj.avanzar(1)
        await mundo.c.esperar_tareas()
        return mensaje, len(mundo.s.mensajes) - antes

    mensaje, mensajes_nuevos = correr(flujo())
    fila = postulaciones(mundo)[0]
    assert mensajes_nuevos == 1 and fila["mensaje_id"] == mensaje  # todo en el mismo mensaje
    assert "En cola" in ultimo_texto(mundo, mensaje) and not botones_de(mundo, mensaje)
    assert mundo.base.kv_obtener(f"cuenta:{usuario.id}:{corta}") == ""


@respx.mock
def test_cancelar_a_tiempo_no_encola_y_postular_reabre_la_cuenta_en_el_mismo_mensaje(mundo):
    usuario = preparar_toque(mundo)
    reloj = con_cuenta(mundo, 3)
    corta = id_corto("linkedin:1")

    async def flujo():
        antes = len(mundo.s.mensajes)
        await mundo.c.procesar_toque(usuario, corta)
        mensaje = mundo.s._id
        await reloj.avanzar(1)
        await mundo.c.al_boton(ANA, cb("cancel", corta))
        await reloj.avanzar(5)  # aunque pasara el tiempo, nada se encola
        cancelada = ultimo_texto(mundo, mensaje), botones_de(mundo, mensaje), postulaciones(mundo)
        await mundo.c.al_boton(ANA, cb("post", corta))
        reabierta = ultimo_texto(mundo, mensaje), botones_de(mundo, mensaje), postulaciones(mundo)
        await reloj.avanzar(3)
        await mundo.c.esperar_tareas()
        return mensaje, len(mundo.s.mensajes) - antes, cancelada, reabierta

    mensaje, mensajes_nuevos, cancelada, reabierta = correr(flujo())
    assert "Cancelaste la postulación. No envié nada." in cancelada[0]
    assert cancelada[1] == ["Postular"] and cancelada[2] == []
    assert "Postulando en 3 s" in reabierta[0] and reabierta[1] == ["Cancelar"]
    assert reabierta[2] == []
    assert mensajes_nuevos == 1  # ningún mensaje nuevo en todo el recorrido
    assert postulaciones(mundo)[0]["mensaje_id"] == mensaje


@respx.mock
def test_cancelar_tarde_avisa_y_no_cambia_la_card(mundo):
    usuario = preparar_toque(mundo)
    reloj = con_cuenta(mundo, 2)
    corta = id_corto("linkedin:1")

    async def flujo():
        await mundo.c.procesar_toque(usuario, corta)
        mensaje = mundo.s._id
        await reloj.avanzar(2)
        await mundo.c.esperar_tareas()
        antes = len(mundo.s.ediciones)
        aviso = await mundo.c.al_boton(ANA, cb("cancel", corta))
        return mensaje, aviso, len(mundo.s.ediciones) - antes

    mensaje, aviso, ediciones = correr(flujo())
    assert "Ya se está postulando" in aviso and ediciones == 0
    assert len(postulaciones(mundo)) == 1 and "En cola" in ultimo_texto(mundo, mensaje)


@respx.mock
def test_un_segundo_toque_mientras_cuenta_no_abre_otra_cuenta(mundo):
    usuario = preparar_toque(mundo)
    reloj = con_cuenta(mundo, 3)
    corta = id_corto("linkedin:1")

    async def flujo():
        antes = len(mundo.s.mensajes)
        await mundo.c.procesar_toque(usuario, corta)
        segundo = await mundo.c.procesar_toque(usuario, corta)
        canal = await mundo.c.al_toque_canal(ANA, corta)
        await reloj.avanzar(3)
        await mundo.c.esperar_tareas()
        return segundo, canal, len(mundo.s.mensajes) - antes

    segundo, canal, mensajes_nuevos = correr(flujo())
    assert segundo.camino == Camino.EN_CUENTA and segundo.motivo == "ya_contando"
    assert "Ya está contando" in canal.texto
    assert mensajes_nuevos == 1 and len(postulaciones(mundo)) == 1


@respx.mock
def test_el_toque_del_canal_responde_al_instante_con_el_aviso_de_los_segundos(mundo):
    preparar_toque(mundo)
    con_cuenta(mundo, 5)  # nadie avanza el reloj: si la respuesta esperara la cuenta, no llegaría

    async def flujo():
        return await asyncio.wait_for(mundo.c.al_toque_canal(ANA, id_corto("linkedin:1")), 1)

    respuesta = correr(flujo())
    assert respuesta.texto == "⚡ Tienes 5 s para cancelar en el bot." and not respuesta.alerta
    assert postulaciones(mundo) == []


@respx.mock
def test_una_vacante_que_ya_existe_no_abre_cuenta(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)  # con la cuenta en 0 se encola de inmediato
    con_cuenta(mundo, 3)

    async def flujo():
        antes = len(mundo.s.mensajes)
        toque = await mundo.c.procesar_toque(usuario, id_corto("linkedin:1"))
        return toque, mundo.s.mensajes[antes:]

    toque, nuevos = correr(flujo())
    assert toque.camino != Camino.EN_CUENTA and toque.postulacion.id == pid
    assert not any("Postulando en" in (m[1] or "") for m in nuevos)


@respx.mock
def test_los_toques_automaticos_encolan_sin_cuenta(mundo):
    usuario = preparar_toque(mundo)
    con_cuenta(mundo, 3)
    toque = correr(mundo.c.procesar_toque(usuario, id_corto("linkedin:1"), origen="automatico"))
    assert toque.camino == Camino.AUTOMATICA and len(postulaciones(mundo)) == 1
    assert not mundo.base.kv_con_prefijo("cuenta:")


@respx.mock
def test_con_cuenta_en_cero_la_card_dice_en_cola_sin_boton_cancelar(mundo):
    usuario = preparar_toque(mundo)
    pid, nuevos = tocar(mundo, usuario)
    assert "En cola" in nuevos[0][1]
    assert all("Cancelar" not in texto for fila in nuevos[0][2] or [] for texto, _ in fila)


@respx.mock
def test_el_reintento_de_un_bloqueo_no_pasa_por_la_cuenta(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    con_cuenta(mundo, 3)
    correr(mundo.c.al_boton(ANA, cb("rei", pid)))
    assert not any("Postulando en" in (m[1] or "") for m in mundo.s.mensajes)


@respx.mock
def test_la_vacante_pendiente_del_alta_cuenta_en_la_tarjeta_y_se_adopta_el_mensaje(mundo):
    respx.get(URL_LI).mock(return_value=httpx.Response(200, text=FIXTURE_LI))
    mundo.n.camino_automatico = lambda *_: None  # la vacante de la prueba es de LinkedIn
    reloj = con_cuenta(mundo, 2)

    async def flujo():
        await hasta_resumen(mundo, ANA, payload="v_" + id_corto("linkedin:1"))
        # El auxiliar espera las tareas de fondo, y la cuenta espera al reloj: va en paralelo
        alta = asyncio.create_task(vincular_navegador(mundo, ANA))
        while not any("Postulando en" in e[2] for e in mundo.s.ediciones):
            await asyncio.sleep(0.01)
        en_cuenta = [e for e in mundo.s.ediciones if "Postulando en" in e[2]]
        mensajes = len(mundo.s.mensajes)
        durante = postulaciones(mundo)
        await reloj.avanzar(2)
        await alta
        return en_cuenta, mensajes, durante

    en_cuenta, mensajes, durante = correr(flujo())
    assert durante == []  # la cuenta corre antes de encolar
    assert en_cuenta and "Conexión" in en_cuenta[0][2]  # bajo el bloque de conexión
    fila = postulaciones(mundo)[0]
    assert fila["mensaje_id"] == en_cuenta[0][1]  # la card adopta el mensaje de la tarjeta
    assert len(mundo.s.mensajes) == mensajes  # el final no mandó mensajes nuevos


@respx.mock
def test_el_reinicio_descarta_la_cuenta_y_deja_la_card_interrumpida(mundo):
    usuario = preparar_toque(mundo)
    con_cuenta(mundo, 5)
    corta = id_corto("linkedin:1")
    correr(mundo.c.procesar_toque(usuario, corta))
    mensaje = mundo.s._id

    async def reinicio():
        otra = Conversacion(mundo.n, mundo.s, mundo.comprobador)
        await otra.descartar_cuentas()

    correr(reinicio())
    assert postulaciones(mundo) == []
    assert "La cuenta se interrumpió; no envié nada." in ultimo_texto(mundo, mensaje)
    assert botones_de(mundo, mensaje) == ["Postular"]
    assert '"cancelada": true' in mundo.base.kv_obtener(f"cuenta:{usuario.id}:{corta}")


# --- preguntas de dato del redactor y revisión de respuestas ------------------------------------

DATO = "¿En qué institución estudias?"


def pendiente_dato(mundo, usuario, pid, sugerencias='["SENA", "ITM"]'):
    with mundo.base.transaccion() as cx:
        cx.execute(
            "INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, pregunta_norm, "
            "opciones_json, tipo, creada) VALUES (?, ?, ?, ?, ?, 'dato', 'x')",
            (usuario.id, pid, DATO, normalizar_pregunta(DATO), sugerencias),
        )


def con_dato_pendiente(mundo, sugerencias='["SENA", "ITM"]'):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    esperando_usuario(mundo, pid)
    pendiente_dato(mundo, usuario, pid, sugerencias)
    preguntar(mundo, usuario)
    return usuario, pid, mensaje


@respx.mock
def test_dato_con_sugerencia_se_guarda_y_la_postulacion_vuelve_a_la_cola(mundo):
    usuario, pid, mensaje = con_dato_pendiente(mundo)
    texto, botones = card_de(mundo, mensaje)
    assert DATO in texto and "Elige una opción o escríbela tú." in texto
    assert [b for fila in botones for b, _ in fila] == [
        "SENA", "ITM", tp.BOTON_ESCRIBIR, tp.BOTON_RESERVADO,
    ]  # fmt: skip
    correr(mundo.c.al_texto(ANA, "Otra cosa", 80))  # con sugerencias, el texto espera al botón
    assert (ANA, 80) in mundo.s.borrados and aprendida(
        mundo.base, usuario.id, normalizar_pregunta(DATO)
    ) is None
    correr(mundo.c.al_boton(ANA, botones[0][0][1]))
    assert aprendida(mundo.base, usuario.id, normalizar_pregunta(DATO)) == "SENA"
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    assert card_guardada(mundo, pid).fase == tp.EN_COLA


@respx.mock
def test_escribir_yo_espera_el_texto_y_lo_borra_del_chat(mundo):
    usuario, pid, mensaje = con_dato_pendiente(mundo)
    pendiente_id = mundo.n.pendientes(usuario.id)[0]["id"]
    correr(mundo.c.al_boton(ANA, cb("pesc", pendiente_id)))
    texto, botones = card_de(mundo, mensaje)
    assert "Escribe tu respuesta." in texto
    assert [b for fila in botones for b, _ in fila] == [tp.BOTON_RESERVADO]
    antes = len(mundo.s.mensajes)
    correr(mundo.c.al_texto(ANA, "Politécnico Grancolombiano", 81))
    assert (ANA, 81) in mundo.s.borrados and len(mundo.s.mensajes) == antes
    guardado = aprendida(mundo.base, usuario.id, normalizar_pregunta(DATO))
    assert guardado == "Politécnico Grancolombiano"
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA


@respx.mock
def test_prefiero_no_decirlo_guarda_el_dato_reservado(mundo):
    usuario, pid, _ = con_dato_pendiente(mundo)
    pendiente_id = mundo.n.pendientes(usuario.id)[0]["id"]
    correr(mundo.c.al_boton(ANA, cb("pres", pendiente_id)))
    assert aprendida(mundo.base, usuario.id, normalizar_pregunta(DATO)) == RESERVADO
    assert mundo.n.pendientes(usuario.id) == []
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    assert RESERVADO not in "\n".join(mundo.s.de(ANA) + [e[2] for e in mundo.s.ediciones])


@respx.mock
def test_dato_sin_sugerencias_acepta_texto_directo(mundo):
    usuario, pid, _ = con_dato_pendiente(mundo, sugerencias="[]")
    correr(mundo.c.al_texto(ANA, "SENA", 82))
    assert aprendida(mundo.base, usuario.id, normalizar_pregunta(DATO)) == "SENA"
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA


@respx.mock
def test_sin_ia_la_pregunta_del_formulario_no_ofrece_botones_de_dato(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    esperando_usuario(mundo, pid)
    pendiente(mundo, usuario, pid, "¿Por qué te interesa?", "por que te interesa")
    preguntar(mundo, usuario)
    texto, botones = card_de(mundo, mensaje)
    assert "Escribe tu respuesta." in texto and botones is None
    correr(mundo.c.al_texto(ANA, "Quiero aprender", 83))
    assert aprendida(mundo.base, usuario.id, "por que te interesa") == "Quiero aprender"


def propuestas(mundo, pid):
    with mundo.base.transaccion() as cx:
        for n, (pregunta, respuesta) in enumerate(
            [("¿Por qué te interesa?", "Quiero aplicar Python."), ("¿Qué estudias?", "ADSO.")]
        ):
            cx.execute(
                "INSERT INTO respuestas(postulacion_id, pregunta, respuesta, origen, "
                "pregunta_norm, estado) VALUES (?, ?, ?, 'ia', ?, 'propuesta')",
                (pid, pregunta, respuesta, f"p{n}"),
            )


@respx.mock
def test_revision_corregir_y_enviar(mundo):
    usuario = preparar_toque(mundo)
    pid, _ = tocar(mundo, usuario)
    mensaje = card_guardada(mundo, pid).mensaje_id
    esperando_usuario(mundo, pid)
    propuestas(mundo, pid)
    correr(mundo.c.notificar({"tipo": "revision_respuestas", "usuario_id": usuario.id,
                              "postulacion_id": pid}))  # fmt: skip
    texto, botones = card_de(mundo, mensaje)
    assert card_guardada(mundo, pid).fase == tp.REVISION
    assert "Aún no envié nada" in texto and "<b>Quiero aplicar Python.</b>" in texto
    assert [b for fila in botones for b, _ in fila] == ["✅ Enviar", "✏️ Corregir"]
    correr(mundo.c.al_boton(ANA, cb("rev", pid, "c")))
    assert [b for fila in card_de(mundo, mensaje)[1] for b, _ in fila] == ["1", "2", "Volver"]
    correr(mundo.c.al_boton(ANA, cb("rev", pid, 2)))
    assert "texto nuevo para la respuesta 2" in card_de(mundo, mensaje)[0]
    correr(mundo.c.al_texto(ANA, "Tecnología en ADSO en el SENA.", 84))
    assert (ANA, 84) in mundo.s.borrados
    texto, _ = card_de(mundo, mensaje)
    assert "<b>Tecnología en ADSO en el SENA.</b> 💬" in texto and "Aún no envié nada" in texto
    assert mundo.n.cola.obtener(pid).estado == E.ESPERANDO_USUARIO  # nada se envía aún
    correr(mundo.c.al_boton(ANA, cb("rev", pid, "ok")))
    assert mundo.n.cola.obtener(pid).estado == E.EN_COLA
    assert card_guardada(mundo, pid).fase == tp.EN_COLA
    filas = mundo.base.cx.execute(
        "SELECT respuesta, origen, estado FROM respuestas WHERE postulacion_id = ? ORDER BY id",
        (pid,),
    ).fetchall()
    assert [tuple(f) for f in filas] == [
        ("Quiero aplicar Python.", "ia", "aprobada"),
        ("Tecnología en ADSO en el SENA.", "usuario", "aprobada"),
    ]
    # Un toque viejo de la revisión ya no hace nada: se repinta la card vigente
    correr(mundo.c.al_boton(ANA, cb("rev", pid, "c")))
    assert card_guardada(mundo, pid).fase == tp.EN_COLA


# --- la card en cola explica por qué espera y se actualiza sola -----------------------------


def en_cola_con_card(mundo, plataforma="magneto", *, vinculado=True):
    """Usuario con un navegador vinculado y una postulación en cola con su card (mensaje 42)."""
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.config.extension.version_minima = "1.0.0"
    mundo.n.cargar_selectores()
    mundo.n.indice.indexar(T0)
    if vinculado:
        codigo = vinculos.crear_codigo(mundo.base, usuario.id, T0)
        vinculos.canjear(mundo.base, codigo, "Edge", "1.4.0", T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), plataforma, T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET mensaje_id = 42 WHERE id = ?", (p.id,))
    return usuario, p


def latido_del_navegador(mundo, portales):
    with mundo.base.transaccion() as cx:
        cx.execute(
            "UPDATE navegadores SET ultimo_latido = ?, version = '1.4.0', portales_json = ?",
            (a_texto(T0), json.dumps({"_pausado": False, **portales})),
        )


def revisar(mundo, usuario):
    correr(mundo.c.notificar({"tipo": "esperas", "usuario_id": usuario.id}))


def ultima_edicion(mundo, mensaje=42):
    return [texto for _, m, texto in mundo.s.ediciones if m == mensaje][-1]


def test_sin_sesion_se_explica_en_la_card_y_no_se_repite(mundo):
    usuario, p = en_cola_con_card(mundo)
    latido_del_navegador(
        mundo, {"magneto": {"estado": "sin_sesion", "motivo": "enlace_ingresar", "cuenta": "ok"}}
    )
    revisar(mundo, usuario)
    assert "Inicia sesión en Magneto" in ultima_edicion(mundo)
    assert "enlace_ingresar" not in ultima_edicion(mundo)
    assert _etiquetas(mundo.s.botones_editados[42]) == ["Iniciar sesión", "Crear cuenta"]
    ediciones = len(mundo.s.ediciones)
    for _ in range(3):  # latidos cada 30 s con la misma causa
        revisar(mundo, usuario)
    assert len(mundo.s.ediciones) == ediciones


def test_al_iniciar_sesion_la_card_vuelve_a_en_cola(mundo):
    usuario, p = en_cola_con_card(mundo)
    latido_del_navegador(mundo, {"magneto": {"estado": "sin_sesion", "cuenta": "ok"}})
    revisar(mundo, usuario)
    latido_del_navegador(mundo, {"magneto": {"estado": "listo", "cuenta": "ok"}})
    revisar(mundo, usuario)
    assert "En cola. Te aviso el resultado." in ultima_edicion(mundo)
    assert not mundo.s.botones_editados[42]
    assert tp.Card.de_texto(mundo.base.kv_obtener(f"card:{p.id}")).espera is None


def test_la_card_pasa_de_esperando_navegador_a_en_cola_al_volver_el_navegador(mundo):
    usuario, p = en_cola_con_card(mundo)
    latido_del_navegador(mundo, {"magneto": {"estado": "listo", "cuenta": "ok"}})
    correr(mundo.c._cerrar_card(usuario, p.id, tp.ESPERANDO_NAVEGADOR))
    assert "Se enviará cuando abras tu navegador." in ultima_edicion(mundo)
    revisar(mundo, usuario)
    assert "En cola. Te aviso el resultado." in ultima_edicion(mundo)


def test_las_postulaciones_en_otras_fases_no_se_tocan(mundo):
    usuario, p = en_cola_con_card(mundo)
    correr(mundo.c._poner_fase(usuario, p.id, tp.SESION))
    ediciones = len(mundo.s.ediciones)
    latido_del_navegador(mundo, {"magneto": {"estado": "sin_sesion", "cuenta": "ok"}})
    revisar(mundo, usuario)
    assert len(mundo.s.ediciones) == ediciones


def test_plataformas_off_y_on_cambian_la_card_en_cola(mundo):
    usuario, p = en_cola_con_card(mundo)
    latido_del_navegador(mundo, {"magneto": {"estado": "listo", "cuenta": "ok"}})
    revisar(mundo, usuario)
    correr(mundo.c._a_plataformas(usuario, ["magneto", "off"]))
    assert "automática en Magneto está pausada" in ultima_edicion(mundo)
    assert not mundo.s.botones_editados[42]
    correr(mundo.c._a_plataformas(usuario, ["magneto", "on"]))
    assert "En cola. Te aviso el resultado." in ultima_edicion(mundo)


def test_la_vigilancia_de_cada_minuto_actualiza_las_cards_en_cola(mundo):
    usuario, p = en_cola_con_card(mundo)
    latido_del_navegador(mundo, {"magneto": {"estado": "sin_sesion", "cuenta": "ok"}})
    correr(mundo.c.revisar_esperas())
    assert "Inicia sesión en Magneto" in ultima_edicion(mundo)


def api_con_navegador(mundo, usuario):
    """La API real sobre el mismo núcleo y un navegador vinculado por su ruta pública."""
    from fastapi.testclient import TestClient

    from buscador_vacantes.asistente.api import crear_app

    cliente = TestClient(crear_app(mundo.n))
    codigo = vinculos.mostrar_codigo(vinculos.crear_codigo(mundo.base, usuario.id, T0))
    r = cliente.post("/api/v1/vincular", json={"codigo": codigo, "version": "1.4.0"})
    return cliente, {"Authorization": f"Bearer {r.json()['token']}"}


def test_punta_a_punta_magneto_sin_sesion_como_la_postulacion_43(mundo):
    pytest.importorskip("fastapi", reason="requiere uv sync --group asistente")
    usuario, p = en_cola_con_card(mundo, "magneto", vinculado=False)
    cliente, cab = api_con_navegador(mundo, usuario)
    cuerpo = {
        "version": "1.4.0",
        "portales": {"magneto": {"estado": "sin_sesion", "motivo": "enlace_ingresar"}},
    }
    assert cliente.post("/api/v1/latido", headers=cab, json=cuerpo).json()["trabajo"] is None
    assert "Inicia sesión en Magneto" in ultima_edicion(mundo)
    assert _etiquetas(mundo.s.botones_editados[42]) == ["Iniciar sesión", "Crear cuenta"]


def test_punta_a_punta_de_sin_permiso_a_sin_sesion_en_el_mismo_mensaje(mundo):
    pytest.importorskip("fastapi", reason="requiere uv sync --group asistente")
    usuario, p = en_cola_con_card(mundo, "elempleo", vinculado=False)
    cliente, cab = api_con_navegador(mundo, usuario)

    def latido(portales):
        cuerpo = {"version": "1.4.0", "portales": portales}
        assert cliente.post("/api/v1/latido", headers=cab, json=cuerpo).status_code == 200

    # Al permiso de elempleo.com todavía le falta activarse: el portal no viene en el latido
    latido({"computrabajo": {"estado": "listo", "correo": "ana@gmail.com"}})
    assert "activa el permiso de elempleo.com" in ultima_edicion(mundo)
    # Lo concede pero aún no tiene sesión: cambia el motivo, en el mismo mensaje
    mensajes = len(mundo.s.mensajes)
    latido({"elempleo": {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    assert "Inicia sesión en elempleo" in ultima_edicion(mundo)
    assert _etiquetas(mundo.s.botones_editados[42])[0] == "Iniciar sesión"
    assert len(mundo.s.mensajes) == mensajes  # solo se editó la card, no hubo mensajes nuevos


# --- motivos del motor genérico y avisos al dueño (6.4) -------------------------------------


@pytest.mark.parametrize("estado", [E.BLOQUEADA, E.FORMULARIO_DESCONOCIDO])
def test_el_motivo_del_motor_generico_llega_a_la_card_de_respaldo(mundo, estado):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, estado, "ats_con_cuenta")))
    correr(mundo.c.esperar_tareas())
    texto, botones = card_de(mundo)
    assert "pide crear una cuenta" in texto
    assert ("Pegar preguntas", cb("pegar", p.id)) in [b for fila in botones for b in fila]
    # Es un caso esperado, no un fallo: el dueño no recibe la alerta de revisar evidencia
    assert not any("Postulación" in m for m in mundo.s.de(DUENO))


def test_sin_ia_ofrece_configurar_la_clave_desde_la_card(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.FORMULARIO_DESCONOCIDO,
                                    "sin_ia")))  # fmt: skip
    correr(mundo.c.esperar_tareas())
    texto, botones = card_de(mundo)
    assert "necesito tu clave de IA" in texto
    assert botones[0][0] == ("Configurar IA", cb("clave", "nueva"))
    correr(mundo.c.al_boton(ANA, cb("clave", "nueva")))
    assert "Pega una clave nueva" in mundo.s.de(ANA)[-1]


def test_el_formulario_desconocido_sin_motivo_conocido_sigue_alertando_al_dueno(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.FORMULARIO_DESCONOCIDO,
                                    "no_encontrado")))  # fmt: skip
    correr(mundo.c.esperar_tareas())
    assert any("Postulación" in m for m in mundo.s.de(DUENO))


def test_el_dueno_recibe_el_aviso_de_la_receta_apagada(mundo):
    with mundo.base.transaccion() as cx:
        cx.execute(
            "INSERT INTO recetas(host, ruta_patron, familia, firma, receta_json, actualizada) "
            "VALUES ('job-boards.greenhouse.io', '/x', 'greenhouse', '[]', '{}', 'x')"
        )
    correr(mundo.c.notificar({"tipo": "receta_apagada", "receta_id": 1, "postulacion_id": 9}))
    aviso = mundo.s.de(DUENO)[-1]
    assert "job-boards.greenhouse.io" in aviso and "falló 2 veces seguidas" in aviso


def test_el_dueno_recibe_el_parche_nuevo_con_el_selector_y_la_evidencia(mundo):
    parche = proponer_parche(mundo.base, "computrabajo", "aplicar", "a.btn-nuevo", T0, 9)
    correr(mundo.c.notificar({"tipo": "parche_nuevo", "parche_id": parche,
                              "plataforma": "computrabajo", "paso": "aplicar",
                              "postulacion_id": 9}))  # fmt: skip
    aviso = mundo.s.de(DUENO)[-1]
    assert "Parche candidato para <b>Computrabajo</b>" in aviso and "«aplicar»" in aviso
    assert "<code>&quot;a.btn-nuevo&quot;</code>" in aviso or "a.btn-nuevo" in aviso
    assert "data/asistente/postulaciones/9/" in aviso
    correr(mundo.c.notificar({"tipo": "parche_firme", "parche_id": parche,
                              "plataforma": "computrabajo", "paso": "aplicar",
                              "postulacion_id": 10}))  # fmt: skip
    assert "Parche firme" in mundo.s.de(DUENO)[-1] and "JSON revisado" in mundo.s.de(DUENO)[-1]


def test_el_aviso_del_dominio_barrera_dice_como_quitarlo(mundo):
    correr(mundo.c.notificar({"tipo": "dominio_barrera", "host": "ats.example.com",
                              "motivo": "ats_con_cuenta", "postulacion_id": 9}))  # fmt: skip
    assert "/barreras quitar ats.example.com" in mundo.s.de(DUENO)[-1]


def test_los_avisos_al_dueno_no_van_a_nadie_si_no_hay_dueno(mundo):
    mundo.c.config.dueno_telegram_id = 0
    antes = len(mundo.s.mensajes)
    correr(mundo.c.notificar({"tipo": "dominio_barrera", "host": "x.co", "motivo": "oauth",
                              "postulacion_id": 9}))  # fmt: skip
    assert len(mundo.s.mensajes) == antes


def test_el_dueno_lista_y_quita_dominios_barrera(mundo):
    correr(alta_completa(mundo, DUENO))
    marcar_barrera(mundo.base, "ats.example.com", "ats_con_cuenta", T0)
    correr(mundo.c.al_comando(DUENO, "barreras", []))
    assert "ats.example.com: ats_con_cuenta" in mundo.s.de(DUENO)[-1]
    correr(mundo.c.al_comando(DUENO, "barreras", ["quitar", "ATS.example.com"]))
    assert mundo.s.de(DUENO)[-1] == "No hay dominios barrera."
    assert barrera_de(mundo.base, "ats.example.com") is None
    auditoria = mundo.base.cx.execute("SELECT accion FROM auditoria").fetchall()
    assert "barrera_quitada" in [f[0] for f in auditoria]


def test_un_usuario_comun_no_puede_ver_las_barreras(mundo):
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_comando(ANA, "barreras", []))
    assert "No conozco ese comando" in mundo.s.de(ANA)[-1]


def ensayada_con_card_42(mundo, motivo="boton:Submit application"):
    usuario, p = encolar_con_card_42(mundo)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET estado = 'ensayada' WHERE id = ?", (p.id,))
        cx.execute(
            "INSERT INTO respuestas(postulacion_id, pregunta, respuesta, origen) "
            "VALUES (?, '¿Por qué nosotros?', 'Me gusta su producto', 'ia')",
            (p.id,),
        )
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENSAYADA, motivo)))
    return usuario, p


def test_ensayada_pinta_la_card_con_las_respuestas_y_los_dos_botones(mundo):
    usuario, p = ensayada_con_card_42(mundo)
    _, mensaje, texto = mundo.s.ediciones[-1]
    assert mensaje == 42 and "🧪 Ensayo: no envié nada." in texto
    assert "Habría pulsado «Submit application»" in texto and "Me gusta su producto" in texto
    botones = mundo.s.botones_editados[42]
    datos = [b[1] for fila in botones for b in fila]
    assert cb("ens", p.id, "real") in datos and cb("ens", p.id, "resp") in datos


def test_enviar_de_verdad_vuelve_a_la_cola_sin_ensayo_y_la_card_a_en_cola(mundo):
    usuario, p = ensayada_con_card_42(mundo)
    mundo.n.preferencias.fijar_ensayo_usuario(usuario.id, True)
    assert correr(mundo.c.al_boton(ANA, cb("ens", p.id, "real"))) == "🚀 Enviando de verdad"
    nueva = mundo.n.cola.obtener(p.id)
    assert nueva.estado == E.EN_COLA and nueva.forzar_real
    assert not mundo.n.en_ensayo(nueva)  # aunque el usuario siga en ensayo
    assert "En cola" in mundo.s.ediciones[-1][2]
    # Ya no está ensayada: otro toque no hace nada
    assert "ya no se puede" in correr(mundo.c.al_boton(ANA, cb("ens", p.id, "real")))


def test_el_paquete_de_respaldo_de_un_ensayo_termina_con_plataforma_en_ensayo(mundo):
    usuario, p = ensayada_con_card_42(mundo)
    correr(mundo.c.al_boton(ANA, cb("ens", p.id, "resp")))
    assert mundo.n.cola.obtener(p.id).estado == E.RESPALDO
    assert "estaba en modo ensayo" in mundo.s.ediciones[-1][2]


def test_los_botones_del_ensayo_son_solo_del_dueno_de_la_postulacion(mundo):
    usuario, p = ensayada_con_card_42(mundo)
    correr(alta_completa(mundo, LUIS))
    correr(mundo.c.al_boton(LUIS, cb("ens", p.id, "real")))
    correr(mundo.c.al_boton(LUIS, cb("ens", p.id, "resp")))
    assert mundo.n.cola.obtener(p.id).estado == E.ENSAYADA


def test_un_ensayo_trabado_muestra_la_pantalla_y_el_dueno_recibe_la_evidencia(mundo):
    usuario, p = encolar_con_card_42(mundo)
    with mundo.base.transaccion() as cx:
        mundo.n.cola.paso(cx, p.id, "ensayo_trabado", T0, detalle="pantalla 3: no hay botón")
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.FORMULARIO_DESCONOCIDO, "x")))
    texto = mundo.s.ediciones[-1][2]
    assert "Se trabaría en la pantalla 3: no hay botón." in texto
    assert not any(b[1] == cb("ens", p.id, "real") for f in mundo.s.botones_editados[42] for b in f)
    assert any("Revisa la evidencia" in m for m in mundo.s.de(DUENO))


def test_ensayo_del_dueno_se_enciende_y_apaga_con_el_comando(mundo):
    correr(alta_completa(mundo, DUENO))
    dueno = mundo.n.usuarios.obtener(DUENO)
    correr(mundo.c.al_comando(DUENO, "ensayo", []))
    assert "apagado" in mundo.s.ultimo(DUENO)[1]
    correr(mundo.c.al_comando(DUENO, "ensayo", ["on"]))
    assert "activado" in mundo.s.ultimo(DUENO)[1]
    assert mundo.n.preferencias.ensayo_usuario(dueno.id)
    correr(mundo.c.al_comando(DUENO, "ensayo", ["off"]))
    assert not mundo.n.preferencias.ensayo_usuario(dueno.id)
    correr(alta_completa(mundo, ANA))
    correr(mundo.c.al_comando(ANA, "ensayo", ["on"]))
    assert mundo.s.ultimo(ANA)[1].startswith("No conozco ese comando")


def test_plataformas_pone_y_quita_el_ensayo_de_una_plataforma(mundo):
    correr(alta_completa(mundo, DUENO))
    config = mundo.n.config
    correr(mundo.c.al_comando(DUENO, "plataformas", ["magneto", "ensayo"]))
    assert "magneto" in mundo.n.preferencias.plataformas_en_ensayo(config.ensayo.plataformas)
    assert "magneto: automática · 🧪 en ensayo" in mundo.s.ultimo(DUENO)[1]
    correr(mundo.c.al_comando(DUENO, "plataformas", ["magneto", "real"]))
    assert "magneto" not in mundo.n.preferencias.plataformas_en_ensayo(config.ensayo.plataformas)
    assert "en ensayo" not in mundo.s.ultimo(DUENO)[1]
    correr(mundo.c.al_comando(DUENO, "plataformas", ["inexistente", "ensayo"]))
    assert mundo.n.preferencias.plataformas_en_ensayo(config.ensayo.plataformas) == {}


def vigia_del_dueno(mundo):
    correr(alta_completa(mundo, DUENO))
    dueno = mundo.n.usuarios.obtener(DUENO)
    mundo.n.indice.indexar(T0)
    p = mundo.n.cola.encolar_vigia(dueno.id, id_corto("linkedin:1"), "computrabajo", T0)
    return dueno, p


def test_vigia_limpio_no_le_avisa_nada_al_dueno(mundo):
    dueno, p = vigia_del_dueno(mundo)
    antes = (len(mundo.s.mensajes), len(mundo.s.ediciones))
    correr(mundo.c.notificar(Evento("resultado", p.id, dueno.id, E.ENSAYADA, "boton:Aplicar")))
    assert (len(mundo.s.mensajes), len(mundo.s.ediciones)) == antes
    assert mundo.n.preferencias.plataformas_en_ensayo([]) == {}


def test_vigia_que_falla_avisa_al_dueno_y_deja_la_plataforma_en_ensayo(mundo):
    dueno, p = vigia_del_dueno(mundo)
    with mundo.base.transaccion() as cx:
        mundo.n.cola.paso(cx, p.id, "ensayo_trabado", T0, detalle="pantalla 1: sin botón")
    correr(mundo.c.notificar(
        Evento("resultado", p.id, dueno.id, E.FORMULARIO_DESCONOCIDO, "no apareció el botón")
    ))  # fmt: skip
    aviso = mundo.s.de(DUENO)[-1]
    assert "El vigía no pudo ensayar Computrabajo" in aviso and "pantalla 1: sin botón" in aviso
    assert "/plataformas computrabajo real" in aviso
    assert "computrabajo" in mundo.n.preferencias.plataformas_en_ensayo([])
    # Un usuario común que toque ⚡ en esa plataforma ahora ensaya en lugar de enviar
    ana = mundo.n.usuarios.obtener(DUENO)
    otra, _ = mundo.n.cola.encolar(ana.id, id_corto("linkedin:1"), "computrabajo", T0)
    assert mundo.n.en_ensayo(otra)


def test_vigia_reparado_avisa_que_la_plataforma_cambio_sin_ponerla_en_ensayo(mundo):
    dueno, p = vigia_del_dueno(mundo)
    with mundo.base.transaccion() as cx:
        mundo.n.cola.paso(cx, p.id, "respaldo_generico", T0, detalle="paso 2")
    correr(mundo.c.notificar(Evento("resultado", p.id, dueno.id, E.ENSAYADA, "paso:enviar")))
    assert "cambió y el asistente lo reparó" in mundo.s.de(DUENO)[-1]
    assert mundo.n.preferencias.plataformas_en_ensayo([]) == {}


def test_vigia_no_abre_card_de_progreso_ni_de_verificacion(mundo):
    dueno, p = vigia_del_dueno(mundo)
    antes = len(mundo.s.mensajes)
    for tipo in ("postulando", "verificacion"):
        correr(mundo.c.notificar({"tipo": tipo, "postulacion_id": p.id, "usuario_id": dueno.id}))
    correr(mundo.c.notificar({"tipo": "paso", "postulacion_id": p.id, "usuario_id": dueno.id,
                              "paso": "abrir"}))  # fmt: skip
    assert len(mundo.s.mensajes) == antes and mundo.c._card(p.id) is None


def test_vigia_que_el_navegador_no_pudo_correr_no_es_un_fallo_de_la_plataforma(mundo):
    dueno, p = vigia_del_dueno(mundo)
    antes = len(mundo.s.mensajes)
    correr(mundo.c.notificar(
        Evento("respaldo", p.id, dueno.id, E.RESPALDO, "navegador_desconectado")
    ))  # fmt: skip
    assert len(mundo.s.mensajes) == antes
    assert mundo.n.preferencias.plataformas_en_ensayo([]) == {}
