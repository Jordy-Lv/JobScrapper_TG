"""Motor genérico de la extensión sobre copias reales de formularios (grupo `navegador`).

Las copias recortadas de tests/fixtures/formularios/ (Greenhouse, Ashby, Typeform, Workday y
Pandapé, del reconocimiento del 2026-10-21) y las de tests/fixtures/extension/ se sirven con
`context.route` desde un sitio falso que cuenta los envíos. extension/motor.js se inyecta en cada
página y se maneja como lo hará el service worker: leer la pantalla, pedir la decisión (aquí, un
servidor falso con decisiones fijas en lugar de POST /pantalla), llenar, pulsar y leer el
resultado. Las reglas son las de assets/asistente/motor_generico.json.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import unicodedata
from pathlib import Path

import pytest
import yaml

playwright_api = pytest.importorskip("playwright.async_api")

pytestmark = pytest.mark.navegador

RAIZ = Path(__file__).resolve().parents[2]
MOTOR = RAIZ / "extension" / "motor.js"
FORMULARIOS = Path(__file__).parent.parent / "fixtures" / "formularios"
EXTENSION = Path(__file__).parent.parent / "fixtures" / "extension"
REGLAS = json.loads((RAIZ / "assets" / "asistente" / "motor_generico.json").read_text("utf-8"))
ESPERADO = yaml.safe_load((FORMULARIOS / "esperado.yaml").read_text(encoding="utf-8"))
PDF = b"%PDF-1.4\n% documento de prueba\n"
ARCHIVOS = {
    "cv": {"nombre": "CV_Prueba.pdf", "base64": base64.b64encode(PDF).decode()},
    "certificado_notas": {"nombre": "Notas_Prueba.pdf", "base64": base64.b64encode(PDF).decode()},
}

GH = "https://job-boards.greenhouse.io/prueba/jobs/101"
ASHBY = "https://jobs.ashbyhq.com/prueba/4b3b7cc7/application"
ASHBY_VACANTE = "https://jobs.ashbyhq.com/prueba/4b3b7cc7/"
TYPEFORM = "https://prueba.typeform.com/to/AbCdEf"
WORKDAY = (
    "https://prueba.wd12.myworkdayjobs.com/es/prueba/job/Bogota/Practicante/apply/applyManually"
)
PANDAPE = "https://prueba.pandape.computrabajo.com/ApplyCT/101"
EE_CUESTIONARIO = "https://www.elempleo.com/co/JobOffers/Questionnaires/Index/101"
ENVIO_ASHBY = '<div class="ashby-application-form-submit-container">'
IGNORA = 'data-combo data-ignora="si"'  # la lista no deja elegida la opción pulsada
DISPONIBILIDAD = "Fecha de disponibilidad para iniciar"


def normalizar(texto: str | None) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto or "")
    return " ".join("".join(c for c in sin_tildes if not unicodedata.combining(c)).lower().split())


# --- sitio falso -----------------------------------------------------------------------------


class Sitio:
    """Sirve las copias por URL y guarda los POST que recibe (los envíos)."""

    def __init__(self) -> None:
        self.paginas: dict[str, str] = {}
        self.envios: dict[str, str | None] = {}
        self.posts: list[str] = []

    def poner(self, url: str, archivo: str, reemplazos: dict[str, str] | None = None) -> None:
        carpeta = EXTENSION if (EXTENSION / archivo).is_file() else FORMULARIOS
        html = (carpeta / archivo).read_text(encoding="utf-8")
        for a, b in (reemplazos or {}).items():
            assert a in html, f"{archivo}: no está el texto a reemplazar {a!r}"
            html = html.replace(a, b)
        self.paginas[url] = html

    def al_enviar(self, url: str, archivo: str | None) -> None:
        self.envios[url] = None if archivo is None else (FORMULARIOS / archivo).read_text("utf-8")

    def contados(self, url: str) -> int:
        return self.posts.count(url)

    async def atender(self, route) -> None:
        peticion = route.request
        url = peticion.url.split("#")[0].split("?")[0] if "recaptcha" not in peticion.url else ""
        if "recaptcha" in peticion.url:
            await route.fulfill(status=200, body="<html><body>reto</body></html>",
                                content_type="text/html")  # fmt: skip
            return
        if peticion.method == "POST":
            self.posts.append(url)
            if url in self.envios:
                respuesta = self.envios[url]
                if respuesta is None:
                    await route.fulfill(status=200, body="{}", content_type="application/json")
                else:
                    await route.fulfill(status=200, body=respuesta,
                                        content_type="text/html; charset=utf-8")  # fmt: skip
                return
            await route.fulfill(status=404, body="no encontrada")
            return
        html = self.paginas.get(peticion.url.split("#")[0])
        if html is None:
            await route.fulfill(status=404, body="no encontrada", content_type="text/html")
        else:
            await route.fulfill(status=200, body=html, content_type="text/html; charset=utf-8")


def sitio_de(copia: str) -> Sitio:
    datos = ESPERADO["copias"][copia]
    sitio = Sitio()
    for url, archivo in datos["paginas"].items():
        sitio.poner(url, archivo)
    for url, archivo in (datos.get("envios") or {}).items():
        sitio.al_enviar(url, archivo)
    return sitio


# --- servidor falso: decisiones fijas en vez de POST /pantalla --------------------------------

# Respuestas de una usuaria de prueba por patrón sobre el texto, el nombre y el autocomplete del
# campo. Un valor de opción se elige por su texto; los archivos van por su etiqueta.
RESPUESTAS = [
    (r"given-name|first name|^nombre\b", "Ana"),
    (r"family-name|last name|apellido", "Pérez"),
    (r"full name|nombre completo", "Ana Pérez"),
    (r"email|correo", "ana@example.com"),
    (r"phone|telefono", "+57 3001234567"),
    (r"^country\b", "Colombia"),
    (r"location \(city\)|city you live", "Medellín"),
    (r"authorized to work", "Yes"),
    (r"located in", "No"),
    (r"university", "Universidad de prueba"),
    (r"\bgpa\b", "4.0 - 4.09"),
    (r"english level", "B2"),
    (r"pay expectations", "COP 2.500.000"),
    (r"how did you (hear|find)|como te enteraste", "LinkedIn"),
    (r"linkedin profile", "https://www.linkedin.com/in/prueba"),
    (r"background", "Two years helping users with their computers in a university lab."),
    (r"years of experience", "1-2 years"),
    (r"disponibilidad", "2026-11-03"),
    (r"privacidad|privacy", "Sí"),
]


class ServidorFalso:
    def __init__(self) -> None:
        self.pantallas: list[dict] = []

    def decidir(self, pantalla: dict) -> list[dict]:
        self.pantallas.append(pantalla)
        respuestas = []
        for i, campo in enumerate(pantalla["campos"]):
            if campo["tipo"] == "archivo":
                continue
            clave = normalizar(f"{campo['texto']} {campo.get('autocomplete') or ''}")
            valor = next((v for patron, v in RESPUESTAS if re.search(patron, clave)), None)
            if valor is None:
                continue
            opciones = [normalizar(o) for o in campo["opciones"]]
            if normalizar(valor) in opciones:
                respuestas.append({"indice": i, "opcion": opciones.index(normalizar(valor))})
            else:
                respuestas.append({"indice": i, "valor": valor})
        return respuestas


# --- navegador ---------------------------------------------------------------------------------


def correr(corutina):
    return asyncio.run(corutina)


async def abrir(sitio: Sitio):
    pw = await playwright_api.async_playwright().start()
    try:
        navegador = await pw.chromium.launch(headless=True)
    except Exception as exc:  # Chromium no instalado
        await pw.stop()
        pytest.skip(f"Chromium no disponible: {exc}")
    contexto = await navegador.new_context(viewport={"width": 1280, "height": 900})
    await contexto.add_init_script(path=str(MOTOR))
    await contexto.route("https://**/*", sitio.atender)
    pagina = await contexto.new_page()
    pagina.pw = pw
    pagina.navegador = navegador
    return pagina


async def cerrar(pagina) -> None:
    await pagina.navegador.close()
    await pagina.pw.stop()


async def evaluar(pagina, expresion: str, argumento=None):
    """Evalúa en la página; si una navegación cortó el script, espera la nueva y repite."""
    for intento in range(20):
        try:
            return await pagina.evaluate(expresion, argumento)
        except playwright_api.Error as exc:
            if "destroyed" not in str(exc) and "navigat" not in str(exc) and intento > 0:
                raise
            await asyncio.sleep(0.3)
            await pagina.wait_for_load_state("load")
    raise AssertionError("la página no terminó de navegar")


async def leer(pagina) -> dict:
    return await evaluar(pagina, "r => __asistente.generico.leerPantalla(r)", REGLAS)


async def llenar(pagina, respuestas: list[dict], archivos: dict | None = None) -> dict:
    return await evaluar(
        pagina, "([r, a]) => __asistente.generico.llenar(r, a)", [respuestas, archivos or {}]
    )


async def pulsar(pagina, indice: int) -> dict:
    return await evaluar(pagina, "i => __asistente.generico.pulsar(i)", indice)


async def resultado(pagina, previo: dict, ms: int = 3000) -> dict:
    return await evaluar(
        pagina, "([r, p, ms]) => __asistente.generico.resultado(r, p, ms)", [REGLAS, previo, ms]
    )


def textos(pantalla: dict) -> list[str]:
    return [c["texto"] for c in pantalla["campos"]]


def campo(pantalla: dict, texto: str) -> dict:
    return next(c for c in pantalla["campos"] if c["texto"] == texto)


def indice(pantalla: dict, texto: str) -> int:
    return textos(pantalla).index(texto)


def boton(pantalla: dict, texto: str) -> dict:
    return next(b for b in pantalla["botones"] if b["texto"] == texto)


def previo_de(pantalla: dict) -> dict:
    """Lo que `resultado` compara con la pantalla siguiente."""
    return {
        "firma": pantalla["firma"],
        "url": pantalla["url"],
        "encabezados": pantalla["resumen"]["encabezados"],
        "accion": (pantalla["sugerido"] or {}).get("accion"),
    }


async def completar(pagina, servidor: ServidorFalso, inicio: str, tope: int = 40) -> str:
    """Conduce el motor desde `inicio` hasta un resultado, como el bucle del service worker."""
    await pagina.goto(inicio)
    envio_registrado = False
    for _ in range(tope):
        pantalla = await leer(pagina)
        if pantalla["clase"] == "exito":
            return "enviada" if envio_registrado else "exito_sin_envio"
        if pantalla["clase"] == "barrera":
            return f"barrera:{pantalla['motivo']}"
        if pantalla["clase"] in ("formulario", "error"):
            lleno = await llenar(pagina, servidor.decidir(pantalla), ARCHIVOS)
            if lleno.get("error"):
                return f"formulario_desconocido:{lleno['motivo']}"
        sugerido = pantalla["sugerido"]
        if not sugerido:
            return f"desconocida:{pantalla['clase']}"
        if sugerido["accion"] == "enviar":
            envio_registrado = True  # el servicio lo registra en el servidor antes del clic
        await pulsar(pagina, sugerido["indice"])
        previo = previo_de(pantalla)
        await asyncio.sleep(0.2)
        cambio = await resultado(pagina, previo)
        if cambio["resultado"] == "sin_cambios":
            return "sin_cambios"
    return "tope"


# --- 1.1: copias sin datos personales ----------------------------------------------------------

CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")
TELEFONO = re.compile(r"\+?\d[\d\s().-]{5,}\d")
FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")


def test_las_copias_no_traen_correos_ni_telefonos():
    archivos = sorted(FORMULARIOS.glob("*"))
    assert len(archivos) >= 9
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        assert not CORREO.search(texto), (archivo.name, CORREO.search(texto).group())
        for posible in TELEFONO.findall(texto):
            if FECHA.fullmatch(posible.strip()):
                continue
            assert len(re.sub(r"\D", "", posible)) < 7, (archivo.name, posible)


def test_cada_copia_del_banco_existe_y_trae_su_pagina_final():
    for nombre, datos in ESPERADO["copias"].items():
        for archivo in [*datos["paginas"].values(), *(datos.get("envios") or {}).values()]:
            if archivo is not None:
                assert (FORMULARIOS / archivo).is_file(), (nombre, archivo)
        if datos["resultado"] == "enviada":
            assert datos["envio_final"] in datos["envios"], nombre


# --- 1.2 y 3.1: lectura de la pantalla y esquema ------------------------------------------------


def test_esquema_de_greenhouse_con_combobox_y_archivos():
    async def flujo():
        pagina = await abrir(sitio_de("greenhouse"))
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            assert p["clase"] == "formulario"
            assert p["idioma"] == "en"
            assert textos(p) == [
                "First Name", "Last Name", "Email", "Country", "Phone", "Location (City)",
                "Resume/CV", "Cover Letter", "Are you legally authorized to work in Colombia?",
                "Are you located in Bogotá?",
                "What university are you currently pursuing your bachelor's degree?",
                "Please list your current cumulative GPA.",
                "Please upload a copy of your unofficial university transcripts.",
                "What is your English level?",
                "What are your monthly pay expectations in Colombian Pesos?",
                "How did you hear about this opportunity?",
                "Optional additional documents to support your application.",
            ]  # fmt: skip
            nombre = campo(p, "First Name")
            assert nombre["autocomplete"] == "given-name"
            assert nombre["obligatoria"] is True and nombre["maximo"] == 255
            assert nombre["nombre"] == "first_name" and nombre["idioma"] == "en"
            assert campo(p, "Phone")["tipo"] == "telefono"
            # react-select: las opciones aparecen solo al abrir la lista; queda cerrada y vacía
            autorizado = campo(p, "Are you legally authorized to work in Colombia?")
            assert autorizado["tipo"] == "opciones" and autorizado["opciones"] == ["Yes", "No"]
            assert autorizado["obligatoria"] is True and autorizado["busqueda"] is False
            assert len(campo(p, "Please list your current cumulative GPA.")["opciones"]) == 23
            assert campo(p, "Country")["busqueda"] is True  # más de 100 países
            assert campo(p, "Country")["opciones"] == []
            assert campo(p, "Location (City)")["busqueda"] is True  # se busca escribiendo
            cerrados = await pagina.evaluate(
                "[...document.querySelectorAll('[role=combobox]')].every(c => "
                "c.getAttribute('aria-expanded') === 'false' && !c.value) && "
                "!document.querySelector('[role=listbox]') && "
                "[...document.querySelectorAll('.requerido')].every(i => !i.value)"
            )
            assert cerrados
            cv = campo(p, "Resume/CV")
            assert cv["tipo"] == "archivo" and cv["obligatoria"] is True
            assert cv["accept"] == ".pdf,.doc,.docx,.txt,.rtf"
            assert campo(p, "Cover Letter")["obligatoria"] is False
            notas = campo(p, "Please upload a copy of your unofficial university transcripts.")
            assert notas["obligatoria"] is True
            # Ni la respuesta del captcha ni los <input required> ocultos de react-select
            assert all("recaptcha" not in (c["nombre"] or "") for c in p["campos"])
            assert boton(p, "Submit application")["clase"] == "enviar"
            assert p["sugerido"] == {"indice": boton(p, "Submit application")["indice"],
                                     "accion": "enviar"}  # fmt: skip
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_esquema_de_ashby_sin_form_y_sin_el_archivo_de_autorrelleno():
    async def flujo():
        pagina = await abrir(sitio_de("ashby"))
        try:
            await pagina.goto(ASHBY)
            p = await leer(pagina)
            assert p["clase"] == "formulario"
            assert textos(p) == ["Nombre Completo", "Email", "Teléfono", "Curriculum"]
            assert [c["obligatoria"] for c in p["campos"]] == [True, True, False, True]
            assert [c["tipo"] for c in p["campos"]] == ["texto", "correo", "telefono", "archivo"]
            assert campo(p, "Curriculum")["nombre"] == "_systemfield_resume"
            enviar = boton(p, "Submit Application")
            assert enviar["clase"] == "enviar" and enviar["en_contenedor"] is True
            assert boton(p, "Upload file")["clase"] == "nunca"
            assert p["sugerido"]["accion"] == "enviar"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_vacante_con_boton_de_postular_es_intermedia():
    async def flujo():
        pagina = await abrir(sitio_de("ashby"))
        try:
            await pagina.goto(ASHBY_VACANTE)
            p = await leer(pagina)
            assert p["clase"] == "intermedia"
            assert p["campos"] == []
            assert boton(p, "Apply for this Job")["clase"] == "intermedia"
            assert p["sugerido"] == {"indice": boton(p, "Apply for this Job")["indice"],
                                     "accion": "avanzar"}  # fmt: skip
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_typeform_una_pregunta_por_pantalla_con_radios_aria():
    async def flujo():
        pagina = await abrir(sitio_de("typeform"))
        try:
            await pagina.goto(TYPEFORM)
            bienvenida = await leer(pagina)
            assert bienvenida["clase"] == "intermedia"
            assert boton(bienvenida, "Start")["clase"] == "avanzar"
            await pagina.evaluate("document.querySelector('[data-qa=start-button]').click()")
            p = await leer(pagina)
            assert p["clase"] == "formulario"
            assert textos(p) == ["Full Name"]  # sin la numeración ni el asterisco
            assert p["campos"][0]["obligatoria"] is True
            assert boton(p, "OK")["clase"] == "avanzar"
            assert p["sugerido"]["accion"] == "avanzar"
            await pagina.evaluate(
                "document.querySelectorAll('.screen').forEach((s, i) => "
                "s.classList.toggle('oculto', i !== 7))"
            )
            radios = await leer(pagina)
            assert textos(radios) == ["How many years of experience do you have in tech support?"]
            assert radios["campos"][0]["opciones"] == ["<1 year", "1-2 years", "2-5 years",
                                                       "5+ years"]  # fmt: skip
            assert radios["campos"][0]["obligatoria"] is True
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_workday_crear_cuenta_es_barrera_sin_trampa_ni_contrasenas():
    async def flujo():
        pagina = await abrir(sitio_de("workday_cuenta"))
        try:
            await pagina.goto(WORKDAY)
            p = await leer(pagina)
            assert p["clase"] == "barrera" and p["motivo"] == "ats_con_cuenta"
            # El banner de cookies tapaba la página: se declinó, no se aceptó
            assert p["cookies"] == "rechazadas"
            assert await pagina.evaluate("document.body.dataset.cookies") == "declinadas"
            nombres = [c["nombre"] for c in p["campos"]]
            assert "beecatcher" not in nombres
            assert not any("assword" in (n or "") for n in nombres)
            assert all(c["tipo"] != "clave" for c in p["campos"])
            resumen = json.dumps(p["resumen"])
            assert "beecatcher" not in resumen and "Deja este campo" not in resumen
            assert await pagina.evaluate("document.body.dataset.pulsado") is None
            escrito = await pagina.evaluate(
                "[...document.querySelectorAll('input')].some(i => "
                "i.type === 'checkbox' ? i.checked : i.value)"
            )
            assert escrito is False
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_pandape_aviso_de_cookies_que_solo_acepta_no_se_pulsa():
    async def flujo():
        pagina = await abrir(sitio_de("pandape"))
        try:
            await pagina.goto(PANDAPE)
            p = await leer(pagina)
            assert p["clase"] == "formulario"
            assert p["cookies"] == "sin_tocar"
            assert await pagina.evaluate("document.body.dataset.cookies") is None
            assert textos(p) == ["Correo electrónico"]
            assert p["campos"][0]["tipo"] == "correo" and p["campos"][0]["obligatoria"] is True
            assert boton(p, "Continuar")["clase"] == "avanzar"
            assert p["idioma"] == "es"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_cuestionario_adicional_de_elempleo_se_lee_con_el_motor_generico():
    async def flujo():
        sitio = Sitio()
        sitio.poner(EE_CUESTIONARIO, "ee_cuestionario.html")
        pagina = await abrir(sitio)
        try:
            await pagina.goto(EE_CUESTIONARIO)
            p = await leer(pagina)
            assert p["clase"] == "formulario"  # el modal de éxito está oculto
            assert len(p["campos"]) == 3
            assert all(c["tipo"] == "texto" and c["obligatoria"] for c in p["campos"])
            assert p["campos"][0]["texto"].startswith("El salario es")
            assert p["campos"][0]["maximo"] is None or p["campos"][0]["maximo"] > 0
            assert boton(p, "Postularme a oferta")["clase"] == "enviar"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_captcha_invisible_no_es_barrera_y_el_desafio_visible_si():
    async def flujo(visible: bool):
        sitio = Sitio()
        reemplazos = {'class="recaptcha-oculto"': 'class="recaptcha-visible"'} if visible else {}
        sitio.poner(GH, "greenhouse.html", reemplazos)
        pagina = await abrir(sitio)
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            return p["clase"], p["motivo"]
        finally:
            await cerrar(pagina)

    assert correr(flujo(False)) == ("formulario", None)
    assert correr(flujo(True)) == ("barrera", "captcha")


def test_obligatorio_por_asterisco_sin_required():
    async def flujo():
        sitio = Sitio()
        sitio.poner(PANDAPE, "pandape_paso2.html")
        pagina = await abrir(sitio)
        try:
            await pagina.goto(PANDAPE)
            p = await leer(pagina)
            assert campo(p, "Apellidos")["obligatoria"] is True  # «Apellidos *»
            assert campo(p, "Fecha de disponibilidad para iniciar")["obligatoria"] is False
            # El prefijo del teléfono es parte del teléfono, no una pregunta aparte
            assert "Prefijo" not in textos(p)
            assert campo(p, "¿Cómo te enteraste de esta oferta?")["opciones"] == [
                "Computrabajo", "LinkedIn", "Referido", "Otro"
            ]  # fmt: skip
        finally:
            await cerrar(pagina)

    correr(flujo())


MARCADOR = "MARCADOR-7Q"


def test_resumen_y_evidencia_sin_los_valores_escritos():
    async def flujo():
        pagina = await abrir(sitio_de("greenhouse"))
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            respuestas = [
                {"indice": i, "valor": f"{MARCADOR}-{i}"}
                for i, c in enumerate(p["campos"])
                if c["tipo"] in ("texto", "correo", "telefono")
            ]
            assert len(respuestas) == 6
            respuestas.append({"indice": indice(p, "Location (City)"), "valor": "Medellín"})
            lleno = await llenar(pagina, respuestas)
            assert lleno["ok"] is True
            assert await pagina.evaluate("document.querySelector('#first_name').value") == (
                f"{MARCADOR}-0"
            )
            otra = await leer(pagina)
            assert len(otra["resumen"]["elementos"]) <= 150
            assert len(json.dumps(otra["resumen"])) <= 12 * 1024
            assert MARCADOR not in json.dumps(otra)
            evidencia = await evaluar(pagina, "() => __asistente.generico.html()")
            assert MARCADOR not in evidencia
            # La ciudad elegida en el combobox (la lista del sitio sí puede quedar)
            assert "Antioquia, Colombia</div>" not in evidencia
            assert (
                await pagina.evaluate(
                    "document.querySelector('[data-buscar] .select__single-value').textContent"
                )
                == "Medellín, Antioquia, Colombia"
            )
            assert "First Name" in evidencia and "Location (City)" in evidencia
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_resumen_numera_lo_visible_sin_contrasenas():
    async def flujo():
        pagina = await abrir(sitio_de("workday_cuenta"))
        try:
            await pagina.goto(WORKDAY)
            p = await leer(pagina)
            elementos = p["resumen"]["elementos"]
            assert [e["indice"] for e in elementos] == list(range(len(elementos)))
            assert "Create Account" in p["resumen"]["encabezados"]
            assert not any(e["tipo"] == "password" for e in elementos)
            assert any(e["texto"] == "Create Account" and e["rol"] == "button" for e in elementos)
        finally:
            await cerrar(pagina)

    correr(flujo())


# --- 3.2: llenado comprobado ---------------------------------------------------------------------


def test_greenhouse_combobox_y_ciudad_con_busqueda_quedan_elegidos():
    async def flujo():
        pagina = await abrir(sitio_de("greenhouse"))
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            autorizado = indice(p, "Are you legally authorized to work in Colombia?")
            lleno = await llenar(pagina, [
                {"indice": autorizado, "opcion": 1},
                {"indice": indice(p, "Location (City)"), "valor": "Medellín"},
                {"indice": indice(p, "Country"), "valor": "Colombia"},
            ])  # fmt: skip
            assert lleno["ok"] is True, lleno
            elegidos = await pagina.evaluate(
                "[...document.querySelectorAll('[data-combo]')].map(c => "
                "c.querySelector('.select__single-value').textContent)"
            )
            assert elegidos[0] == "Colombia"
            assert elegidos[1] == "Medellín, Antioquia, Colombia"  # la que empieza por Medellín
            assert elegidos[2] == "No"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_opcion_que_no_queda_elegida_corta_el_llenado():
    async def flujo():
        sitio = Sitio()
        si_no = 'data-combo data-opciones=\'["Yes", "No"]\'>'
        sitio.poner(GH, "greenhouse.html", {si_no: si_no.replace("data-combo", IGNORA)})
        pagina = await abrir(sitio)
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            autorizado = indice(p, "Are you legally authorized to work in Colombia?")
            universidad = indice(
                p, "What university are you currently pursuing your bachelor's degree?"
            )
            lleno = await llenar(pagina, [
                {"indice": autorizado, "opcion": 1},
                {"indice": universidad, "valor": "Otra"},
            ])  # fmt: skip
            assert lleno["error"] == "formulario_desconocido"
            assert "no quedó mostrada" in lleno["motivo"]
            assert lleno["escritas"] == []  # no siguió con el campo de la universidad
            assert MARCADOR not in lleno["html"]
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_ashby_el_cv_va_solo_en_el_campo_etiquetado():
    async def flujo():
        pagina = await abrir(sitio_de("ashby"))
        try:
            await pagina.goto(ASHBY)
            await leer(pagina)
            lleno = await llenar(pagina, [], ARCHIVOS)
            assert lleno["ok"] is True and lleno["adjuntos"] == [4]
            archivos = await pagina.evaluate(
                "[...document.querySelectorAll('input[type=file]')].map(i => "
                "[...i.files].map(f => f.name))"
            )
            assert archivos == [[], ["CV_Prueba.pdf"]]
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_greenhouse_cv_y_certificado_de_notas_cada_uno_en_su_campo():
    async def flujo():
        pagina = await abrir(sitio_de("greenhouse"))
        try:
            await pagina.goto(GH)
            await leer(pagina)
            lleno = await llenar(pagina, [], ARCHIVOS)
            assert lleno["ok"] is True
            archivos = await pagina.evaluate(
                "Object.fromEntries([...document.querySelectorAll('input[type=file]')].map(i => "
                "[i.id, [...i.files].map(f => f.name)]))"
            )
            assert archivos == {
                "resume": ["CV_Prueba.pdf"],
                "cover_letter": [],
                "question_105": ["Notas_Prueba.pdf"],
                "question_109": [],
            }
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_documento_pedido_que_no_existe_corta_el_llenado():
    async def flujo():
        pagina = await abrir(sitio_de("greenhouse"))
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            notas = indice(p, "Please upload a copy of your unofficial university transcripts.")
            lleno = await llenar(pagina, [{"indice": notas, "documento": "certificado_notas"}])
            assert lleno["error"] == "formulario_desconocido"
            assert "falta el documento" in lleno["motivo"]
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_typeform_radio_aria_queda_marcado():
    async def flujo():
        pagina = await abrir(sitio_de("typeform"))
        try:
            await pagina.goto(TYPEFORM)
            await pagina.evaluate(
                "document.querySelectorAll('.screen').forEach((s, i) => "
                "s.classList.toggle('oculto', i !== 7))"
            )
            await leer(pagina)
            lleno = await llenar(pagina, [{"indice": 0, "opcion": 1}])
            assert lleno["ok"] is True
            marcado = await pagina.evaluate(
                "[...document.querySelectorAll('[role=radio]')]"
                ".map(r => r.getAttribute('aria-checked'))"
            )
            assert marcado == ["false", "true", "false", "false"]
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_pandape_telefono_con_prefijo_fecha_lista_y_casilla():
    async def flujo():
        sitio = Sitio()
        sitio.poner(PANDAPE, "pandape_paso2.html")
        pagina = await abrir(sitio)
        try:
            await pagina.goto(PANDAPE)
            p = await leer(pagina)
            lleno = await llenar(pagina, [
                {"indice": indice(p, "Teléfono celular"), "valor": "+57 3001234567"},
                {"indice": indice(p, DISPONIBILIDAD), "valor": "2026-11-03"},
                {"indice": indice(p, "¿Cómo te enteraste de esta oferta?"), "opcion": 1},
                {"indice": indice(p, "Acepto la política de privacidad"), "opcion": 0},
            ], ARCHIVOS)  # fmt: skip
            assert lleno["ok"] is True, lleno
            valores = await pagina.evaluate(
                "({prefijo: PhonePrefix.value, telefono: Phone.value, fecha: Availability.value, "
                "fuente: Source.value, privacidad: Privacy.checked, cv: Cv.files[0].name})"
            )
            assert valores == {
                "prefijo": "57",
                "telefono": "3001234567",
                "fecha": "03/11/2026",
                "fuente": "2",
                "privacidad": True,
                "cv": "CV_Prueba.pdf",
            }
        finally:
            await cerrar(pagina)

    correr(flujo())


# --- 3.3: botones, barreras y resultado ---------------------------------------------------


def test_clases_de_los_botones_de_greenhouse():
    async def flujo():
        pagina = await abrir(sitio_de("greenhouse"))
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            clases = {b["texto"]: b["clase"] for b in p["botones"]}
            assert clases["Submit application"] == "enviar"
            for nunca in ("Locate me", "Attach", "Dropbox", "Google Drive", "Enter manually"):
                assert clases[nunca] == "nunca", nunca
            # El «Apply» de la cabecera queda fuera: está antes del formulario
            assert "Apply" not in clases and "Autofill my application" not in clases
            nunca = boton(p, "Locate me")["indice"]
            rechazo = await pulsar(pagina, nunca)
            assert rechazo["error"] == "formulario_desconocido"
        finally:
            await cerrar(pagina)

    correr(flujo())


@pytest.mark.parametrize(
    ("html", "motivo"),
    [
        ('<input type="password" aria-label="Clave">', "ats_con_cuenta"),
        ('<input type="text" autocomplete="current-password" aria-label="x">', "ats_con_cuenta"),
        ("<h2>Sign in to apply</h2>", "ats_con_cuenta"),
        ('<label for="c">Verification code</label><input id="c">', "codigo_verificacion"),
        ('<iframe src="https://www.google.com/recaptcha/api2/anchor?k=x" width="304" '
         'height="78"></iframe>', "captcha"),
    ],
    ids=["contrasena", "autocomplete", "texto", "codigo", "desafio"],
)  # fmt: skip
def test_barreras_detienen_sin_enviar(html, motivo):
    async def flujo():
        sitio = Sitio()
        sitio.poner(ASHBY, "ashby.html", {ENVIO_ASHBY: html + ENVIO_ASHBY})
        pagina = await abrir(sitio)
        try:
            await pagina.goto(ASHBY)
            p = await leer(pagina)
            assert (p["clase"], p["motivo"]) == ("barrera", motivo)
            assert p["sugerido"] is None
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_desafio_diminuto_no_cuenta_como_captcha():
    async def flujo():
        sitio = Sitio()
        diminuto = (
            '<iframe src="https://www.google.com/recaptcha/api2/bframe?k=x" '
            'width="10" height="10"></iframe>'
        )
        sitio.poner(ASHBY, "ashby.html", {ENVIO_ASHBY: diminuto + ENVIO_ASHBY})
        pagina = await abrir(sitio)
        try:
            await pagina.goto(ASHBY)
            assert (await leer(pagina))["clase"] == "formulario"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_oauth_como_unico_camino_es_barrera():
    async def flujo():
        sitio = Sitio()
        oauth = (
            '<button type="button">Apply with LinkedIn</button>'
            '<button type="button">Continue with Google</button>'
        )
        sitio.poner(ASHBY_VACANTE, "ashby_vacante.html", {"<span>Apply for this Job</span>": oauth})
        pagina = await abrir(sitio)
        try:
            await pagina.goto(ASHBY_VACANTE)
            p = await leer(pagina)
            assert (p["clase"], p["motivo"]) == ("barrera", "oauth")
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_pagina_de_gracias_es_exito_por_texto_y_por_url():
    async def flujo():
        sitio = Sitio()
        sitio.poner(GH, "greenhouse_gracias.html")
        sitio.poner(GH + "/confirmation", "greenhouse_gracias.html",
                    {"<h1>Thank you for applying.</h1>": "<h1>Listo</h1>",
                     "Your application has been received.": ""})  # fmt: skip
        pagina = await abrir(sitio)
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            assert p["clase"] == "exito" and p["exito"]["senal"] == "texto"
            await pagina.goto(GH + "/confirmation")
            p = await leer(pagina)
            assert p["clase"] == "exito" and p["exito"]["senal"] == "url"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_enviar_vacio_marca_errores_y_no_cuenta_un_envio():
    async def flujo():
        sitio = sitio_de("greenhouse")
        pagina = await abrir(sitio)
        try:
            await pagina.goto(GH)
            p = await leer(pagina)
            previo = previo_de(p)
            await pulsar(pagina, p["sugerido"]["indice"])
            cambio = await resultado(pagina, previo)
            assert cambio["resultado"] == "error"
            assert "Please complete all required fields." in cambio["avisos"]
            assert (await leer(pagina))["clase"] == "error"
            assert sitio.posts == []
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_formulario_que_desaparece_es_exito_y_ashby_cuenta_un_envio():
    async def flujo():
        sitio = sitio_de("ashby")
        sitio.envios["https://jobs.ashbyhq.com/api/enviar"] = None
        pagina = await abrir(sitio)
        try:
            await pagina.goto(ASHBY)
            p = await leer(pagina)
            datos = [{"indice": 0, "valor": "Ana Pérez"}, {"indice": 1, "valor": "ana@example.com"}]
            assert (await llenar(pagina, datos, ARCHIVOS))["ok"] is True
            previo = previo_de(p)
            await pulsar(pagina, p["sugerido"]["indice"])
            cambio = await resultado(pagina, previo)
            assert cambio["resultado"] == "exito"
            assert sitio.contados("https://jobs.ashbyhq.com/api/enviar") == 1
        finally:
            await cerrar(pagina)

    correr(flujo())


# --- 3.4: selector estable -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("copia", "url"),
    [("greenhouse", GH), ("ashby", ASHBY), ("workday_cuenta", WORKDAY), ("pandape", PANDAPE)],
    ids=["greenhouse", "ashby", "workday", "pandape"],
)
def test_el_selector_estable_vuelve_a_encontrar_el_mismo_elemento(copia, url):
    async def flujo():
        pagina = await abrir(sitio_de(copia))
        try:
            await pagina.goto(url)
            p = await leer(pagina)
            objetivos = [{"campo": i} for i in range(len(p["campos"]))]
            objetivos += [{"boton": i} for i in range(len(p["botones"]))]
            assert objetivos
            for objetivo in objetivos:
                selector = await evaluar(
                    pagina, "o => __asistente.generico.selectorDe(o)", objetivo
                )
                assert selector, objetivo
                mismo = await pagina.evaluate(
                    "([o, s]) => __asistente.generico.encontrar(s) === "
                    "__asistente.generico.elemento(o)",
                    [objetivo, selector],
                )
                assert mismo, (objetivo, selector)
            if copia == "greenhouse":
                primero = await evaluar(pagina, "o => __asistente.generico.selectorDe(o)",
                                        {"campo": 0})  # fmt: skip
                assert primero == "#first_name"
            if copia == "workday_cuenta":
                correo = await evaluar(pagina, "o => __asistente.generico.selectorDe(o)",
                                       {"campo": 0})  # fmt: skip
                assert correo == 'input[data-automation-id="email"]'  # el id input-4 es generado
        finally:
            await cerrar(pagina)

    correr(flujo())


# --- 1.3: el banco no baja ---------------------------------------------------------------------


def test_el_banco_no_baja():
    async def una(nombre: str, datos: dict) -> tuple[str, int]:
        sitio = sitio_de(nombre)
        pagina = await abrir(sitio)
        try:
            obtenido = await completar(pagina, ServidorFalso(), datos["inicio"])
            envios = sitio.contados(datos["envio_final"]) if datos["envio_final"] else 0
            return obtenido, envios
        finally:
            await cerrar(pagina)

    resultados = {}
    completas = 0
    for nombre, datos in ESPERADO["copias"].items():
        obtenido, envios = correr(una(nombre, datos))
        resultados[nombre] = (obtenido, envios)
        esperados = 1 if datos["resultado"] == "enviada" else 0
        if obtenido == datos["resultado"] and envios == esperados:
            completas += 1
    assert completas >= ESPERADO["minimo"], resultados


# Controles ARIA de Workday: una casilla role=checkbox y una lista que se abre con un botón
# aria-haspopup=listbox (marcado tomado de los pasos «Mis datos» de Workday, sin estilos)
ARIA_WORKDAY = """<!doctype html><html lang="es"><body><main>
<div data-automation-id="formField-source">
  <label id="fuente-label">¿Cómo nos encontraste?*</label>
  <button type="button" id="fuente" aria-haspopup="listbox" aria-labelledby="fuente-label"
    aria-required="true" data-automation-id="sourceDropdown">Selecciona uno</button>
