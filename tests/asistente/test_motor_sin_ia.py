"""Funcionamiento sin IA de extremo a extremo (change motor-generico-autorreparable, tarea 6.9).

La extensión real corre en Chromium contra el servidor real (Nucleo + API en un hilo de uvicorn)
y las copias de tests/fixtures/formularios/. El usuario no tiene clave de IA: lo que se envía
sale de las recetas del sitio y de los datos del usuario, nunca de una llamada a la IA.
"""

# ruff: noqa: F811
from __future__ import annotations

import json
import socket
import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi", reason="requiere uv sync --group asistente")
pytest.importorskip("fpdf", reason="requiere uv sync --group asistente")
uvicorn = pytest.importorskip("uvicorn")

from buscador_vacantes.asistente import recetas  # noqa: E402
from buscador_vacantes.asistente import tarjeta_postulacion as tp  # noqa: E402
from buscador_vacantes.asistente.api import crear_app  # noqa: E402
from buscador_vacantes.asistente.cola import E  # noqa: E402
from buscador_vacantes.asistente.enlaces import id_corto  # noqa: E402
from buscador_vacantes.asistente.respuestas import recordar  # noqa: E402
from buscador_vacantes.asistente.vinculos import hash_token  # noqa: E402
from buscador_vacantes.comun.estado import a_texto  # noqa: E402
from buscador_vacantes.comun.modelo import Vacante  # noqa: E402
from tests.asistente.test_bucle_generico import ejecutar  # noqa: E402
from tests.asistente.test_extension import TOKEN  # noqa: E402
from tests.asistente.test_motor_generico import GH, Sitio, sitio_de  # noqa: E402
from tests.asistente.test_nucleo import T0, Mundo  # noqa: E402

pytestmark = pytest.mark.navegador

CAMPOS_GH = {
    "first_name": "nombre_pila", "last_name": "apellido", "email": "correo", "country": "pais",
    "phone": "telefono", "candidate-location": "ciudad",
    "question_101": "autorizacion_trabajo:colombia", "question_102": "ciudad",
    "question_103": "institucion", "question_104": "promedio", "question_106": "ingles_nivel",
    "question_107": "salario", "question_108": "fuente_vacante",
}  # fmt: skip
PREGUNTA_ABIERTA = (
    '<label for="question_110">Why do you want to join our team?*</label>'
    '<textarea id="question_110" name="question_110" required maxlength="1000"></textarea>'
)
TEXTO_DEL_USUARIO = "Quiero aprender soporte técnico con un equipo real."


