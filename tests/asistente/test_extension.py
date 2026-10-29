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
from urllib.parse import parse_qs

import pytest

playwright_api = pytest.importorskip("playwright.async_api")
fastapi = pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, Response  # noqa: E402

from buscador_vacantes.asistente.api import PAGINA_VINCULO  # noqa: E402

pytestmark = pytest.mark.navegador

RAIZ = Path(__file__).resolve().parents[2]
EXTENSION = RAIZ / "extension"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "extension"
SELECTORES = RAIZ / "assets" / "asistente" / "selectores"
REGLAS_MOTOR = json.loads(
    (RAIZ / "assets" / "asistente" / "motor_generico.json").read_text(encoding="utf-8")
)
FAMILIAS_ATS = json.loads(
    (RAIZ / "assets" / "asistente" / "familias_ats.json").read_text(encoding="utf-8")
)
TOKEN = "token-de-prueba"
PDF = b"%PDF-1.4\n% CV de prueba\n"


# --- API de prueba -----------------------------------------------------------------------


class ApiPrueba:
    def __init__(self) -> None:
        self.llamadas: list[tuple[str, dict]] = []
        self.trabajos: list[dict] = []
        self.respuestas = lambda campos: []
        self.esperar = False  # True: el servidor le pregunta al usuario lo que falta
        self.ajustar = lambda plataforma, selectores: selectores
        self.preferencias: dict[str, dict] = {}
        self.cuentas: dict[str, dict] = {}
        self.nivel_ia = "normal"
        self.uso_ia = {"llamadas": 3, "tokens": 1200}
        self.con_nivel_ia = True  # False: servidor desactualizado, sin la ruta /nivel_ia (404)
        self.con_ping = True  # False: servidor desactualizado, sin la ruta /ping (404)
        self.demora_ping = 0.0
        self.pantalla = lambda cuerpo: {}  # decisión de POST /pantalla (la tarea 5.1 del servidor)
        self.al_envio = lambda: None  # se llama al registrar el envío, antes del clic
        self.demora_pantalla = 0.0
        self.selectores_extra: dict[str, dict] = {}  # plataformas de prueba sin archivo
        # Respuesta de POST /destino (postular-linkedin): por defecto, respaldo
        self.destino = lambda cuerpo: {"accion": "respaldo", "motivo": "linkedin_apagado"}
        self.app = self._app()

    def de(self, ruta: str) -> list[dict]:
        return [c for r, c in self.llamadas if r == ruta]

    def _app(self) -> FastAPI:
        app = FastAPI()
        api = self

        @app.get("/api/v1/vincular/{codigo}", response_class=HTMLResponse)
        async def pagina(codigo: str):
            return PAGINA_VINCULO.format(boton_telegram="", codigo=codigo, visible=codigo, api="")

        @app.post("/api/v1/vincular")
        async def vincular(request: Request):
            cuerpo = await request.json()
            api.llamadas.append(("vincular", cuerpo))
            if cuerpo["codigo"] != "ABCD2345":
                return JSONResponse({"detail": "código inválido"}, status_code=400)
            return {"token": TOKEN}

        @app.get("/api/v1/ping")
        async def ping(request: Request):
            api.llamadas.append(("ping", {"authorization": request.headers.get("authorization")}))
            await asyncio.sleep(api.demora_ping)
            if not api.con_ping:
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return {"ok": True}

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
                    "selectores": versiones, "cuentas": cuentas, "latido_s": 30,
                    "motor_generico": REGLAS_MOTOR["version"],
                    "familias_ats": FAMILIAS_ATS["version"]}  # fmt: skip

        @app.get("/api/v1/motor_generico")
        async def motor_generico(request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            api.llamadas.append(("motor_generico", {}))
            reglas = {k: v for k, v in REGLAS_MOTOR.items() if k != "nota"}
            return {"version": REGLAS_MOTOR["version"], "reglas": reglas}

        @app.get("/api/v1/familias_ats")
        async def familias_ats(request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            api.llamadas.append(("familias_ats", {}))
            return {"version": FAMILIAS_ATS["version"], "familias": FAMILIAS_ATS["familias"]}

        @app.get("/api/v1/preferencias/{plataforma}")
        async def ver_preferencias(plataforma: str, request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            api.llamadas.append(("preferencias_ver", {"plataforma": plataforma}))
            datos = {"automatico": True, "umbral": None, "avisar": True,
                     "revisar_respuestas": False,
                     "cuenta": api.cuentas.get(plataforma)}  # fmt: skip
            datos.update(api.preferencias.get(plataforma, {}))
            return datos

        @app.post("/api/v1/preferencias/{plataforma}")
        async def guardar_preferencias(plataforma: str, request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            cuerpo = await request.json()
            api.llamadas.append(("preferencias_guardar", {"plataforma": plataforma, **cuerpo}))
            api.preferencias[plataforma] = cuerpo
            return {"ok": True}

        @app.get("/api/v1/nivel_ia")
        async def ver_nivel_ia(request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            if not api.con_nivel_ia:
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            api.llamadas.append(("nivel_ia_ver", {}))
            return {"nivel": api.nivel_ia, "hoy": api.uso_ia, "niveles": [
                {"clave": "ahorro", "nombre": "Ahorro", "llamadas_estimadas": 2},
                {"clave": "normal", "nombre": "Normal", "llamadas_estimadas": 6},
                {"clave": "maximo", "nombre": "Máximo", "llamadas_estimadas": 14},
            ]}  # fmt: skip

        @app.post("/api/v1/nivel_ia")
        async def guardar_nivel_ia(request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            cuerpo = await request.json()
            api.llamadas.append(("nivel_ia_guardar", cuerpo))
            api.nivel_ia = cuerpo["nivel"]
            return {"ok": True, "nivel": cuerpo["nivel"]}

        @app.post("/api/v1/cuenta/{plataforma}/olvidar")
        async def olvidar(plataforma: str, request: Request):
            if not autorizado(request):
                return JSONResponse({"detail": "token"}, status_code=401)
            api.llamadas.append(("olvidar", {"plataforma": plataforma}))
            api.cuentas.pop(plataforma, None)
            return {"ok": True}

        @app.get("/api/v1/selectores/{plataforma}")
        async def selectores(plataforma: str):
            if plataforma in api.selectores_extra:
                contenido = {"version": "prueba", **api.selectores_extra[plataforma]}
            else:
                archivo = SELECTORES / f"{plataforma}.json"
                contenido = json.loads(archivo.read_text(encoding="utf-8"))
            contenido = api.ajustar(plataforma, contenido)
            return {"version": contenido["version"], "selectores": contenido}

        @app.post("/api/v1/postulaciones/{pid}/{accion}")
        async def postulacion(pid: int, accion: str, request: Request):
            cuerpo = await request.json() if await request.body() else {}
            api.llamadas.append((accion, {"id": pid, **cuerpo}))
            if accion == "tomar":
                api.trabajos = [t for t in api.trabajos if t["id"] != pid]
            if accion == "envio":
                api.al_envio()
            if accion == "pantalla":
                await asyncio.sleep(api.demora_pantalla)
                return api.pantalla(cuerpo)
            if accion == "destino":
                return api.destino(cuerpo)
            pedir_usuario = (
                (api.esperar(cuerpo["campos"]) if callable(api.esperar) else api.esperar)
                if accion == "formulario" and cuerpo.get("campos")
                else False
            )
            if accion == "formulario" and pedir_usuario and cuerpo["campos"]:
                return {"esperar_usuario": True}
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
    servidor.esperar = False
    servidor.ajustar = lambda plataforma, selectores: selectores
    servidor.con_ping = True
    servidor.demora_ping = 0.0
    servidor.pantalla = lambda cuerpo: {}
    servidor.al_envio = lambda: None
    servidor.demora_pantalla = 0.0
    servidor.selectores_extra = {}
    servidor.destino = lambda cuerpo: {"accion": "respaldo", "motivo": "linkedin_apagado"}
    return servidor


# --- navegador con la extensión ----------------------------------------------------------


def copia_extension(destino: Path, permisos: tuple[str, ...] = (),
                    plataformas: dict[str, list[str]] | None = None,
                    externa: bool = False) -> Path:  # fmt: skip
    """Copia la extensión y permite el servidor local de prueba (como lo haría Opciones).

    `permisos`: dominios opcionales que el usuario ya activó desde el popup (por ejemplo
    elempleo.com). `plataformas`: plataformas de prueba {nombre: dominios} que se suman a
    DOMINIOS, con su permiso. `externa`: el usuario ya concedió el permiso de las páginas de las
    empresas (`https://*/*`, postular-linkedin)."""
    shutil.copytree(EXTENSION, destino)
    manifiesto = json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
    manifiesto["host_permissions"].append("http://127.0.0.1/*")
    manifiesto["host_permissions"] += [f"https://*.{d}/*" for d in permisos]
    if externa:
        manifiesto["host_permissions"].append("https://*/*")
    if plataformas:
        archivo = destino / "portales.js"
        texto = archivo.read_text(encoding="utf-8")
        marca = '  spe: ["buscadordeempleo.gov.co"],\n'
        assert marca in texto
        nuevas = "".join(f"  {n}: {json.dumps(d)},\n" for n, d in plataformas.items())
        archivo.write_text(texto.replace(marca, marca + nuevas), encoding="utf-8")
        manifiesto["host_permissions"] += [
            f"https://*.{d}/*" for dominios in plataformas.values() for d in dominios
        ]
    (destino / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    return destino


class Portales:
    """Sirve las páginas de los portales desde los fixtures y guarda lo que reciben."""

    def __init__(self) -> None:
        self.paginas: dict[str, str] = {}
        self.envios: dict[str, str] = {}  # respuesta a un POST de formulario, por URL
        self.redirecciones: dict[str, str] = {}
        self.recibido: list[bytes] = []
        self.pedidas: list[str] = []  # URLs que pidió el navegador, en orden

    @staticmethod
    def _leer(fixture: str, reemplazos: dict[str, str] | None) -> str:
        html = (FIXTURES / fixture).read_text(encoding="utf-8")
        for a, b in (reemplazos or {}).items():
            html = html.replace(a, b)
        return html

    def poner(self, url: str, fixture: str, reemplazos: dict[str, str] | None = None) -> None:
        self.paginas[url] = self._leer(fixture, reemplazos)

    def al_enviar(self, url: str, fixture: str) -> None:
        """Página que devuelve el portal cuando se envía un formulario a `url` (POST)."""
        self.envios[url] = self._leer(fixture, None)

    async def atender(self, route) -> None:
        peticion = route.request
        url = peticion.url.split("#")[0]
        self.pedidas.append(url)
        if url.endswith("/recibir"):
            self.recibido.append(peticion.post_data_buffer or b"")
            await route.fulfill(status=200, body="ok")
            return
        if peticion.method == "POST" and url in self.envios:
            self.recibido.append(peticion.post_data_buffer or b"")
            await route.fulfill(status=200, body=self.envios[url],
                                content_type="text/html; charset=utf-8")  # fmt: skip
            return
        if url in self.redirecciones:
            # Redirección desde la página: la petición que sigue a un 302 respondido con
            # route.fulfill no pasa por context.route y saldría a la red real
            destino = json.dumps(self.redirecciones[url])
            await route.fulfill(status=200, content_type="text/html",
                                body=f"<script>location.replace({destino})</script>")  # fmt: skip
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
BUSCAR_MG = "https://www.magneto365.com/co/trabajos/buscar"
INGRESO_MG = "https://web.magneto365.com/sign-in"
RESUME_MG = "https://web.magneto365.com/profile/resume?callback=true"
CORREO_MG = "candidato.prueba@example.com"
INGRESO_CT = "https://candidato.co.computrabajo.com/acceso/"
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
            "pruebas: {sondeo_captcha_ms: 500, sondeo_sesion_ms: 300, "
            "espera_sesion_max_ms: 8000}})"
        )

    async def latido(self):
        # Si ya hay un latido en curso (el de la instalación), se espera y se hace uno nuevo
        return await self.evaluar("asistente.latido().then(() => asistente.latido())")

    async def guardar(self, objeto: dict) -> None:
        await self.evaluar(f"chrome.storage.local.set({json.dumps(objeto)})")

    async def popup(self):
        id_extension = self.worker.url.split("/")[2]
        pagina = await self.contexto.new_page()
        await pagina.set_viewport_size({"width": 360, "height": 600})
        await pagina.goto(f"chrome-extension://{id_extension}/popup.html")
        return pagina


def correr(corutina):
    return asyncio.run(corutina)


async def abrir(tmp_path: Path, url_api: str, portales: Portales, *, vinculado=True,
                permisos: tuple[str, ...] = (), plataformas=None, externa=False):  # fmt: skip
    pw = await playwright_api.async_playwright().start()
    ruta = copia_extension(tmp_path / "ext", permisos, plataformas, externa)
    try:
        contexto = await pw.chromium.launch_persistent_context(
            str(tmp_path / "perfil"), channel="chromium", headless=True,
            args=[f"--disable-extensions-except={ruta}", f"--load-extension={ruta}"],
        )  # fmt: skip
    except Exception as exc:  # Chromium no instalado
        await pw.stop()
        pytest.skip(f"Chromium no disponible: {exc}")
    if externa:
        # Con el permiso amplio la extensión puede abrir cualquier sitio: nada sale a la red real
        # (las rutas que se registran después tienen prioridad)
        await contexto.route("https://**/*", portales.atender)
    await contexto.route("https://*.computrabajo.com/**", portales.atender)
    await contexto.route("https://*.magneto365.com/**", portales.atender)
    await contexto.route("https://*.elempleo.com/**", portales.atender)
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
    p.poner(BUSCAR_MG, "mg_sin_sesion.html")
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
    assert manifiesto["version"] == "1.3.3"
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
    # Las páginas externas de LinkedIn (postular-linkedin): el permiso amplio es solo opcional y lo
    # pide el popup con un gesto del usuario; nunca viene de fábrica
    assert "https://*/*" in opcionales
    assert "https://*/*" not in manifiesto["host_permissions"]


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
    assert vinculo["version"] == "1.3.3"


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


def test_latido_informa_si_la_extension_esta_en_pausa(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            await nav.guardar({"pausado": True})
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    cuerpos = [c for r, c in api.llamadas if r == "latido"]
    assert cuerpos[0]["pausado"] is False
    assert cuerpos[-1]["pausado"] is True


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
    adjunto = next(p for p in api.de("paso") if p["paso"] == "cv_adjunto")
    assert adjunto["detalle"] == "CV_Ana_Perez.pdf"


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


# --- Preguntas de selección reales de Computrabajo (postulaciones 6 y 7 del piloto) -----------

KQ = "https://candidato.co.computrabajo.com/candidate/kq?oi=PRUEBA&p=57&d=33&idb=1"
KQ_ENVIO = "https://candidato.co.computrabajo.com/candidate/kq"
HOME_CT = "https://candidato.co.computrabajo.com/candidate/home?uvma=true"


def respuestas_kq(campos: list[dict]) -> list[dict]:
    salida = []
    for i, c in enumerate(campos):
        if c["tipo"] == "opciones":
            salida.append({"indice": i, "valor": None, "opcion": c["opciones"].index("no")})
        elif "institución" in c["texto"]:
            salida.append({"indice": i, "valor": "SENA", "opcion": None})
        elif "etapa lectiva" in c["texto"]:
            salida.append({"indice": i, "valor": "Sí, en junio", "opcion": None})
    return salida


def test_preguntas_de_seleccion_reales_se_leen_llenan_y_confirman(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.redirecciones[MATCH] = KQ
    portales.poner(KQ, "ct_kq.html")
    # Enviar las preguntas recarga la página: el portal responde con la de "Aplicación enviada"
    portales.al_enviar(KQ_ENVIO, "ct_aplicada.html")
    api.trabajos = [trabajo()]
    api.respuestas = respuestas_kq

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    campos = api.de("formulario")[0]["campos"]
    assert [(c["texto"], c["obligatoria"]) for c in campos] == [
        ("¿Ha firmado anteriormente un contrato de aprendizaje?", True),
        ("Indica el nombre de tu institución de formación", True),
        ("¿Ya finalizó su etapa lectiva?", True),
    ]
    assert campos[0]["opciones"] == ["si", "no"]
    # El maxlength de las preguntas abiertas llega al servidor; sin atributo, no hay límite
    assert [c.get("maximo") for c in campos] == [None, 500, 500]
    enviado = portales.recibido[0].decode("utf-8")
    assert "KillerQuestions%5B0%5D.ClosedQuestion=12" in enviado
    assert "SENA" in enviado and "junio" in enviado
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "enviada", resultado
    assert "Aplicación enviada" in resultado["confirmacion"]


def test_campo_sin_responder_no_se_envia_a_ciegas(tmp_path, api):
    """Si falta una respuesta, el portal marca el campo y la extensión lo reporta."""
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.redirecciones[MATCH] = KQ
    portales.poner(KQ, "ct_kq.html")
    portales.al_enviar(KQ_ENVIO, "ct_aplicada.html")
    api.trabajos = [trabajo()]
    api.respuestas = lambda campos: respuestas_kq(campos)[:2]

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "sin responder" in resultado["motivo"]
    assert not portales.recibido


def test_correo_marcado_por_el_portal_bloquea_sin_tocar_la_cuenta(tmp_path, api):
    """Computrabajo redirige Aplicar al inicio con «Email incorrecto»: no se llena nada."""
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.redirecciones[MATCH] = HOME_CT
    portales.poner(HOME_CT, "ct_home_correo.html")
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
    assert (resultado["estado"], resultado["motivo"]) == ("bloqueada", "portal_correo_incorrecto")
    assert not api.de("formulario")
    assert not portales.recibido


def test_inicio_sin_aviso_conocido_tambien_bloquea(tmp_path, api):
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.redirecciones[MATCH] = HOME_CT
    portales.poner(HOME_CT, "ct_home_sesion.html")
    api.trabajos = [trabajo()]

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    resultado = api.de("resultado")[0]
    assert (resultado["estado"], resultado["motivo"]) == ("bloqueada", "portal_redirige_inicio")
    assert not api.de("formulario")


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


def test_linkedin_lee_el_correo_con_el_perfil_real_y_no_con_in_me(tmp_path, api):
    """`/in/me/` salta al perfil con JavaScript (ya cargada la página) y la ventana de contacto se
    pinta tarde: la extensión espera el salto, toma el usuario de la URL en la que cae y espera el
    correo en `<perfil>/overlay/contact-info/` (visto con la sesión del dueño)."""
    perfil = "https://www.linkedin.com/in/ana-perez"
    portales = portales_listos()
    portales.paginas["https://www.linkedin.com/in/me/"] = (
        "<!doctype html><html><body>Cargando…<script>setTimeout(() => "
        f'location.replace("{perfil}/"), 1500)</script></body></html>'
    )
    portales.paginas[f"{perfil}/"] = "<!doctype html><html><body>Perfil de Ana</body></html>"
    portales.paginas[f"{perfil}/overlay/contact-info/"] = (
        "<!doctype html><html><body><script>setTimeout(() => { document.body.innerHTML = "
        "\"<dialog open aria-labelledby='t'><h2 id='t'>Información de contacto</h2>"
        "<a href='mailto:ana.linkedin@gmail.com'>ana.linkedin@gmail.com</a></dialog>\"; }, 2500)"
        "</script></body></html>"
    )

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales, externa=True)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    li = api.de("latido")[-1]["portales"]["linkedin"]
    assert li["estado"] == "listo"
    assert li["correo"] == "ana.linkedin@gmail.com"
    assert li["pagina_correo"] == "/in/ana-perez/overlay/contact-info/"


# Como entrega LinkedIn la página de contacto (2026-10-28): el correo solo viene en los datos de
# React Server Components; el <dialog> con el enlace lo crea su JavaScript, que en la pestaña de
# revisión (en segundo plano) no llega a correr
CONTACTO_SIN_PINTAR_LI = (
    '<!doctype html><html><body><script>self.__next_f.push([1,"{\\"urlValue\\":{\\"$case'
    '\\":\\"url\\",\\"url\\":\\"mailto:{correo}\\"}}"])</script></body></html>'
)


def latido_linkedin(tmp_path, api, portales: Portales) -> dict:
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales, externa=True)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    return api.de("latido")[-1]["portales"]["linkedin"]


def test_linkedin_lee_el_correo_del_html_sin_que_la_pagina_lo_pinte(tmp_path, api):
    """`/in/me/` no salta al perfil y la página de contacto nunca pinta la ventana: el usuario
    sale del HTML de `/in/me/` (el más repetido, no un sugerido) y el correo de los datos de
    la página de contacto."""
    perfil = "https://www.linkedin.com/in/ana-perez"
    portales = portales_listos()
    portales.paginas["https://www.linkedin.com/in/me/"] = (
        '<!doctype html><html><body>Cargando…<script>self.__next_f.push([1,"'
        + "linkedin.com/in/ana-perez " * 5
        + 'linkedin.com/in/otro-sugerido"])</script>'
        "</body></html>"
    )
    portales.paginas[f"{perfil}/overlay/contact-info/"] = CONTACTO_SIN_PINTAR_LI.replace(
        "{correo}", "ana.linkedin@gmail.com"
    )

    li = latido_linkedin(tmp_path, api, portales)
    assert li["estado"] == "listo"
    assert li["correo"] == "ana.linkedin@gmail.com"
    assert li["pagina_correo"] == "/in/ana-perez/overlay/contact-info/"
    assert li["motivo"] is None


def test_linkedin_sin_correo_en_el_contacto_informa_el_motivo(tmp_path, api):
    perfil = "https://www.linkedin.com/in/ana-perez"
    portales = portales_listos()
    portales.paginas["https://www.linkedin.com/in/me/"] = (
        f"<!doctype html><html><body><a href='{perfil}/'>Ana</a></body></html>"
    )
    portales.paginas[f"{perfil}/overlay/contact-info/"] = (
        "<!doctype html><html><body>Información de contacto</body></html>"
    )

    li = latido_linkedin(tmp_path, api, portales)
    assert li["estado"] == "listo"
    assert li["correo"] is None
    assert li["motivo"] == "sin_correo"


def test_un_portal_sin_correo_se_vuelve_a_revisar_a_los_10_minutos(tmp_path, api):
    """Con sesión y sin correo no se espera el plazo de 6 h: pasados 10 min se revisa otra
    vez; con correo, el estado guardado se respeta."""
    portales = portales_listos()

    async def revisado_hace_11_min(nav, correo: str | None) -> list[str]:
        valor = json.dumps(correo)
        await nav.evaluar(
            "chrome.storage.local.get('portales').then(({portales}) => chrome.storage.local.set("
            f"{{portales: {{...portales, computrabajo: {{estado: 'listo', correo: {valor}, "
            "revisado: Date.now() - 11 * 60 * 1000}}}))"
        )
        antes = len(portales.pedidas)
        await nav.evaluar("asistente.latido()")
        return [u for u in portales.pedidas[antes:] if "computrabajo.com" in u]

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
            con_correo = await revisado_hace_11_min(nav, "ana.perez@gmail.com")
            sin_correo = await revisado_hace_11_min(nav, None)
            return con_correo, sin_correo
        finally:
            await cerrar(nav)

    con_correo, sin_correo = correr(flujo())
    assert not con_correo  # con correo se respeta el plazo de 6 h
    assert sin_correo  # sin correo se revisó otra vez
    ct = api.de("latido")[-1]["portales"]["computrabajo"]
    assert ct["correo"] == "ana.perez@gmail.com"


# --- "Iniciar sesión": abre, espera, cierra sola y reporta ---------------------------------


def test_iniciar_sesion_cierra_la_pestana_sola_y_reporta_al_servidor(tmp_path, api):
    """El botón abre la página de ingreso; en cuanto esa pestaña muestra la sesión iniciada
    (el usuario ya inició sesión), la extensión la cierra sola, relee el portal y avisa al
    servidor sin que el usuario haga nada más."""
    portales = portales_listos()
    # Simula el formulario de acceso: tras "iniciar sesión", el portal redirige a la home
    portales.paginas[INGRESO_CT] = (
        "<!doctype html><html><body>Formulario de acceso"
        f'<script>setTimeout(() => {{ location.href = "{INICIO_CT}"; }}, 300)</script>'
        "</body></html>"
    )
    portales.poner(INICIO_CT, "ct_cuenta.html")  # la home, ya con la sesión iniciada

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            antes = len(nav.contexto.pages)
            await nav.evaluar("asistente.vigilarInicioSesion('computrabajo')")
            vigilando = await nav.almacenamiento("vigilando")
            return vigilando, antes, len(nav.contexto.pages)
        finally:
            await cerrar(nav)

    vigilando, antes, despues = correr(flujo())
    assert not vigilando  # se limpió al terminar de vigilar
    assert despues == antes  # la pestaña de ingreso se cerró sola: no quedó ninguna de más
    ct = api.de("latido")[-1]["portales"]["computrabajo"]
    assert ct["estado"] == "listo" and ct["correo"] == "ana.perez@gmail.com"


# --- Magneto: la sesión se ve por el avatar, no por el enlace de ingreso -------------------


def latido_magneto(tmp_path, api, portales: Portales) -> dict:
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    return api.de("latido")[-1]["portales"]["magneto"]


def test_magneto_con_sesion_se_detecta_aunque_el_html_traiga_iniciar_sesion(tmp_path, api):
    """El HTML de Magneto trae «Iniciar sesión» aunque haya sesión; el JS lo cambia por el
    avatar segundos después. La extensión espera la marca y no se queda con el enlace."""
    portales = portales_listos()
    portales.poner(BUSCAR_MG, "mg_con_sesion.html")

    mg = latido_magneto(tmp_path, api, portales)
    assert mg["estado"] == "listo"
    assert mg["correo"] == CORREO_MG


# Sin el script, la página se queda con el enlace «Iniciar sesión» y nunca muestra el avatar
SIN_AVATAR = {"<script>": "<script>/*", "</script>": "*/</script>"}


@pytest.mark.parametrize("enlace_antiguo", [False, True], ids=["actual", "sin_sesion_antiguo"])
def test_magneto_sin_avatar_queda_sin_sesion(tmp_path, api, enlace_antiguo):
    portales = portales_listos()
    portales.poner(BUSCAR_MG, "mg_con_sesion.html", SIN_AVATAR)

    def ajustar(plataforma, sel):
        if plataforma == "magneto":
            sel["sesion"]["espera_ms"] = 3000
            if enlace_antiguo:
                sel["sesion"]["sin_sesion"].append("a[href*='web.magneto365.com/sign-in']")
        return sel

    api.ajustar = ajustar
    mg = latido_magneto(tmp_path, api, portales)
    assert mg["estado"] == "sin_sesion"
    assert mg["motivo"] == ("enlace_ingresar" if enlace_antiguo else "sin_marca_sesion")


@pytest.mark.parametrize("con_abrir", [True, False], ids=["con_clic", "sin_clic"])
def test_magneto_lee_el_correo_tras_abrir_el_menu_del_avatar(tmp_path, api, con_abrir):
    """El tooltip con el correo solo existe después de hacer clic en el avatar (cuenta.abrir):
    sin ese dato la sesión se detecta igual, pero el correo no aparece."""
    portales = portales_listos()
    portales.poner(BUSCAR_MG, "mg_con_sesion.html")

    def ajustar(plataforma, sel):
        if plataforma == "magneto" and not con_abrir:
            sel["cuenta"].pop("abrir")
            sel["cuenta"]["urls"] = [BUSCAR_MG]  # sin más páginas donde buscarlo
        return sel

    api.ajustar = ajustar
    mg = latido_magneto(tmp_path, api, portales)
    assert mg["estado"] == "listo"
    assert mg["correo"] == (CORREO_MG if con_abrir else None)


def test_vigilar_magneto_no_cierra_la_pestana_en_la_pagina_intermedia(tmp_path, api):
    """Tras iniciar sesión, Magneto pasa por /profile/resume con el cuerpo vacío antes de
    llegar al portal con el avatar. Esa página no es sesión iniciada: la pestaña sigue
    abierta hasta ver el avatar."""
    destino = BUSCAR_MG + "?desde=ingreso"  # solo la pide la pestaña de ingreso
    portales = portales_listos()
    portales.paginas[INGRESO_MG] = (
        "<!doctype html><html><body>Formulario de acceso"
        f'<script>setTimeout(() => {{ location.href = "{RESUME_MG}"; }}, 300)</script>'
        "</body></html>"
    )
    portales.paginas[RESUME_MG] = (
        "<!doctype html><html><body>"
        f'<script>setTimeout(() => {{ location.href = "{destino}"; }}, 1500)</script>'
        "</body></html>"
    )
    portales.poner(destino, "mg_con_sesion.html")
    portales.poner(BUSCAR_MG, "mg_con_sesion.html")

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            antes = len(nav.contexto.pages)
            await nav.evaluar("asistente.vigilarInicioSesion('magneto')")
            vigilando = await nav.almacenamiento("vigilando")
            return vigilando, antes, len(nav.contexto.pages)
        finally:
            await cerrar(nav)

    vigilando, antes, despues = correr(flujo())
    assert destino in portales.pedidas  # no se cerró en la página vacía
    assert not vigilando
    assert despues == antes
    mg = api.de("latido")[-1]["portales"]["magneto"]
    assert mg["estado"] == "listo" and mg["correo"] == CORREO_MG


def test_vigilar_sin_token_no_deja_errores_sin_capturar(tmp_path, api):
    """Sin token, «Iniciar sesión» no abre la pestaña ni deja el 401 «navegador sin
    vincular» como rechazo sin capturar en el service worker; el latido tampoco."""

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos(), vinculado=False)
        try:
            await nav.evaluar(
                "globalThis.__rechazos = []; self.addEventListener('unhandledrejection', "
                "(e) => __rechazos.push(String((e.reason && e.reason.message) || e.reason)))"
            )
            pagina = await nav.popup()
            antes = len(nav.contexto.pages)
            respuesta = await pagina.evaluate(
                "chrome.runtime.sendMessage({tipo: 'iniciarSesion', plataforma: 'magneto'})"
            )
            await asyncio.sleep(3)
            await nav.evaluar("asistente.latido()")
            return respuesta, antes, len(nav.contexto.pages), await nav.evaluar("__rechazos")
        finally:
            await cerrar(nav)

    respuesta, antes, despues, rechazos = correr(flujo())
    assert respuesta == {"ok": True}
    assert despues == antes  # no abrió la página de ingreso
    assert rechazos == []


def test_sin_confirmar_la_cuenta_el_popup_no_la_muestra_como_lista(tmp_path, api):
    """Mientras el servidor no diga explícitamente que la cuenta quedó confirmada (por
    ejemplo, justo tras cancelar en el bot, antes del siguiente latido), el popup no debe
    asumir que sí lo está."""
    portales = portales_listos()

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            # El servidor no mandó nada sobre esta cuenta todavía (ni true ni false)
            await nav.evaluar(
                "chrome.storage.local.set({"
                "estado: {en_linea: true, cuentas: {}}, "
                "portales: {computrabajo: {estado: 'listo', correo: 'ana.perez@gmail.com'}}, "
                "selectores_version: {computrabajo: '1', magneto: '1'}})"
            )
            id_extension = nav.worker.url.split("/")[2]
            pagina = await nav.contexto.new_page()
            await pagina.goto(f"chrome-extension://{id_extension}/popup.html")
            await pagina.wait_for_timeout(300)
            texto = await pagina.inner_text("#portales")
            await pagina.close()
            return texto
        finally:
            await cerrar(nav)

    texto = correr(flujo())
    assert "Confírmala" in texto or "Esperando confirmación" in texto
    assert "Listo" not in texto


# --- engranaje de la tarjeta: preferencias del portal --------------------------------------


def test_engranaje_lee_y_guarda_las_preferencias_del_portal(tmp_path, api):
    portales = portales_listos()
    api.cuentas["computrabajo"] = {
        "correo": "ana.perez@gmail.com", "estado": "confirmada",
        "confirmada_en": "2026-10-05T10:00:00+00:00",
    }  # fmt: skip

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
            id_extension = nav.worker.url.split("/")[2]
            pagina = await nav.contexto.new_page()
            await pagina.goto(f"chrome-extension://{id_extension}/popup.html")
            await pagina.wait_for_timeout(300)
            await pagina.click(".tarjeta.computrabajo .abrir")
            await pagina.wait_for_function(
                "document.getElementById('vp-detalle-cuerpo').textContent !== 'Cargando…'"
            )
            # <details> empieza cerrado: su contenido no se "ve", así que se lee con
            # text_content (lo que hay en el DOM) en vez de inner_text (lo que se renderiza)
            detalle = await pagina.text_content("#vp-detalle-cuerpo")
            automatico_inicial = await pagina.is_checked("#vp-automatico")
            # El usuario apaga "Postular automáticamente" y sube la afinidad mínima propia
            # (se hace clic en la pista visible del interruptor, no en el checkbox oculto)
            await pagina.click("label:has(#vp-automatico) .pista")
            await pagina.select_option("#vp-umbral", "85")
            await pagina.wait_for_timeout(300)
            await pagina.close()
            return detalle, automatico_inicial
        finally:
            await cerrar(nav)

    detalle, automatico_inicial = correr(flujo())
    assert "ana.perez@gmail.com" in detalle and "Confirmada" in detalle
    assert automatico_inicial is True
    guardados = api.de("preferencias_guardar")
    assert guardados[-1] == {"plataforma": "computrabajo", "automatico": False, "umbral": 85,
                             "avisar": True, "revisar_respuestas": False}  # fmt: skip


def abrir_vista_portal(nav, plataforma="computrabajo"):
    async def abrir_vista():
        id_extension = nav.worker.url.split("/")[2]
        pagina = await nav.contexto.new_page()
        await pagina.goto(f"chrome-extension://{id_extension}/popup.html")
        await pagina.wait_for_timeout(300)
        await pagina.click(f".tarjeta.{plataforma} .abrir")
        # Con selector y no con wait_for_function: la CSP del popup no deja evaluar texto
        await pagina.wait_for_selector("#vp-revisar:not([disabled])", state="attached")
        return pagina

    return abrir_vista()


def test_revisar_respuestas_viene_apagado_y_se_guarda_al_encenderlo(tmp_path, api):
    api.preferencias.clear()  # la API falsa la comparten las pruebas del módulo

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            pagina = await abrir_vista_portal(nav)
            inicial = await pagina.is_checked("#vp-revisar")
            texto = await pagina.inner_text("label:has(#vp-revisar)")
            await pagina.click("label:has(#vp-revisar) .pista")
            await pagina.wait_for_timeout(300)
            await pagina.close()
            # Al volver a abrir la vista, refleja lo que guardó el servidor
            pagina = await abrir_vista_portal(nav)
            despues = await pagina.is_checked("#vp-revisar")
            await pagina.close()
            return inicial, texto, despues
        finally:
            await cerrar(nav)

    inicial, texto, despues = correr(flujo())
    assert inicial is False and despues is True
    assert "Revisar respuestas antes de enviar" in texto
    assert api.de("preferencias_guardar")[-1] == {
        "plataforma": "computrabajo", "automatico": True, "umbral": None, "avisar": True,
        "revisar_respuestas": True,
    }  # fmt: skip


JS_NIVEL_IA = (
    "({oculto: document.getElementById('nivel-ia-bloque').hidden,"
    " valor: document.getElementById('nivel-ia').value,"
    " deshabilitado: document.getElementById('nivel-ia').disabled,"
    " opciones: [...document.querySelectorAll('#nivel-ia option')]"
    ".map(o => [o.value, o.textContent]),"
    " hoy: document.getElementById('nivel-ia-hoy').textContent})"
)


def test_el_popup_muestra_y_cambia_el_nivel_de_ia(tmp_path, api):
    api.nivel_ia, api.uso_ia = "normal", {"llamadas": 3, "tokens": 1200}  # API compartida

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            pagina = await nav.popup()
            await pagina.wait_for_selector("#nivel-ia:not([disabled])", state="attached")
            inicial = await pagina.evaluate(JS_NIVEL_IA)
            await pagina.select_option("#nivel-ia", "maximo")
            await pagina.wait_for_selector("#nivel-ia:not([disabled])", state="attached")
            tras_cambiar = await pagina.evaluate(JS_NIVEL_IA)
            await pagina.close()
            # Al volver a abrir el popup, refleja lo que guardó el servidor
            pagina = await nav.popup()
            await pagina.wait_for_selector("#nivel-ia:not([disabled])", state="attached")
            reabierto = await pagina.evaluate(JS_NIVEL_IA)
            await pagina.close()
            return inicial, tras_cambiar, reabierto
        finally:
            await cerrar(nav)

    inicial, tras_cambiar, reabierto = correr(flujo())
    assert inicial["oculto"] is False and inicial["valor"] == "normal"
    assert inicial["opciones"] == [
        ["ahorro", "Ahorro · ~2 llamadas"], ["normal", "Normal · ~6 llamadas"],
        ["maximo", "Máximo · ~14 llamadas"],
    ]  # fmt: skip
    assert "Hoy llevas 3 llamadas y 1200 tokens" in inicial["hoy"]
    assert tras_cambiar["valor"] == "maximo" and reabierto["valor"] == "maximo"
    assert api.de("nivel_ia_guardar") == [{"nivel": "maximo"}]


def test_el_popup_esconde_el_nivel_de_ia_si_el_servidor_no_lo_conoce(tmp_path, api):
    api.con_nivel_ia = False

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            pagina = await nav.popup()
            await pagina.wait_for_timeout(800)
            return await pagina.evaluate(JS_NIVEL_IA)
        finally:
            await cerrar(nav)
            api.con_nivel_ia = True

    assert correr(flujo())["oculto"] is True


def test_olvidar_cuenta_pide_confirmar_dos_veces(tmp_path, api):
    portales = portales_listos()
    api.cuentas["computrabajo"] = {
        "correo": "ana.perez@gmail.com",
        "estado": "confirmada",
        "confirmada_en": None,
    }

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
            id_extension = nav.worker.url.split("/")[2]
            pagina = await nav.contexto.new_page()
            await pagina.goto(f"chrome-extension://{id_extension}/popup.html")
            await pagina.wait_for_timeout(300)
            await pagina.click(".tarjeta.computrabajo .abrir")
            await pagina.wait_for_timeout(300)
            await pagina.click("#vp-olvidar")
            texto_1 = await pagina.inner_text("#vp-olvidar")
            await pagina.click("#vp-olvidar")
            await pagina.wait_for_timeout(300)
            await pagina.close()
            return texto_1
        finally:
            await cerrar(nav)

    texto_1 = correr(flujo())
    assert "Seguro" in texto_1
    assert api.de("olvidar") == [{"plataforma": "computrabajo"}]
    assert "computrabajo" not in api.cuentas


def test_encuesta_que_el_portal_no_acepta_queda_como_no_enviada(tmp_path, api):
    """El formulario sigue en pantalla tras enviar (postulaciones 12 a 14 del piloto)."""
    portales = portales_listos()
    portales.poner(VACANTE, "ct_vacante.html")
    portales.redirecciones[MATCH] = KQ
    portales.poner(KQ, "ct_kq.html", {"if (falta) e.preventDefault();": "e.preventDefault();"})
    api.trabajos = [trabajo()]
    api.respuestas = respuestas_kq

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "no aceptó el envío" in resultado["motivo"]


# --- Magneto: encuesta en la página y confirmación por el modal de resumen ------------------

VACANTE_MG = "https://www.magneto365.com/co/empleos/desarrollador-junior-erp-odoo-1100511"
# El modal de Magneto tarda en salir; sin él las preguntas siguen en pantalla
SIN_MODAL = {"}, 2000);": "}, 2000000);"}


def trabajo_mg():
    return {"id": 31, "tipo": "postular", "plataforma": "magneto", "url": VACANTE_MG,
            "titulo": "Desarrollador junior", "actualizar_cv_portal": False}  # fmt: skip


def portales_magneto(fixture="mg_cuestionario.html", reemplazos=None) -> Portales:
    p = portales_listos()
    for url in (CUENTA_MG, INICIO_MG, BUSCAR_MG):
        p.poner(url, "mg_con_sesion.html")
    p.poner(VACANTE_MG, fixture, reemplazos)
    return p


def respuestas_mg(campos: list[dict]) -> list[dict]:
    return [{"indice": i, "valor": None, "opcion": 0} for i, _ in enumerate(campos)]


def postular_magneto(tmp_path, api, portales, *, rapido=False, pruebas=None) -> None:
    """`pruebas`: opciones de la extensión que la prueba acorta (por ejemplo llenado_max_ms)."""
    api.trabajos = [trabajo_mg()]
    if rapido:
        api.ajustar = confirmar_rapido

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            if pruebas:
                await nav.evaluar(
                    "chrome.storage.local.get('pruebas').then(r => chrome.storage.local.set("
                    f"{{pruebas: {{...r.pruebas, ...{json.dumps(pruebas)}}}}}))"
                )
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())


def test_magneto_encuesta_se_lee_se_responde_y_se_confirma_por_el_modal(tmp_path, api):
    api.respuestas = respuestas_mg
    postular_magneto(tmp_path, api, portales_magneto())
    campos = api.de("formulario")[0]["campos"]
    assert [(c["texto"], c["tipo"], c["obligatoria"]) for c in campos] == [
        ("¿Tienes disponibilidad para trabajar de forma presencial?", "opciones", True),
        ("¿Autorizas el tratamiento de tus datos personales?", "opciones", True),
    ]
    assert [[o.lower() for o in c["opciones"]] for c in campos] == [["si", "no"]] * 2
    pasos = [p["paso"] for p in api.de("paso")]
    assert "llenado" in pasos and "enviar" in pasos
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "enviada", resultado
    assert "Se ha enviado tu aplicación" in resultado["confirmacion"]


def test_magneto_sin_encuesta_llega_a_enviada_sin_pedir_formulario(tmp_path, api):
    postular_magneto(tmp_path, api, portales_magneto("mg_aplicada_sin_encuesta.html"))
    assert not api.de("formulario")
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "enviada", resultado
    assert "Se ha enviado tu aplicación" in resultado["confirmacion"]


def test_magneto_ya_aplicaste_no_pulsa_nada(tmp_path, api):
    postular_magneto(tmp_path, api, portales_magneto("mg_ya_aplicaste.html"))
    assert api.de("resultado")[0]["estado"] == "ya_postulada"
    assert not api.de("envio")
    assert "aplicar" not in [p["paso"] for p in api.de("paso")]


def test_magneto_pregunta_sin_respuesta_espera_al_usuario_sin_enviar(tmp_path, api):
    api.esperar = True  # el servidor no sabe la respuesta y se la pregunta al usuario
    postular_magneto(tmp_path, api, portales_magneto())
    assert len(api.de("formulario")[0]["campos"]) == 2
    pasos = [p["paso"] for p in api.de("paso")]
    assert "esperando_usuario" in pasos and "enviar" not in pasos
    assert not api.de("resultado")
    assert len(api.de("envio")) == 1  # solo el de «Aplicar»; «Enviar respuestas» no se pulsó


def test_magneto_encuesta_que_el_portal_no_acepta_queda_como_no_enviada(tmp_path, api):
    api.respuestas = respuestas_mg
    portales = portales_magneto(reemplazos=SIN_MODAL)
    postular_magneto(tmp_path, api, portales, rapido=True)
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    assert "no aceptó el envío" in resultado["motivo"]


def test_magneto_opcion_que_no_queda_marcada_no_se_envia(tmp_path, api):
    api.respuestas = respuestas_mg
    sin_marcar = {'boton.querySelector("input.ant-radio-input").checked = true;': ""}
    portales = portales_magneto(reemplazos=sin_marcar)
    postular_magneto(tmp_path, api, portales)
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    assert "no quedó marcada" in resultado["motivo"]
    assert "enviar" not in [p["paso"] for p in api.de("paso")]


# Postulación 51 (2026-10-18): la encuesta mezcla botones con preguntas abiertas (textarea sin
# maxlength y con el contador «0 de 140»)
PROGRAMA = "¿Cómo se llama tu programa de formación actual?"
SEMESTRE = "¿Qué semestre cursas?"
AUTORIZAS = '"¿Autorizas el tratamiento de tus datos personales?",'
MIXTA = {AUTORIZAS: f'{{abierta: "{PROGRAMA}"}}, {AUTORIZAS} {{abierta: "{SEMESTRE}"}},'}


def respuestas_mg_mixta(campos: list[dict]) -> list[dict]:
    return [{"indice": i, "valor": None, "opcion": 0} if c["tipo"] == "opciones"
            else {"indice": i, "valor": f"Respuesta {i}", "opcion": None}
            for i, c in enumerate(campos)]  # fmt: skip


def test_magneto_encuesta_con_preguntas_abiertas_se_escribe_y_se_confirma(tmp_path, api):
    api.respuestas = respuestas_mg_mixta
    postular_magneto(tmp_path, api, portales_magneto(reemplazos=MIXTA))
    campos = api.de("formulario")[0]["campos"]
    assert [(c["texto"], c["tipo"], c["obligatoria"], c.get("maximo")) for c in campos] == [
        ("¿Tienes disponibilidad para trabajar de forma presencial?", "opciones", True, None),
        (PROGRAMA, "texto", True, 140),
        ("¿Autorizas el tratamiento de tus datos personales?", "opciones", True, None),
        (SEMESTRE, "texto", True, 140),
    ]
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "enviada", resultado
    assert "Se ha enviado tu aplicación" in resultado["confirmacion"]


def test_magneto_pregunta_sin_botones_ni_campo_es_formulario_desconocido(tmp_path, api):
    api.respuestas = respuestas_mg_mixta
    vacia = {AUTORIZAS: f'{AUTORIZAS} {{vacia: "¿Pregunta sin respuesta posible?"}},'}
    postular_magneto(tmp_path, api, portales_magneto(reemplazos=vacia))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    assert "¿Pregunta sin respuesta posible?" in resultado["motivo"]
    assert not api.de("formulario")
    assert "enviar" not in [p["paso"] for p in api.de("paso")]


def test_magneto_texto_que_el_portal_borra_no_se_envia(tmp_path, api):
    api.respuestas = respuestas_mg_mixta
    borra = {**MIXTA, 'campo.addEventListener("input", () => {':
             'campo.addEventListener("input", () => { campo.value = "";'}  # fmt: skip
    postular_magneto(tmp_path, api, portales_magneto(reemplazos=borra))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    assert "no quedó escrita" in resultado["motivo"]
    assert "enviar" not in [p["paso"] for p in api.de("paso")]


def test_magneto_enviar_respuestas_deshabilitado_no_se_pulsa(tmp_path, api):
    api.respuestas = respuestas_mg_mixta
    nunca = {
        **MIXTA,
        "const revisar = () => (enviar.disabled = !completo());": "const revisar = () => {};",
    }
    postular_magneto(tmp_path, api, portales_magneto(reemplazos=nunca), rapido=True)
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    assert "deshabilitado" in resultado["motivo"]


# Fallas del 2026-10-18 (postulaciones 54 y 55)
SIN_EFECTO = {"}, 1500);": "}, 1500000);"}  # «Aplicar» no hace nada: el modal nunca sale
# «Aplicar» sí envía (la vacante ya no muestra el botón) pero el modal nunca sale
ENVIA_SIN_MODAL = {
    **SIN_EFECTO,
    'addEventListener("click", () => {': (
        'addEventListener("click", (e) => { e.currentTarget.remove();'
    ),
}


def test_magneto_aplicar_que_no_hace_nada_no_queda_como_incierta(tmp_path, api):
    portales = portales_magneto("mg_aplicada_sin_encuesta.html", SIN_EFECTO)
    postular_magneto(tmp_path, api, portales, rapido=True)
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    assert resultado["motivo"] == "aplicar_sin_efecto"
    assert "applyButton_apply-btn" in resultado["html"]  # la evidencia es la vacante intacta
    assert not api.de("formulario")


def test_magneto_envio_sin_modal_y_sin_boton_sigue_incierta(tmp_path, api):
    portales = portales_magneto("mg_aplicada_sin_encuesta.html", ENVIA_SIN_MODAL)
    postular_magneto(tmp_path, api, portales, rapido=True)
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "incierta", resultado


def llenados(api) -> list[dict]:
    return [p for p in api.de("paso") if p["paso"].startswith("llenado_")]


def test_magneto_registra_un_paso_por_cada_respuesta_sin_su_texto(tmp_path, api):
    api.respuestas = respuestas_mg_mixta
    postular_magneto(tmp_path, api, portales_magneto(reemplazos=MIXTA))
    nombres = [p["paso"] for p in api.de("paso")]
    assert [p["paso"] for p in llenados(api)] == [f"llenado_{n}" for n in (1, 2, 3, 4)]
    assert nombres.index("llenado_4") < nombres.index("enviar")
    assert not any("Respuesta" in str(p.get("detalle") or "") for p in llenados(api))
    assert api.de("resultado")[0]["estado"] == "enviada"


def test_magneto_llenado_que_se_corta_deja_el_ultimo_numero(tmp_path, api):
    api.respuestas = respuestas_mg_mixta
    borra = {**MIXTA, 'campo.addEventListener("input", () => {':
             'campo.addEventListener("input", () => { campo.value = "";'}  # fmt: skip
    postular_magneto(tmp_path, api, portales_magneto(reemplazos=borra))
    assert [p["paso"] for p in llenados(api)] == ["llenado_1"]  # la 2 es la abierta que se borra
    assert "llenado" not in [p["paso"] for p in api.de("paso")]
    assert api.de("resultado")[0]["estado"] == "formulario_desconocido"


def test_magneto_llenado_que_no_termina_se_corta_sin_enviar(tmp_path, api):
    """Postulación 55: el llenado se colgó ~3 min dentro de la extensión. Con la página
    bloqueada 8 s al marcar una opción, el tope (1,5 s en la prueba, 30 s real) lo corta."""
    api.respuestas = respuestas_mg
    cuelga = {'boton.querySelector("input.ant-radio-input").checked = true;':
              'for (const fin = Date.now() + 8000; Date.now() < fin; ) {} '
              'boton.querySelector("input.ant-radio-input").checked = true;'}  # fmt: skip
    postular_magneto(tmp_path, api, portales_magneto(reemplazos=cuelga),
                     pruebas={"llenado_max_ms": 1500})  # fmt: skip
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    assert resultado["motivo"] == "llenado_sin_respuesta"
    assert "enviar" not in [p["paso"] for p in api.de("paso")]
    assert len(api.de("envio")) == 1  # solo el de «Aplicar»


# --- popup: ping y recarga de la conexión ---------------------------------------------------

LEER_PING = "chrome.storage.local.get('ping').then(r => r.ping)"
MEDIR_PING = f"import('./api.js').then(m => m.ping()).then(() => {LEER_PING})"


def servidor_apagado() -> str:
    return f"http://127.0.0.1:{puerto_libre()}"  # nadie escucha en ese puerto


@pytest.mark.parametrize("con_ping", [True, False], ids=["con_ruta", "servidor_desactualizado"])
def test_ping_guarda_la_latencia_con_cualquier_respuesta(tmp_path, api, con_ping):
    api.con_ping = con_ping

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            pagina = await nav.popup()
            return await pagina.evaluate(MEDIR_PING)
        finally:
            await cerrar(nav)

    ping = correr(flujo())
    assert ping["ok"] is True and ping["ms"] >= 0 and ping["en"] > 0
    # Sin credenciales: el ping no lleva el token del navegador
    assert api.de("ping") and all(c["authorization"] is None for c in api.de("ping"))


def test_ping_con_el_servidor_apagado(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.guardar({"servidor": servidor_apagado()})
            pagina = await nav.popup()
            return await pagina.evaluate(MEDIR_PING)
        finally:
            await cerrar(nav)

    ping = correr(flujo())
    assert ping["ok"] is False and ping["ms"] is None


BARRA_LISTA = "document.getElementById('linea-texto').textContent !== 'Midiendo…'"
RECARGA_TERMINADA = "!document.getElementById('recargar').disabled"


async def esperar(pagina, expresion: str, timeout: float = 10.0) -> None:
    """wait_for_function evalúa el texto con eval, que la CSP del popup no permite."""
    limite = time.monotonic() + timeout
    while not await pagina.evaluate(expresion):
        if time.monotonic() > limite:
            raise TimeoutError(expresion)
        await asyncio.sleep(0.05)


JS_BARRA = (
    "({texto: document.getElementById('linea-texto').textContent,"
    " ping: document.getElementById('ping').textContent,"
    " clase_ping: document.getElementById('ping').className,"
    " clase: document.getElementById('conexion').className,"
    " oculta: document.getElementById('conexion').hidden,"
    " recargar_deshabilitado: document.getElementById('recargar').disabled})"
)


async def leer_barra(pagina) -> dict:
    return await pagina.evaluate(JS_BARRA)


def test_barra_de_conexion_colorea_el_ping_y_muestra_la_pausa(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            pagina = await nav.popup()
            await esperar(pagina, BARRA_LISTA)
            medida_real = await leer_barra(pagina)
            barras = {}
            # Se simula la medición en el almacenamiento: el popup se repinta al cambiar
            for ms in (42, 149, 150, 499, 500, 650):
                await nav.guardar({"ping": {"ms": ms, "ok": True, "en": 1}})
                await esperar(pagina, f"document.getElementById('ping').textContent === '{ms} ms'")
                barras[ms] = await leer_barra(pagina)
            await nav.guardar({"ping": {"ms": None, "ok": False, "en": 1}})
            await pagina.wait_for_timeout(200)
            barras["sin_respuesta"] = await leer_barra(pagina)
            await nav.guardar({"ping": {"ms": 80, "ok": True, "en": 1}, "pausado": True})
            await pagina.wait_for_timeout(200)
            barras["pausa"] = await leer_barra(pagina)
            return medida_real, barras
        finally:
            await cerrar(nav)

    medida_real, barras = correr(flujo())
    assert medida_real["texto"] == "Conectado" and medida_real["ping"].endswith(" ms")
    assert barras[42]["texto"] == "Conectado" and barras[42]["ping"] == "42 ms"
    colores = {ms: barras[ms]["clase_ping"].split()[-1] for ms in (42, 149, 150, 499, 500, 650)}
    assert colores == {42: "rapido", 149: "rapido", 150: "medio", 499: "medio",
                       500: "lento", 650: "lento"}  # fmt: skip
    assert barras["sin_respuesta"]["texto"] == "Sin respuesta"
    assert barras["sin_respuesta"]["ping"] == "" and "caido" in barras["sin_respuesta"]["clase"]
    assert barras["pausa"]["texto"] == "En pausa" and barras["pausa"]["ping"] == "80 ms"


def test_barra_midiendo_mientras_llega_la_primera_medicion(tmp_path, api):
    api.demora_ping = 1.5

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            pagina = await nav.popup()
            await pagina.wait_for_selector("#conexion:not([hidden])")
            antes = await leer_barra(pagina)
            await esperar(pagina, BARRA_LISTA, 6)
            return antes, await leer_barra(pagina)
        finally:
            await cerrar(nav)

    antes, despues = correr(flujo())
    assert antes["texto"] == "Midiendo…" and antes["ping"] == ""
    assert despues["texto"] == "Conectado"
    assert int(despues["ping"].removesuffix(" ms")) >= 1500


def test_sin_vincular_no_hay_barra_ni_pausa(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos(), vinculado=False)
        try:
            pagina = await nav.popup()
            await pagina.wait_for_selector("#sin-vincular:not([hidden])")
            return (await leer_barra(pagina), await pagina.is_hidden("#pausar"),
                    await pagina.inner_text("h1"))  # fmt: skip
        finally:
            await cerrar(nav)

    barra, pausa_oculta, titulo = correr(flujo())
    assert barra["oculta"] and pausa_oculta and titulo == "APOLO TI"
    assert not api.de("ping")  # sin vincular no se mide nada


def test_engranaje_de_la_cabecera_abre_las_opciones(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            pagina = await nav.popup()
            async with nav.contexto.expect_page() as nueva:
                await pagina.click("#opciones")
            opciones = await nueva.value
            await opciones.wait_for_load_state()
            return opciones.url
        finally:
            await cerrar(nav)

    assert correr(flujo()).endswith("/opciones.html")


def test_recargar_tras_una_caida_reconecta_y_manda_un_latido(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            await nav.guardar({"servidor": servidor_apagado()})
            pagina = await nav.popup()
            await esperar(pagina, BARRA_LISTA)
            caida = await leer_barra(pagina)
            # El servidor vuelve: el usuario toca recargar (dos veces seguidas)
            await nav.guardar({"servidor": api.url})
            latidos_antes = len(api.de("latido"))
            # La barra se lee en el mismo evaluate que los toques: si no, la recarga podría
            # avanzar entre una llamada y otra
            durante = await pagina.evaluate(
                "window.latidosPedidos = 0;"
                "const enviar = chrome.runtime.sendMessage.bind(chrome.runtime);"
                "chrome.runtime.sendMessage = (m, ...r) => {"
                "  if (m.tipo === 'latido') window.latidosPedidos++; return enviar(m, ...r); };"
                "document.getElementById('recargar').click();"
                "document.getElementById('recargar').click();" + JS_BARRA
            )
            await esperar(pagina, RECARGA_TERMINADA, 30)
            final = await leer_barra(pagina)
            pedidos = await pagina.evaluate("window.latidosPedidos")
            return caida, durante, final, pedidos, len(api.de("latido")) - latidos_antes
        finally:
            await cerrar(nav)

    caida, durante, final, pedidos, latidos = correr(flujo())
    assert caida["texto"] == "Sin respuesta"
    assert durante["texto"] == "Reconectando…" and durante["recargar_deshabilitado"]
    assert "reconectando" in durante["clase"]
    assert final["texto"] == "Conectado" and final["ping"].endswith(" ms")
    assert pedidos == 1 and latidos == 1  # el segundo toque no lanzó otra recarga
    assert api.de("latido")[-1]["portales"]["computrabajo"]["estado"] == "listo"


def test_recargar_sin_servidor_deja_el_boton_disponible(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            await nav.guardar({"servidor": servidor_apagado()})
            pagina = await nav.popup()
            await esperar(pagina, BARRA_LISTA)
            latidos_antes = len(api.de("latido"))
            await pagina.click("#recargar")
            await esperar(pagina, RECARGA_TERMINADA, 15)
            return await leer_barra(pagina), len(api.de("latido")) - latidos_antes
        finally:
            await cerrar(nav)

    barra, latidos = correr(flujo())
    assert barra["texto"] == "Sin respuesta" and not barra["recargar_deshabilitado"]
    assert latidos == 0


def test_el_popup_ya_no_tiene_boton_revisar():
    html = (EXTENSION / "popup.html").read_text(encoding="utf-8")
    assert 'id="revisar"' not in html and 'id="recargar"' in html
    assert 'aria-label="Recargar la conexión"' in html


# --- popup: etiquetas de las tarjetas de portal -------------------------------------------


async def tarjetas(pagina) -> dict[str, dict]:
    return await pagina.evaluate(
        "Object.fromEntries([...document.querySelectorAll('#portales .tarjeta')].map(t => ["
        "  t.classList[1], {pill: t.querySelector('.pill')?.textContent ?? null,"
        "  sub: t.querySelector('.sub').textContent, engranaje: !!t.querySelector('.abrir'),"
        "  apagada: t.classList.contains('apagada')}]))"
    )


def test_etiquetas_de_las_tarjetas(tmp_path, api):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos())
        try:
            await nav.latido()
            # Computrabajo lista y confirmada, Magneto sin sesión, elempleo habilitado pero sin
            # el permiso del navegador, y el resto sin habilitar en el servidor
            await nav.guardar({
                "estado": {"en_linea": True, "cuentas": {"computrabajo": True}},
                "portales": {"computrabajo": {"estado": "listo", "correo": "ana.perez@gmail.com"},
                             "magneto": {"estado": "sin_sesion"}},
                "selectores_version": {"computrabajo": "1", "magneto": "1", "elempleo": "1"},
            })  # fmt: skip
            pagina = await nav.popup()
            await pagina.wait_for_timeout(400)
            primero = await tarjetas(pagina)
            # Avance de la cuenta: correo aún sin encontrar e inicio de sesión en curso
            await nav.guardar({
                "portales": {"computrabajo": {"estado": "listo"},
                             "magneto": {"estado": "sin_sesion"}},
                "vigilando": {"magneto": int(time.time() * 1000)},
                "selectores_version": {"computrabajo": "1", "magneto": "1"},
            })  # fmt: skip
            await pagina.wait_for_timeout(400)
            segundo = await tarjetas(pagina)
            await nav.guardar({
                "portales": {"computrabajo": {"estado": "incompleto", "correo": "ana@x.co"}},
            })  # fmt: skip
            await pagina.wait_for_timeout(400)
            return primero, segundo, await tarjetas(pagina)
        finally:
            await cerrar(nav)

    primero, segundo, tercero = correr(flujo())
    assert primero["computrabajo"]["pill"] == "Listo ✓"
    assert primero["computrabajo"]["sub"] == "ana.perez@gmail.com"
    assert primero["computrabajo"]["engranaje"]
    assert primero["magneto"]["pill"] == "Sin sesión"
    assert "Iniciar sesión" in primero["magneto"]["sub"]
    assert primero["elempleo"]["pill"] == "Sin activar" and "Activar" in primero["elempleo"]["sub"]
    for p in ("getonboard", "linkedin", "spe"):
        assert primero[p]["pill"] == "Próximamente" and primero[p]["apagada"]
        assert not primero[p]["engranaje"]
    assert segundo["computrabajo"]["pill"] == "Buscando correo"
    assert segundo["magneto"]["pill"] == "Iniciando sesión…"
    assert segundo["elempleo"]["pill"] == "Próximamente"  # ya no está habilitado
    assert tercero["computrabajo"]["pill"] == "Perfil incompleto"


# --- elempleo (conectar-plataformas-extension, grupo 4) --------------------------------------
# Las páginas imitan el marcado y el comportamiento reales del portal (reconocimiento del
# 2026-10-15, docs/asistente/portales.md): la variante normal postula con un solo clic, la
# rápida abre un modal con el CV, las ofertas VIP piden una nota y algunas un video opcional.

VACANTE_EE = "https://www.elempleo.com/co/ofertas-trabajo/auxiliar-de-pruebas-1886700000"
GUARDAR_EE = "https://www.elempleo.com/co/JobOffers/JobOfferDetail/Save?jobOfferId=PRUEBA"
GUARDAR_RAPIDA_EE = (
    "https://www.elempleo.com/co/JobOffers/JobOfferDetail/SaveQuickApplication?jobOfferId=PRUEBA"
)
INICIO_EE = "https://www.elempleo.com/co/"
CUENTA_EE = "https://www.elempleo.com/co/hoja-de-vida/mi-cuenta"
PASO_DESCONOCIDO_EE = "https://www.elempleo.com/co/postulacion/paso-desconocido"
BOTON_NORMAL = 'js-apply-offer" data-ga4-typebutton="Boton 1"'
RAPIDA = {
    'data-is-quick-offer-application="False"': 'data-is-quick-offer-application="True"',
    BOTON_NORMAL: 'js-apply-modal-quick-offer" data-ga4-typebutton="Boton 1"',
}
VIP = {
    'data-is-vip="False"': 'data-is-vip="True"',
    BOTON_NORMAL: 'js-apply-offer-vip" data-ga4-typebutton="Boton 1"',
}
VIP_RAPIDA = {**RAPIDA, **VIP}
VIDEO = {'data-vprez-url=""': 'data-vprez-url="https://v-prez.com/jobboard/cuestionario"'}
NOTA = "Me motiva aprender y aportar con orden y puntualidad."


def portales_elempleo(
    reemplazos=None, *, fixture="ee_vacante.html", respuesta="ee_respuesta_ok.json"
) -> Portales:
    p = portales_listos()
    p.poner(INICIO_EE, "ee_inicio.html")
    p.poner(CUENTA_EE, "ee_cuenta.html")
    p.poner(VACANTE_EE, fixture, reemplazos)
    p.al_enviar(GUARDAR_EE, respuesta)
    p.al_enviar(GUARDAR_RAPIDA_EE, respuesta)
    return p


def trabajo_ee(autorizado=False):
    return {"id": 21, "tipo": "postular", "plataforma": "elempleo", "url": VACANTE_EE,
            "titulo": "Auxiliar de pruebas", "actualizar_cv_portal": autorizado}  # fmt: skip


def confirmar_rapido(plataforma, sel):
    """Acorta la espera de la confirmación en los casos que terminan sin ella."""
    sel = json.loads(json.dumps(sel))
    for paso in sel["postular"]:
        if paso["accion"] == "confirmar":
            paso["ms"] = 3000
    return sel


async def latido_elempleo(tmp_path, api, portales) -> None:
    nav = await abrir(tmp_path, api.url, portales, permisos=("elempleo.com",))
    try:
        await nav.latido()
    finally:
        await cerrar(nav)


def postular_elempleo(tmp_path, api, portales, *, autorizado=False) -> Portales:
    api.trabajos = [trabajo_ee(autorizado)]
    correr(latido_elempleo(tmp_path, api, portales))
    return portales


def recibidos(portales: Portales) -> list[str]:
    return [r.decode("latin-1") for r in portales.recibido]


def test_elempleo_latido_lee_el_correo_en_mi_cuenta(tmp_path, api):
    correr(latido_elempleo(tmp_path, api, portales_elempleo()))
    ee = api.de("latido")[-1]["portales"]["elempleo"]
    assert ee["estado"] == "listo"
    # El correo del pie (@elempleo.com) es del portal: se toma el de "Mi cuenta"
    assert ee["correo"] == "ana.perez@example.com"
    assert ee["pagina_correo"] == "/co/hoja-de-vida/mi-cuenta"


def test_elempleo_sin_sesion_en_el_latido(tmp_path, api):
    portales = portales_elempleo()
    portales.poner(INICIO_EE, "ee_sin_sesion.html")
    correr(latido_elempleo(tmp_path, api, portales))
    ee = api.de("latido")[-1]["portales"]["elempleo"]
    assert (ee["estado"], ee["correo"]) == ("sin_sesion", None)


def test_elempleo_sin_correo_legible_no_postula(tmp_path, api):
    portales = portales_elempleo()
    portales.poner(CUENTA_EE, "ee_inicio.html")  # "Mi cuenta" sin el correo
    postular_elempleo(tmp_path, api, portales)
    assert api.de("latido")[-1]["portales"]["elempleo"]["correo"] is None
    assert not api.de("tomar") and not portales.recibido


def test_elempleo_postulacion_normal_llega_a_enviada(tmp_path, api):
    portales = postular_elempleo(tmp_path, api, portales_elempleo())
    assert api.de("resultado")[0]["estado"] == "enviada"
    acciones = [r for r, _ in api.llamadas if r in ("tomar", "envio", "formulario", "resultado")]
    assert acciones == ["tomar", "envio", "resultado"]  # sin formulario
    assert recibidos(portales) == ["ApplicationNote=undefined"]
    pasos = [p["paso"] for p in api.de("paso")]
    assert pasos[:3] == ["abrir", "revisar_vacante", "aplicar"]
    assert "revisar_postulacion" in pasos and "cv_subir" not in pasos


def test_elempleo_rapida_sin_autorizacion_envia_el_documento_elegido(tmp_path, api):
    portales = postular_elempleo(tmp_path, api, portales_elempleo(RAPIDA))
    assert api.de("resultado")[0]["estado"] == "enviada"
    enviado = recibidos(portales)[0]
    assert 'name="Attachments.SelectedIds"\r\n\r\n1002' in enviado
    assert "CV_Ana_Perez.pdf" not in enviado
    pasos = [p["paso"] for p in api.de("paso")]
    assert "cv_sin_autorizacion" in pasos and "enviar" in pasos


def test_elempleo_rapida_con_autorizacion_sube_el_cv_antes_de_enviar(tmp_path, api):
    portales = postular_elempleo(tmp_path, api, portales_elempleo(RAPIDA), autorizado=True)
    assert api.de("resultado")[0]["estado"] == "enviada"
    assert 'filename="CV_Ana_Perez.pdf"' in recibidos(portales)[0]
    pasos = [p["paso"] for p in api.de("paso")]
    assert "cv_subir" in pasos and "cv_verificar_fallo" not in pasos


@pytest.mark.parametrize("variante", [{}, RAPIDA], ids=["normal", "rapida"])
def test_elempleo_el_video_opcional_se_omite(tmp_path, api, variante):
    portales = postular_elempleo(tmp_path, api, portales_elempleo({**variante, **VIDEO}))
    assert api.de("resultado")[0]["estado"] == "enviada"
    avisos = recibidos(portales)
    assert "video:omitido" in avisos
    assert "video:grabar" not in avisos  # su imagen y su voz, nunca sin respuesta expresa


@pytest.mark.parametrize("variante", [VIP, VIP_RAPIDA], ids=["normal", "rapida"])
def test_elempleo_nota_vip_se_llena_antes_de_enviar(tmp_path, api, variante):
    api.respuestas = lambda campos: [
        {"indice": i, "valor": NOTA, "opcion": None}
        for i, c in enumerate(campos)
        if c["nombre"] == "ApplicationNote"
    ]
    portales = postular_elempleo(tmp_path, api, portales_elempleo(variante))
    campos = api.de("formulario")[0]["campos"]
    assert [(c["nombre"], c["tipo"]) for c in campos] == [("ApplicationNote", "texto")]
    assert "candidato ideal" in campos[0]["texto"]
    assert api.de("resultado")[0]["estado"] == "enviada"
    enviado = recibidos(portales)[0]
    assert "Me motiva aprender" in enviado or "Me+motiva+aprender" in enviado


def test_elempleo_nota_sin_respuesta_espera_al_usuario_sin_enviar(tmp_path, api):
    api.esperar = True  # la IA no la redactó: el servidor la pregunta por la card
    portales = postular_elempleo(tmp_path, api, portales_elempleo(VIP))
    assert api.de("formulario")
    assert "esperando_usuario" in [p["paso"] for p in api.de("paso")]
    assert not api.de("resultado")
    assert not portales.recibido


def test_elempleo_ya_postulada(tmp_path, api):
    portales = postular_elempleo(tmp_path, api, portales_elempleo(fixture="ee_postulado.html"))
    assert api.de("resultado")[0]["estado"] == "ya_postulada"
    assert not api.de("envio") and not portales.recibido


def test_elempleo_vacante_cerrada(tmp_path, api):
    postular_elempleo(tmp_path, api, portales_elempleo(fixture="ee_cerrada.html"))
    assert api.de("resultado")[0]["estado"] == "vacante_cerrada"
    assert not api.de("envio")


def test_elempleo_sin_sesion_queda_esperando_sesion(tmp_path, api):
    postular_elempleo(tmp_path, api, portales_elempleo(fixture="ee_sin_sesion.html"))
    assert api.de("resultado")[0]["estado"] == "esperando_sesion"


def test_elempleo_hoja_de_vida_incompleta_bloquea(tmp_path, api):
    postular_elempleo(tmp_path, api, portales_elempleo(respuesta="ee_respuesta_incompleta.json"))
    resultado = api.de("resultado")[0]
    assert (resultado["estado"], resultado["motivo"]) == ("bloqueada", "portal_perfil_incompleto")


def test_elempleo_sin_boton_de_postular_es_formulario_desconocido(tmp_path, api):
    portales = postular_elempleo(tmp_path, api, portales_elempleo({BOTON_NORMAL: 'otra-clase"'}))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "clic" in resultado["motivo"]
    assert "js-offer-apply-container" in resultado["html"]
    assert not portales.recibido


def test_elempleo_nota_que_no_se_puede_enviar_no_filtra_lo_escrito(tmp_path, api):
    """El portal cambió el botón de la nota: no se envía y el HTML del reporte no trae la nota."""
    api.respuestas = lambda campos: [{"indice": 0, "valor": NOTA, "opcion": None}]
    api.ajustar = confirmar_rapido
    reemplazos = {**VIP, "js-apply-with-note": "js-enviar-nota-nuevo"}
    portales = postular_elempleo(tmp_path, api, portales_elempleo(reemplazos))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "ApplicationNote" in resultado["html"]
    assert "Me motiva" not in resultado["html"]
    assert not portales.recibido


def test_elempleo_paso_obligatorio_desconocido_no_se_da_por_enviado(tmp_path, api):
    api.ajustar = confirmar_rapido
    portales = portales_elempleo(respuesta="ee_respuesta_redirige.json")
    portales.poner(PASO_DESCONOCIDO_EE, "ee_paso_desconocido.html")
    postular_elempleo(tmp_path, api, portales)
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "preguntasEmpleador" in resultado["html"]


# --- elempleo: cuestionario adicional (piloto del 2026-10-17) -------------------------------
# Algunas ofertas responden al envío con 1 o 5 y llevan a una página con preguntas abiertas
# obligatorias; ee_cuestionario.html es la evidencia de la postulación 39 del piloto.

CUESTIONARIO_EE = "https://www.elempleo.com/co/JobOffers/Questionnaires/Index?jobOfferId=PRUEBA"
FIN_CUESTIONARIO_EE = "https://www.elempleo.com/co/JobOffers/Questionnaires/EndQuestionnaire"
RESPUESTAS_CUESTIONARIO = {
    "[0].OpenAnswer": "Sí, me interesa.",
    "[1].OpenAnswer": "Sí, dos años en empresas del sector corporativo.",
    "[2].OpenAnswer": "Sí, cinco años en soporte de aplicaciones.",
}


def portales_cuestionario(variante=None, *, fin="ee_cuestionario_ok.json") -> Portales:
    p = portales_elempleo(variante, respuesta="ee_respuesta_cuestionario.json")
    p.poner(CUESTIONARIO_EE, "ee_cuestionario.html")
    p.al_enviar(FIN_CUESTIONARIO_EE, fin)
    return p


def respuestas_cuestionario(campos: list[dict]) -> list[dict]:
    return [
        {"indice": i, "valor": RESPUESTAS_CUESTIONARIO[c["nombre"]], "opcion": None}
        for i, c in enumerate(campos)
        if c["nombre"] in RESPUESTAS_CUESTIONARIO
    ]


def cuestionario_recibido(portales: Portales) -> dict[str, list[str]] | None:
    """Respuestas que recibió el portal en EndQuestionnaire, o None si no se envió."""
    if FIN_CUESTIONARIO_EE not in portales.pedidas:
        return None
    return parse_qs(recibidos(portales)[-1])


@pytest.mark.parametrize("variante", [{}, RAPIDA], ids=["normal", "rapida"])
def test_elempleo_cuestionario_adicional_se_responde_y_llega_a_enviada(tmp_path, api, variante):
    api.respuestas = respuestas_cuestionario
    portales = postular_elempleo(tmp_path, api, portales_cuestionario(variante))
    campos = api.de("formulario")[0]["campos"]
    assert [(c["nombre"], c["tipo"], c["obligatoria"]) for c in campos] == [
        (f"[{i}].OpenAnswer", "texto", True) for i in range(3)
    ]
    assert campos[0]["texto"].startswith("1. El salario es $3.000.000 + comisiones")
    assert campos[2]["texto"] == "3. ¿Cuentas con experiencia en el sector de tecnología?"
    assert api.de("resultado")[0]["estado"] == "enviada"
    enviado = cuestionario_recibido(portales)
    assert enviado is not None
    for nombre, valor in RESPUESTAS_CUESTIONARIO.items():
        assert enviado[nombre] == [valor]
    assert enviado["[0].QuestionId"] == ["9001"]
    pasos = [p["paso"] for p in api.de("paso")]
    assert "llenado" in pasos
    if variante:
        assert "cuestionario_tras_enviar" in pasos  # sale después del modal del CV
    else:
        assert "revisar_cuestionario" in pasos and "cv_subir" not in pasos


def test_elempleo_cuestionario_sin_respuesta_espera_al_usuario_sin_enviar(tmp_path, api):
    api.esperar = True  # al banco le falta una respuesta: el servidor la pregunta por la card
    portales = postular_elempleo(tmp_path, api, portales_cuestionario())
    assert len(api.de("formulario")[0]["campos"]) == 3
    assert "esperando_usuario" in [p["paso"] for p in api.de("paso")]
    assert not api.de("resultado")
    assert cuestionario_recibido(portales) is None
    assert recibidos(portales) == ["ApplicationNote=undefined"]  # solo el envío de la oferta


def test_elempleo_cuestionario_con_respuestas_vacias_no_se_da_por_enviado(tmp_path, api):
    """El portal marca una pregunta sin responder: no se envía y el reporte no trae lo escrito."""
    api.respuestas = lambda campos: respuestas_cuestionario(campos)[:2]
    portales = postular_elempleo(tmp_path, api, portales_cuestionario())
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido"
    assert "campos sin responder" in resultado["motivo"]
    assert "js-questionnaire-form" in resultado["html"]
    assert "me interesa" not in resultado["html"]
    assert cuestionario_recibido(portales) is None


def test_elempleo_cuestionario_guardado_hacia_el_empleador_queda_incierta(tmp_path, api):
    api.respuestas = respuestas_cuestionario
    portales = portales_cuestionario(fin="ee_cuestionario_ats.json")
    postular_elempleo(tmp_path, api, portales)
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "incierta"
    assert "empleador" in resultado["motivo"]
    assert cuestionario_recibido(portales) is not None


# --- postular-linkedin 5.3: LinkedIn y las páginas de las empresas ----------------------------
# Las páginas de LinkedIn son los recortes de tests/fixtures/linkedin/ (5.1) y las de las empresas,
# las copias de tests/fixtures/formularios/. La API de prueba responde POST /destino con lo que
# fija cada prueba y las pantallas con las decisiones fijas de ServidorFalso.

FIXTURES_LINKEDIN = Path(__file__).parent.parent / "fixtures" / "linkedin"
VACANTE_LI = "https://www.linkedin.com/jobs/view/4100100/"
GH_LI = "https://job-boards.greenhouse.io/prueba/jobs/101"
GH_ENVIO = "https://job-boards.greenhouse.io/prueba/jobs/101/enviar"
EMPRESA_LI = "https://empresa-prueba.com/trabajo/101"
FAMILIAS_HOSTS = ["ashbyhq.com", "greenhouse.io", "grnh.se", "lever.co", "myworkdayjobs.com"]


def recorte_linkedin(nombre: str) -> str:
    return (FIXTURES_LINKEDIN / nombre).read_text(encoding="utf-8")


def sitio_linkedin(pagina: str = "vacante_externa.html", url: str = VACANTE_LI):
    """Sitio falso con la vacante de LinkedIn y la copia de Greenhouse; guarda lo que se pide."""
    from tests.asistente.test_motor_generico import Sitio, sitio_de

    class SitioLinkedin(Sitio):
        def __init__(self) -> None:
            super().__init__()
            self.pedidas: list[str] = []
            self.cuerpos: dict[str, list[str]] = {}

        async def atender(self, route) -> None:
            peticion = route.request
            self.pedidas.append(peticion.url)
            if peticion.method == "POST" and "linkedin.com" in peticion.url:
                url = peticion.url.split("?")[0]
                self.posts.append(url)
                self.cuerpos.setdefault(url, []).append(peticion.post_data or "")
                await route.fulfill(status=200, body="{}", content_type="application/json")
                return
            await super().atender(route)

    sitio = SitioLinkedin()
    gh = sitio_de("greenhouse")
    sitio.paginas.update(gh.paginas)
    sitio.envios.update(gh.envios)
    sitio.paginas[url] = recorte_linkedin(pagina)
    return sitio


def trabajo_li(pid: int = 60, url: str = VACANTE_LI, **extra) -> dict:
    return {"id": pid, "tipo": "postular", "plataforma": "linkedin", "url": url,
            "titulo": "Practicante de soporte", "actualizar_cv_portal": False,
            "motor_generico": {"respaldo_declarado": False, "max_pantallas": 12,
                               "max_pantallas_una_pregunta": 40, "max_minutos": 10},
            **extra}  # fmt: skip


def abrir_destino(url: str = GH_LI, familia: str | None = "greenhouse") -> dict:
    return {"accion": "abrir", "url": url, "familia": familia, "receta": None,
            "familia_datos": FAMILIAS_ATS["familias"].get(familia) if familia else None,
            "familias_hosts": FAMILIAS_HOSTS}  # fmt: skip


def decision_fija(api):
    """Las decisiones de ServidorFalso con el botón que sugieren las reglas (como el bucle)."""
    from tests.asistente.test_bucle_generico import decide_con
    from tests.asistente.test_motor_generico import ServidorFalso

    api.pantalla = decide_con(ServidorFalso())


def ejecutar_li(tmp_path, api, sitio, pedido: dict, *, externa: bool = True) -> None:
    async def flujo():
        nav = await abrir(tmp_path, api.url, Portales(), externa=externa,
                          permisos=("linkedin.com",))  # fmt: skip
        try:
            await nav.contexto.route("https://**/*", sitio.atender)
            await nav.guardar({"pruebas": {"resultado_ms": 1500}})
            await asyncio.wait_for(nav.evaluar(f"asistente.ejecutar({json.dumps(pedido)})"), 240)
        finally:
            await cerrar(nav)

    correr(flujo())


def resultado_li(api) -> dict:
    resultados = api.de("resultado")
    assert len(resultados) == 1, [resultados, [p["paso"] for p in api.de("paso")]]
    return resultados[0]


def test_externa_lee_el_destino_del_enlace_y_llega_a_la_pagina_de_gracias(tmp_path, api):
    decision_fija(api)
    api.destino = lambda cuerpo: abrir_destino()
    sitio = sitio_linkedin()
    ejecutar_li(tmp_path, api, sitio, trabajo_li())
    # El destino sale del enlace «Solicitar en el sitio web de la empresa», no del aviso de
    # privacidad, y nunca se pulsa «Solicitar» (no se pide /safety/go)
    [destino] = api.de("destino")
    assert destino == {
        "id": 60,
        "tipo": "externa",
        "url": "https://job-boards.greenhouse.io/prueba/jobs/4100100?utm_source=linkedin",
    }
    assert not [u for u in sitio.pedidas if "/safety/go" in u]
    assert resultado_li(api)["estado"] == "enviada"
    assert sitio.contados(GH_ENVIO) == 1 and len(api.de("envio")) == 1
    # La misma pestaña pasó de LinkedIn a la página de la empresa: las pantallas son de Greenhouse
    assert all("greenhouse.io" in p["url"] for p in api.de("pantalla"))
    assert "linkedin_tipo" in [p["paso"] for p in api.de("paso")]


def test_un_destino_guardado_se_abre_sin_pasar_por_linkedin(tmp_path, api):
    decision_fija(api)
    sitio = sitio_linkedin()
    destino = {"url": GH_LI, "familia": "greenhouse", "familias_hosts": FAMILIAS_HOSTS}
    ejecutar_li(tmp_path, api, sitio, trabajo_li(destino=destino))
    assert resultado_li(api)["estado"] == "enviada"
    assert not api.de("destino")
    assert not [u for u in sitio.pedidas if "linkedin.com" in u]
    # Los datos de la familia se piden aparte (GET /familias_ats) cuando el trabajo no los trae
    assert api.de("familias_ats")


PAGINA_SALTO = """<!doctype html><html lang="en"><body><main><h1>Support intern</h1>
<p>Join our team in Medellín.</p><a href="{destino}">Apply now</a></main></body></html>"""


@pytest.mark.parametrize(("ir_a", "motivo"), [
    ("https://otro-dominio.org/formulario", "salto_de_dominio"),
    ("https://accounts.google.com/o/oauth2/auth?client_id=prueba", "oauth"),
], ids=["salto_de_dominio", "oauth"])  # fmt: skip
def test_la_pagina_externa_se_detiene_si_lleva_a_otro_sitio(tmp_path, api, ir_a, motivo):
    decision_fija(api)
    api.destino = lambda cuerpo: abrir_destino(EMPRESA_LI, familia=None)
    sitio = sitio_linkedin()
    sitio.paginas[EMPRESA_LI] = PAGINA_SALTO.format(destino=ir_a)
    sitio.paginas[ir_a] = "<!doctype html><html><body><form><input name=x></form></body></html>"
    ejecutar_li(tmp_path, api, sitio, trabajo_li())
    resultado = resultado_li(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert resultado["motivo"] == motivo
    assert not api.de("envio")
    # Nada se leyó ni se llenó en el otro sitio
    assert all(p["url"].startswith(EMPRESA_LI) for p in api.de("pantalla"))


def test_un_destino_que_ya_es_de_otro_sitio_no_se_abre(tmp_path, api):
    api.destino = lambda cuerpo: abrir_destino("https://login.empresa-prueba.com/login", None)
    sitio = sitio_linkedin()
    ejecutar_li(tmp_path, api, sitio, trabajo_li())
    resultado = resultado_li(api)
    assert (resultado["estado"], resultado["motivo"]) == (
        "formulario_desconocido",
        "pagina_prohibida",
    )
    assert not [u for u in sitio.pedidas if "empresa-prueba.com" in u]


def test_respaldo_del_servidor_no_abre_el_destino(tmp_path, api):
    api.destino = lambda cuerpo: {"accion": "respaldo", "motivo": "destino_mensajeria",
                                  "url": "https://wa.me/570000000"}  # fmt: skip
    sitio = sitio_linkedin()
    ejecutar_li(tmp_path, api, sitio, trabajo_li())
    resultado = resultado_li(api)
    assert (resultado["estado"], resultado["motivo"]) == (
        "formulario_desconocido",
        "destino_mensajeria",
    )
    assert not [u for u in sitio.pedidas if "wa.me" in u]


@pytest.mark.parametrize(("recorte", "motivo"), [
    ("vacante_cerrada.html", "cerrada"), ("vacante_pausada.html", "pausada"),
], ids=["cerrada", "pausada"])  # fmt: skip
def test_vacante_cerrada_o_pausada_no_toca_nada(tmp_path, api, recorte, motivo):
    sitio = sitio_linkedin(recorte)
    ejecutar_li(tmp_path, api, sitio, trabajo_li())
    resultado = resultado_li(api)
    assert (resultado["estado"], resultado["motivo"]) == ("vacante_cerrada", motivo)
    assert not api.de("destino")


def test_aviso_de_seguridad_bloquea_con_su_motivo(tmp_path, api):
    sitio = sitio_linkedin()
    sitio.paginas[VACANTE_LI] = (
        "<!doctype html><html lang=es><body><main><h1>Verificación de "
        "seguridad</h1><p>Confirma que eres tú.</p></main></body></html>"
    )
    ejecutar_li(tmp_path, api, sitio, trabajo_li())
    resultado = resultado_li(api)
    assert (resultado["estado"], resultado["motivo"]) == ("bloqueada", "aviso_seguridad")


def test_el_muro_de_ingreso_es_falta_de_sesion_y_no_aviso_de_seguridad(tmp_path, api):
    """/authwall también dice «Verificación de seguridad» (visto el 2026-10-27)."""
    muro = "https://www.linkedin.com/authwall?trk=prueba"
    sitio = sitio_linkedin()
    sitio.paginas[muro] = (
        "<!doctype html><html lang=es><body><dialog open><h2>Verificación de "
        "seguridad</h2></dialog></body></html>"
    )
    ejecutar_li(tmp_path, api, sitio, trabajo_li(url=muro))
    assert resultado_li(api)["estado"] == "esperando_sesion"


VACANTE_SENCILLA = "https://www.linkedin.com/jobs/view/4200200/"


def test_sencilla_llega_a_la_confirmacion_con_seguir_a_la_empresa_desmarcado(tmp_path, api):
    decision_fija(api)
    api.destino = lambda cuerpo: {"accion": "sencilla"}
    sitio = sitio_linkedin("sencilla_simulada.html", VACANTE_SENCILLA)
    ejecutar_li(tmp_path, api, sitio, trabajo_li(url=VACANTE_SENCILLA), externa=False)
    assert api.de("destino") == [{"id": 60, "tipo": "sencilla"}]
    assert resultado_li(api)["estado"] == "enviada", [p["paso"] for p in api.de("paso")]
    [enviado] = sitio.cuerpos["https://www.linkedin.com/recibir-solicitud"]
    datos = json.loads(enviado)
    assert datos["seguir"] is False  # «Sigue a …» venía marcada
    assert datos["cv"] == "cv-1"  # el primer CV guardado
    assert datos["correo"] == "1" and "3001234567" in datos["telefono"]
    assert len(api.de("envio")) == 1
    # Las pantallas son las del modal: la casilla y el grupo de CV no van al servidor
    textos = [c["texto"] for p in api.de("pantalla") for c in p["campos"]]
    assert not [t for t in textos if t.startswith("Sigue a") or "CV_Ana" in t]
    assert not [u for u in sitio.posts if u.endswith(("/guardar", "/descartar"))]
    assert "seguir_empresa" in [p["paso"] for p in api.de("paso")]


def test_sencilla_sin_cv_guardado_ni_autorizacion_va_al_respaldo_y_descarta(tmp_path, api):
    decision_fija(api)
    api.destino = lambda cuerpo: {"accion": "sencilla"}
    url = VACANTE_SENCILLA + "?sin_cv=1"
    sitio = sitio_linkedin("sencilla_simulada.html", url)
    ejecutar_li(tmp_path, api, sitio, trabajo_li(url=url), externa=False)
    resultado = resultado_li(api)
    assert (resultado["estado"], resultado["motivo"]) == (
        "formulario_desconocido",
        "linkedin_sin_cv",
    )
    assert not api.de("envio") and "https://www.linkedin.com/recibir-solicitud" not in sitio.posts
    # Se cerró con la X y «Descartar», nunca «Guardar»
    assert "https://www.linkedin.com/descartar" in sitio.posts
    assert "https://www.linkedin.com/guardar" not in sitio.posts


def test_sencilla_apagada_por_el_usuario_no_abre_el_modal(tmp_path, api):
    api.destino = lambda cuerpo: {"accion": "respaldo", "motivo": "linkedin_apagado"}
    sitio = sitio_linkedin("sencilla_simulada.html", VACANTE_SENCILLA)
    ejecutar_li(tmp_path, api, sitio, trabajo_li(url=VACANTE_SENCILLA), externa=False)
    resultado = resultado_li(api)
    assert (resultado["estado"], resultado["motivo"]) == (
        "formulario_desconocido",
        "linkedin_apagado",
    )
    assert not api.de("pantalla")


def test_regla_de_salto_y_paginas_prohibidas_de_la_plataforma_externa(tmp_path, api):
    casos = {
        "https://empresa-prueba.com/trabajo/101": None,
        "https://careers.empresa-prueba.com/apply": None,  # mismo dominio registrable
        "https://empresa.com.co/a": "salto_de_dominio",
        "https://boards.greenhouse.io/empresa/jobs/1": None,  # familia de ATS conocida
        "https://otro-dominio.org/formulario": "salto_de_dominio",
        "https://accounts.google.com/o/oauth2/auth": "oauth",
        "https://www.linkedin.com/oauth/v2/authorization": "oauth",
        "https://empresa-prueba.com/login": "pagina_prohibida",
        "https://empresa-prueba.com/users/sign_up": "pagina_prohibida",
        "https://empresa-prueba.com/checkout/pago": "pagina_prohibida",
        "https://www.paypal.com/x": "pagina_prohibida",
        "http://empresa-prueba.com/trabajo/101": "pagina_prohibida",
    }
    ambito = {"destino": EMPRESA_LI, "familias_hosts": FAMILIAS_HOSTS,
              "hosts_prohibidos": json.loads((SELECTORES / "linkedin.json").read_text(
                  encoding="utf-8"))["hosts_prohibidos"]}  # fmt: skip

    async def flujo():
        nav = await abrir(tmp_path, api.url, Portales())
        try:
            # El service worker no admite import(): se evalúa en una página de la extensión
            pagina = await nav.popup()
            return await pagina.evaluate(
                f"import('./portales.js').then(m => Object.fromEntries({json.dumps(list(casos))}"
                f".map(u => [u, m.motivoExterno(u, {json.dumps(ambito)})])))"
            )
        finally:
            await cerrar(nav)

    assert correr(flujo()) == casos


def test_latido_reporta_la_plataforma_externa_solo_con_el_permiso(tmp_path, api):
    async def flujo(externa):
        nav = await abrir(tmp_path / str(externa), api.url, Portales(), externa=externa)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo(True))
    assert api.de("latido")[-1]["portales"]["externa"]["estado"] == "listo"
    api.llamadas.clear()
    correr(flujo(False))
    assert "externa" not in api.de("latido")[-1]["portales"]


JS_EXTERNA = (
    "({visible: !document.getElementById('externa-bloque').hidden,"
    " estado: document.getElementById('externa-estado').textContent,"
    " permitir: !document.getElementById('externa-permitir').hidden,"
    " quitar: !document.getElementById('externa-quitar').hidden,"
    " explica: document.getElementById('externa-explicacion').textContent})"
)


@pytest.mark.parametrize("concedido", [False, True], ids=["sin_permiso", "con_permiso"])
def test_el_popup_explica_y_ofrece_el_permiso_de_las_paginas_externas(tmp_path, api, concedido):
    async def flujo():
        nav = await abrir(tmp_path, api.url, portales_listos(), externa=concedido)
        try:
            await nav.latido()
            pagina = await nav.popup()
            await esperar(pagina, "document.getElementById('externa-estado').textContent !== ''")
            await asyncio.sleep(0.5)
            return await pagina.evaluate(JS_EXTERNA)
        finally:
            await cerrar(nav)

    vista = correr(flujo())
    assert vista["visible"]  # el servidor habilitó LinkedIn
    assert (vista["permitir"], vista["quitar"]) == (not concedido, concedido)
    assert vista["estado"] == ("Permitido ✓" if concedido else "Sin permiso")
    assert "nunca entra a páginas de ingreso, registro o pago" in vista["explica"]


# --- Magneto: cuestionario conversacional por turnos (postulaciones 74, 89, 94 y 96) -----------


def respuestas_mg_chat(campos: list[dict]) -> list[dict]:
    c = campos[0]
    if c.get("multiple"):
        return [{"indice": 0, "valor": None, "opcion": 0, "opciones": [0, 2]}]
    if c["tipo"] == "opciones":
        return [{"indice": 0, "valor": None, "opcion": 0}]
    # Incluye caracteres que el filtro de Magneto borra si no se normalizan antes (/, —, «»)
    return [
        {"indice": 0, "valor": "Soporte N1/N2 — mesa «ITIL» y atención oportuna.", "opcion": None}
    ]


def test_magneto_chat_conversacional_completo_con_cuatro_tipos_y_limpieza_texto(tmp_path, api):
    api.respuestas = respuestas_mg_chat
    postular_magneto(tmp_path, api, portales_magneto("mg_chat_cuestionario.html"))
    turnos = [f["campos"][0] for f in api.de("formulario")]
    assert [(c["texto"], c["tipo"], c.get("multiple", False), c.get("maximo")) for c in turnos] == [
        ("¿Tienes disponibilidad para trabajar de forma presencial?", "opciones", False, None),
        ("¿Qué herramientas manejas actualmente?", "opciones", True, None),
        ("¿Cuál es tu experiencia en soporte técnico?", "texto", False, 140),
        ("Cuéntanos brevemente por qué te interesa esta vacante", "texto", False, 500),
    ]
    # La instrucción genérica va en `ayuda`, nunca pegada al enunciado
    assert turnos[0]["ayuda"] == "Selecciona una opción"
    assert "Selecciona" not in turnos[0]["texto"]
    assert [p["paso"] for p in llenados(api)] == [
        "llenado_1",
        "llenado_2",
        "llenado_3",
        "llenado_4",
    ]
    pasos = [p["paso"] for p in api.de("paso")]
    assert "llenado" in pasos and pasos.index("llenado") < pasos.index("enviar")
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "enviada", resultado
    assert "Se ha enviado tu aplicación" in resultado["confirmacion"]


def test_magneto_chat_espera_al_usuario_en_turno_intermedio_sin_enviar(tmp_path, api):
    api.respuestas = respuestas_mg_chat
    api.esperar = lambda campos: "herramientas" in campos[0]["texto"]
    postular_magneto(tmp_path, api, portales_magneto("mg_chat_cuestionario.html"))
    assert len(api.de("formulario")) == 2
    assert [p["paso"] for p in llenados(api)] == ["llenado_1"]
    pasos = [p["paso"] for p in api.de("paso")]
    assert "esperando_usuario" in pasos and "enviar" not in pasos
    assert not api.de("resultado")


def test_magneto_chat_fallo_conserva_footer_y_header_del_cajon_en_evidencia(tmp_path, api):
    api.respuestas = respuestas_mg_chat
    rota = {'tipo: "multiple",': 'tipo: "vacia",'}
    postular_magneto(
        tmp_path, api, portales_magneto("mg_chat_cuestionario.html", rota), rapido=True
    )
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "formulario_desconocido", resultado
    html = resultado["html"]
    assert "detailChatQuestionnaireChat_chat__footer" in html
    assert "mg_chat_questionnaire_header" in html
    assert "Todos los derechos reservados" not in html
    assert "logoutBlock_avatar" not in html


def test_magneto_proceso_abandonado_termina_bloqueada_sin_pulsar_aplicar(tmp_path, api):
    postular_magneto(tmp_path, api, portales_magneto("mg_proceso_abandonado.html"))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "bloqueada", resultado
    assert resultado["motivo"] == "proceso_abandonado"
    assert not api.de("envio")
    assert "aplicar" not in [p["paso"] for p in api.de("paso")]


def test_magneto_cuestionario_ya_respondido_con_modal_final_termina_enviada(tmp_path, api):
    reemplazos = {
        "raiz.innerHTML =": (
            "document.body.insertAdjacentHTML('beforeend', "
            '\'<div class="alreadyAnsweredQuestionnaireModal_modal__Hs15t">'
            "Ya presentaste el cuestionario prefiltro</div>'); "
            "setTimeout(() => { document.body.insertAdjacentHTML('beforeend', "
            '\'<div class="mg_application_summary_summary-modal_17gu5">'
            "<h2>Se ha enviado tu aplicación</h2></div>'); }, 600); "
            "if (false) raiz.innerHTML ="
        ),
    }
    postular_magneto(tmp_path, api, portales_magneto("mg_chat_cuestionario.html", reemplazos))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "enviada", resultado
    assert "Se ha enviado tu aplicación" in resultado["confirmacion"]


@pytest.mark.parametrize(
    "extra_html",
    [
        "<magneto-spe open></magneto-spe>",
        '<magneto-sign-up id="sign-up" open="true"></magneto-sign-up>',
        '<div class="appliedSummaryPending_applied-modal__9mShs">'
        "Tu aplicación quedará pendiente</div>",
    ],
    ids=["spe_shadow", "signup_shadow", "modal_pendiente"],
)
def test_magneto_cuestionario_ya_respondido_con_spe_o_sign_up_termina_datos_adicionales(
    tmp_path, api, extra_html
):
    reemplazos = {
        "raiz.innerHTML =": (
            "document.body.insertAdjacentHTML('beforeend', "
            '\'<div class="alreadyAnsweredQuestionnaireModal_modal__Hs15t">'
            "Ya presentaste el cuestionario prefiltro</div>'); "
            "setTimeout(() => { document.body.insertAdjacentHTML("
            f"'beforeend', {extra_html!r}); }}, 300); "
            "if (false) raiz.innerHTML ="
        ),
    }
    postular_magneto(tmp_path, api, portales_magneto("mg_chat_cuestionario.html", reemplazos))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "bloqueada", resultado
    assert resultado["motivo"] == "datos_adicionales_portal"


def test_magneto_aplicacion_pendiente_en_cabecera_no_se_confunde_con_ya_postulada(tmp_path, api):
    reemplazos = {
        '<button type="button" class="applyButton_apply-btn__x9p2q">Aplicar</button>': (
            '<div data-testid="application-status-alert">Aplicación pendiente</div>'
            '<div class="renderApplyButton_status-label__x9p2q">¡Ya aplicaste!</div>'
        ),
    }
    postular_magneto(tmp_path, api, portales_magneto("mg_chat_cuestionario.html", reemplazos))
    resultado = api.de("resultado")[0]
    assert resultado["estado"] == "bloqueada", resultado
    assert resultado["motivo"] == "datos_adicionales_portal"
    assert not api.de("envio")