</div>
<div data-automation-id="formField-terms">
  <div role="checkbox" aria-checked="false" tabindex="0" aria-labelledby="terminos"
    data-automation-id="agreementCheckbox"></div>
  <span id="terminos">Acepto los términos*</span>
</div>
<button type="button" data-automation-id="bottom-navigation-next-button">Siguiente</button>
</main><script>
var boton = document.getElementById("fuente"), lista = null;
boton.addEventListener("click", function () {
  if (lista) { lista.remove(); lista = null; boton.setAttribute("aria-expanded", "false"); return; }
  lista = document.createElement("ul");
  lista.id = "fuente-lista";
  lista.setAttribute("role", "listbox");
  ["LinkedIn", "Sitio web de la empresa", "Referido"].forEach(function (t) {
    var op = document.createElement("li");
    op.setAttribute("role", "option");
    op.textContent = t;
    op.addEventListener("click", function () {
      boton.textContent = t; lista.remove(); lista = null;
      boton.setAttribute("aria-expanded", "false");
    });
    lista.appendChild(op);
  });
  boton.after(lista);
  boton.setAttribute("aria-expanded", "true");
  boton.setAttribute("aria-controls", "fuente-lista");
});
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape" || !lista) return;
  lista.remove(); lista = null; boton.setAttribute("aria-expanded", "false");
});
var casilla = document.querySelector("[role=checkbox]");
casilla.addEventListener("click", function () {
  var marcada = casilla.getAttribute("aria-checked") === "true";
  casilla.setAttribute("aria-checked", marcada ? "false" : "true");
});
</script></body></html>"""


def test_lista_de_boton_y_casilla_aria_se_leen_y_se_llenan():
    async def flujo():
        sitio = Sitio()
        sitio.paginas[WORKDAY] = ARIA_WORKDAY
        pagina = await abrir(sitio)
        try:
            await pagina.goto(WORKDAY)
            p = await leer(pagina)
            assert textos(p) == ["¿Cómo nos encontraste?", "Acepto los términos"]
            fuente = campo(p, "¿Cómo nos encontraste?")
            assert fuente["opciones"] == ["LinkedIn", "Sitio web de la empresa", "Referido"]
            assert fuente["obligatoria"] is True
            assert campo(p, "Acepto los términos")["opciones"] == ["Sí", "No"]
            assert await pagina.evaluate("document.querySelector('[role=listbox]')") is None
            assert await pagina.evaluate("fuente.textContent") == "Selecciona uno"
            lleno = await llenar(pagina, [{"indice": 0, "opcion": 0}, {"indice": 1, "opcion": 0}])
            assert lleno["ok"] is True, lleno
            estado = await pagina.evaluate(
                "[fuente.textContent, document.querySelector('[role=checkbox]')"
                ".getAttribute('aria-checked')]"
            )
            assert estado == ["LinkedIn", "true"]
            assert p["sugerido"]["accion"] == "avanzar"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_formulario_que_desaparece_sin_texto_de_gracias_tambien_es_exito():
    async def flujo():
        sitio = Sitio()
        sitio.poner(ASHBY, "ashby.html", {
            "<h2>Application submitted</h2>": "<h2>¡Listo!</h2>",
            "<p>Thank you for applying. We've received your application and will be in touch.</p>":
            "<p>Te escribiremos pronto.</p>",
        })  # fmt: skip
        sitio.al_enviar("https://jobs.ashbyhq.com/api/enviar", None)
        pagina = await abrir(sitio)
        try:
            await pagina.goto(ASHBY)
            p = await leer(pagina)
            datos = [{"indice": 0, "valor": "Ana Pérez"}, {"indice": 1, "valor": "ana@example.com"}]
            assert (await llenar(pagina, datos, ARCHIVOS))["ok"] is True
            previo = previo_de(p)
            await pulsar(pagina, p["sugerido"]["indice"])
            cambio = await resultado(pagina, previo)
            assert cambio["resultado"] == "exito" and cambio["senal"] == "desaparicion"
        finally:
            await cerrar(pagina)

    correr(flujo())


def test_avanzar_sin_cambios_se_reporta():
    async def flujo():
        sitio = Sitio()
        sitio.paginas[WORKDAY] = ARIA_WORKDAY
        pagina = await abrir(sitio)
        try:
            await pagina.goto(WORKDAY)
            p = await leer(pagina)
            previo = previo_de(p)
            await pulsar(pagina, p["sugerido"]["indice"])
            assert (await resultado(pagina, previo, 1000))["resultado"] == "sin_cambios"
        finally:
            await cerrar(pagina)

    correr(flujo())


MODAL_CAJON = """<!doctype html><html lang="es"><body>
<header><nav><a href="/buscar">Buscar empleos</a></nav></header>
<main>
  <input type="text" name="busqueda_fondo" aria-label="Buscar cargo">
  <button type="button">Aplicar</button>