class Servidor:
    """El Nucleo y la API reales de un usuario sin clave de IA, en un hilo de uvicorn."""

    def __init__(self, tmp_path) -> None:
        self.mundo = Mundo(tmp_path)
        self.nucleo = self.mundo.nucleo
        v = Vacante(fuente="computrabajo", id_fuente="9", titulo="Practicante de soporte",
                    empresa="ACME", url=GH, keyword="k")  # fmt: skip
        self.mundo.estado.registrar_vista(v, "hgh", momento=T0, enviada=True)
        self.nucleo.indice.indexar(T0)
        with self.mundo.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO navegadores(usuario_id, token_hash, nombre, version, creado, "
                "ultimo_latido) VALUES (?, ?, 'Edge', '1.2.0', ?, ?)",
                (self.mundo.usuario.id, hash_token(TOKEN), a_texto(T0), a_texto(T0)),
            )
            cx.execute(
                "INSERT INTO selectores(plataforma, version, contenido_json, cargado_en) "
                "VALUES ('prueba', '1', ?, ?)",
                (json.dumps({"postular": []}), a_texto(T0)),
            )
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            puerto = s.getsockname()[1]
        self.proceso = uvicorn.Server(
            uvicorn.Config(crear_app(self.nucleo), host="127.0.0.1", port=puerto,
                           log_level="warning")  # fmt: skip
        )
        self.hilo = threading.Thread(target=self.proceso.run, daemon=True)
        self.hilo.start()
        for _ in range(100):
            if self.proceso.started:
                break
            time.sleep(0.05)
        self.url = f"http://127.0.0.1:{puerto}"

    def recordar_lo_que_ya_contesto(self) -> None:
        """Lo que el usuario ya contestó en su cuestionario y en la card de otras postulaciones."""
        uid = self.mundo.usuario.id
        self.nucleo.guardar_cuestionario(uid, {
            "salario": "1300000", "correo": "ana@gmail.com", "telefono": "3105551234",
            "pais": "Colombia", "autorizacion_trabajo:colombia": "Sí",
        })  # fmt: skip
        self.nucleo.documentos.guardar(self.mundo.usuario, "certificado_notas", "Notas",
                                       b"%PDF-1.4 notas", T0)  # fmt: skip
        recordar(self.nucleo.base, uid, "Are you located in Bogotá?", "Yes", T0)
        promedio = "Please list your current cumulative GPA."
        recordar(self.nucleo.base, uid, promedio, "4.0 - 4.09", T0)

    def encolar(self):
        p, _ = self.nucleo.cola.encolar(self.mundo.usuario.id, id_corto("computrabajo:9"),
                                        "linkedin", T0)  # fmt: skip
        return p

    def trabajo(self, p) -> dict:
        """El trabajo que le daría el latido (con la receta del sitio). La postulación viene de
        LinkedIn (así «¿cómo te enteraste?» se responde con una opción de la lista); la
        extensión de estas pruebas solo conoce la plataforma de prueba."""
        from buscador_vacantes.asistente.api import _trabajo

        return {**_trabajo(self.nucleo, p), "plataforma": "prueba"}

    def guardar_receta(self, mapeo: dict[str, str]) -> int:
        receta = recetas.Receta(
            pantallas=[recetas.PantallaReceta(
                firma=sorted(mapeo), mapeo=mapeo,
                boton=recetas.BotonReceta(texto="Submit application", clase="enviar"),
            )],
            senal="texto",
        )  # fmt: skip
        return recetas.guardar_receta(
            self.nucleo.base, host=recetas.host_de(GH), ruta=recetas.ruta_patron(GH),
            familia="greenhouse", receta=receta, origen="real", ahora=T0, enviada=True,
        )  # fmt: skip

    def llamadas_a_la_ia(self) -> int:
        return self.nucleo.base.cx.execute("SELECT COUNT(*) FROM ia_uso").fetchone()[0]

    def estado(self, pid: int):
        return self.nucleo.cola.obtener(pid)

    def pasos(self, pid: int) -> list[tuple[str, str | None]]:
        filas = self.nucleo.base.cx.execute(
            "SELECT paso, detalle FROM postulacion_pasos WHERE postulacion_id = ? ORDER BY id",
            (pid,),
        )
        return [(f["paso"], f["detalle"]) for f in filas]

    def cerrar(self) -> None:
        self.proceso.should_exit = True
        self.hilo.join(5)
        self.mundo.cerrar()


@pytest.fixture
def real(tmp_path):
    servidor = Servidor(tmp_path / "servidor")
    yield servidor
    servidor.cerrar()


def correr_trabajo(tmp_path, real: Servidor, sitio: Sitio, pedido: dict) -> None:
    ejecutar(tmp_path, SimpleNamespace(url=real.url), sitio, pedido)


class SitioConCuerpos(Sitio):
    """Guarda también lo que lleva cada POST, para ver lo que se envió."""

    def __init__(self) -> None:
        super().__init__()
        self.cuerpos: list[str] = []

    async def atender(self, route) -> None:
        if route.request.method == "POST":
            self.cuerpos.append(route.request.post_data or "")
        await super().atender(route)


def sitio_con_pregunta_abierta() -> SitioConCuerpos:
    ancla = '<textarea id="g-recaptcha-response-100000"'
    sitio = SitioConCuerpos()
    sitio.poner(GH, "greenhouse.html", {ancla: PREGUNTA_ABIERTA + ancla})
    sitio.al_enviar(GH + "/enviar", "greenhouse_gracias.html")
    return sitio


