"""Corrida con detalle de ofertas: cola persistente, presupuesto, cooldown y reevaluación."""

import logging
from datetime import timedelta

import httpx
import pytest
import respx
from test_buscador import (
    AHORA,
    SECRETOS,
    URL,
    FuenteFalsa,
    IAFalsa,
    NotificadorFalso,
)

from buscador_vacantes.config import Detalle, cargar_configuracion
from buscador_vacantes.config import Fuente as ConfFuente
from buscador_vacantes.corrida import Corrida, Modo
from buscador_vacantes.estado import Estado, a_texto
from buscador_vacantes.fuentes.base import Peticion
from buscador_vacantes.ia_cliente import RespuestaIA
from buscador_vacantes.normalizar import huella

URL_DETALLE = "https://falsa.test/detalle/{id}"


class FuenteConDetalle(FuenteFalsa):
    nombre = "con_detalle"
    soporta_detalle = True

    def peticion_detalle(self, vacante):
        return Peticion(URL_DETALLE.format(id=vacante.id_fuente))

    def extraer_detalle(self, respuesta):
        return respuesta.text.strip() or None


class IAPorTexto(IAFalsa):
    """Acepta la dudosa solo si su descripción dice remoto y no presencial."""

    def __init__(self):
        super().__init__()
        self.lotes = []

    def chat_json(self, proposito, prompt, payload, **kwargs):
        self.llamadas += 1
        self.lotes.append(payload["vacantes"])
        return RespuestaIA(True, {"vacantes": [
            {"id": v["id"], "categoria": "desarrollo", "motivo": "ok",
             "aceptar": "remot" in (v["descripcion"] or "").lower()
             and "presencial" not in (v["descripcion"] or "").lower()}
            for v in payload["vacantes"]
        ]})  # fmt: skip


def oferta(id_, titulo="Practicante de Sistemas", ubicacion="Bogotá", empresa="Sezzle"):
    return {"id": id_, "titulo": titulo, "empresa": empresa, "ubicacion": ubicacion}


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    e.marcar_inicializada()
    yield e
    e.cerrar()


def hacer_config(**detalle):
    parametros = {"pausa_min_s": 0, "pausa_max_s": 0, **detalle}
    base = cargar_configuracion()
    fuentes = {
        "con_detalle": ConfFuente(presupuesto=1, reservado_nucleo=1, detalle=Detalle(**parametros))
    }
    return base.model_copy(update={"fuentes": fuentes})


@pytest.fixture
def config():
    return hacer_config()


def corrida(config, estado, modo=None, ia=None, notificador=None, reloj=lambda: AHORA, pausas=None):
    return Corrida(
        config, SECRETOS, estado, modo or Modo(),
        notificador=notificador or NotificadorFalso(), ia=ia or IAPorTexto(),
        fuentes={"con_detalle": FuenteConDetalle}, reloj=reloj,
        dormir=(pausas if pausas is not None else []).append, salida=lambda s: None,
    )  # fmt: skip


def mock_busqueda(ofertas):
    return respx.get(URL).mock(return_value=httpx.Response(200, json=ofertas))


def mock_detalle(id_, texto="Esta posición es 100% remota.", status=200, **kwargs):
    return respx.get(URL_DETALLE.format(id=id_)).mock(
        return_value=httpx.Response(status, text=texto, **kwargs)
    )


def encolar(estado, id_, horas_atras=1, **vacante):
    from buscador_vacantes.modelo import Vacante

    v = Vacante(
        fuente="con_detalle", id_fuente=id_, empresa="Sezzle", keyword="kw", ubicacion="Bogotá",
        titulo=vacante.get("titulo", "Practicante de Sistemas"),
        url=f"https://falsa.test/{id_}", publicada=AHORA - timedelta(hours=2),
    )  # fmt: skip
    desde = AHORA - timedelta(hours=horas_atras)
    estado.encolar_detalle(v, huella(v.titulo, v.empresa, v.clave), desde)
    return v


def cola(estado):
    return [v.clave for v, _, _ in estado.cola_detalle_lista(AHORA + timedelta(days=30))]


