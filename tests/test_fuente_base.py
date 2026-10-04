from datetime import datetime, timedelta

import httpx
import pytest
import respx

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import CambioHTML, Fuente, Peticion, TipoError
from buscador_vacantes.modelo import Vacante
from buscador_vacantes.rotacion import Consulta

URL = "https://empleos.ejemplo/buscar"
HTML_OK = "<html><body><div class='oferta'>Practicante</div></body></html>"


class FuenteFalsa(Fuente):
    nombre = "falsa"

    def construir_peticion(self, keyword):
        return Peticion(URL, params={"q": keyword})

    def parsear(self, respuesta, keyword, ahora):
        if "oferta" not in respuesta.text:
            raise CambioHTML("no hay div.oferta")
        return [
            Vacante(
                fuente=self.nombre,
                id_fuente=str(i),
                titulo="Practicante",
                empresa="X",
                url=f"{URL}/{i}",
                keyword=keyword,
            )
            for i in range(respuesta.text.count("oferta"))
        ]


class Reloj:
    def __init__(self):
        self.momento = datetime(2026, 10, 3, 10, 0, tzinfo=ZONA)

    def __call__(self):
        return self.momento


@pytest.fixture
def config():
    return cargar_configuracion()


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def pausas():
    return []


@pytest.fixture
def fuente(config, estado, reloj, pausas):
    f = FuenteFalsa(
        config.fuentes["linkedin"],
        config.red,
        estado,
        corrida_id=1,
        dormir=pausas.append,
        aleatorio=lambda a, b: (a + b) / 2,
        reloj=reloj,
    )
    yield f
    f.cerrar()


def lote(n=3):
    return [Consulta(f"kw{i}", "cola_larga") for i in range(n)]


def fila_estado(estado):
    return dict(estado.cx.execute("SELECT * FROM fuentes_estado WHERE fuente='falsa'").fetchone())


def intentos(estado):
    return [dict(f) for f in estado.cx.execute("SELECT * FROM intentos ORDER BY id")]


@respx.mock
def test_exito_registra_intento_y_respeta_pausas(fuente, estado, pausas, config):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    resultado = fuente.ejecutar(lote(3))
    assert len(resultado.vacantes) == 3
    assert pausas == [7.0, 7.0]  # 2 pausas entre 3 requests, rango 4-10 s
    filas = intentos(estado)
    assert len(filas) == 3
    assert filas[0]["status"] == 200 and filas[0]["items"] == 1
    assert filas[0]["keyword"] == "kw0" and filas[0]["corrida_id"] == 1
    assert filas[0]["ms"] >= 0
    assert fila_estado(estado)["ultimo_exito"] is not None
    peticion = respx.calls[0].request
    assert peticion.headers["accept-language"].startswith("es-CO")
    assert "Mozilla" in peticion.headers["user-agent"]


@respx.mock
def test_presupuesto_limita_requests(fuente):
    ruta = respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    resultado = fuente.ejecutar(lote(6))
    assert ruta.call_count == 3  # presupuesto de linkedin
    assert len(resultado.ejecutadas) == 3


@respx.mock
def test_429_cooldown_2h_y_se_detiene(fuente, estado, reloj):
    ruta = respx.get(URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "3600", "Set-Cookie": "x=1"})
    )
    resultado = fuente.ejecutar(lote(3))
    assert ruta.call_count == 1
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=2)
    assert resultado.intentos[0].tipo_error == TipoError.BLOQUEO
    assert resultado.intentos[0].cabeceras == {"retry-after": "3600"}
    assert fuente.cooldown_vigente(reloj.momento + timedelta(hours=1))
    assert fuente.cooldown_vigente(reloj.momento + timedelta(hours=2, minutes=1)) is None
    assert intentos(estado)[0]["tipo_error"] == "bloqueo"


@respx.mock
def test_bloqueo_repetido_escala_6h_y_24h(fuente, reloj):
    respx.get(URL).mock(return_value=httpx.Response(429))
    esperados = [2, 6, 24, 24]
    for horas in esperados:
        resultado = fuente.ejecutar(lote(1))
        assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=horas)
        reloj.momento = resultado.cooldown_hasta


