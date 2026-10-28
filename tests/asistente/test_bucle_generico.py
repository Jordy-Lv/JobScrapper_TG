"""Bucle genérico del service worker (change motor-generico-autorreparable, grupo 4).

La extensión real corre en Chromium y habla con la API de prueba de test_extension.py, que en
lugar del POST /pantalla del servidor (tarea 5.1) responde con las decisiones fijas de
`ServidorFalso`. Las páginas son las copias de tests/fixtures/formularios/. Como la plataforma
«externa» llega con `postular-linkedin`, la copia de la extensión agrega una plataforma de
prueba («prueba») con los dominios de las copias y la ejecuta con `asistente.ejecutar`.
"""

# ruff: noqa: F811  (api y servidor son fixtures de test_extension)
from __future__ import annotations

import asyncio
import json

import pytest

from tests.asistente.test_extension import (  # noqa: F401
    Portales,
    abrir,
    api,
    cerrar,
    confirmar_rapido,
    correr,
    portales_magneto,
    servidor,
    trabajo_mg,
)
from tests.asistente.test_motor_generico import (
    ARIA_WORKDAY,
    ASHBY_VACANTE,
    ESPERADO,
    GH,
    WORKDAY,
    ServidorFalso,
    Sitio,
    sitio_de,
)

pytestmark = pytest.mark.navegador

PLATAFORMAS = {
    "prueba": ["greenhouse.io", "ashbyhq.com", "typeform.com", "myworkdayjobs.com",
               "empresa-prueba.com"],
}  # fmt: skip
EMPRESA = "https://empresa-prueba.com/trabajo/101"
AJENO = "https://otro-dominio.org/formulario"


def trabajo(url: str, *, pid: int = 50, motor: dict | None = None) -> dict:
    return {"id": pid, "tipo": "postular", "plataforma": "prueba", "url": url,
            "titulo": "Practicante de soporte", "actualizar_cv_portal": False,
            "motor_generico": {"respaldo_declarado": False, "max_pantallas": 12,
                               "max_pantallas_una_pregunta": 40, "max_minutos": 10,
                               **(motor or {})}}  # fmt: skip


def decide_con(servidor_falso: ServidorFalso, omitir: str | None = None):
    """Imita la decisión del servidor: respuestas del banco y el botón que sugieren las reglas.

    `omitir`: texto de un campo que se deja sin responder en la primera vuelta."""

    def decidir(cuerpo: dict) -> dict:
        respuestas = servidor_falso.decidir(cuerpo)
        if omitir and not cuerpo["correccion"]:
            respuestas = [r for r in respuestas if cuerpo["campos"][r["indice"]]["texto"] != omitir]
        sugerido = cuerpo["sugerido"]
        accion = ({"tipo": sugerido["accion"], "indice": sugerido["indice"]} if sugerido
                  else {"tipo": "respaldo", "motivo": "sin_boton"})  # fmt: skip
        return {"esperar_usuario": False, "respuestas": respuestas, "accion": accion,
                "cv_url": "/api/v1/cv/uno", "cv_nombre": "CV_Ana_Perez.pdf",
                "documentos": {"certificado_notas": {"url": "/api/v1/cv/dos",
                                                     "nombre": "Notas_Ana.pdf"}}}  # fmt: skip

    return decidir


def ejecutar(tmp_path, api, sitio: Sitio, pedido: dict, *, pruebas: dict | None = None,
             durante=None, portales: Portales | None = None):  # fmt: skip
    """Corre `asistente.ejecutar(pedido)` en el service worker y espera a que termine."""

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales or Portales(), plataformas=PLATAFORMAS)
        try:
            await nav.contexto.route("https://**/*", sitio.atender)
            await nav.guardar({"pruebas": {"resultado_ms": 1500, **(pruebas or {})}})
            tarea = asyncio.create_task(nav.evaluar(f"asistente.ejecutar({json.dumps(pedido)})"))
            if durante:
                await durante(nav)
            await asyncio.wait_for(tarea, 240)
        finally:
            await cerrar(nav)

    correr(flujo())


def final(api) -> dict:
    resultados = api.de("resultado")
    assert len(resultados) == 1, resultados
    return resultados[0]


def pasos(api, prefijo: str = "") -> list[str]:
    return [p["paso"] for p in api.de("paso") if p["paso"].startswith(prefijo)]