def fila_cola(estado, clave):
    fila = estado.cx.execute("SELECT * FROM pendientes_detalle WHERE clave = ?", (clave,))
    return dict(fila.fetchone())


# --- 4.1: la oferta pendiente entra a la cola ----------------------------------------------


@respx.mock
def test_oferta_sin_modalidad_queda_en_la_cola_y_no_cuenta_como_descarte(estado):
    mock_busqueda([oferta("10")])
    # Sin presupuesto de detalle, la oferta espera en la cola
    resumen = corrida(hacer_config(max_por_corrida=0), estado).ejecutar()
    assert resumen.crudas == 1
    assert sum(resumen.descartes.values()) == 0
    assert (len(resumen.aceptadas_reglas), len(resumen.dudosas), resumen.duplicadas) == (0, 0, 0)
    assert cola(estado) == ["con_detalle:10"]
    assert estado.contar_vistas() == 0
    assert resumen.detalles_en_cola == 1 and resumen.detalles_pedidos == 0


@respx.mock
def test_la_misma_oferta_en_la_corrida_siguiente_no_se_duplica(estado):
    mock_busqueda([oferta("10"), oferta("10")])  # repetida también dentro de la corrida
    config = hacer_config(max_por_corrida=0)
    primera = corrida(config, estado).ejecutar()
    assert (primera.crudas, primera.duplicadas) == (2, 1)
    segunda = corrida(config, estado).ejecutar()
    assert (segunda.crudas, segunda.duplicadas) == (2, 2)
    assert cola(estado) == ["con_detalle:10"]


@respx.mock
def test_titulo_sin_ti_se_rechaza_sin_cola_ni_detalle(estado, config):
    mock_busqueda([oferta("11", titulo="Cajera Sur de Bogotá")])
    resumen = corrida(config, estado).ejecutar()
    assert resumen.descartes["no_ti"] == 1 and cola(estado) == []
    assert resumen.detalles_pedidos == 0


@respx.mock
def test_lo_declarado_presencial_se_rechaza_sin_detalle(estado, config):
    mock_busqueda([oferta("12", ubicacion="Bogotá (Presencial)")])
    resumen = corrida(config, estado).ejecutar()
    assert resumen.descartes["presencial_fuera"] == 1 and cola(estado) == []


@respx.mock
def test_con_detalle_apagado_se_rechaza_como_antes(estado):
    mock_busqueda([oferta("10")])
    resumen = corrida(hacer_config(activo=False), estado).ejecutar()
    assert resumen.descartes["presencial_fuera"] == 1 and cola(estado) == []


# --- 4.2: resolución de la cola --------------------------------------------------------------


@respx.mock
def test_con_presupuesto_2_y_5_en_cola_se_piden_las_2_mas_antiguas(estado):
    mock_busqueda([])
    for id_, horas in (("a", 5), ("b", 1), ("c", 4), ("d", 2), ("e", 3)):
        encolar(estado, id_, horas)
    rutas = {id_: mock_detalle(id_) for id_ in "abcde"}
    pausas = []
    resumen = corrida(hacer_config(max_por_corrida=2, pausa_min_s=6, pausa_max_s=12), estado,
                      pausas=pausas).ejecutar()  # fmt: skip
    pedidas = [id_ for id_, ruta in rutas.items() if ruta.called]
    assert pedidas == ["a", "c"]  # las dos más antiguas
    assert resumen.detalles_pedidos == 2
    assert sorted(cola(estado)) == ["con_detalle:b", "con_detalle:d", "con_detalle:e"]
    # Una sola pausa del detalle (6 a 12 s), entre las dos peticiones
    assert len([p for p in pausas if 6 <= p <= 12]) == 1