@respx.mock
def test_exito_reinicia_el_escalon(fuente, estado, reloj):
    ruta = respx.get(URL)
    ruta.mock(return_value=httpx.Response(999))
    fuente.ejecutar(lote(1))
    reloj.momento += timedelta(hours=3)
    ruta.mock(return_value=httpx.Response(200, text=HTML_OK))
    fuente.ejecutar(lote(1))
    fila = fila_estado(estado)
    assert fila["fallos_consecutivos"] == 0 and fila["escalon"] == 0
    assert fila["cooldown_hasta"] is None
    ruta.mock(return_value=httpx.Response(403))
    resultado = fuente.ejecutar(lote(1))
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=2)


@respx.mock
def test_200_con_cf_chl_es_desafio(fuente, estado, reloj):
    cuerpo = "<html><script src='/cdn-cgi/challenge-platform/cf-chl'></script>Verificando</html>"
    respx.get(URL).mock(
        return_value=httpx.Response(200, text=cuerpo, headers={"content-type": "text/html"})
    )
    resultado = fuente.ejecutar(lote(2))
    assert resultado.vacantes == []
    assert resultado.intentos[0].tipo_error == TipoError.CAPTCHA
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=2)
    fila = intentos(estado)[0]
    assert fila["desafio"] == 1 and fila["tipo_error"] == "captcha"


@respx.mock
def test_marcador_en_pagina_con_listado_no_es_desafio(fuente):
    cuerpo = HTML_OK.replace("</body>", "<script src='https://www.google.com/recaptcha/api.js'>"
                             "</script></body>")  # fmt: skip
    respx.get(URL).mock(return_value=httpx.Response(200, text=cuerpo))
    resultado = fuente.ejecutar(lote(1))
    assert len(resultado.vacantes) == 1
    assert resultado.intentos[0].tipo_error is None
    assert resultado.cooldown_hasta is None


@respx.mock
def test_challenge_en_json_no_es_desafio(fuente):
    respx.get(URL).mock(return_value=httpx.Response(200, json={"oferta": "a challenge"}))
    resultado = fuente.ejecutar(lote(1))
    assert resultado.intentos[0].tipo_error is None
    assert resultado.cooldown_hasta is None


@respx.mock
def test_timeout_registrado_y_continua(fuente, estado):
    ruta = respx.get(URL)
    ruta.side_effect = [httpx.ReadTimeout("lento"), httpx.Response(200, text=HTML_OK)]
    resultado = fuente.ejecutar(lote(2))
    assert [i.tipo_error for i in resultado.intentos] == [TipoError.TIMEOUT, None]
    assert intentos(estado)[0]["tipo_error"] == "timeout"
    assert intentos(estado)[0]["status"] is None
    assert len(resultado.vacantes) == 1


@respx.mock
def test_error_de_conexion_sin_cooldown(fuente):
    respx.get(URL).mock(side_effect=httpx.ConnectError("Name or service not known"))
    resultado = fuente.ejecutar(lote(2))
    assert all(i.tipo_error == TipoError.CONEXION for i in resultado.intentos)
    assert not any(i.con_respuesta for i in resultado.intentos)
    assert resultado.cooldown_hasta is None


@respx.mock
def test_5xx_es_error_de_servidor(fuente):
    respx.get(URL).mock(return_value=httpx.Response(503))
    resultado = fuente.ejecutar(lote(1))
    assert resultado.intentos[0].tipo_error == TipoError.SERVIDOR
    assert resultado.cooldown_hasta is None


@respx.mock
def test_estructura_ausente_es_cambio_html(fuente):
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html><p>nuevo diseño</p></html>"))
    resultado = fuente.ejecutar(lote(1))
    assert resultado.intentos[0].tipo_error == TipoError.CAMBIO_HTML
    assert resultado.intentos[0].items == 0


@respx.mock
def test_parser_con_excepcion_no_tumba_la_corrida(fuente, monkeypatch):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    monkeypatch.setattr(fuente, "parsear", lambda *a: 1 / 0)
    resultado = fuente.ejecutar(lote(2))
    assert [i.tipo_error for i in resultado.intentos] == [TipoError.CAMBIO_HTML] * 2
