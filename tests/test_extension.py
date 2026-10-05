"""Pruebas de la extensión en Chromium real (grupo `navegador`: uv sync --group navegador).

La extensión se carga descomprimida con Playwright y habla con una API de prueba que imita la
API v1 del servidor. Las páginas de los portales se sirven con `context.route` desde
tests/fixtures/extension/, con el marcado tomado de las páginas reales.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.async_api")
fastapi = pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, Response  # noqa: E402

from buscador_vacantes.asistente.api import PAGINA_VINCULO  # noqa: E402

pytestmark = pytest.mark.navegador

RAIZ = Path(__file__).resolve().parent.parent
EXTENSION = RAIZ / "extension"
FIXTURES = Path(__file__).parent / "fixtures" / "extension"
SELECTORES = RAIZ / "assets" / "selectores"
TOKEN = "token-de-prueba"
PDF = b"%PDF-1.4\n% CV de prueba\n"


# --- API de prueba -----------------------------------------------------------------------


class ApiPrueba:
    def __init__(self) -> None:
        self.llamadas: list[tuple[str, dict]] = []
        self.trabajos: list[dict] = []
        self.respuestas = lambda campos: []
        self.ajustar = lambda plataforma, selectores: selectores
        self.app = self._app()

    def de(self, ruta: str) -> list[dict]:
        return [c for r, c in self.llamadas if r == ruta]

    def _app(self) -> FastAPI:
        app = FastAPI()
        api = self

        @app.get("/api/v1/vincular/{codigo}", response_class=HTMLResponse)
        async def pagina(codigo: str):
            return PAGINA_VINCULO.format(codigo=codigo, visible=codigo, api="")

        @app.post("/api/v1/vincular")
        async def vincular(request: Request):
            cuerpo = await request.json()
            api.llamadas.append(("vincular", cuerpo))
            if cuerpo["codigo"] != "ABCD2345":
                return JSONResponse({"detail": "código inválido"}, status_code=400)
            return {"token": TOKEN}

        def autorizado(request: Request) -> bool:
            return request.headers.get("authorization") == f"Bearer {TOKEN}"

        @app.post("/api/v1/latido")
        async def latido(request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            cuerpo = await request.json()
            api.llamadas.append(("latido", cuerpo))
            cuentas = {p: v["estado"] != "sin_sesion" and bool(v.get("correo"))
                       for p, v in cuerpo["portales"].items()}  # fmt: skip
            trabajo = api.trabajos[0] if api.trabajos else None
            versiones = {p.stem: json.loads(p.read_text(encoding="utf-8"))["version"]
                         for p in SELECTORES.glob("*.json")}  # fmt: skip
            return {"trabajo": trabajo, "version_minima": "1.0.0", "actualizar": False,
                    "selectores": versiones, "cuentas": cuentas, "latido_s": 30}  # fmt: skip

        @app.get("/api/v1/selectores/{plataforma}")
        async def selectores(plataforma: str):
            contenido = json.loads((SELECTORES / f"{plataforma}.json").read_text(encoding="utf-8"))
            contenido = api.ajustar(plataforma, contenido)
            return {"version": contenido["version"], "selectores": contenido}

        @app.post("/api/v1/postulaciones/{pid}/{accion}")
        async def postulacion(pid: int, accion: str, request: Request):
            cuerpo = await request.json() if await request.body() else {}
            api.llamadas.append((accion, {"id": pid, **cuerpo}))
            if accion == "tomar":
                api.trabajos = [t for t in api.trabajos if t["id"] != pid]
            if accion == "formulario":
                return {"esperar_usuario": False, "respuestas": api.respuestas(cuerpo["campos"]),
                        "cv_url": "/api/v1/cv/uno", "cv_nombre": "CV_Ana_Perez.pdf"}  # fmt: skip
            return {"ok": True}

        @app.get("/api/v1/cv/{token}")
        async def cv(token: str):
            return Response(PDF, media_type="application/pdf")

        return app


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor():
    api = ApiPrueba()
    puerto = puerto_libre()
    config = uvicorn.Config(api.app, host="127.0.0.1", port=puerto, log_level="warning")
    proceso = uvicorn.Server(config)
    hilo = threading.Thread(target=proceso.run, daemon=True)
    hilo.start()
    for _ in range(100):
        if proceso.started:
            break
        time.sleep(0.05)
    api.url = f"http://127.0.0.1:{puerto}"
    yield api
    proceso.should_exit = True
    hilo.join(5)


@pytest.fixture
def api(servidor):
    servidor.llamadas.clear()
    servidor.trabajos.clear()
    servidor.respuestas = lambda campos: []
    servidor.ajustar = lambda plataforma, selectores: selectores
    return servidor


# --- navegador con la extensión ----------------------------------------------------------


def copia_extension(destino: Path) -> Path:
    """Copia la extensión y permite el servidor local de prueba (como lo haría Opciones)."""
    shutil.copytree(EXTENSION, destino)
    manifiesto = json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["host_permissions"].append("http://127.0.0.1/*")
    (destino / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    return destino


class Portales:
    """Sirve las páginas de los portales desde los fixtures y guarda lo que reciben."""

    def __init__(self) -> None:
        self.paginas: dict[str, str] = {}
        self.recibido: list[bytes] = []

    def poner(self, url: str, fixture: str, reemplazos: dict[str, str] | None = None) -> None:
        html = (FIXTURES / fixture).read_text(encoding="utf-8")
        for a, b in (reemplazos or {}).items():
            html = html.replace(a, b)
        self.paginas[url] = html

    async def atender(self, route) -> None:
        peticion = route.request
        url = peticion.url.split("#")[0]
        if url.endswith("/recibir"):
            self.recibido.append(peticion.post_data_buffer or b"")
            await route.fulfill(status=200, body="ok")
            return
        if "recaptcha" in url:
            await route.fulfill(status=200, body="<html><body>reto</body></html>",
                                content_type="text/html")  # fmt: skip
            return
        html = self.paginas.get(url)
        if html is None:
            await route.fulfill(status=404, body="no encontrada", content_type="text/html")
        else:
            await route.fulfill(status=200, body=html, content_type="text/html; charset=utf-8")


VACANTE = "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-prueba-PRUEBA"
MATCH = "https://candidato.co.computrabajo.com/match/?oi=PRUEBA&p=57&idb=1&d=33"
CUENTA_CT = "https://candidato.co.computrabajo.com/candidate/configuration/"
PERFIL_CT = "https://candidato.co.computrabajo.com/candidate/cv/"
CUENTA_MG = "https://www.magneto365.com/co/perfil"
INICIO_CT = "https://co.computrabajo.com/"
INICIO_MG = "https://www.magneto365.com/co"
MI_CUENTA_CT = "https://candidato.co.computrabajo.com/candidate/micuenta/"


class Navegador:
    def __init__(self, contexto, worker, portales: Portales) -> None:
        self.contexto = contexto
        self.worker = worker
        self.portales = portales

    async def evaluar(self, codigo: str):
        return await self.worker.evaluate(codigo)

    async def almacenamiento(self, clave: str):
        return await self.evaluar(f"chrome.storage.local.get('{clave}').then(r => r['{clave}'])")

    async def vincular_directo(self, url_api: str) -> None:
        await self.evaluar(
            f"chrome.storage.local.set({{servidor: '{url_api}', token: '{TOKEN}', "
            "pruebas: {sondeo_captcha_ms: 500}})"
        )

    async def latido(self):
        # Si ya hay un latido en curso (el de la instalación), se espera y se hace uno nuevo
        return await self.evaluar("asistente.latido().then(() => asistente.latido())")


def correr(corutina):
    return asyncio.run(corutina)


async def abrir(tmp_path: Path, url_api: str, portales: Portales, *, vinculado=True):
    pw = await playwright_api.async_playwright().start()
    ruta = copia_extension(tmp_path / "ext")
    try:
        contexto = await pw.chromium.launch_persistent_context(
            str(tmp_path / "perfil"), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={ruta}", f"--load-extension={ruta}"],
        )  # fmt: skip
    except Exception as exc:  # Chromium no instalado
        await pw.stop()
        pytest.skip(f"Chromium no disponible: {exc}")
    await contexto.route("https://*.computrabajo.com/**", portales.atender)
    await contexto.route("https://*.magneto365.com/**", portales.atender)
    await contexto.route("https://www.google.com/**", portales.atender)
    worker = (
        contexto.service_workers[0]
        if contexto.service_workers
        else (await contexto.wait_for_event("serviceworker"))
    )
    nav = Navegador(contexto, worker, portales)
    await nav.evaluar(f"chrome.storage.local.set({{servidor: '{url_api}'}})")
    if vinculado:
        await nav.vincular_directo(url_api)
    nav.pw = pw
    return nav


async def cerrar(nav: Navegador) -> None:
    await nav.contexto.close()
    await nav.pw.stop()


def portales_listos() -> Portales:
    p = Portales()
    p.poner(CUENTA_CT, "ct_cuenta.html")
    p.poner(PERFIL_CT, "ct_cuenta.html")
    p.poner(CUENTA_MG, "mg_sin_sesion.html")  # Magneto: sin sesión
    p.poner(INICIO_CT, "ct_cuenta.html")
    p.poner(INICIO_MG, "mg_sin_sesion.html")
    return p


def respuestas_ana(campos: list[dict]) -> list[dict]:
    salida = []
    for i, c in enumerate(campos):
        nombre = c.get("nombre")
        if nombre == "nombre_completo":
            salida.append({"indice": i, "valor": "Ana Pérez", "opcion": None})
        elif nombre == "correo":
            salida.append({"indice": i, "valor": "ana@example.com", "opcion": None})
        elif nombre == "salario":
            salida.append({"indice": i, "valor": "1300000", "opcion": None})
        elif nombre == "ciudad":
            salida.append({"indice": i, "valor": None, "opcion": c["opciones"].index("Medellín")})
        elif nombre == "modalidad":
            salida.append({"indice": i, "valor": None, "opcion": 1})
        elif nombre == "acepta":
            salida.append({"indice": i, "valor": None, "opcion": 0})
        elif nombre == "motivo":
            texto = "Quiero aprender en un equipo real."
            salida.append({"indice": i, "valor": texto, "opcion": None})
    return salida


# --- 7.1: permisos, vinculación y latido --------------------------------------------------


def test_manifiesto_con_permisos_minimos():
    manifiesto = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    assert manifiesto["manifest_version"] == 3
    assert set(manifiesto["permissions"]) == {"storage", "tabs", "alarms", "scripting"}
    for origen in manifiesto["host_permissions"]:
        assert origen.startswith(("https://*.computrabajo.com", "https://*.magneto365.com",
                                  "https://postulador."))  # fmt: skip
    todo = json.dumps(manifiesto)
    for prohibido in ("<all_urls>", "cookies", "history", "webRequest", "*://*/*"):
        assert prohibido not in todo
    assert "content_security_policy" not in manifiesto  # sin relajar la política por defecto
    # Las demás plataformas del buscador quedan como permisos opcionales: se activan desde el
    # popup cuando el servidor las habilita, sin publicar otra versión
    opcionales = set(manifiesto["optional_host_permissions"])
    for dominio in ("elempleo.com", "getonbrd.com", "linkedin.com", "buscadordeempleo.gov.co"):
        assert f"https://*.{dominio}/*" in opcionales


def test_sin_codigo_remoto():
    """La extensión no evalúa ni descarga código: los selectores son datos."""
    for archivo in EXTENSION.rglob("*.js"):
        texto = archivo.read_text(encoding="utf-8")
        for prohibido in ("eval(", "new Function", "importScripts(", "innerHTML ="):
            assert prohibido not in texto, (archivo.name, prohibido)


def test_vinculacion_automatica_desde_la_pagina(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos(), vinculado=False)
        try:
            pagina = await nav.contexto.new_page()
            await pagina.goto(f"{api.url}/api/v1/vincular/ABCD2345")
            await pagina.wait_for_selector("body[data-vinculado='si']", timeout=15000)
            assert "vinculado" in (await pagina.inner_text("#estado")).lower()
            assert await nav.almacenamiento("token") == TOKEN
        finally:
            await cerrar(nav)

    correr(flujo())
    vinculo = api.de("vincular")[0]
    assert vinculo["codigo"] == "ABCD2345"
    assert vinculo["version"] == "1.0.0"


def test_codigo_vencido_lo_dice_en_la_pagina(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos(), vinculado=False)
        try:
            pagina = await nav.contexto.new_page()
            await pagina.goto(f"{api.url}/api/v1/vincular/ZZZZ9999")
            await pagina.wait_for_selector("body[data-vinculado='no']", timeout=15000)
            assert "venció" in await pagina.inner_text("#estado")
            assert await nav.almacenamiento("token") is None
        finally:
            await cerrar(nav)

    correr(flujo())


def test_latido_informa_sesion_y_correo_de_cada_portal(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    portales = api.de("latido")[-1]["portales"]
    assert portales["computrabajo"]["estado"] == "listo"
    assert portales["computrabajo"]["correo"] == "ana.perez@gmail.com"
    assert portales["magneto"]["estado"] == "sin_sesion"


# --- 7.2 y 7.3: motor y flujo de Computrabajo ---------------------------------------------


def trabajo(pid=7, url=VACANTE):
    return {"id": pid, "tipo": "postular", "plataforma": "computrabajo", "url": url,
            "titulo": "Practicante de sistemas", "actualizar_cv_portal": False}  # fmt: skip


def test_postulacion_completa_llena_todos_los_campos(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.poner(MATCH, "ct_match.html")
    api.trabajos = [trabajo()]
    api.respuestas = respuestas_ana

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    acciones = [r for r, _ in api.llamadas if r not in ("latido", "paso")]
    assert acciones == ["tomar", "envio", "formulario", "envio", "resultado"]
    campos = api.de("formulario")[0]["campos"]
    tipos = {c["nombre"]: c["tipo"] for c in campos}
    assert tipos == {"nombre_completo": "texto", "correo": "correo", "salario": "numero",
                     "ciudad": "opciones", "modalidad": "opciones", "acepta": "opciones",
                     "motivo": "texto", "cv": "archivo"}  # fmt: skip
    ciudad = next(c for c in campos if c["nombre"] == "ciudad")
    assert ciudad["opciones"] == ["Bogotá", "Medellín", "Cali"]
    assert ciudad["texto"] == "¿En qué ciudad vives?"
    assert next(c for c in campos if c["nombre"] == "nombre_completo")["obligatoria"]
    # El portal recibió todos los valores y el PDF adjunto
    enviado = portales.recibido[0].decode("latin-1")
    esperados = ("Ana P", "ana@example.com", "1300000", "med", "Quiero aprender", "CV_Ana_P")
    for valor in esperados:
        assert valor in enviado, valor
    assert 'name="modalidad"\r\n\r\nh' in enviado
    assert 'name="acepta"\r\n\r\nsi' in enviado
    assert api.de("resultado")[0]["estado"] == "enviada"
    pasos = [p["paso"] for p in api.de("paso")]
    assert pasos[:3] == ["abrir", "revisar_vacante", "aplicar"]


def test_ya_postulado_no_toca_nada(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_postulado.html")
    api.trabajos = [trabajo()]

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    assert api.de("resultado")[0]["estado"] == "ya_postulada"
    assert not api.de("envio")
    assert not portales.recibido


def test_sin_sesion_queda_esperando_sesion(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_sin_sesion.html")
    api.trabajos = [trabajo()]

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    assert api.de("resultado")[0]["estado"] == "esperando_sesion"


def test_vacante_cerrada(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html", {"<p>Descripción de la oferta.</p>":
                                                "<p>Esta oferta ha finalizado.</p>"})  # fmt: skip
    api.trabajos = [trabajo()]

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    assert api.de("resultado")[0]["estado"] == "vacante_cerrada"


def test_selector_ausente_reporta_formulario_desconocido_sin_valores(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.poner(
        MATCH, "ct_match.html", {'<button type="submit" class="b_primary">Postularme</button>': ""}
    )
    api.trabajos = [trabajo()]
    api.respuestas = respuestas_ana

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "enviar" in resultado["motivo"]
    assert "kqForm" in resultado["html"]
    for valor in ("Ana Pérez", "ana@example.com", "1300000", "Quiero aprender"):
        assert valor not in resultado["html"]
    assert not portales.recibido


def test_captcha_detiene_y_continua_al_resolverse(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    reto = (
        '<iframe id="reto" src="https://www.google.com/recaptcha/api2/bframe?k=1" '
        'width="300" height="300"></iframe><script>setTimeout(() => '
        'document.getElementById("reto").remove(), 2500)</script>'
    )
    portales.poner(MATCH, "ct_match.html", {"<!--CAPTCHA-->": reto})
    api.trabajos = [trabajo()]
    api.respuestas = respuestas_ana

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    verificaciones = [v["estado"] for v in api.de("verificacion")]
    assert verificaciones == ["pendiente", "resuelta"]
    assert api.de("resultado")[0]["estado"] == "enviada"


def test_el_motor_no_opera_fuera_del_portal(tmp_path, api):
    api.trabajos = [trabajo(url="https://co.computrabajo.com/candidato/cambiar-contrasena")]
    portales = portales_listos()
    portales.poner("https://co.computrabajo.com/candidato/cambiar-contrasena", "ct_vacante.html")

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "no permitida" in resultado["motivo"]
    assert not api.de("envio")


# --- 7.6: CV del perfil del portal ------------------------------------------------------------


def con_pasos_de_cv(modo: str, limite: int = 3):
    def ajustar(plataforma, sel):
        sel = json.loads(json.dumps(sel))
        sel["cv"] = {"modo": modo}
        sel["postular"] = [
            {"nombre": "cv_liberar", "accion": "cv_liberar", "url": PERFIL_CT,
             "item": [".cv-item"], "nombre_cv": [".cv-name"], "eliminar": [".borrar"],
             "limite": limite},
            {"nombre": "cv_subir", "accion": "cv_subir", "url": PERFIL_CT,
             "selector": ["#archivo"], "guardar": ["#guardar"]},
            {"nombre": "cv_verificar", "accion": "cv_verificar", "ms": 3000},
            {**sel["postular"][0], "url": "$vacante"},
            *sel["postular"][1:],
        ]  # fmt: skip
        return sel

    return ajustar


def filas(*nombres: str) -> str:
    return "".join(
        f'<li class="cv-item"><span class="cv-name">{n}</span>'
        '<button class="borrar" type="button">Eliminar</button></li>'
        for n in nombres
    )


def postular_con_cv(tmp_path, api, *, modo, autorizado, existentes, actualiza=True):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.poner(MATCH, "ct_match.html")
    reemplazos = {"<!--FILAS-->": filas(*existentes),
                  "<body>": f'<body data-modo="{modo.removeprefix("perfil_")}">'}  # fmt: skip
    if not actualiza:
        reemplazos["<body>"] = reemplazos["<body>"].replace("<body", '<body data-actualiza="no"')
    portales.poner(PERFIL_CT, "ct_perfil_cv.html", reemplazos)
    api.trabajos = [{**trabajo(), "actualizar_cv_portal": autorizado}]
    api.respuestas = respuestas_ana
    api.ajustar = con_pasos_de_cv(modo)

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    return portales


def test_perfil_unico_reemplaza_el_cv_antes_de_enviar(tmp_path, api):
    portales = postular_con_cv(tmp_path, api, modo="perfil_unico", autorizado=True,
                               existentes=["MiHojaVieja.pdf"])  # fmt: skip
    recibido = [r.decode("latin-1") for r in portales.recibido]
    # Primero se sube el CV adaptado al perfil y después se envía la postulación
    assert "CV_Ana_Perez.pdf" in recibido[0]
    assert "nombre_completo" in recibido[-1]
    assert not any(r.startswith("borrar:") for r in recibido)  # perfil único: no se borra
    pasos = [p["paso"] for p in api.de("paso")]
    assert "cv_subir" in pasos and "cv_verificar_fallo" not in pasos
    assert api.de("resultado")[0]["estado"] == "enviada"


def test_perfil_multiple_solo_reemplaza_el_cv_del_sistema(tmp_path, api):
    portales = postular_con_cv(
        tmp_path, api, modo="perfil_multiple", autorizado=True,
        existentes=["Personal.pdf", "CV_Ana_Perez.pdf", "Otro.pdf"],
    )  # fmt: skip
    borrados = [r.decode() for r in portales.recibido if r.startswith(b"borrar:")]
    assert borrados == ["borrar:CV_Ana_Perez.pdf"]
    assert api.de("resultado")[0]["estado"] == "enviada"


def test_perfil_multiple_sin_cv_propio_no_borra_nada(tmp_path, api):
    portales = postular_con_cv(
        tmp_path, api, modo="perfil_multiple", autorizado=True,
        existentes=["Personal.pdf", "Otro.pdf", "Tercero.pdf"],
    )  # fmt: skip
    assert not [r for r in portales.recibido if r.startswith(b"borrar:")]
    assert "cv_sin_espacio" in [p["paso"] for p in api.de("paso")]


def test_sin_autorizacion_no_se_toca_el_cv(tmp_path, api):
    portales = postular_con_cv(tmp_path, api, modo="perfil_unico", autorizado=False,
                               existentes=["MiHojaVieja.pdf"])  # fmt: skip
    # Solo llegó la postulación (con el PDF adjunto al formulario), nada al perfil
    assert len(portales.recibido) == 1
    assert "nombre_completo" in portales.recibido[0].decode("latin-1")
    assert "cv_sin_autorizacion" in [p["paso"] for p in api.de("paso")]
    assert api.de("resultado")[0]["estado"] == "enviada"


def test_si_la_verificacion_falla_se_postula_con_el_existente(tmp_path, api):
    postular_con_cv(tmp_path, api, modo="perfil_unico", autorizado=True,
                    existentes=["MiHojaVieja.pdf"], actualiza=False)  # fmt: skip
    assert "cv_verificar_fallo" in [p["paso"] for p in api.de("paso")]
    assert api.de("resultado")[0]["estado"] == "enviada"


def test_el_correo_se_busca_siguiendo_mi_cuenta(tmp_path, api):
    """Sin el correo en la página principal, se sigue el enlace "Mi cuenta" del portal; el
    correo de soporte del portal no se confunde con el del usuario."""
    portales = portales_listos()
    portales.poner(INICIO_CT, "ct_home_sesion.html")
    portales.poner(MI_CUENTA_CT, "ct_cuenta.html")
    portales.paginas.pop(CUENTA_CT)  # la página de cuenta conocida no tiene el correo

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    ct = api.de("latido")[-1]["portales"]["computrabajo"]
    assert ct["estado"] == "listo"
    assert ct["correo"] == "ana.perez@gmail.com"
    assert ct["pagina_correo"] == "/candidate/micuenta/"

