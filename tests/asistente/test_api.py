import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="requiere uv sync --group asistente")
pytest.importorskip("cryptography", reason="requiere uv sync --group asistente")

from fastapi.testclient import TestClient  # noqa: E402

from buscador_vacantes.asistente import api as api_modulo  # noqa: E402
from buscador_vacantes.asistente import destinos_linkedin, vinculos  # noqa: E402
from buscador_vacantes.asistente.api import (  # noqa: E402
    LIMITE_PING_POR_MINUTO,
    MAX_CUERPO,
    PaqueteDocumentos,
    ResultadoFormulario,
    crear_app,
    sin_valores,
)
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import Cola, E  # noqa: E402
from buscador_vacantes.asistente.cuentas_portal import CuentasPortal  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.asistente.pantalla import (  # noqa: E402
    AccionPagina,
    AccionReparacion,
    DecisionPagina,
    Reparacion,
)
from buscador_vacantes.asistente.preferencias import Preferencias  # noqa: E402
from buscador_vacantes.asistente.respuestas import Origen, Pregunta, Respuesta  # noqa: E402
from buscador_vacantes.asistente.usuarios_linkedin import UsuariosLinkedin  # noqa: E402
from buscador_vacantes.comun.config import cargar_configuracion  # noqa: E402
from buscador_vacantes.comun.estado import a_texto  # noqa: E402

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
CT = "computrabajo"
CORREO = "ana.perez@gmail.com"


class NucleoFalso:
    def __init__(self, tmp_path: Path):
        self.base = BaseAsistente.abrir(tmp_path / "a.db")
        self.config = cargar_configuracion().asistente
        self.cola = Cola(self.base, self.config)
        self.cuentas = CuentasPortal(self.base, Cifrador(generar_clave()))
        self.preferencias = Preferencias(self.base)
        self.archivos = tmp_path / "archivos"
        self.momento = T0
        self.eventos: list = []
        self.con_selectores = {CT}
        self.faltan = False
        self.revisar = False
        self.preguntas = []
        self.arbitro = None  # función Consulta → DecisionPagina; None simula «sin IA»
        self.consultas: list = []
        self.reparador = None  # función ConsultaReparacion → Reparacion; None: «sin IA»
        self.reparaciones: list = []
        self.ensayo = False  # lo que devuelve en_ensayo
        self.resuelto: dict = {}  # lo que devuelve esquema_resuelto
        self.linkedin = UsuariosLinkedin(self.base)
        self.permiso = True  # lo que devuelve permiso_externo
        self.redirecciones: dict[str, str] = {}  # acortador → URL final (resolver_redireccion)
        self.esquemas_leidos: list = []  # (familia, url) que preparar_esquema recibió
        self.esquema_completo = True  # False: falta un dato del usuario (esperar_usuario)
        self.paquete_documentos = PaqueteDocumentos()  # lo que devuelve documentos_pantalla
        self.documentos_pedidos: list = []
        self.demora_resolver: timedelta | None = None
        self.eventos_vigilar: list = []
        self.cv = tmp_path / "CV_Ana_Perez.pdf"
        self.cv.write_bytes(b"%PDF-1.4 cv")
        with self.base.transaccion() as cx:
            for uid in (1, 2):
                cx.execute(
                    "INSERT INTO usuarios(id, telegram_id, directorio, creado, estado) "
                    "VALUES (?, ?, ?, 'x', 'activo')",
                    (uid, uid, f"u{uid}"),
                )
            cx.execute(
                "INSERT INTO vacantes(id_corto, clave, fuente, plataforma, url, titulo, "
                "indexada_en) VALUES ('abc', 'computrabajo:1', 'computrabajo', 'computrabajo', "
                "'https://co.computrabajo.com/ofertas-de-trabajo/oferta-1', 'Practicante', 'x')"
            )

    def ahora(self):
        return self.momento

    def vacante(self, id_corto):
        fila = self.base.cx.execute("SELECT * FROM vacantes WHERE id_corto = ?", (id_corto,))
        fila = fila.fetchone()
        return dict(fila) if fila else None

    def selectores(self, plataforma):
        return ("1", {"postular": "#postular"}) if plataforma in self.con_selectores else None

    async def resolver_formulario(self, postulacion, preguntas):
        self.preguntas = preguntas
        if self.demora_resolver:
            # Una resolución larga: el reloj avanza, el latido del servidor tiene tiempo de
            # correr y la cola vigila a mitad, como cada minuto en producción
            self.momento += self.demora_resolver
            await asyncio.sleep(0.05)
            self.eventos_vigilar.append(self.cola.vigilar(self.momento))
        if self.revisar:
            return ResultadoFormulario(revisar=True)
        if self.faltan:
            return ResultadoFormulario(faltan=[Respuesta(preguntas[0], falta=True)])
        respuestas = [Respuesta(p, valor="Sí", origen=Origen.PERFIL) for p in preguntas
                      if p.tipo != "archivo"]  # el CV lo adjunta la extensión
        return ResultadoFormulario(respuestas=respuestas, cv=self.cv)

    async def arbitrar_pantalla(self, postulacion, consulta):
        self.consultas.append(consulta)
        return self.arbitro(consulta) if self.arbitro else None  # None: sin IA

    async def reparar_pantalla(self, postulacion, consulta):
        self.reparaciones.append(consulta)
        return self.reparador(consulta) if self.reparador else None

    def en_ensayo(self, postulacion):
        return self.ensayo or postulacion.tipo == "vigia"

    def esquema_resuelto(self, postulacion):
        return self.resuelto

    async def resolver_redireccion(self, url):
        return self.redirecciones.get(url, url)

    def permiso_externo(self, usuario_id):
        return self.permiso

    def destino_guardado(self, postulacion):
        if postulacion.plataforma != "linkedin" or not postulacion.id_corto:
            return None
        return destinos_linkedin.vigente(
            self.base, postulacion.id_corto, self.momento, self.config.linkedin.destino_dias
        )

    def pausar_linkedin(self, usuario_id):
        hasta = self.momento + timedelta(hours=self.config.linkedin.pausa_seguridad_h)
        self.linkedin.pausar(usuario_id, hasta)
        return hasta

    async def preparar_esquema(self, postulacion, familia, url):
        self.esquemas_leidos.append((familia, url))
        return self.esquema_completo

    async def documentos_pantalla(self, postulacion, preguntas):
        self.documentos_pedidos.append(preguntas)
        return self.paquete_documentos

    async def notificar(self, evento):
        self.eventos.append(evento)


@pytest.fixture
def entorno(tmp_path):
    nucleo = NucleoFalso(tmp_path)
    cliente = TestClient(crear_app(nucleo))
    yield nucleo, cliente
    nucleo.base.cerrar()


def vincular(nucleo, cliente, usuario_id=1):
    codigo = vinculos.crear_codigo(nucleo.base, usuario_id, nucleo.momento)
    cuerpo = {"codigo": vinculos.mostrar_codigo(codigo), "nombre": "Edge casa", "version": "1.0.0"}
    r = cliente.post("/api/v1/vincular", json=cuerpo)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def latido(cliente, cabeceras, estado="listo", correo=CORREO, version="1.0.0"):
    return cliente.post(
        "/api/v1/latido",
        headers=cabeceras,
        json={"version": version, "portales": {CT: {"estado": estado, "correo": correo}}},
    ).json()


def latido_con(cliente, cabeceras, portales, **extra):
    return cliente.post(
        "/api/v1/latido",
        headers=cabeceras,
        json={"version": "1.0.0", "portales": portales, **extra},
    ).json()


def portales_guardados(nucleo, navegador_id=1):
    fila = nucleo.base.cx.execute(
        "SELECT portales_json FROM navegadores WHERE id = ?", (navegador_id,)
    ).fetchone()
    return json.loads(fila[0])


def preparar_cuenta(nucleo, cliente, cab):
    latido(cliente, cab)  # primera vez: por confirmar
    nucleo.cuentas.confirmar(1, CT, T0)


def test_codigo_vencido_o_usado(entorno):
    nucleo, cliente = entorno
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    nucleo.momento = T0 + timedelta(minutes=11)
    assert cliente.post("/api/v1/vincular", json={"codigo": codigo}).status_code == 400
    nucleo.momento = T0
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    assert cliente.post("/api/v1/vincular", json={"codigo": codigo}).status_code == 200
    assert cliente.post("/api/v1/vincular", json={"codigo": codigo}).status_code == 400


def test_pagina_de_vinculo_lleva_el_codigo(entorno):
    nucleo, cliente = entorno
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    r = cliente.get(f"/api/v1/vincular/{codigo}")
    assert r.status_code == 200 and f'data-codigo="{codigo}"' in r.text


def test_pagina_de_vinculo_vuelve_al_bot_de_telegram(entorno):
    nucleo, cliente = entorno
    nucleo.config.bot_usuario = "mi_bot"
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    texto = cliente.get(f"/api/v1/vincular/{codigo}").text
    assert 'href="https://t.me/mi_bot"' in texto and "Volver a Telegram" in texto
    assert "¡Navegador vinculado con éxito!" in texto and vinculos.mostrar_codigo(codigo) in texto


def test_pagina_de_vinculo_sin_bot_configurado_no_ofrece_el_boton(entorno):
    nucleo, cliente = entorno
    nucleo.config.bot_usuario = ""
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    assert "Volver a Telegram" not in cliente.get(f"/api/v1/vincular/{codigo}").text


def test_politica_de_privacidad_publica(entorno):
    _, cliente = entorno
    r = cliente.get("/api/v1/privacidad")
    assert r.status_code == 200 and "contraseñas" in r.text and "/borrarme" in r.text


def test_ping_publico_sin_token(entorno):
    _, cliente = entorno
    r = cliente.get("/api/v1/ping")
    assert r.status_code == 200 and r.json() == {"ok": True}  # sin versión ni datos