@respx.mock
def test_un_429_corta_el_paso_deja_la_cola_intacta_y_aplica_el_cooldown(estado):
    mock_busqueda([])
    for id_, horas in (("a", 3), ("b", 2), ("c", 1)):
        encolar(estado, id_, horas)
    rutas = {id_: mock_detalle(id_, status=429, headers={"Retry-After": "3600"}) for id_ in "abc"}
    resumen = corrida(hacer_config(max_por_corrida=3), estado).ejecutar()
    assert [r.called for r in rutas.values()] == [True, False, False]
    assert sorted(cola(estado)) == ["con_detalle:a", "con_detalle:b", "con_detalle:c"]
    intacta = fila_cola(estado, "con_detalle:a")
    assert (intacta["intentos"], intacta["proximo_intento"]) == (0, None)
    assert intacta["ultimo_error"] is None
    fila = estado.cx.execute("SELECT cooldown_hasta FROM fuentes_estado").fetchone()
    assert fila["cooldown_hasta"] == a_texto(AHORA + timedelta(hours=2))
    assert resumen.detalles_pedidos == 1 and resumen.detalles_fallidos == 1


@respx.mock
def test_en_cooldown_no_se_piden_detalles(estado, config):
    mock_busqueda([])
    encolar(estado, "a")
    ruta = mock_detalle("a")
    estado.cx.execute(
        "INSERT INTO fuentes_estado(fuente, cooldown_hasta) VALUES ('con_detalle', ?)",
        (a_texto(AHORA + timedelta(hours=1)),),
    )
    resumen = corrida(config, estado).ejecutar()
    assert not ruta.called and cola(estado) == ["con_detalle:a"]
    assert "con_detalle" in resumen.omitidas


@respx.mock
def test_remoto_en_el_detalle_de_otra_ciudad_llega_a_la_ia_con_la_condicion(estado, config):
    mock_busqueda([oferta("20", ubicacion="Medellín, Antioquia")])
    mock_detalle("20", "Buscamos practicante. Esta posición es 100% remota para Colombia.")
    ia, notificador = IAPorTexto(), NotificadorFalso()
    resumen = corrida(config, estado, ia=ia, notificador=notificador).ejecutar()
    [item] = ia.lotes[0]
    assert item["exige_modalidad"] == "remoto o híbrido"
    assert "100% remota" in item["descripcion"]
    assert (resumen.detalles_pedidos, resumen.detalles_recuperadas) == (1, 1)
    assert resumen.enviadas == 1 and "Practicante de Sistemas" in notificador.mensajes[0][1]
    assert cola(estado) == []  # sale de la cola al terminar de publicarse


@respx.mock
def test_oferta_con_presencial_en_el_detalle_se_rechaza(estado, config):
    mock_busqueda([oferta("21", ubicacion="Bogotá")])
    mock_detalle("21", "El trabajo es presencial en nuestras oficinas.")
    ia, notificador = IAPorTexto(), NotificadorFalso()
    resumen = corrida(config, estado, ia=ia, notificador=notificador).ejecutar()
    assert resumen.enviadas == 0 and notificador.mensajes == []
    assert (resumen.ia_aceptadas, resumen.ia_rechazadas) == (0, 1)
    assert cola(estado) == []  # resuelta: la IA ya la rechazó


@respx.mock
def test_detalle_con_presencial_declarado_se_rechaza_por_reglas(estado, config):
    mock_busqueda([])
    encolar(estado, "30")
    mock_detalle("30", "Modalidad presencial. Sede en Bogotá.")
    resumen = corrida(config, estado).ejecutar()
    # Sin remoto ni híbrido en el texto, la IA decide; aquí la IA falsa la rechaza
    assert resumen.enviadas == 0 and cola(estado) == []


@respx.mock
def test_oferta_cerrada_sale_de_la_cola_y_queda_contada(estado, config, caplog):
    mock_busqueda([])
    encolar(estado, "40", titulo="Practicante Cerrado")
    mock_detalle("40", status=404)
    with caplog.at_level(logging.INFO, logger="buscador"):
        resumen = corrida(config, estado).ejecutar()
    assert cola(estado) == [] and resumen.detalles_cerradas == 1
    assert "Practicante Cerrado" in caplog.text and "con_detalle:40" in caplog.text