def test_sin_clave_la_copia_de_greenhouse_con_receta_se_envia_sin_llamadas_a_la_ia(
    tmp_path, real
):
    real.guardar_receta(CAMPOS_GH)
    real.recordar_lo_que_ya_contesto()
    p = real.encolar()
    sitio = sitio_de("greenhouse")
    correr_trabajo(tmp_path / "navegador", real, sitio, real.trabajo(p))
    pendientes = [x["pregunta"] for x in real.nucleo.pendientes(real.mundo.usuario.id)]
    assert real.estado(p.id).estado == E.ENVIADA, (real.pasos(p.id), pendientes)
    assert sitio.contados(GH + "/enviar") == 1
    assert real.llamadas_a_la_ia() == 0
    assert not any(paso == "arbitro" for paso, _ in real.pasos(p.id))
    assert real.nucleo.pendientes(real.mundo.usuario.id) == []


def test_una_pregunta_abierta_va_a_la_card_y_la_respuesta_del_usuario_se_envia_tal_cual(
    tmp_path, real
):
    real.guardar_receta({**CAMPOS_GH, "question_110": "redactar"})
    real.recordar_lo_que_ya_contesto()
    p = real.encolar()
    sitio = sitio_con_pregunta_abierta()
    correr_trabajo(tmp_path / "primera", real, sitio, real.trabajo(p))
    # Sin clave nadie redacta: la card pregunta y no se envió nada
    assert real.estado(p.id).estado == E.ESPERANDO_USUARIO
    [pendiente] = real.nucleo.pendientes(real.mundo.usuario.id)
    assert pendiente["pregunta"].startswith("Why do you want to join our team?")
    assert sitio.posts == [] and real.llamadas_a_la_ia() == 0
    # El usuario contesta en la card y la postulación vuelve a la cola
    uid = real.mundo.usuario.id
    assert real.nucleo.responder_pendiente(uid, pendiente["id"], TEXTO_DEL_USUARIO)
    assert real.estado(p.id).estado == E.EN_COLA
    correr_trabajo(tmp_path / "segunda", real, sitio, real.trabajo(p))
    assert real.estado(p.id).estado == E.ENVIADA, real.pasos(p.id)
    assert sitio.contados(GH + "/enviar") == 1
    enviado = " ".join(sitio.cuerpos).replace("+", " ")
    assert "Quiero aprender soporte" in enviado and "equipo real" in enviado
    assert real.llamadas_a_la_ia() == 0


def test_un_paso_que_falla_sin_clave_termina_en_respaldo_con_sin_ia_y_ofrece_configurarla(
    tmp_path, real
):
    real.guardar_receta({k: v for k, v in CAMPOS_GH.items()})
    real.recordar_lo_que_ya_contesto()
    p = real.encolar()
    sitio = Sitio()  # el botón de enviar cambió de texto: las reglas no lo reconocen
    boton = '<button type="submit" aria-disabled="false">Submit application</button>'
    sitio.poner(GH, "greenhouse.html", {boton: '<button type="button">Xyzzy</button>'})
    sitio.al_enviar(GH + "/enviar", "greenhouse_gracias.html")
    pedido = real.trabajo(p)
    pedido["receta"]["pantallas"][0]["boton"] = None  # y la receta tampoco sabe cuál es
    correr_trabajo(tmp_path / "navegador", real, sitio, pedido)
    assert real.estado(p.id).estado == E.FORMULARIO_DESCONOCIDO, real.pasos(p.id)
    assert sitio.posts == [] and real.llamadas_a_la_ia() == 0
    [evento] = [
        e for e in real.mundo.eventos if getattr(e, "estado", None) == E.FORMULARIO_DESCONOCIDO
    ]
    assert evento.detalle == "sin_ia"
    card = tp.Card(fase=tp.RESPALDO, motivo=evento.detalle)
    d = tp.Datos(pid=p.id, titulo="Practicante de soporte", empresa="ACME",
                 plataforma="computrabajo", url=GH)  # fmt: skip
    assert "Con tu clave de IA puedo seguir sola" in tp.texto(card, d)
    assert "Configurar IA" in [b[0] for fila in tp.botones(card, d, lambda *a: "x") for b in fila]