def test_ping_no_cuenta_como_latido(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    latido(cliente, cab)
    consulta = "SELECT ultimo_latido FROM navegadores"
    antes = nucleo.base.cx.execute(consulta).fetchone()[0]
    nucleo.momento = T0 + timedelta(minutes=5)
    assert cliente.get("/api/v1/ping", headers=cab).status_code == 200
    assert nucleo.base.cx.execute(consulta).fetchone()[0] == antes


def test_ping_limitado_por_ip(entorno):
    nucleo, cliente = entorno
    for _ in range(LIMITE_PING_POR_MINUTO):
        assert cliente.get("/api/v1/ping").status_code == 200
    assert cliente.get("/api/v1/ping").status_code == 429
    otra_ip = TestClient(cliente.app, client=("10.0.0.2", 50000))
    assert otra_ip.get("/api/v1/ping").status_code == 200


def test_token_invalido_401(entorno):
    _, cliente = entorno
    cab = {"Authorization": "Bearer x"}
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1"})
    assert r.status_code == 401


def test_cuerpo_grande_413(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post(
        "/api/v1/latido", headers={**cab, "Content-Type": "application/json"},
        content=b"{" + b" " * (MAX_CUERPO + 1) + b"}",
    )  # fmt: skip
    assert r.status_code == 413


def test_fuera_de_la_api_404(entorno):
    _, cliente = entorno
    assert cliente.get("/").status_code == 404
    assert cliente.get("/docs").status_code == 404


def test_primera_cuenta_pide_confirmar_y_no_da_trabajo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    nucleo.cola.encolar(1, "abc", CT, T0)
    respuesta = latido(cliente, cab)
    assert respuesta["trabajo"] is None and respuesta["cuentas"][CT] is False
    assert any(
        e.get("tipo") == "cuenta_por_confirmar" for e in nucleo.eventos if isinstance(e, dict)
    )


def test_flujo_completo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    trabajo = latido(cliente, cab)["trabajo"]
    assert trabajo["id"] == p.id and trabajo["url"].startswith("https://co.computrabajo.com")
    assert cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab).status_code == 200
    r = cliente.post(
        f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
        json={"campos": [{"texto": "¿Tienes computador?", "tipo": "opciones",
                          "opciones": ["Sí", "No"]}]},
    ).json()  # fmt: skip
    assert r["respuestas"][0]["valor"] == "Sí" and r["cv_nombre"] == "CV_Ana_Perez.pdf"
    pdf = cliente.get(r["cv_url"], headers=cab)
    assert pdf.content == b"%PDF-1.4 cv"
    assert cliente.get(r["cv_url"], headers=cab).status_code == 404  # un solo uso
    assert cliente.post(f"/api/v1/postulaciones/{p.id}/envio", headers=cab).status_code == 200
    html = '<form><input name="correo" value="ana@x.com"><textarea>hola</textarea></form>'
    cuerpo = {"estado": "enviada", "html": html, "confirmacion": "¡Postulado!"}
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/resultado", headers=cab, json=cuerpo)
    assert r.status_code == 200
    assert nucleo.cola.obtener(p.id).estado == E.ENVIADA
    archivo = nucleo.base.cx.execute("SELECT archivo FROM evidencia").fetchone()[0]
    guardado = Path(archivo).read_text(encoding="utf-8")
    assert "ana@x.com" not in guardado and "hola" not in guardado


def test_dos_tomar_simultaneos_uno_gana(entorno):
    nucleo, cliente = entorno
    cab1 = vincular(nucleo, cliente)
    cab2 = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab1)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    codigos = [
        cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=c).status_code
        for c in (cab1, cab2)
    ]
    assert sorted(codigos) == [200, 409]


def test_otro_usuario_no_ve_la_postulacion(entorno):
    nucleo, cliente = entorno
    cab_luis = vincular(nucleo, cliente, usuario_id=2)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    assert cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab_luis).status_code == 404


def test_dato_faltante_libera_la_postulacion(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    nucleo.faltan = True
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
                     json={"campos": [{"texto": "¿Licencia de conducción?"}]}).json()  # fmt: skip
    assert r == {"esperar_usuario": True}
    assert nucleo.cola.obtener(p.id).estado == E.ESPERANDO_USUARIO


def test_formulario_lleva_el_maximo_del_campo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
                     json={"campos": [{"texto": "¿Por qué te interesa?", "maximo": 150},
                                      {"texto": "Ciudad"}]})  # fmt: skip
    assert r.status_code == 200
    assert [q.maximo for q in nucleo.preguntas] == [150, None]


def test_revision_de_respuestas_libera_la_postulacion(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    nucleo.revisar = True
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
                     json={"campos": [{"texto": "¿Por qué te interesa?"}]}).json()  # fmt: skip
    assert r == {"esperar_usuario": True}
    assert nucleo.cola.obtener(p.id).estado == E.ESPERANDO_USUARIO


def test_formulario_largo_no_deja_la_postulacion_como_navegador_cerrado(entorno, monkeypatch):
    """Postulación 55: resolver el formulario tarda más que `navegador_caido_min` y la cola,
    que vigila cada minuto, la marcaba como navegador cerrado aunque el servidor siguiera
    trabajando. Mientras resuelve, el servidor mantiene vivo el latido del navegador."""
    nucleo, cliente = entorno
    monkeypatch.setattr(api_modulo, "LATIDO_FORMULARIO_S", 0.01, raising=False)
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    nucleo.demora_resolver = timedelta(minutes=nucleo.config.extension.navegador_caido_min + 1)
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
                     json={"campos": [{"texto": "¿Tienes computador?"}]})  # fmt: skip
    assert r.status_code == 200
    # La vigilancia corrió a mitad de la resolución, con el reloj ya pasado del plazo
    assert nucleo.eventos_vigilar == [[]]
    assert nucleo.cola.obtener(p.id).estado == E.EN_CURSO
    pasos = nucleo.base.cx.execute(
        "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? AND paso = ?",
        (p.id, "formulario_resuelto"),
    ).fetchall()
    assert len(pasos) == 1 and pasos[0]["detalle"].endswith(" s")


def test_formulario_acepta_el_esquema_ampliado_de_la_extension_nueva(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    campo = {"texto": "Ciudad", "ayuda": "Donde vives", "autocomplete": "address-level2",
             "accept": None, "idioma": "es", "busqueda": True}  # fmt: skip
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
                     json={"campos": [campo]})  # fmt: skip
    assert r.status_code == 200 and r.json()["respuestas"][0]["indice"] == 0