@respx.mock
def test_un_fallo_reintenta_tras_la_espera(estado):
    mock_busqueda([])
    encolar(estado, "50")
    ruta = mock_detalle("50", status=503)
    config = hacer_config(espera_reintento_min=30)
    resumen = corrida(config, estado).ejecutar()
    assert resumen.detalles_fallidos == 1 and cola(estado) == ["con_detalle:50"]
    fila = fila_cola(estado, "con_detalle:50")
    assert (fila["intentos"], fila["ultimo_error"]) == (1, "servidor")
    # Una corrida a los 10 minutos no reintenta
    corrida(config, estado, reloj=lambda: AHORA + timedelta(minutes=10)).ejecutar()
    assert ruta.call_count == 1
    # A los 31 minutos sí, y esta vez responde bien
    ruta.mock(return_value=httpx.Response(200, text="100% remoto"))
    corrida(config, estado, reloj=lambda: AHORA + timedelta(minutes=31)).ejecutar()
    assert ruta.call_count == 2 and cola(estado) == []


@respx.mock
def test_200_sin_descripcion_deja_la_oferta_en_la_cola(estado, config):
    mock_busqueda([])
    encolar(estado, "60")
    mock_detalle("60", "   ")
    resumen = corrida(config, estado).ejecutar()
    assert resumen.detalles_fallidos == 1
    assert fila_cola(estado, "con_detalle:60")["ultimo_error"] == "cambio_html"


@respx.mock
def test_detalle_guardado_se_reutiliza_si_la_oferta_reaparece(estado, config):
    mock_busqueda([oferta("70", ubicacion="Medellín")])
    ruta = mock_detalle("70", "Posición remota en Colombia.")
    corrida(config, estado, ia=IAPorTexto()).ejecutar()
    assert ruta.call_count == 1
    assert estado.leer_detalle("con_detalle:70") == "Posición remota en Colombia."
    # La oferta ya se publicó: reaparece como duplicada, sin pedir otra vez el detalle
    resumen = corrida(config, estado).ejecutar()
    assert ruta.call_count == 1 and resumen.duplicadas == 1


# --- 4.3: ninguna oferta se pierde -------------------------------------------------------------


class Interrupcion(BaseException):  # noqa: N818
    pass


@respx.mock
def test_interrumpida_tras_pedir_el_detalle_no_pierde_la_oferta(estado, config, monkeypatch):
    mock_busqueda([])
    encolar(estado, "80", titulo="Practicante de Sistemas")
    ruta = mock_detalle("80", "Trabajo 100% remoto en Colombia.")

    def explotar(self, *args, **kwargs):
        raise Interrupcion

    with monkeypatch.context() as m:
        m.setattr(Corrida, "_reevaluar", explotar)
        with pytest.raises(Interrupcion):
            corrida(config, estado).ejecutar()
    assert cola(estado) == ["con_detalle:80"]  # sigue en la cola
    assert estado.leer_detalle("con_detalle:80") is not None  # y la descripción quedó guardada
    # La corrida siguiente la resuelve sin volver a pedir el detalle
    notificador = NotificadorFalso()
    resumen = corrida(config, estado, notificador=notificador).ejecutar()
    assert ruta.call_count == 1
    assert resumen.enviadas == 1 and cola(estado) == []


@respx.mock
def test_interrumpida_antes_de_publicar_deja_la_oferta_en_la_cola(estado, config, monkeypatch):
    mock_busqueda([])
    encolar(estado, "81")
    mock_detalle("81", "Trabajo 100% remoto en Colombia.")
    monkeypatch.setattr(
        Corrida, "_publicar", lambda self, resumen: (_ for _ in ()).throw(Interrupcion())
    )
    with pytest.raises(Interrupcion):
        corrida(config, estado).ejecutar()
    assert cola(estado) == ["con_detalle:81"]
    assert estado.contar_vistas() == 0