def preparar(api, servidor_falso: ServidorFalso | None = None, **opciones) -> ServidorFalso:
    servidor_falso = servidor_falso or ServidorFalso()
    api.selectores_extra["prueba"] = {"postular": []}
    api.pantalla = decide_con(servidor_falso, **opciones)
    return servidor_falso


# --- 4.1: las copias hasta la página de gracias, con un solo envío ---------------------------


def respuestas_por_clave(servidor_falso: ServidorFalso, pantallas: list[dict]) -> dict[str, str]:
    """Lo que el servidor habría resuelto de antemano, por la clave de cada campo."""
    from buscador_vacantes.asistente.recetas import clave_campo

    resueltas = {}
    for cuerpo in pantallas:
        for r in servidor_falso.decidir(cuerpo):
            campo = cuerpo["campos"][r["indice"]]
            texto = campo["opciones"][r["opcion"]] if "opcion" in r else r["valor"]
            resueltas[clave_campo(campo["nombre"], campo["texto"])] = texto
    return resueltas


def completas(pantallas: list[dict], resueltas: dict[str, str]) -> list[dict]:
    """Las pantallas con campos cuyos campos están todos en el esquema anticipado."""
    from buscador_vacantes.asistente.recetas import clave_campo

    return [
        c for c in pantallas
        if c["campos"] and all(clave_campo(f["nombre"], f["texto"]) in resueltas
                               for f in c["campos"])
    ]  # fmt: skip


def test_esquema_anticipado_no_consulta_al_servidor_por_los_campos_ya_resueltos(tmp_path, api):
    datos = ESPERADO["copias"]["typeform"]
    servidor_falso = preparar(api)
    ejecutar(tmp_path / "primera", api, sitio_de("typeform"), trabajo(datos["inicio"]))
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    consultadas = api.de("pantalla")
    resueltas = respuestas_por_clave(servidor_falso, consultadas)
    resueltas_de_antemano = completas(consultadas, resueltas)
    assert resueltas_de_antemano  # el servidor sabe responder varias pantallas del formulario
    api.llamadas.clear()
    # Segunda vuelta: el trabajo trae las respuestas que el servidor resolvió al tocar ⚡
    sitio = sitio_de("typeform")
    pedido = {**trabajo(datos["inicio"], pid=51), "esquema": {"respuestas": resueltas}}
    ejecutar(tmp_path / "segunda", api, sitio, pedido)
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    assert sitio.contados(datos["envio_final"]) == 1 and len(api.de("envio")) == 1
    # Solo se consulta por lo que no estaba en el esquema
    nuevas = api.de("pantalla")
    assert len(nuevas) == len(consultadas) - len(resueltas_de_antemano)
    assert not [c for c in completas(nuevas, resueltas)]
    anticipadas = [p for p in api.de("paso") if "esquema anticipado" in (p["detalle"] or "")]
    assert len(anticipadas) == len(resueltas_de_antemano)
    assert api.de("tomar") and not api.de("verificacion")


def test_esquema_anticipado_con_un_campo_que_no_esta_consulta_al_servidor(tmp_path, api):
    from buscador_vacantes.asistente.recetas import clave_campo

    datos = ESPERADO["copias"]["typeform"]
    servidor_falso = preparar(api)
    ejecutar(tmp_path / "primera", api, sitio_de("typeform"), trabajo(datos["inicio"]))
    consultadas = api.de("pantalla")
    resueltas = respuestas_por_clave(servidor_falso, consultadas)
    antes = completas(consultadas, resueltas)
    quitada = clave_campo(antes[0]["campos"][0]["nombre"], antes[0]["campos"][0]["texto"])
    del resueltas[quitada]  # el servidor no resolvió ese campo
    api.llamadas.clear()
    pedido = {**trabajo(datos["inicio"], pid=52), "esquema": {"respuestas": resueltas}}
    ejecutar(tmp_path / "segunda", api, sitio_de("typeform"), pedido)
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    despues = completas(consultadas, resueltas)
    assert len(despues) == len(antes) - 1
    assert len(api.de("pantalla")) == len(consultadas) - len(despues)