def test_formulario_pasa_el_esquema_ampliado_a_las_preguntas(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    campo = {"texto": "First Name", "ayuda": "Como en tu cédula", "autocomplete": "given-name",
             "accept": ".pdf", "idioma": "en", "busqueda": True}  # fmt: skip
    cliente.post(f"/api/v1/postulaciones/{p.id}/formulario", headers=cab, json={"campos": [campo]})
    [q] = nucleo.preguntas
    assert (q.ayuda, q.autocomplete, q.accept, q.idioma, q.busqueda) == (
        "Como en tu cédula", "given-name", ".pdf", "en", True,
    )  # fmt: skip


# --- /pantalla: decisión de cada pantalla del bucle genérico ---------------------------------


def boton(indice, texto, clase=None, **extra):
    return {"indice": indice, "texto": texto, "clase": clase, "oauth": False, "tipo": "button",
            "en_contenedor": True, **extra}  # fmt: skip


def pantalla(clase="formulario", **extra):
    base = {"numero": 1, "clase": clase, "motivo": None, "idioma": "es", "url": "https://x.co/a",
            "campos": [], "botones": [], "sugerido": None, "firma": [],
            "resumen": {"elementos": [], "encabezados": [], "avisos": []},
            "exito": None, "correccion": False}  # fmt: skip
    return {**base, **extra}


def en_curso(nucleo, cliente, nivel=None):
    """Postulación en curso; `nivel` es el de IA del usuario al encolar (por defecto, Normal)."""
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    if nivel:
        nucleo.preferencias.fijar_nivel_ia(1, nivel)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    return p, cab


def decidir(cliente, p, cab, cuerpo):
    return cliente.post(f"/api/v1/postulaciones/{p.id}/pantalla", headers=cab, json=cuerpo)


def test_pantalla_decide_por_reglas_sin_llamar_a_la_ia(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    cuerpo = pantalla(
        campos=[{"texto": "First name", "autocomplete": "given-name"},
                {"texto": "Resume", "tipo": "archivo", "accept": ".pdf"}],
        botones=[boton(0, "Cancelar", "nunca"), boton(1, "Submit application", "enviar")],
        sugerido={"indice": 1, "accion": "enviar"},
    )  # fmt: skip
    r = decidir(cliente, p, cab, cuerpo)
    assert r.status_code == 200
    d = r.json()
    assert d["esperar_usuario"] is False
    assert d["accion"] == {"tipo": "enviar", "indice": 1}
    assert [x["indice"] for x in d["respuestas"]] == [0]  # el archivo lo adjunta el CV
    assert d["cv_nombre"] == "CV_Ana_Perez.pdf" and d["documentos"] == {}
    assert cliente.get(d["cv_url"], headers=cab).content == b"%PDF-1.4 cv"
    assert nucleo.consultas == []  # el árbitro no entró
    assert [q.tipo for q in nucleo.preguntas] == ["texto", "archivo"]


def test_pantalla_el_idioma_de_la_pagina_llega_a_los_campos_que_no_traen_el_suyo(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    campos = [{"texto": "First Name", "autocomplete": "given-name"},
              {"texto": "Ciudad", "idioma": "es"}]  # fmt: skip
    decidir(cliente, p, cab, pantalla(idioma="en", campos=campos))
    assert [q.idioma for q in nucleo.preguntas] == ["en", "es"]
    assert nucleo.preguntas[0].autocomplete == "given-name"


def test_pantalla_sin_campo_de_archivo_no_ofrece_el_cv(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    cuerpo = pantalla(campos=[{"texto": "Ciudad"}], botones=[boton(0, "Siguiente", "avanzar")],
                      sugerido={"indice": 0, "accion": "avanzar"})  # fmt: skip
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d["cv_url"] is None and d["cv_nombre"] is None
    assert d["accion"] == {"tipo": "avanzar", "indice": 0}


def test_pantalla_intermedia_avanza_sin_resolver_campos(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    cuerpo = pantalla("intermedia", botones=[boton(0, "Apply now", "intermedia")],
                      sugerido={"indice": 0, "accion": "avanzar"})  # fmt: skip
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d["respuestas"] == [] and d["accion"] == {"tipo": "avanzar", "indice": 0}
    assert nucleo.preguntas == []


def test_pantalla_la_clase_del_boton_manda_sobre_lo_sugerido(entorno):
    """Solo un botón `enviar` registra el envío; si la extensión sugiere avanzar sobre uno, el
    servidor lo trata como enviar, y un botón `nunca` no se pulsa aunque venga sugerido."""
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    cuerpo = pantalla(botones=[boton(0, "Enviar solicitud", "enviar")],
                      sugerido={"indice": 0, "accion": "avanzar"})  # fmt: skip
    assert decidir(cliente, p, cab, cuerpo).json()["accion"] == {"tipo": "enviar", "indice": 0}
    cuerpo = pantalla(botones=[boton(0, "Continuar con Google", "nunca", oauth=True)],
                      sugerido={"indice": 0, "accion": "avanzar"})  # fmt: skip
    assert decidir(cliente, p, cab, cuerpo).json()["accion"] == {"tipo": "respaldo",
                                                                 "motivo": "sin_ia"}  # fmt: skip


def test_pantalla_pregunta_al_usuario_lo_que_falta(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.faltan = True
    cuerpo = pantalla(campos=[{"texto": "¿Licencia de conducción?"}],
                      botones=[boton(0, "Enviar", "enviar")],
                      sugerido={"indice": 0, "accion": "enviar"})  # fmt: skip
    assert decidir(cliente, p, cab, cuerpo).json() == {"esperar_usuario": True}
    assert nucleo.cola.obtener(p.id).estado == E.ESPERANDO_USUARIO


def test_pantalla_revision_de_respuestas_libera_la_postulacion(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.revisar = True
    cuerpo = pantalla(campos=[{"texto": "¿Por qué te interesa?"}])
    assert decidir(cliente, p, cab, cuerpo).json() == {"esperar_usuario": True}
    assert nucleo.cola.obtener(p.id).estado == E.ESPERANDO_USUARIO


def test_pantalla_de_exito_y_de_barrera_no_llaman_a_la_ia(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    d = decidir(cliente, p, cab, pantalla("exito", exito={"senal": "texto", "texto": "Gracias"}))
    assert d.json()["accion"] == {"tipo": "exito", "texto": "Gracias"}
    d = decidir(cliente, p, cab, pantalla("barrera", motivo="captcha"))
    assert d.json()["accion"] == {"tipo": "respaldo", "motivo": "captcha"}
    assert nucleo.consultas == []


def arbitro_con(clase, *acciones, motivo=""):
    return lambda consulta: DecisionPagina(
        clase=clase, acciones=[AccionPagina(accion=a, indice=i) for a, i in acciones], motivo=motivo
    )


def test_pantalla_desconocida_la_decide_el_arbitro(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.arbitro = arbitro_con("intermedia", ("avanzar", 1))
    cuerpo = pantalla(
        "desconocida", url="https://empresa.co/jobs/1",
        botones=[boton(0, "Compartir"), boton(1, "Quick apply")],
        resumen={"elementos": [{"indice": 0, "rol": "button", "texto": "Quick apply"}],
                 "encabezados": ["Backend Engineer"], "avisos": []},
    )  # fmt: skip
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d["accion"] == {"tipo": "avanzar", "indice": 1} and d["respuestas"] == []
    (consulta,) = nucleo.consultas
    peticion = consulta.peticion
    assert peticion.clase == "desconocida" and peticion.resumen.encabezados == ["Backend Engineer"]
    assert [b.texto for b in peticion.botones] == ["Compartir", "Quick apply"]
    pasos = nucleo.base.cx.execute(
        "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? AND paso = 'arbitro'",
        (p.id,),
    ).fetchall()
    assert len(pasos) == 1


def test_pantalla_con_campos_y_boton_dudoso_llena_por_reglas_y_el_arbitro_elige_el_boton(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.arbitro = arbitro_con("formulario", ("enviar", 0))
    cuerpo = pantalla(campos=[{"texto": "Ciudad"}], botones=[boton(0, "Apply"), boton(1, "Back")])
    d = decidir(cliente, p, cab, cuerpo).json()
    assert [x["indice"] for x in d["respuestas"]] == [0]
    assert d["accion"] == {"tipo": "enviar", "indice": 0}  # botón sin clase: vale lo del árbitro


@pytest.mark.parametrize(
    ("veredicto", "esperada"),
    [
        (arbitro_con("intermedia", ("avanzar", 7)), {"tipo": "respaldo",
                                                      "motivo": "pantalla_desconocida"}),
        (arbitro_con("intermedia", ("enviar", 0)), {"tipo": "respaldo",
                                                     "motivo": "pantalla_desconocida"}),
        (arbitro_con("intermedia", ("avanzar", 1)), {"tipo": "enviar", "indice": 1}),
        (arbitro_con("intermedia", ("avanzar", 2)), {"tipo": "avanzar", "indice": 2}),
        (arbitro_con("intermedia", ("esperar", None)), {"tipo": "esperar", "ms": 1500}),
        (arbitro_con("barrera"), {"tipo": "respaldo", "motivo": "barrera"}),
        (arbitro_con("desconocida"), {"tipo": "respaldo", "motivo": "pantalla_desconocida"}),
        (arbitro_con("exito", motivo=" Gracias  por postular "),
         {"tipo": "exito", "texto": "Gracias por postular"}),
    ],
)  # fmt: skip
def test_pantalla_el_arbitro_solo_actua_dentro_de_la_lista_cerrada(entorno, veredicto, esperada):
    """Índice inexistente o de un botón `nunca`: se descarta. La clase del botón manda sobre la
    acción que pida el árbitro."""
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.arbitro = veredicto
    botones = [boton(0, "Continuar con Google", "nunca", oauth=True),
               boton(1, "Enviar solicitud", "enviar"), boton(2, "Siguiente")]  # fmt: skip
    d = decidir(cliente, p, cab, pantalla("desconocida", botones=botones))
    assert d.json()["accion"] == esperada


def test_pantalla_sin_ia_va_a_respaldo(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    d = decidir(cliente, p, cab, pantalla("desconocida", botones=[boton(0, "Quick apply")]))
    assert d.json()["accion"] == {"tipo": "respaldo", "motivo": "sin_ia"}
    assert len(nucleo.consultas) == 1


def test_pantalla_tope_de_llamadas_al_arbitro_por_postulacion(entorno):
    nucleo, cliente = entorno
    nucleo.config.motor_generico.max_arbitro = 2
    p, cab = en_curso(nucleo, cliente)
    nucleo.arbitro = arbitro_con("intermedia", ("avanzar", 0))
    cuerpo = pantalla("desconocida", botones=[boton(0, "Quick apply")])
    acciones = [decidir(cliente, p, cab, cuerpo).json()["accion"] for _ in range(3)]
    assert acciones[:2] == [{"tipo": "avanzar", "indice": 0}] * 2
    assert acciones[2] == {"tipo": "respaldo", "motivo": "tope_arbitro"}
    assert len(nucleo.consultas) == 2


def test_pantalla_publica_los_documentos_y_la_extension_los_baja_una_sola_vez(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.paquete_documentos = PaqueteDocumentos(
        {"carta": ("Carta_Ana_Perez.pdf", b"%PDF-1.4 carta")}
    )
    cuerpo = pantalla(
        campos=[{"texto": "Resume", "tipo": "archivo"},
                {"texto": "Cover letter", "tipo": "archivo", "obligatoria": False}],
        botones=[boton(0, "Submit application", "enviar")],
        sugerido={"indice": 0, "accion": "enviar"},
    )  # fmt: skip
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d["documentos"]["carta"]["nombre"] == "Carta_Ana_Perez.pdf"
    bajada = cliente.get(d["documentos"]["carta"]["url"], headers=cab)
    assert bajada.status_code == 200 and bajada.content == b"%PDF-1.4 carta"
    assert "Carta_Ana_Perez.pdf" in bajada.headers["content-disposition"]
    assert cliente.get(d["documentos"]["carta"]["url"], headers=cab).status_code == 404
    assert [q.texto for q in nucleo.documentos_pedidos[0]] == ["Resume", "Cover letter"]


def test_pantalla_con_un_documento_obligatorio_que_falta_espera_al_usuario(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.paquete_documentos = PaqueteDocumentos(faltan=[Pregunta("Transcript", "archivo")])
    cuerpo = pantalla(
        campos=[{"texto": "Transcript", "tipo": "archivo"}],
        botones=[boton(0, "Submit application", "enviar")],
        sugerido={"indice": 0, "accion": "enviar"},
    )  # fmt: skip
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d == {"esperar_usuario": True}
    assert nucleo.cola.obtener(p.id).estado == E.ESPERANDO_USUARIO


def test_pantalla_sin_campos_de_archivo_no_pide_documentos(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    cuerpo = pantalla(botones=[boton(0, "Submit application", "enviar")],
                      sugerido={"indice": 0, "accion": "enviar"})  # fmt: skip
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d["documentos"] == {} and nucleo.documentos_pedidos == []


def guardar_receta_de_prueba(nucleo, p, cuerpo, boton_texto):
    """Receta del host de la vacante con el mapeo de los campos de `cuerpo`."""
    from buscador_vacantes.asistente import recetas

    mapeo = {recetas.clave_campo(c.get("nombre"), c["texto"]): "salario" for c in cuerpo["campos"]}
    receta = recetas.Receta(
        pantallas=[recetas.PantallaReceta(
            firma=sorted(mapeo), mapeo=mapeo,
            boton=recetas.BotonReceta(texto=boton_texto, clase="enviar"),
        )], senal="texto",
    )  # fmt: skip
    receta_id = recetas.guardar_receta(
        nucleo.base, host="co.computrabajo.com", ruta="/ofertas-de-trabajo/*", familia="x",
        receta=receta, origen="real", ahora=T0, enviada=True,
    )  # fmt: skip
    with nucleo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET receta_id = ? WHERE id = ?", (receta_id, p.id))


def test_pantalla_con_receta_pasa_el_campo_conocido_y_decide_el_boton_sin_arbitro(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    cuerpo = pantalla(
        campos=[{"texto": "Pretensión mensual", "nombre": "question_9"}],
        botones=[boton(0, "Back", "avanzar"), boton(1, "Submit application", "enviar")],
    )  # fmt: skip
    guardar_receta_de_prueba(nucleo, p, cuerpo, "Submit application")
    nucleo.arbitro = arbitro_con("intermedia", ("avanzar", 0))  # no debe consultarse
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d["accion"] == {"tipo": "enviar", "indice": 1}
    assert [q.campo_receta for q in nucleo.preguntas] == ["salario"]
    assert nucleo.consultas == []


def test_pantalla_con_receta_de_otra_forma_no_la_aplica(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    antes = pantalla(campos=[{"texto": "Pretensión mensual", "nombre": "question_9"}],
                     botones=[boton(1, "Submit application", "enviar")])  # fmt: skip
    guardar_receta_de_prueba(nucleo, p, antes, "Submit application")
    ahora = pantalla(campos=[{"texto": "Ciudad", "nombre": "city"},
                             {"texto": "País", "nombre": "country"}],
                     botones=[boton(1, "Submit application", "enviar")])  # fmt: skip
    nucleo.arbitro = arbitro_con("intermedia", ("avanzar", 1))
    d = decidir(cliente, p, cab, ahora).json()
    assert [q.campo_receta for q in nucleo.preguntas] == [None, None]
    assert len(nucleo.consultas) == 1 and d["accion"] == {"tipo": "enviar", "indice": 1}


def test_pantalla_en_ahorro_no_consulta_al_arbitro_y_va_a_respaldo_nivel_ahorro(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente, "ahorro")
    nucleo.arbitro = arbitro_con("intermedia", ("avanzar", 0))
    cuerpo = pantalla("desconocida", botones=[boton(0, "Quick apply")])
    d = decidir(cliente, p, cab, cuerpo).json()
    assert d["accion"] == {"tipo": "respaldo", "motivo": "nivel_ahorro"}
    assert nucleo.consultas == []
    # Lo que las reglas deciden sigue funcionando en Ahorro: el nivel solo quita llamadas a la IA
    por_reglas = pantalla(botones=[boton(1, "Submit application", "enviar")],
                          sugerido={"indice": 1, "accion": "enviar"})  # fmt: skip
    assert decidir(cliente, p, cab, por_reglas).json()["accion"] == {"tipo": "enviar", "indice": 1}


@pytest.mark.parametrize(("nivel", "tope"), [("normal", 3), ("maximo", 6)])
def test_pantalla_tope_del_arbitro_segun_el_nivel(entorno, nivel, tope):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente, nivel)
    nucleo.arbitro = arbitro_con("intermedia", ("avanzar", 0))
    cuerpo = pantalla("desconocida", botones=[boton(0, "Quick apply")])
    acciones = [decidir(cliente, p, cab, cuerpo).json()["accion"] for _ in range(tope + 1)]
    assert acciones[:tope] == [{"tipo": "avanzar", "indice": 0}] * tope
    assert acciones[tope] == {"tipo": "respaldo", "motivo": "tope_arbitro"}
    assert len(nucleo.consultas) == tope


def test_el_tope_de_motor_generico_manda_sobre_el_del_nivel(entorno):
    nucleo, cliente = entorno
    nucleo.config.motor_generico.max_arbitro = 1  # por debajo de lo que permite Máximo
    p, cab = en_curso(nucleo, cliente, "maximo")
    nucleo.arbitro = arbitro_con("intermedia", ("avanzar", 0))
    cuerpo = pantalla("desconocida", botones=[boton(0, "Quick apply")])
    acciones = [decidir(cliente, p, cab, cuerpo).json()["accion"] for _ in range(2)]
    assert acciones[1] == {"tipo": "respaldo", "motivo": "tope_arbitro"}
    assert len(nucleo.consultas) == 1


def test_cambiar_el_nivel_no_afecta_a_la_postulacion_en_curso(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente, "maximo")
    nucleo.preferencias.fijar_nivel_ia(1, "ahorro")  # después de encolar
    nucleo.reparador = reparacion_con(("avanzar", 1))
    assert reparar(cliente, p, cab).json()["accion"] is None  # sigue en Máximo
    assert reparar(cliente, p, cab).json()["accion"] is None
    assert len(nucleo.reparaciones) == 2


def test_postulacion_anterior_al_esquema_6_corre_en_normal_y_no_en_el_nivel_del_usuario(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente, "maximo")
    with nucleo.base.transaccion() as cx:
        cx.execute("UPDATE postulaciones SET nivel_ia = NULL WHERE id = ?", (p.id,))
    nucleo.reparador = reparacion_con(("avanzar", 1))
    assert reparar(cliente, p, cab).json()["accion"] is None
    assert reparar(cliente, p, cab).json()["accion"]["motivo"] == "tope_reparaciones"  # Normal: 1


def pasos_de(nucleo, p, paso):
    filas = nucleo.base.cx.execute(
        "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? AND paso = ?",
        (p.id, paso),
    ).fetchall()
    return [f["detalle"] for f in filas]


def test_la_bajada_por_cuota_deja_el_paso_nivel_bajado_una_sola_vez(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente, "maximo")
    cuerpo = pantalla("desconocida", botones=[boton(0, "Quick apply")])
    assert pasos_de(nucleo, p, "nivel_bajado") == []

    def arbitro_sin_cuota(consulta):
        # lo que hace ClienteIA cuando se agota la cuota del modelo de Máximo
        nucleo.preferencias.bajar_nivel(1, "normal", nucleo.momento)
        return DecisionPagina(
            clase="intermedia", acciones=[AccionPagina(accion="avanzar", indice=0)]
        )

    nucleo.arbitro = arbitro_sin_cuota
    decidir(cliente, p, cab, cuerpo)
    decidir(cliente, p, cab, cuerpo)
    assert pasos_de(nucleo, p, "nivel_bajado") == ["maximo>normal"]
    # El tope ya es el de Normal (3 consultas del árbitro): la 4.ª no se hace
    for _ in range(3):
        decidir(cliente, p, cab, cuerpo)
    assert len(nucleo.consultas) == 3


def test_la_bajada_vence_al_dia_siguiente(entorno):
    nucleo, cliente = entorno
    nucleo.preferencias.bajar_nivel(1, "ahorro", T0)
    assert nucleo.preferencias.nivel_efectivo(1, "maximo", T0) == "ahorro"
    assert nucleo.preferencias.nivel_efectivo(1, "normal", T0) == "ahorro"
    assert nucleo.preferencias.nivel_efectivo(1, "ahorro", T0) == "ahorro"
    manana = T0 + timedelta(days=1)
    assert nucleo.preferencias.nivel_efectivo(1, "maximo", manana) == "maximo"
    assert nucleo.preferencias.nivel_efectivo(1, None, manana) == "normal"
    # Una bajada no sube un nivel que ya estaba más bajo
    nucleo.preferencias.bajar_nivel(1, "normal", T0)
    assert nucleo.preferencias.nivel_bajado(1, T0) == "ahorro"


def test_pantalla_con_el_motor_apagado_o_sin_estar_en_curso(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.config.motor_generico.activo = False
    assert decidir(cliente, p, cab, pantalla()).status_code == 404
    nucleo.config.motor_generico.activo = True
    nucleo.cola.esperar_usuario(p.id, 1, T0)
    assert decidir(cliente, p, cab, pantalla()).status_code == 409


def test_pantalla_no_es_de_otro_usuario(entorno):
    nucleo, cliente = entorno
    p, _ = en_curso(nucleo, cliente)
    cab_luis = vincular(nucleo, cliente, usuario_id=2)
    assert decidir(cliente, p, cab_luis, pantalla()).status_code == 404


def test_pantalla_larga_no_deja_la_postulacion_como_navegador_cerrado(entorno, monkeypatch):
    nucleo, cliente = entorno
    monkeypatch.setattr(api_modulo, "LATIDO_FORMULARIO_S", 0.01, raising=False)
    p, cab = en_curso(nucleo, cliente)
    nucleo.demora_resolver = timedelta(minutes=nucleo.config.extension.navegador_caido_min + 1)
    cuerpo = pantalla(campos=[{"texto": "Ciudad"}], botones=[boton(0, "Siguiente", "avanzar")],
                      sugerido={"indice": 0, "accion": "avanzar"})  # fmt: skip
    assert decidir(cliente, p, cab, cuerpo).status_code == 200
    assert nucleo.eventos_vigilar == [[]]
    assert nucleo.cola.obtener(p.id).estado == E.EN_CURSO
    pasos = nucleo.base.cx.execute(
        "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? AND paso = ?",
        (p.id, "pantalla_resuelta"),
    ).fetchall()
    assert len(pasos) == 1 and pasos[0]["detalle"].endswith(" s")


def test_cuenta_distinta_no_da_trabajo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    respuesta = latido(cliente, cab, correo="luis.g@hotmail.com")
    assert respuesta["trabajo"] is None
    evento = [e for e in nucleo.eventos if isinstance(e, dict) and e["tipo"] == "cuenta_distinta"]
    assert evento and evento[0]["encontrado"] == "l***@hotmail.com"
    fila = nucleo.base.cx.execute("SELECT correo_cifrado FROM cuentas_portal").fetchone()
    assert "luis" not in fila[0]


def test_extension_desactualizada_no_recibe_trabajo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    nucleo.config.extension.version_minima = "1.2.0"
    respuesta = latido(cliente, cab, version="1.1.9")
    assert respuesta["actualizar"] is True and respuesta["trabajo"] is None


def test_perfil_incompleto_encola_completar_perfil(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    trabajo = latido(cliente, cab, estado="incompleto")["trabajo"]
    assert trabajo["tipo"] == "completar_perfil"


def test_token_revocado(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    vinculos.revocar(nucleo.base, 1)
    assert cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).status_code == 401


def test_sin_valores():
    texto = sin_valores('<input type="text" value="secreto"><textarea id=x>dato</textarea>')
    assert "secreto" not in texto and "dato" not in texto


def test_latido_entrega_los_enlaces_del_bot_y_el_grupo(entorno):
    nucleo, cliente = entorno
    nucleo.enlace_grupo = "https://t.me/c/4429829042/1"
    cab = vincular(nucleo, cliente)
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).json()
    assert r["enlaces"]["grupo"] == "https://t.me/c/4429829042/1"
    bot = nucleo.config.bot_usuario
    assert r["enlaces"]["bot"] == (f"https://t.me/{bot}" if bot else None)


def test_latido_entrega_la_version_de_las_reglas_del_motor_generico(entorno):
    from buscador_vacantes.asistente.reglas_motor import reglas

    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).json()
    assert r["motor_generico"] == reglas().version
    completo = cliente.get("/api/v1/motor_generico", headers=cab).json()
    assert completo["version"] == reglas().version
    assert "submit" in completo["reglas"]["textos"]["enviar"]["en"]
    assert "nota" not in completo["reglas"]
    assert cliente.get("/api/v1/motor_generico").status_code == 401  # sin token


def test_latido_entrega_la_version_de_los_datos_de_familias_de_ats(entorno):
    from buscador_vacantes.asistente.familias_ats import familias

    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).json()
    assert r["familias_ats"] == familias().version
    completo = cliente.get("/api/v1/familias_ats", headers=cab).json()
    assert completo["version"] == familias().version
    assert "Submit application" in completo["familias"]["greenhouse"]["enviar"]["textos"]
    assert "nota" not in completo
    assert cliente.get("/api/v1/familias_ats").status_code == 401  # sin token
    nucleo.config.motor_generico.activo = False
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).json()
    assert r["familias_ats"] is None
    assert cliente.get("/api/v1/familias_ats", headers=cab).status_code == 404


def test_motor_generico_apagado_no_entrega_reglas(entorno):
    nucleo, cliente = entorno
    nucleo.config.motor_generico.activo = False
    cab = vincular(nucleo, cliente)
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).json()
    assert r["motor_generico"] is None
    assert cliente.get("/api/v1/motor_generico", headers=cab).status_code == 404


def test_el_trabajo_lleva_los_topes_y_la_bandera_del_respaldo_declarado(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    motor = latido(cliente, cab)["trabajo"]["motor_generico"]
    assert motor == {"respaldo_declarado": False, "max_pantallas": 12,
                     "max_pantallas_una_pregunta": 40, "max_minutos": 10}  # fmt: skip
    nucleo.config.motor_generico.respaldo_declarado = True
    nucleo.config.motor_generico.max_pantallas = 5
    motor = latido(cliente, cab)["trabajo"]["motor_generico"]
    assert motor["respaldo_declarado"] is True and motor["max_pantallas"] == 5


def test_el_trabajo_no_lleva_el_motor_si_esta_apagado(entorno):
    nucleo, cliente = entorno
    nucleo.config.motor_generico.activo = False
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    assert "motor_generico" not in latido(cliente, cab)["trabajo"]


def test_enlace_del_grupo():
    from buscador_vacantes.asistente.servicio import enlace_grupo

    config = cargar_configuracion().asistente
    secretos = type("S", (), {"telegram_chat_id": "-1004429829042"})()
    assert enlace_grupo(config, secretos) == "https://t.me/c/4429829042/1"
    con_invitacion = config.model_copy(
        update={"grupo": config.grupo.model_copy(update={"enlace": "https://t.me/+abc"})}
    )
    assert enlace_grupo(con_invitacion, secretos) == "https://t.me/+abc"
    secretos.telegram_chat_id = "@canal"
    assert enlace_grupo(config, secretos) is None


# --- engranaje de cada portal: preferencias y cuenta ---------------------------------------


def test_preferencias_por_defecto(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.get(f"/api/v1/preferencias/{CT}", headers=cab)
    assert r.status_code == 200
    datos = r.json()
    assert datos["automatico"] is True
    assert datos["umbral"] is None
    assert datos["avisar"] is True
    assert datos["revisar_respuestas"] is False  # apagada por defecto
    assert datos["cuenta"] is None


def test_guardar_y_leer_preferencias(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post(
        f"/api/v1/preferencias/{CT}", headers=cab,
        json={"automatico": False, "umbral": 85, "avisar": False, "revisar_respuestas": True},
    )  # fmt: skip
    assert r.status_code == 200
    r = cliente.get(f"/api/v1/preferencias/{CT}", headers=cab)
    datos = r.json()
    assert datos == {
        "automatico": False, "umbral": 85, "avisar": False, "revisar_respuestas": True,
        "cuenta": None,
    }  # fmt: skip


def test_preferencias_con_cuenta_confirmada_muestra_el_detalle(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    r = cliente.get(f"/api/v1/preferencias/{CT}", headers=cab)
    cuenta = r.json()["cuenta"]
    assert cuenta["correo"] == CORREO
    assert cuenta["estado"] == "confirmada"
    assert cuenta["confirmada_en"]


def test_preferencias_plataforma_no_soportada_404(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    assert cliente.get("/api/v1/preferencias/getonboard", headers=cab).status_code == 404
    assert cliente.post("/api/v1/preferencias/getonboard", headers=cab, json={}).status_code == 404


def test_preferencias_umbral_fuera_de_rango_422(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post(f"/api/v1/preferencias/{CT}", headers=cab, json={"umbral": 150})
    assert r.status_code == 422


def test_nivel_ia_por_defecto_es_normal_con_el_consumo_de_cada_nivel(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.get("/api/v1/nivel_ia", headers=cab)
    assert r.status_code == 200
    datos = r.json()
    assert datos["nivel"] == "normal"
    niveles = nucleo.config.niveles_ia
    assert [(n["clave"], n["nombre"], n["llamadas_estimadas"]) for n in datos["niveles"]] == [
        ("ahorro", "Ahorro", niveles.ahorro.llamadas_estimadas),
        ("normal", "Normal", niveles.normal.llamadas_estimadas),
        ("maximo", "Máximo", niveles.maximo.llamadas_estimadas),
    ]
    assert datos["hoy"] == {"llamadas": 0, "tokens": 0}


def test_guardar_el_nivel_ia_es_por_usuario(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post("/api/v1/nivel_ia", headers=cab, json={"nivel": "maximo"})
    assert r.status_code == 200 and r.json() == {"ok": True, "nivel": "maximo"}
    assert cliente.get("/api/v1/nivel_ia", headers=cab).json()["nivel"] == "maximo"
    assert nucleo.preferencias.nivel_ia(1) == "maximo"
    assert nucleo.preferencias.nivel_ia(2) == "normal"  # el otro usuario no cambia


def test_nivel_ia_desconocido_422_y_no_cambia_nada(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    enorme = cliente.post("/api/v1/nivel_ia", headers=cab, json={"nivel": "enorme"})
    assert enorme.status_code == 422
    assert cliente.post("/api/v1/nivel_ia", headers=cab, json={}).status_code == 422
    assert nucleo.preferencias.nivel_ia(1) == "normal"


def test_nivel_ia_muestra_el_uso_de_hoy_y_no_el_de_ayer_ni_el_fallido(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    hoy = a_texto(T0)
    ayer = a_texto(T0 - timedelta(days=1))
    with nucleo.base.transaccion() as cx:
        cx.executemany(
            "INSERT INTO ia_uso(usuario_id, ts, tarea, ok, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, hoy, "entender_pagina", 1, 100, 20),
                (1, hoy, "redactar", 1, 300, 80),
                (1, hoy, "redactar", 0, 500, 0),  # un 503 del proveedor no cuenta
                (1, ayer, "redactar", 1, 999, 999),
                (2, hoy, "redactar", 1, 7, 7),  # de otro usuario
            ],
        )
    assert cliente.get("/api/v1/nivel_ia", headers=cab).json()["hoy"] == {
        "llamadas": 2, "tokens": 500,
    }  # fmt: skip


def test_nivel_ia_sin_token_401(entorno):
    _, cliente = entorno
    assert cliente.get("/api/v1/nivel_ia").status_code == 401
    assert cliente.post("/api/v1/nivel_ia", json={"nivel": "ahorro"}).status_code == 401


def test_olvidar_cuenta(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    assert nucleo.cuentas.asociado(1, CT) is not None
    r = cliente.post(f"/api/v1/cuenta/{CT}/olvidar", headers=cab)
    assert r.status_code == 200
    assert nucleo.cuentas.asociado(1, CT) is None


def test_preferencias_sin_token_401(entorno):
    _, cliente = entorno
    assert cliente.get(f"/api/v1/preferencias/{CT}").status_code == 401


# --- estado de los portales guardado en el latido ---------------------------------------------


def test_latido_guarda_magneto_sin_sesion_con_su_motivo(entorno):
    nucleo, cliente = entorno
    nucleo.con_selectores = {CT, "magneto"}
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    latido_con(cliente, cab, {
        CT: {"estado": "listo", "correo": CORREO},
        "magneto": {"estado": "sin_sesion", "motivo": "enlace_ingresar"},
    })  # fmt: skip
    guardado = portales_guardados(nucleo)
    assert guardado["magneto"]["estado"] == "sin_sesion"
    assert guardado["magneto"]["motivo"] == "enlace_ingresar"
    assert guardado["magneto"]["visto"] == a_texto(T0)
    assert guardado[CT]["estado"] == "listo" and guardado[CT]["cuenta"] == "ok"
    assert CORREO not in json.dumps(guardado)


def test_sin_sesion_conserva_la_cuenta_previa(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    latido(cliente, cab)
    assert portales_guardados(nucleo)[CT]["cuenta"] == "ok"
    latido_con(cliente, cab, {CT: {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    assert portales_guardados(nucleo)[CT]["cuenta"] == "ok"


def test_portal_con_selectores_ausente_del_latido_queda_sin_permiso(entorno):
    nucleo, cliente = entorno
    nucleo.con_selectores = {CT, "elempleo"}
    cab = vincular(nucleo, cliente)
    latido(cliente, cab)
    guardado = portales_guardados(nucleo)
    assert guardado["elempleo"]["estado"] == "sin_permiso"
    assert guardado[CT]["estado"] == "listo"
    # Sin selectores cargados no se puede hablar de permiso
    assert "magneto" not in guardado


def test_latido_guarda_el_permiso_de_las_paginas_externas_y_lo_borra_al_quitarlo(entorno):
    """La extensión reporta `externa` solo con el permiso `https://*/*` (postular-linkedin)."""
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    latido_con(cliente, cab, {CT: {"estado": "listo"}, "externa": {"estado": "listo"}})
    assert portales_guardados(nucleo)["externa"]["estado"] == "listo"
    latido_con(cliente, cab, {CT: {"estado": "listo"}})
    assert "externa" not in portales_guardados(nucleo)


def test_guardar_el_estado_completo_no_repite_los_avisos(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    latido(cliente, cab)
    avisos = len(nucleo.eventos)
    # Perder y recuperar la sesión con el portal igual de listo no vuelve a avisar
    latido_con(cliente, cab, {CT: {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    latido(cliente, cab)
    latido(cliente, cab)
    assert len(nucleo.eventos) == avisos


def test_volver_de_sin_sesion_avisa_solo_si_el_estado_cambio(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    latido(cliente, cab)
    latido_con(cliente, cab, {CT: {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    latido(cliente, cab, estado="incompleto")
    tipos = [e["tipo"] for e in nucleo.eventos if isinstance(e, dict)]
    assert tipos.count("portal_incompleto") == 1


def tipos_de_aviso(nucleo):
    return [e["tipo"] for e in nucleo.eventos if isinstance(e, dict)]


def test_reabrir_la_sesion_con_la_cuenta_por_confirmar_vuelve_a_avisar(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    latido(cliente, cab)  # primera vez: por confirmar
    assert tipos_de_aviso(nucleo).count("cuenta_por_confirmar") == 1
    latido(cliente, cab)
    latido(cliente, cab)  # con la sesión abierta y sin cambios no se repite
    assert tipos_de_aviso(nucleo).count("cuenta_por_confirmar") == 1
    latido_con(cliente, cab, {CT: {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    latido(cliente, cab)
    assert tipos_de_aviso(nucleo).count("cuenta_por_confirmar") == 2
    latido(cliente, cab)
    assert tipos_de_aviso(nucleo).count("cuenta_por_confirmar") == 2


def test_reabrir_la_sesion_con_cuenta_distinta_vuelve_a_avisar(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    latido(cliente, cab, correo="luis.g@hotmail.com")
    assert tipos_de_aviso(nucleo).count("cuenta_distinta") == 1
    latido_con(cliente, cab, {CT: {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    latido(cliente, cab, correo="luis.g@hotmail.com")
    assert tipos_de_aviso(nucleo).count("cuenta_distinta") == 2


def test_reabrir_la_sesion_con_la_cuenta_confirmada_no_avisa(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    avisos = len(tipos_de_aviso(nucleo))
    latido_con(cliente, cab, {CT: {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    latido(cliente, cab)
    nuevos = tipos_de_aviso(nucleo)[avisos:]
    assert not [t for t in nuevos if t.startswith("cuenta_")]


def test_reabrir_la_sesion_sin_poder_leer_el_correo_no_repite_el_aviso(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    latido(cliente, cab, correo=None)
    antes = tipos_de_aviso(nucleo).count("cuenta_sin_correo")
    latido_con(cliente, cab, {CT: {"estado": "sin_sesion", "motivo": "enlace_ingresar"}})
    latido(cliente, cab, correo=None)
    assert tipos_de_aviso(nucleo).count("cuenta_sin_correo") == antes


def test_latido_con_y_sin_pausado(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    latido(cliente, cab)  # versión anterior de la extensión: no manda el campo
    assert portales_guardados(nucleo)["_pausado"] is False
    latido_con(cliente, cab, {CT: {"estado": "listo", "correo": CORREO}}, pausado=True)
    assert portales_guardados(nucleo)["_pausado"] is True
    latido_con(cliente, cab, {CT: {"estado": "listo", "correo": CORREO}}, pausado=False)
    assert portales_guardados(nucleo)["_pausado"] is False


def test_plataforma_apagada_no_entrega_su_trabajo_y_al_encender_si(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    nucleo.config.plataformas[CT].automatica = False
    respuesta = latido(cliente, cab)
    assert respuesta["trabajo"] is None
    assert respuesta["cuentas"][CT] is True  # cuentas no cambia: la extensión revalida con ellas
    assert nucleo.cola.obtener(p.id).estado == E.EN_COLA
    nucleo.config.plataformas[CT].automatica = True
    assert latido(cliente, cab)["trabajo"]["id"] == p.id


def test_latido_avisa_las_esperas_solo_si_hay_algo_en_cola(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    esperas = lambda: [e for e in nucleo.eventos if isinstance(e, dict) and e["tipo"] == "esperas"]  # noqa: E731
    latido(cliente, cab)
    assert esperas() == []
    nucleo.cola.encolar(1, "abc", CT, T0)
    nucleo.config.topes.usuario_dia = 0  # no se entrega: se queda esperando en la cola
    latido(cliente, cab)
    assert esperas() == [{"tipo": "esperas", "usuario_id": 1}]


# --- /reparar: corrección de un paso que falló antes del envío ----------------------------------


def reparacion_con(*acciones, diagnostico="El botón cambió de texto"):
    return lambda consulta: Reparacion(
        clase="formulario",
        acciones=[AccionReparacion(accion=a, indice=i) for a, i in acciones],
        diagnostico=diagnostico,
    )


def reparar(cliente, p, cab, **extra):
    cuerpo = pantalla(
        botones=[boton(0, "Compartir"), boton(1, "Postular ahora")],
        resumen={"elementos": [{"indice": 0, "rol": "button", "texto": "Aviso de cookies"},
                               {"indice": 1, "rol": "button", "texto": "Postular ahora"}],
                 "encabezados": ["Backend Engineer"], "avisos": []},
        **extra,
    )  # fmt: skip
    cuerpo.update(paso="clic:postular", fallo="no se encontró el botón #postular")
    return cliente.post(f"/api/v1/postulaciones/{p.id}/reparar", headers=cab, json=cuerpo)


def test_reparar_devuelve_las_acciones_validas_y_el_diagnostico(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.reparador = reparacion_con(("cerrar_modal", 0), ("avanzar", 1), ("avanzar", 9))
    d = reparar(cliente, p, cab).json()
    assert [(a["accion"], a["indice"]) for a in d["acciones"]] == [
        ("cerrar_modal", 0), ("avanzar", 1),
    ]  # fmt: skip
    assert d["diagnostico"] == "El botón cambió de texto" and d["accion"] is None
    (consulta,) = nucleo.reparaciones
    assert (consulta.paso, consulta.fallo) == ("clic:postular", "no se encontró el botón #postular")
    assert consulta.peticion.resumen.encabezados == ["Backend Engineer"]
    pasos = nucleo.base.cx.execute(
        "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? AND paso = 'reparacion'",
        (p.id,),
    ).fetchall()
    assert [f["detalle"] for f in pasos] == ["clic:postular: no se encontró el botón #postular"]


def test_reparar_con_indices_inventados_responde_sin_reparacion(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.reparador = reparacion_con(("avanzar", 7), ("cerrar_modal", 5))
    d = reparar(cliente, p, cab).json()
    assert d["acciones"] == []
    assert d["accion"] == {"tipo": "respaldo", "motivo": "sin_reparacion"}


def test_reparar_tiene_tope_de_dos_por_postulacion_en_maximo(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente, "maximo")
    nucleo.reparador = reparacion_con(("avanzar", 1))
    assert reparar(cliente, p, cab).json()["accion"] is None
    assert reparar(cliente, p, cab).json()["accion"] is None
    tercera = reparar(cliente, p, cab).json()
    assert tercera["acciones"] == []
    assert tercera["accion"] == {"tipo": "respaldo", "motivo": "tope_reparaciones"}
    assert len(nucleo.reparaciones) == 2  # a la tercera ni se le pregunta a la IA


def test_reparar_en_normal_tiene_tope_de_una(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.reparador = reparacion_con(("avanzar", 1))
    assert reparar(cliente, p, cab).json()["accion"] is None
    segunda = reparar(cliente, p, cab).json()
    assert segunda["accion"] == {"tipo": "respaldo", "motivo": "tope_reparaciones"}
    assert len(nucleo.reparaciones) == 1


def test_reparar_en_ahorro_no_consulta_a_la_ia_y_dice_nivel_ahorro(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente, "ahorro")
    nucleo.reparador = reparacion_con(("avanzar", 1))
    d = reparar(cliente, p, cab).json()
    assert d["acciones"] == [] and d["accion"] == {"tipo": "respaldo", "motivo": "nivel_ahorro"}
    assert nucleo.reparaciones == []


def test_reparar_sin_ia_va_a_respaldo_con_sin_ia(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    d = reparar(cliente, p, cab).json()
    assert d["acciones"] == [] and d["accion"] == {"tipo": "respaldo", "motivo": "sin_ia"}


def test_reparar_con_el_motor_apagado_o_sin_estar_en_curso(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    nucleo.config.motor_generico.activo = False
    assert reparar(cliente, p, cab).status_code == 404
    nucleo.config.motor_generico.activo = True
    nucleo.cola.esperar_usuario(p.id, 1, T0)
    assert reparar(cliente, p, cab).status_code == 409


def test_reparar_no_es_de_otro_usuario(entorno):
    nucleo, cliente = entorno
    p, _ = en_curso(nucleo, cliente)
    cab2 = vincular(nucleo, cliente, usuario_id=2)
    assert reparar(cliente, p, cab2).status_code == 404



# --- recetas, parches y dominios barrera (6.3) --------------------------------------------------

GH = "https://job-boards.greenhouse.io/acme/jobs/4455667/apply"


def recetas_en_base(nucleo):
    return nucleo.base.cx.execute("SELECT * FROM recetas").fetchall()


def postular_en_greenhouse(nucleo, cliente, p, cab, senal="texto"):
    campos = [{"texto": "First Name", "nombre": "first_name"},
              {"texto": "Why us?", "nombre": "question_1"}]  # fmt: skip
    envio = pantalla(url=GH, campos=campos, botones=[boton(0, "Submit application", "enviar")],
                     sugerido={"indice": 0, "accion": "enviar"})  # fmt: skip
    assert decidir(cliente, p, cab, envio).json()["accion"]["tipo"] == "enviar"
    if senal:
        gracias = pantalla("exito", numero=2, url=GH + "/gracias",
                           exito={"senal": senal, "texto": "Gracias"})  # fmt: skip
        assert decidir(cliente, p, cab, gracias).json()["accion"]["tipo"] == "exito"


def terminar(cliente, p, cab, estado="enviada", **extra):
    return cliente.post(f"/api/v1/postulaciones/{p.id}/resultado", headers=cab,
                        json={"estado": estado, **extra})  # fmt: skip


def test_un_envio_con_senal_deja_la_receta_del_sitio_sin_valores(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    postular_en_greenhouse(nucleo, cliente, p, cab)
    assert terminar(cliente, p, cab).status_code == 200
    [fila] = recetas_en_base(nucleo)
    assert (fila["host"], fila["ruta_patron"], fila["familia"]) == (
        "job-boards.greenhouse.io", "/acme/jobs/*/apply", "greenhouse",
    )  # fmt: skip
    receta = json.loads(fila["receta_json"])
    assert receta["senal"] == "texto" and len(receta["pantallas"]) == 1
    pantalla_guardada = receta["pantallas"][0]
    assert pantalla_guardada["firma"] == ["first_name", "question_1"]
    assert set(pantalla_guardada["mapeo"]) == {"first_name", "question_1"}
    assert pantalla_guardada["boton"]["texto"] == "Submit application"
    assert "Sí" not in fila["receta_json"]  # el valor con el que se llenó no se guarda


def test_sin_senal_explicita_no_se_guarda_receta(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    postular_en_greenhouse(nucleo, cliente, p, cab, senal=None)
    terminar(cliente, p, cab)
    assert recetas_en_base(nucleo) == []


def test_un_resultado_que_no_es_enviada_no_deja_receta(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    postular_en_greenhouse(nucleo, cliente, p, cab)
    terminar(cliente, p, cab, "formulario_desconocido", motivo="x")
    assert recetas_en_base(nucleo) == []


def guardar_receta_de_computrabajo(nucleo):
    from buscador_vacantes.asistente import recetas

    receta = recetas.Receta(
        pantallas=[recetas.PantallaReceta(firma=["ciudad"], mapeo={"ciudad": "ciudad"})],
        senal="url",
    )  # fmt: skip
    return recetas.guardar_receta(
        nucleo.base, host="co.computrabajo.com", ruta="/ofertas-de-trabajo/oferta-1",
        familia="computrabajo", receta=receta, origen="real", ahora=T0, enviada=True,
    )  # fmt: skip


def test_el_trabajo_lleva_la_receta_del_host_y_el_resultado_la_refuerza(entorno):
    nucleo, cliente = entorno
    receta_id = guardar_receta_de_computrabajo(nucleo)
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    trabajo = latido(cliente, cab)["trabajo"]
    assert trabajo["receta"]["id"] == receta_id and trabajo["receta"]["alcance"] == "host"
    assert trabajo["receta"]["pantallas"][0]["mapeo"] == {"ciudad": "ciudad"}
    fila = nucleo.base.cx.execute("SELECT receta_id FROM postulaciones WHERE id = ?", (p.id,))
    assert fila.fetchone()[0] == receta_id
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    assert terminar(cliente, p, cab).status_code == 200
    assert nucleo.base.cx.execute("SELECT exitos FROM recetas").fetchone()[0] == 2


def test_el_trabajo_lleva_el_esquema_resuelto_de_antemano(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    assert "esquema" not in latido(cliente, cab)["trabajo"]  # sin esquema, el trabajo de siempre
    nucleo.resuelto = {"ciudad": "Bogotá", "years of experience": "1-2 years"}
    trabajo = latido(cliente, cab)["trabajo"]
    assert trabajo["esquema"] == {"respuestas": nucleo.resuelto}
    nucleo.config.motor_generico.activo = False  # con el motor apagado la extensión no lo usa
    assert "esquema" not in latido(cliente, cab)["trabajo"]


def test_dos_fallos_seguidos_apagan_la_receta_y_avisan(entorno):
    from buscador_vacantes.asistente import recetas

    nucleo, cliente = entorno
    receta_id = guardar_receta_de_computrabajo(nucleo)
    recetas.registrar_resultado_receta(nucleo.base, receta_id, False)  # un fallo previo
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    assert latido(cliente, cab)["trabajo"]["receta"]["id"] == receta_id
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    terminar(cliente, p, cab, "formulario_desconocido", motivo="no_encontrado")
    assert nucleo.base.cx.execute("SELECT activa FROM recetas").fetchone()[0] == 0
    assert any(e.get("tipo") == "receta_apagada" for e in nucleo.eventos if isinstance(e, dict))


def test_un_trabajo_sin_receta_ni_parches_no_trae_esas_claves(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    trabajo = latido(cliente, cab)["trabajo"]
    assert "receta" not in trabajo and "parches" not in trabajo


def test_dominio_que_exige_cuenta_queda_como_barrera(entorno):
    from buscador_vacantes.asistente import recetas

    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    pagina = pantalla("barrera", url="https://ats.example.com/jobs/1/apply",
                      motivo="ats_con_cuenta")  # fmt: skip
    decidir(cliente, p, cab, pagina)
    terminar(cliente, p, cab, "bloqueada", motivo="ats_con_cuenta")
    assert recetas.barrera_de(nucleo.base, "ats.example.com") == "ats_con_cuenta"
    assert recetas.barrera_de(nucleo.base, "co.computrabajo.com") is None
    assert any(e.get("tipo") == "dominio_barrera" for e in nucleo.eventos if isinstance(e, dict))


def test_barrera_sin_pantallas_marca_el_host_de_la_vacante(entorno):
    from buscador_vacantes.asistente import recetas

    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    terminar(cliente, p, cab, "bloqueada", motivo="oauth")
    assert recetas.barrera_de(nucleo.base, "co.computrabajo.com") == "oauth"


def test_un_resultado_con_otro_motivo_no_marca_barrera(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    terminar(cliente, p, cab, "bloqueada", motivo="captcha")
    assert nucleo.base.cx.execute("SELECT COUNT(*) FROM dominios_barrera").fetchone()[0] == 0


def test_bucle_generico_que_repara_un_paso_declarado_deja_un_parche_candidato(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    cliente.post(f"/api/v1/postulaciones/{p.id}/paso", headers=cab,
                 json={"paso": "respaldo_generico", "detalle": "buscar: a.viejo"})  # fmt: skip
    parche = {"paso": "aplicar", "selector": "a.btn-nuevo"}
    assert terminar(cliente, p, cab, parche=parche).status_code == 200
    [fila] = nucleo.base.cx.execute("SELECT * FROM parches_flujo").fetchall()
    assert (fila["plataforma"], fila["paso"], fila["estado"]) == (CT, "aplicar", "candidato")
    assert json.loads(fila["selector_json"]) == "a.btn-nuevo" and fila["postulacion_id"] == p.id
    assert any(e.get("tipo") == "parche_nuevo" for e in nucleo.eventos if isinstance(e, dict))


def test_sin_haber_pasado_por_el_bucle_un_parche_no_se_guarda(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    terminar(cliente, p, cab, parche={"paso": "aplicar", "selector": "a.btn-nuevo"})
    assert nucleo.base.cx.execute("SELECT COUNT(*) FROM parches_flujo").fetchone()[0] == 0


def test_el_trabajo_lleva_el_parche_y_un_exito_lo_deja_firme(entorno):
    from buscador_vacantes.asistente import recetas

    nucleo, cliente = entorno
    parche_id = recetas.proponer_parche(nucleo.base, CT, "aplicar", "a.btn-nuevo", T0)
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    trabajo = latido(cliente, cab)["trabajo"]
    assert [(x["id"], x["paso"], x["estado"]) for x in trabajo["parches"]] == [
        (parche_id, "aplicar", "candidato")
    ]  # fmt: skip
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    terminar(cliente, p, cab)
    estado = nucleo.base.cx.execute("SELECT estado FROM parches_flujo").fetchone()[0]
    assert estado == "firme"
    assert any(e.get("tipo") == "parche_firme" for e in nucleo.eventos if isinstance(e, dict))


def test_un_fallo_con_un_parche_candidato_lo_descarta(entorno):
    from buscador_vacantes.asistente import recetas

    nucleo, cliente = entorno
    recetas.proponer_parche(nucleo.base, CT, "aplicar", "a.btn-nuevo", T0)
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    latido(cliente, cab)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    terminar(cliente, p, cab, "formulario_desconocido", motivo="no_encontrado")
    estado = nucleo.base.cx.execute("SELECT estado FROM parches_flujo").fetchone()[0]
    assert estado == "descartado"


def test_un_ensayo_deja_una_receta_de_ensayo_sin_senal(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso(nucleo, cliente)
    postular_en_greenhouse(nucleo, cliente, p, cab, senal=None)
    r = terminar(cliente, p, cab, "ensayada", motivo="boton:Submit application")
    assert r.status_code == 200
    [fila] = recetas_en_base(nucleo)
    assert fila["origen"] == "ensayo" and fila["host"] == "job-boards.greenhouse.io"
    assert json.loads(fila["receta_json"])["senal"] is None
    assert json.loads(fila["receta_json"])["pantallas"][0]["boton"]["texto"] == "Submit application"


def test_el_trabajo_del_vigia_es_un_ensayo_y_la_extension_vieja_no_lo_recibe(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    vigia = nucleo.cola.encolar_vigia(1, "abc", CT, T0)
    # La 1.1.x ignora `ensayo` y enviaría de verdad: no recibe nada
    assert latido(cliente, cab, version="1.1.0")["trabajo"] is None
    trabajo = latido(cliente, cab, version="1.2.0")["trabajo"]
    assert trabajo["id"] == vigia.id and trabajo["tipo"] == "postular"
    assert trabajo["ensayo"] is True and trabajo["url"].startswith("https://co.computrabajo.com")


def test_un_ensayo_de_usuario_tampoco_va_a_la_extension_vieja(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    nucleo.ensayo = True
    assert latido(cliente, cab, version="1.1.0")["trabajo"] is None
    assert latido(cliente, cab, version="1.2.0")["trabajo"]["ensayo"] is True


# --- destino de LinkedIn (postular-linkedin, 4.1) -----------------------------------------------


def en_curso_linkedin(nucleo, cliente):
    """Postulación de LinkedIn en curso en el navegador del usuario 1."""
    cab = vincular(nucleo, cliente)
    nucleo.linkedin.aceptar(1, nucleo.config.linkedin.riesgo_version, T0)
    p, _ = nucleo.cola.encolar(1, "abc", "linkedin", T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    return p, cab


def destino(cliente, p, cab, url=None, **extra):
    cuerpo = {"url": url, **extra} if url else extra
    return cliente.post(f"/api/v1/postulaciones/{p.id}/destino", headers=cab, json=cuerpo)


def guardados(nucleo):
    filas = nucleo.base.cx.execute("SELECT * FROM destinos_linkedin").fetchall()
    return [dict(f) for f in filas]


def test_destino_externo_se_limpia_se_guarda_y_se_abre(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    crudo = (
        "https://www.linkedin.com/safety/go?url=https%3A%2F%2Facme.com%2Fempleo%2F7%3Futm_source"
        "%3Dlinkedin%26ref%3Dx&trk=flagship"
    )
    r = destino(cliente, p, cab, crudo)
    assert r.status_code == 200
    assert r.json()["accion"] == "abrir"
    assert r.json()["url"] == "https://acme.com/empleo/7?ref=x"
    assert r.json()["familia"] == "propio"
    fila = guardados(nucleo)
    assert [(f["id_vacante"], f["destino"], f["familia"]) for f in fila] == [
        ("abc", "https://acme.com/empleo/7?ref=x", "propio")
    ]
    assert fila[0]["resuelto"] and fila[0]["ultima_vez"]
    assert nucleo.esquemas_leidos == []  # una familia sin lector no lee nada


def test_destino_de_greenhouse_por_enlace_corto_se_clasifica_tras_la_redireccion(entorno):
    nucleo, cliente = entorno
    final = "https://job-boards.greenhouse.io/prueba/jobs/4100100"
    nucleo.redirecciones["https://grnh.se/abc123"] = final
    nucleo.resuelto = {"question_9001": "B2"}
    p, cab = en_curso_linkedin(nucleo, cliente)
    r = destino(cliente, p, cab, "https://grnh.se/abc123").json()
    assert r["accion"] == "abrir"
    assert (r["familia"], r["url"]) == ("greenhouse", final)
    assert nucleo.esquemas_leidos == [("greenhouse", final)]
    assert r["esquema"] == {"respuestas": {"question_9001": "B2"}}
    assert "Submit application" in r["familia_datos"]["enviar"]["textos"]  # botón de la familia
    assert guardados(nucleo)[0]["familia"] == "greenhouse"


def test_destino_acortador_hacia_whatsapp_va_al_respaldo_con_el_enlace(entorno):
    nucleo, cliente = entorno
    nucleo.redirecciones["https://ai-job.link/x1"] = "https://wa.me/573001112233?text=hola"
    p, cab = en_curso_linkedin(nucleo, cliente)
    r = destino(cliente, p, cab, "https://ai-job.link/x1").json()
    assert r["accion"] == "respaldo"
    assert r["motivo"] == "destino_mensajeria"
    assert r["url"] == "https://wa.me/573001112233?text=hola"  # el paquete lo lleva
    assert nucleo.esquemas_leidos == []


@pytest.mark.parametrize(
    "url",
    ["mailto:talento@acme.com", "https://t.me/acme_empleo", "https://api.whatsapp.com/send?phone=1"],
)
def test_destino_de_mensajeria_va_al_respaldo(entorno, url):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    r = destino(cliente, p, cab, url).json()
    assert (r["accion"], r["motivo"]) == ("respaldo", "destino_mensajeria")


def test_destino_de_workday_va_al_respaldo_sin_abrir(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    r = destino(cliente, p, cab, "https://acme.wd3.myworkdayjobs.com/es/Careers/job/Bogota/X_R1")
    assert r.json()["accion"] == "respaldo"
    assert r.json()["motivo"] == "ats_con_cuenta"


def test_destino_en_un_dominio_barrera_aprendido_va_al_respaldo(entorno):
    from buscador_vacantes.asistente import recetas

    nucleo, cliente = entorno
    recetas.marcar_barrera(nucleo.base, "empleos.acme.com", "ats_con_cuenta", T0)
    p, cab = en_curso_linkedin(nucleo, cliente)
    r = destino(cliente, p, cab, "https://empleos.acme.com/vacante/9").json()
    assert (r["accion"], r["motivo"]) == ("respaldo", "ats_con_cuenta")


@pytest.mark.parametrize(
    "url", ["https://accounts.google.com/o/oauth2/auth?x=1", "https://www.linkedin.com/oauth/v2/a"]
)
def test_destino_en_un_inicio_de_sesion_ajeno_va_al_respaldo_como_oauth(entorno, url):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    assert destino(cliente, p, cab, url).json()["motivo"] == "oauth"


def test_destino_con_datos_que_faltan_deja_la_postulacion_esperando_al_usuario(entorno):
    nucleo, cliente = entorno
    nucleo.esquema_completo = False
    p, cab = en_curso_linkedin(nucleo, cliente)
    r = destino(cliente, p, cab, "https://job-boards.greenhouse.io/prueba/jobs/4100100")
    assert r.json() == {"esperar_usuario": True}
    assert nucleo.cola.obtener(p.id).estado == E.ESPERANDO_USUARIO


def test_destino_repetido_actualiza_la_fila_de_la_vacante(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    destino(cliente, p, cab, "https://acme.com/a")
    nucleo.momento += timedelta(days=1)
    destino(cliente, p, cab, "https://acme.com/b")
    assert [f["destino"] for f in guardados(nucleo)] == ["https://acme.com/b"]


def test_destino_pide_una_postulacion_de_linkedin_en_curso_y_el_motor_encendido(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    ct, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{ct.id}/tomar", headers=cab)
    assert destino(cliente, ct, cab, "https://acme.com/a").status_code == 409  # no es de LinkedIn
    ln, _ = nucleo.cola.encolar(1, "abc", "linkedin", T0)
    assert destino(cliente, ln, cab, "https://acme.com/a").status_code == 409  # sin tomar
    assert destino(cliente, ln, {}, "https://acme.com/a").status_code == 401
    cliente.post(f"/api/v1/postulaciones/{ln.id}/tomar", headers=cab)
    assert destino(cliente, ln, cab, "ftp://acme.com/a").status_code == 422
    nucleo.config.motor_generico.activo = False
    assert destino(cliente, ln, cab, "https://acme.com/a").status_code == 404


def test_destino_con_las_externas_apagadas_o_sin_permiso_va_al_respaldo(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    nucleo.permiso = False
    r = destino(cliente, p, cab, "https://acme.com/empleo").json()
    assert (r["accion"], r["motivo"]) == ("respaldo", "sin_permiso_externo")
    nucleo.linkedin.fijar(1, externas=False)
    r = destino(cliente, p, cab, "https://acme.com/empleo").json()
    assert (r["accion"], r["motivo"], r["url"]) == (
        "respaldo", "linkedin_apagado", "https://acme.com/empleo",
    )
    # Con el destino ya clasificado como mensajería, el motivo es ese, no el interruptor
    r = destino(cliente, p, cab, "https://wa.me/573001112233").json()
    assert r["motivo"] == "destino_mensajeria"


def test_destino_de_una_sencilla_respeta_su_interruptor(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    assert destino(cliente, p, cab, tipo="sencilla").json() == {"accion": "sencilla"}
    assert guardados(nucleo) == []  # una sencilla no tiene destino que guardar
    nucleo.linkedin.fijar(1, sencilla=False)
    r = destino(cliente, p, cab, tipo="sencilla").json()
    assert (r["accion"], r["motivo"]) == ("respaldo", "linkedin_apagado")


def test_destino_externo_sin_url_es_invalido(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    assert destino(cliente, p, cab).status_code == 422
    assert destino(cliente, p, cab, tipo="rara", url="https://acme.com/a").status_code == 422


def test_el_trabajo_lleva_el_destino_guardado_para_no_abrir_linkedin(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    assert "destino" not in api_modulo._trabajo(nucleo, p)
    destino(cliente, p, cab, "https://job-boards.greenhouse.io/prueba/jobs/4100100")
    otra, _ = nucleo.cola.encolar(2, "abc", "linkedin", T0)  # otro usuario, misma vacante
    guardado = api_modulo._trabajo(nucleo, otra)["destino"]
    assert (guardado["url"], guardado["familia"]) == (
        "https://job-boards.greenhouse.io/prueba/jobs/4100100", "greenhouse",
    )
    # Los hosts de las familias de ATS van con el destino: la regla de salto de la extensión
    assert "greenhouse.io" in guardado["familias_hosts"]
    assert "myworkdayjobs.com" in guardado["familias_hosts"]


def test_un_aviso_de_seguridad_pausa_linkedin_veinticuatro_horas_y_avisa(entorno):
    nucleo, cliente = entorno
    p, cab = en_curso_linkedin(nucleo, cliente)
    r = cliente.post(
        f"/api/v1/postulaciones/{p.id}/resultado", headers=cab,
        json={"estado": "bloqueada", "motivo": "aviso_seguridad"},
    )
    assert r.status_code == 200
    assert nucleo.linkedin.pausado_hasta(1, T0) == T0 + timedelta(hours=24)
    pausas = [e for e in nucleo.eventos if isinstance(e, dict) and e["tipo"] == "linkedin_pausado"]
    [evento] = pausas
    assert evento["usuario_id"] == 1 and evento["postulacion_id"] == p.id
