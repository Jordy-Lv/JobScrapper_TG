import asyncio
import io
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx

pytest.importorskip("telegram", reason="requiere uv sync --group asistente")
fpdf = pytest.importorskip("fpdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import textos as t  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import E, Evento  # noqa: E402
from buscador_vacantes.asistente.conversacion import Conversacion, cb  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro  # noqa: E402
from buscador_vacantes.asistente.detalle import Detalles, Ritmo  # noqa: E402
from buscador_vacantes.asistente.enlaces import id_corto  # noqa: E402
from buscador_vacantes.asistente.gemini import ClienteGemini  # noqa: E402
from buscador_vacantes.asistente.membresia import Comprobador  # noqa: E402
from buscador_vacantes.asistente.nucleo import Nucleo  # noqa: E402
from buscador_vacantes.asistente.respuestas import sembrar_banco  # noqa: E402
from buscador_vacantes.asistente.usuarios import EstadoUsuario  # noqa: E402
from buscador_vacantes.asistente.vacantes import Indice  # noqa: E402
from buscador_vacantes.config import cargar_configuracion  # noqa: E402
from buscador_vacantes.estado import Estado  # noqa: E402
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
        self.documentos = []
        self.borrados = []
        self._id = 0

    async def enviar(self, chat_id, texto, botones=None):
        self._id += 1
        self.mensajes.append((chat_id, texto, botones))
        return self._id

    async def editar(self, chat_id, mensaje_id, texto, botones=None):
        self.ediciones.append((chat_id, mensaje_id, texto))

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
                    ClienteGemini(a.gemini, base, 60, reloj=lambda: T0),
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
    """Responde las preguntas que el CV no cubrió: botones o texto (salario)."""
    for _ in range(len(t.CUESTIONARIO)):
        usuario = m.n.usuarios.obtener(tid)
        if not (usuario.paso_alta or "").startswith("faltantes:"):
            return
        indice = m.c._esperando(usuario)["indice"]
        item = t.CUESTIONARIO[indice]
        if item.opciones:
            await m.c.al_boton(tid, cb("cuest", indice, 0))
        elif item.opcional:
            await m.c.al_boton(tid, cb("cuest", indice, "omitir"))
        else:
            await m.c.al_texto(tid, "1300000")


async def alta_completa(m, tid, *, payload=None):
    """Camino corto: "Información correcta", solo las preguntas que faltan y navegador después."""
    await hasta_resumen(m, tid, payload=payload)
    await m.c.al_boton(tid, cb("resumen", "ok"))
    await responder_faltantes(m, tid)
    await m.c.al_boton(tid, cb("alta", "fin"))
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
    assert t.ALTA_LISTA in mensajes
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
    antes = len(mundo.s.de(ANA))
    correr(mundo.c.al_boton(ANA, cb("resumen", "ok")))
    correr(responder_faltantes(mundo, ANA))
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "navegador"
    preguntadas = "\n".join(mundo.s.de(ANA)[antes:])
    # Lo que el CV (o el perfil manual) ya respondió no se vuelve a preguntar
    for clave in ("nombre", "correo", "telefono", "ciudad"):
        item = next(i for i in t.CUESTIONARIO if i.clave == clave)
        assert item.pregunta not in preguntadas
    # Sí se preguntan las que suelen pedir las vacantes y el CV no dice
    for clave in ("salario", "disponibilidad_inicio", "actualizar_cv_portal"):
        item = next(i for i in t.CUESTIONARIO if i.clave == clave)
        assert t.e(item.pregunta) in preguntadas


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
    async def hasta_pregunta_5():
        c = mundo.c
        await hasta_resumen(mundo, ANA)
        await c.al_boton(ANA, cb("resumen", "editar"))
        for s in ("formacion", "experiencia", "proyectos", "habilidades", "idiomas"):
            await c.al_boton(ANA, cb("seccion", s, "ok"))
        await c.al_boton(ANA, cb("enfoque", "ok"))
        for valor in ("Ana Pérez", "ana@gmail.com", "3105551234"):
            await c.al_texto(ANA, valor)
        await c.al_boton(ANA, cb("cuest", 3, "omitir"))

    correr(hasta_pregunta_5())
    assert mundo.n.usuarios.obtener(ANA).paso_alta == "cuestionario:4"
    # Un servicio nuevo (reinicio) retoma en la misma pregunta
    otra = Conversacion(mundo.n, mundo.s, mundo.comprobador)
    correr(otra.al_iniciar(ANA, "Ana", None))
    assert t.CUESTIONARIO[4].pregunta in mundo.s.de(ANA)[-1]


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
    correr(mundo.c.al_boton(ANA, cb("borrarme")))
    assert mundo.n.usuarios.obtener(ANA) is None


def test_resultado_enviado_edita_el_mensaje_de_progreso(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    mundo.n.indice.indexar(T0)
    p, _ = mundo.n.cola.encolar(usuario.id, id_corto("linkedin:1"), None, T0)
    with mundo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET mensaje_id = 42 WHERE id = ?", (p.id,))
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    assert any(m == 42 and "Postulación enviada" in texto for _, m, texto in mundo.s.ediciones)
    assert "¿Cómo te fue?" in mundo.s.de(ANA)[-1]


def test_cuenta_por_confirmar_muestra_el_correo_y_botones(mundo):
    correr(alta_completa(mundo, ANA))
    usuario = mundo.n.usuarios.obtener(ANA)
    aviso = {"tipo": "cuenta_por_confirmar", "usuario_id": usuario.id,
             "plataforma": "computrabajo", "asociado": "ana@gmail.com"}  # fmt: skip
    correr(mundo.c.notificar(aviso))
    chat, texto, botones = mundo.s.ultimo(ANA)
    assert "Sesión iniciada en Computrabajo" in texto and "ana@gmail.com" in texto
    assert botones[0][0][1] == cb("cuenta", "computrabajo", "si")


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
    assert "¿Tienes moto?" in texto
    correr(mundo.c.al_boton(ANA, botones[1][0][1]))
    assert mundo.n.cola.obtener(p.id).estado == E.EN_COLA
    assert "Sigo con tu postulación" in mundo.s.de(ANA)[-1]


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
    mundo.n.gemini.dormir = dormir

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
    assert "Postulación enviada" in mundo.s.de(ANA)[-2]


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


def test_resumen_detallado_al_confirmar_la_postulacion(mundo):
    usuario, p, cv = postulacion_enviada_con_datos(mundo)
    mundo.s.documentos.clear()
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    resumen = next(m for m in mundo.s.de(ANA) if "Resumen de tu postulación" in m)
    for esperado in (
        "Practicante de sistemas", "ACME", "Medellín, Antioquia", "$ 1.423.500 mensual",
        "De qué trata", "soporte de equipos", "Piden: Sistemas, Redes", "Tu afinidad: 60 %",
        "Hoja de vida enviada", cv.name, "Lo que respondí (2)", "¿En qué institución estudias?",
        "→ SENA", "dato de tu perfil", "redactada con IA",
    ):  # fmt: skip
        assert esperado in resumen, esperado
    assert mundo.s.documentos == [(ANA, cv.name)]
    assert "¿Cómo te fue?" in mundo.s.de(ANA)[-1]


def test_resumen_sin_adjunto_dice_que_fue_la_hoja_de_vida_del_portal(mundo):
    usuario, p, _ = postulacion_enviada_con_datos(mundo)
    with mundo.base.transaccion() as cx:
        cx.execute("DELETE FROM postulacion_pasos WHERE paso = 'cv_adjunto'")
        cx.execute("UPDATE postulaciones SET plataforma = 'computrabajo' WHERE id = ?", (p.id,))
    mundo.s.documentos.clear()
    correr(mundo.c.notificar(Evento("resultado", p.id, usuario.id, E.ENVIADA)))
    resumen = next(m for m in mundo.s.de(ANA) if "Resumen de tu postulación" in m)
    assert "Computrabajo envió la hoja de vida que tienes guardada en tu perfil" in resumen
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
    assert botones == [[("🔁 Reintentar", cb("rei", p.id))]]
    assert not any("paquete" in m for m in mundo.s.de(ANA)[antes:])
    assert not mundo.s.de(DUENO)  # no es un formulario roto: no se avisa al dueño