@pytest.mark.parametrize("copia", ["greenhouse", "ashby", "typeform"])
def test_las_copias_llegan_a_la_pagina_de_gracias_con_un_solo_envio(tmp_path, api, copia):
    datos = ESPERADO["copias"][copia]
    sitio = sitio_de(copia)
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(datos["inicio"]))
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    assert sitio.contados(datos["envio_final"]) == 1
    assert len(api.de("envio")) == 1
    # Un paso por pantalla (la de gracias no cuenta), sin ningún valor escrito
    registradas = pasos(api, "pantalla_")
    assert registradas == [f"pantalla_{i}" for i in range(1, len(registradas) + 1)]
    assert len(registradas) == len(api.de("pantalla"))  # la de gracias la ve el resultado
    historial = json.dumps(api.de("paso"))
    for valor in ("Ana Pérez", "ana@example.com", "3001234567", "Medellín"):
        assert valor not in historial, valor
    assert api.de("tomar") and not api.de("verificacion")
    # Las reglas se pidieron una vez y quedaron en el almacenamiento
    assert len(api.de("motor_generico")) == 1


@pytest.mark.parametrize("copia", ["greenhouse", "ashby", "typeform"])
def test_el_ensayo_llena_todo_y_se_detiene_sin_registrar_ni_contar_ningun_envio(
    tmp_path, api, copia
):
    datos = ESPERADO["copias"][copia]
    sitio = sitio_de(copia)
    preparar(api)
    ejecutar(tmp_path, api, sitio, {**trabajo(datos["inicio"]), "ensayo": True})
    resultado = final(api)
    assert resultado["estado"] == "ensayada", [resultado, pasos(api)]
    assert resultado["motivo"].startswith("boton:")
    assert sitio.posts == [] and not api.de("envio")
    assert "ensayo_boton" in pasos(api) and "ensayo_trabado" not in pasos(api)


def test_un_ensayo_que_no_llega_al_boton_dice_en_que_pantalla_se_trabo(tmp_path, api):
    sitio = sitio_de("greenhouse")
    api.selectores_extra["prueba"] = {"postular": []}
    api.pantalla = lambda cuerpo: {"accion": {"tipo": "respaldo", "motivo": "sin_boton"}}
    ejecutar(tmp_path, api, sitio, {**trabajo(GH), "ensayo": True})
    assert final(api)["estado"] != "enviada"
    [trabado] = [p for p in api.de("paso") if p["paso"] == "ensayo_trabado"]
    assert trabado["detalle"].startswith("pantalla 1:") and not api.de("envio")


def test_el_envio_se_registra_antes_del_clic(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    posts_al_registrar = []
    api.al_envio = lambda: posts_al_registrar.append(len(sitio.posts))
    ejecutar(tmp_path, api, sitio, trabajo(GH))
    assert posts_al_registrar == [0]
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    ordenadas = [r for r, _ in api.llamadas if r in ("pantalla", "envio", "resultado")]
    assert ordenadas == ["pantalla", "envio", "resultado"]


def test_la_pantalla_lleva_el_esquema_sin_valores(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(GH))
    cuerpo = api.de("pantalla")[0]
    assert cuerpo["numero"] == 1 and cuerpo["clase"] == "formulario"
    assert cuerpo["idioma"] == "en" and cuerpo["correccion"] is False
    assert cuerpo["campos"][0]["texto"] == "First Name"
    assert cuerpo["sugerido"]["accion"] == "enviar"
    assert {"elementos", "encabezados", "avisos"} <= set(cuerpo["resumen"])
    assert "Ana" not in json.dumps(cuerpo)  # el CV y las respuestas llegan después


def test_el_cv_se_adjunta_en_el_campo_etiquetado(tmp_path, api):
    sitio = sitio_de("ashby")
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(ASHBY_VACANTE))
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    adjunto = next(p for p in api.de("paso") if p["paso"] == "cv_adjunto")
    assert adjunto["detalle"] == "CV_Ana_Perez.pdf"