</main>
<div role="dialog" aria-modal="true">
  <header><h2>Responde el cuestionario</h2></header>
  <div class="pregunta-turno">
    <p>¿Tienes disponibilidad inmediata?</p>
    <div class="opciones-turno">
      <label><input type="radio" id="r-si"><span>Sí</span></label>
      <label><input type="radio" id="r-no"><span>No</span></label>
    </div>
  </div>
  <footer>
    <button type="button">Cancelar</button>
    <button type="button">Enviar respuestas</button>
  </footer>
</div>
<footer>Pie global del portal</footer>
</body></html>"""


def test_modal_activo_acota_controles_y_botones_incluyendo_footer_y_agrupa_radios_sin_nombre():
    async def flujo():
        sitio = Sitio()
        sitio.paginas[ASHBY] = MODAL_CAJON
        pagina = await abrir(sitio)
        try:
            await pagina.goto(ASHBY)
            p = await leer(pagina)
            assert len(p["campos"]) == 1, p["campos"]
            assert p["campos"][0]["tipo"] == "opciones"
            assert p["campos"][0]["opciones"] == ["Sí", "No"]
            textos_botones = [b["texto"] for b in p["botones"]]
            assert "Enviar respuestas" in textos_botones
            assert "Aplicar" not in textos_botones
            assert p["sugerido"]["accion"] == "enviar"
        finally:
            await cerrar(pagina)

    correr(flujo())