@respx.mock
def test_oferta_con_mas_de_48_horas_sale_como_vencida_con_log(estado, config, caplog):
    mock_busqueda([])
    encolar(estado, "90", horas_atras=49, titulo="Practicante Olvidado")
    encolar(estado, "91", horas_atras=47)
    ruta_vieja, ruta_nueva = mock_detalle("90"), mock_detalle("91", status=503)
    with caplog.at_level(logging.WARNING, logger="buscador"):
        resumen = corrida(config, estado).ejecutar()
    assert not ruta_vieja.called and ruta_nueva.called
    assert resumen.detalles_vencidas == 1
    assert cola(estado) == ["con_detalle:91"]
    assert "Practicante Olvidado" in caplog.text and "con_detalle" in caplog.text
    assert "vencida" in caplog.text


# --- 4.4: métricas, dry-run y seed -------------------------------------------------------------


@respx.mock
def test_las_cifras_de_detalle_se_cuentan_y_se_guardan(estado, config, caplog):
    mock_busqueda([])
    encolar(estado, "1", horas_atras=6)  # recuperada
    encolar(estado, "2", horas_atras=5)  # cerrada
    encolar(estado, "3", horas_atras=4)  # fallida
    encolar(estado, "4", horas_atras=60)  # vencida
    encolar(estado, "5", horas_atras=1)  # sin presupuesto: sigue en cola
    mock_detalle("1", "Trabajo remoto 100%")
    mock_detalle("2", status=410)
    mock_detalle("3", status=500)
    config = hacer_config(max_por_corrida=3)
    with caplog.at_level(logging.INFO, logger="buscador"):
        resumen = corrida(config, estado).ejecutar()
    cifras = ("pedidos", "fallidos", "recuperadas", "cerradas", "vencidas")
    esperadas = (3, 1, 1, 1, 1)
    assert tuple(getattr(resumen, f"detalles_{c}") for c in cifras) == esperadas
    assert resumen.detalles_en_cola == 2
    fila = dict(estado.cx.execute("SELECT * FROM corridas").fetchone())
    assert tuple(fila[f"detalles_{c}"] for c in cifras) == esperadas
    assert "detalles_pedidos=3" in caplog.text and "detalles_en_cola=2" in caplog.text
    # Los intentos del detalle quedan registrados como requests de la fuente
    palabras = [f["keyword"] for f in estado.cx.execute("SELECT keyword FROM intentos")]
    assert {"detalle 1", "detalle 2", "detalle 3"} <= set(palabras)


@respx.mock
def test_dry_run_lista_las_ofertas_que_irian_a_detalle_sin_pedirlas(estado, config):
    mock_busqueda([oferta("10"), oferta("11", titulo="Cajera Sur de Bogotá")])
    encolar(estado, "9", titulo="Practicante Ya En Cola")
    ruta = mock_detalle("10")
    ruta_cola = mock_detalle("9")
    lineas = []
    c = corrida(config, estado, Modo(dry_run=True))
    c.salida = lineas.append
    resumen = c.ejecutar()
    texto = "\n".join(lineas)
    assert "Irían a detalle (1 nuevas, 1 ya en cola)" in texto
    assert "Practicante de Sistemas" in texto and "Practicante Ya En Cola" in texto
    assert not ruta.called and not ruta_cola.called
    assert cola(estado) == ["con_detalle:9"]  # la cola no se toca
    assert resumen.detalles_pedidos == 0


@respx.mock
def test_seed_registra_las_pendientes_como_vistas(estado, config):
    estado.cx.execute("DELETE FROM kv")
    mock_busqueda([oferta("10")])
    ruta = mock_detalle("10")
    resumen = corrida(config, estado, Modo(seed=True)).ejecutar()
    assert resumen.sembradas == 1 and estado.contar_vistas() == 1
    assert cola(estado) == [] and not ruta.called
    # Tras sembrar, la oferta ya está vista: no vuelve a la cola
    resumen = corrida(config, estado).ejecutar()
    assert cola(estado) == [] and resumen.duplicadas == 1


@respx.mock
def test_linea_de_log_conserva_los_requests_por_fuente(estado, config, caplog):
    mock_busqueda([oferta("10")])
    mock_detalle("10", "100% remoto en Colombia")
    with caplog.at_level(logging.INFO, logger="buscador"):
        corrida(config, estado).ejecutar()
    assert "requests={'con_detalle': [200]}" in caplog.text
    assert "detalles_recuperadas=1" in caplog.text