def test_sin_decision_del_servidor_no_envia_nada(tmp_path, api):
    """Mientras /pantalla no exista (404) el bucle se detiene antes de tocar el formulario."""
    sitio = sitio_de("greenhouse")
    api.selectores_extra["prueba"] = {"postular": []}
    api.pantalla = lambda cuerpo: {}  # sin acción: no hay botón que pulsar
    ejecutar(tmp_path, api, sitio, trabajo(GH))
    resultado = final(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert not api.de("envio") and sitio.posts == []


# --- 4.1: topes ------------------------------------------------------------------------------


def test_tope_de_pantallas(tmp_path, api):
    sitio = sitio_de("ashby")
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(ASHBY_VACANTE, motor={"max_pantallas": 1}))
    resultado = final(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert "más de 1 pantallas" in resultado["motivo"]
    assert not api.de("envio") and sitio.posts == []


def test_una_pregunta_por_pantalla_tiene_su_propio_tope(tmp_path, api):
    sitio = sitio_de("typeform")
    preparar(api)
    motor = {"max_pantallas": 2, "max_pantallas_una_pregunta": 4}
    ejecutar(tmp_path, api, sitio, trabajo(ESPERADO["copias"]["typeform"]["inicio"], motor=motor))
    resultado = final(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert "más de 4 pantallas" in resultado["motivo"]
    assert len(api.de("pantalla")) == 4


def test_tope_de_minutos(tmp_path, api):
    sitio = sitio_de("ashby")
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(ASHBY_VACANTE, motor={"max_minutos": 0.00001}))
    resultado = final(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert "minutos" in resultado["motivo"] and not api.de("pantalla")


def test_la_misma_pantalla_tres_veces_corta_el_bucle(tmp_path, api):
    sitio = Sitio()
    sitio.paginas[WORKDAY] = ARIA_WORKDAY  # «Siguiente» no hace nada
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(WORKDAY), pruebas={"resultado_ms": 800})
    resultado = final(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert "3 veces" in resultado["motivo"] and "aria-haspopup" in resultado["html"]
    assert pasos(api, "pantalla_") == ["pantalla_1", "pantalla_2", "pantalla_3"]
    assert len(api.de("pantalla")) == 2 and not api.de("envio")


# --- 4.1: error de validación, sin señal y estado en chrome.storage ------------------------------


def test_un_error_de_validacion_se_corrige_una_sola_vez_sin_otro_envio(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api, omitir="Email")  # la primera vuelta deja el correo vacío
    ejecutar(tmp_path, api, sitio, trabajo(GH))
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    cuerpos = api.de("pantalla")
    assert [c["clase"] for c in cuerpos] == ["formulario", "error"]
    assert [c["correccion"] for c in cuerpos] == [False, True]
    assert len(api.de("envio")) == 1  # la corrección no registra un segundo envío
    assert sitio.contados("https://job-boards.greenhouse.io/prueba/jobs/101/enviar") == 1


def test_un_error_que_persiste_no_se_corrige_dos_veces(tmp_path, api):
    sitio = sitio_de("greenhouse")
    servidor_falso = preparar(api)
    base = api.pantalla

    def sin_correo(cuerpo):
        decision = base(cuerpo)
        decision["respuestas"] = [r for r in decision["respuestas"]
                                  if cuerpo["campos"][r["indice"]]["texto"] != "Email"]  # fmt: skip
        return decision

    api.pantalla = sin_correo
    ejecutar(tmp_path, api, sitio, trabajo(GH))
    resultado = final(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert "errores" in resultado["motivo"]
    assert len(api.de("pantalla")) == 2 and len(api.de("envio")) == 1
    assert sitio.posts == [] and servidor_falso.pantallas


PAGINA_MUDA = """<!doctype html><html lang="en"><body><main><h1>Apply</h1>
<form onsubmit="return false"><label for="n">Full name</label><input id="n" name="n" required>
<button type="submit">Submit application</button></form></main></body></html>"""


def test_envio_sin_ninguna_senal_queda_incierta(tmp_path, api):
    sitio = Sitio()
    sitio.paginas[GH] = PAGINA_MUDA.replace("required", "")
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(GH), pruebas={"resultado_ms": 1200})
    resultado = final(api)
    assert resultado["estado"] == "incierta"
    assert len(api.de("envio")) == 1 and len(api.de("pantalla")) == 1  # no se reintenta


def test_el_estado_del_bucle_queda_en_el_almacenamiento_y_se_borra_al_terminar(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    api.demora_pantalla = 1.5
    visto = {}

    async def durante(nav):
        for _ in range(100):
            guardado = await nav.almacenamiento("bucle_generico")
            if guardado and (guardado["bucle"] or {}).get("pantallas") == 1:
                visto.update(guardado)
                return
            await asyncio.sleep(0.1)

    ejecutar(tmp_path, api, sitio, trabajo(GH), durante=durante)
    assert visto["trabajo"]["id"] == 50 and visto["envio"] is False
    assert visto["tabId"] and visto["bucle"]["pantallas"] == 1
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]


def estado_guardado(pedido: dict, id_pestana: int, *, envio: bool) -> str:
    estado = {"tabId": id_pestana, "trabajo": pedido, "envio": envio, "bucle": None}
    guardado = f"{{...{json.dumps(estado)}, inicio: Date.now()}}"
    return f"chrome.storage.local.set({{bucle_generico: {guardado}}})"


def retomar(tmp_path, api, sitio: Sitio, pedido: dict, *, envio: bool):
    """Un worker «reiniciado»: la pestaña sigue abierta y el estado está en el almacenamiento."""

    async def flujo():
        nav = await abrir(tmp_path, api.url, Portales(), plataformas=PLATAFORMAS)
        try:
            await nav.contexto.route("https://**/*", sitio.atender)
            await nav.guardar({"pruebas": {"resultado_ms": 1500}})
            pagina = await nav.contexto.new_page()
            await pagina.goto(pedido["url"])
            id_pestana = await nav.evaluar(
                f"chrome.tabs.query({{}}).then(ts => ts.find(t => t.url === {json.dumps(GH)}).id)"
            )
            await nav.evaluar(estado_guardado(pedido, id_pestana, envio=envio))
            await asyncio.wait_for(nav.evaluar("asistente.retomarBucle()"), 240)
            cerrada = await nav.evaluar(
                f"chrome.tabs.get({id_pestana}).then(() => false, () => true)"
            )
            return cerrada, await nav.almacenamiento("bucle_generico")
        finally:
            await cerrar(nav)

    return correr(flujo())


def test_un_worker_reiniciado_antes_del_envio_retoma_la_pantalla(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    cerrada, guardado = retomar(tmp_path, api, sitio, trabajo(GH), envio=False)
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    assert "retomar" in pasos(api) and cerrada and guardado is None
    assert len(api.de("envio")) == 1 and sitio.contados(GH + "/enviar") == 1


def test_un_worker_reiniciado_despues_del_envio_no_retoma_nada(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    cerrada, guardado = retomar(tmp_path, api, sitio, trabajo(GH), envio=True)
    assert not api.llamadas or not api.de("pantalla")
    assert not api.de("resultado") and not api.de("envio") and sitio.posts == []
    assert cerrada and guardado is None


# --- 4.2: iframes ------------------------------------------------------------------------------


def sitio_con_iframe() -> Sitio:
    sitio = sitio_de("greenhouse")
    sitio.paginas[EMPRESA] = (
        '<!doctype html><html lang="en"><body><h1>Careers</h1><p>Open roles.</p>'
        f'<iframe src="{AJENO}" width="600" height="300"></iframe>'
        f'<iframe src="{GH}" width="1000" height="2400"></iframe></body></html>'
    )
    campos = "".join(f'<label>Campo ajeno {i}<input name="a{i}"></label>' for i in range(8))
    sitio.paginas[AJENO] = f"<!doctype html><html><body><form>{campos}</form></body></html>"
    return sitio


def test_el_formulario_incrustado_en_un_iframe_se_completa_dentro_del_marco(tmp_path, api):
    sitio = sitio_con_iframe()
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(EMPRESA))
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    cuerpo = api.de("pantalla")[0]
    assert cuerpo["url"] == GH and cuerpo["campos"][0]["texto"] == "First Name"
    # El iframe de otro dominio (con más campos) se trató como si no existiera
    assert "ajeno" not in json.dumps(api.de("pantalla"))
    assert sitio.contados(GH + "/enviar") == 1 and len(api.de("envio")) == 1


def test_una_pagina_sin_marcos_permitidos_no_se_toca(tmp_path, api):
    sitio = Sitio()
    sitio.poner(AJENO, "greenhouse.html")
    preparar(api)
    ejecutar(tmp_path, api, sitio, trabajo(AJENO))
    resultado = final(api)
    assert resultado["estado"] == "formulario_desconocido"
    assert "no permitida" in resultado["motivo"] and not api.de("pantalla")


# --- 4.3: respaldo de los flujos declarados -----------------------------------------------------

# Un paso declarado que no encuentra su elemento antes del envío (el botón «Abrir formulario» ya
# no existe) y el formulario que sí está en la página
PASOS_ROTOS = {"postular": [
    {"nombre": "abrir_formulario", "accion": "clic", "selector": ["#abrir-formulario"], "ms": 500},
]}  # fmt: skip


def test_con_respaldo_declarado_un_paso_roto_sin_envio_sigue_con_el_bucle(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    api.selectores_extra["prueba"] = PASOS_ROTOS
    motor = {"respaldo_declarado": True}
    ejecutar(tmp_path, api, sitio, trabajo(GH, motor=motor))
    assert final(api)["estado"] == "enviada", [final(api), pasos(api)]
    assert "respaldo_generico" in pasos(api)
    assert len(api.de("envio")) == 1 and sitio.contados(GH + "/enviar") == 1


def test_sin_la_bandera_el_paso_roto_termina_como_antes(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    api.selectores_extra["prueba"] = PASOS_ROTOS
    ejecutar(tmp_path, api, sitio, trabajo(GH))
    assert final(api)["estado"] == "formulario_desconocido"
    assert not api.de("pantalla") and not api.de("envio")


def test_un_paso_roto_con_envio_registrado_no_pasa_al_bucle(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)
    api.selectores_extra["prueba"] = {"postular": [{**PASOS_ROTOS["postular"][0], "envia": True}]}
    ejecutar(tmp_path, api, sitio, trabajo(GH, motor={"respaldo_declarado": True}))
    assert final(api)["estado"] == "formulario_desconocido"
    assert len(api.de("envio")) == 1 and not api.de("pantalla")  # nunca un segundo envío


def test_un_fallo_de_magneto_despues_del_envio_sigue_incierta_sin_el_bucle(tmp_path, api):
    from tests.asistente.test_extension import ENVIA_SIN_MODAL

    portales = portales_magneto("mg_aplicada_sin_encuesta.html", ENVIA_SIN_MODAL)
    api.ajustar = confirmar_rapido
    pedido = {**trabajo_mg(), "motor_generico": {"respaldo_declarado": True, "max_pantallas": 12,
                                                  "max_pantallas_una_pregunta": 40,
                                                  "max_minutos": 10}}  # fmt: skip
    api.trabajos = [pedido]
    preparar(api)

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    assert final(api)["estado"] == "incierta"
    assert not api.de("pantalla") and "respaldo_generico" not in pasos(api)


def test_las_reglas_se_piden_otra_vez_solo_si_cambia_la_version(tmp_path, api):
    sitio = sitio_de("greenhouse")
    preparar(api)

    async def flujo():
        nav = await abrir(tmp_path, api.url, Portales(), plataformas=PLATAFORMAS)
        try:
            await nav.contexto.route("https://**/*", sitio.atender)
            await nav.latido()  # el latido guarda la versión de las reglas
            assert (await nav.almacenamiento("motor_generico_version")) is not None
            for pid in (51, 52):
                await nav.evaluar(f"asistente.ejecutar({json.dumps(trabajo(GH, pid=pid))})")
        finally:
            await cerrar(nav)

    correr(flujo())
    assert len(api.de("motor_generico")) == 1
    assert [r["estado"] for r in api.de("resultado")] == ["enviada", "enviada"]


def test_magneto_con_encuesta_abierta_rota_pasa_al_bucle_generico(tmp_path, api):
    """Si «Aplicar» abre una encuesta sin enviar pero cambian sus clases internas, el paso con
    `abre_sin_enviar` restablece el estado previo al envío y deja actuar a `respaldo_declarado`."""
    rota = {
        "mg_chat_questionnaire_question_question_1747a": "otra_clase_pregunta_nueva",
        "const DEMORA_CARGA = 350;": "const DEMORA_CARGA = 50;",
    }
    portales = portales_magneto("mg_chat_cuestionario.html", rota)

    def acortar(plataforma, sel):
        sel = confirmar_rapido(plataforma, sel)
        for p in sel["postular"]:
            if p.get("chat"):
                p["chat"]["espera_turno_ms"] = 600
        return sel

    api.ajustar = acortar
    pedido = {
        **trabajo_mg(),
        "motor_generico": {
            "respaldo_declarado": True,
            "max_pantallas": 6,
            "max_pantallas_una_pregunta": 10,
            "max_minutos": 5,
        },
    }
    api.trabajos = [pedido]
    preparar(api)
    api.pantalla = lambda cuerpo: {
        "esperar_usuario": False,
        "respuestas": [],
        "accion": {"tipo": "respaldo", "motivo": "sin_ia"},
    }

    async def flujo():
        nav = await abrir(tmp_path, api.url, portales)
        try:
            await nav.latido()
        finally:
            await cerrar(nav)

    correr(flujo())
    assert "respaldo_generico" in pasos(api)
    assert len(api.de("pantalla")) >= 1
