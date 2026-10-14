from datetime import datetime, timedelta

import httpx
import pytest
import respx

from buscador_vacantes.config import Fuente as ConfFuente
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

    def construir_peticion(self, keyword, pagina=1):
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
    # Una fuente genérica (presupuesto 3, pausa global): no depende de lo que traiga LinkedIn
    f = FuenteFalsa(
        ConfFuente(presupuesto=3, reservado_nucleo=2),
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


class FuentePaginada(FuenteFalsa):
    nombre = "paginada"
    soporta_paginas = True
    tamano_pagina = 2

    def construir_peticion(self, keyword, pagina=1):
        return Peticion(URL, params={"q": keyword, "p": pagina})


@pytest.fixture
def paginada(config, estado, reloj, pausas):
    conf = ConfFuente(presupuesto=8, reservado_nucleo=2, paginas_nucleo=3)
    f = FuentePaginada(
        conf, config.red, estado, corrida_id=1, dormir=pausas.append,
        aleatorio=lambda a, b: (a + b) / 2, reloj=reloj,
    )  # fmt: skip
    yield f
    f.cerrar()


def lote_paginado():
    return [Consulta(k, "nucleo", p) for k in ("a", "b") for p in (1, 2, 3)]


def responder(paginas):
    """paginas: {(keyword, página): respuesta}; lo no listado responde una página completa."""

    def manejar(request):
        clave = (request.url.params["q"], int(request.url.params["p"]))
        return paginas.get(clave, httpx.Response(200, text="oferta oferta"))

    return manejar


@respx.mock
def test_paginas_completas_continuan(paginada, pausas):
    ruta = respx.get(URL).mock(side_effect=responder({}))
    resultado = paginada.ejecutar(lote_paginado())
    assert ruta.call_count == 6
    assert [(c.keyword, c.pagina) for c in resultado.ejecutadas] == [
        ("a", 1), ("a", 2), ("a", 3), ("b", 1), ("b", 2), ("b", 3),
    ]  # fmt: skip
    assert len(pausas) == 5


@respx.mock
def test_pagina_incompleta_corta_la_palabra_clave(paginada, pausas):
    incompleta = httpx.Response(200, text="oferta")
    ruta = respx.get(URL).mock(side_effect=responder({("a", 1): incompleta}))
    resultado = paginada.ejecutar(lote_paginado())
    assert [(c.keyword, c.pagina) for c in resultado.ejecutadas] == [
        ("a", 1), ("b", 1), ("b", 2), ("b", 3),
    ]  # fmt: skip
    assert ruta.call_count == 4
    assert len(pausas) == 3  # sin pausas por las páginas omitidas


@respx.mock
def test_pagina_con_error_corta_la_palabra_clave(paginada):
    respx.get(URL).mock(side_effect=responder({("a", 2): httpx.Response(500)}))
    resultado = paginada.ejecutar(lote_paginado())
    assert [(c.keyword, c.pagina) for c in resultado.ejecutadas] == [
        ("a", 1), ("a", 2), ("b", 1), ("b", 2), ("b", 3),
    ]  # fmt: skip
    assert resultado.intentos[1].tipo_error == TipoError.SERVIDOR


# --- pausa propia de la fuente ------------------------------------------------------------


def crear_fuente(config, estado, reloj, pausas, **campos):
    conf = ConfFuente(presupuesto=3, reservado_nucleo=2, **campos)
    return FuenteFalsa(
        conf, config.red, estado, corrida_id=1, dormir=pausas.append,
        aleatorio=lambda a, b: (a + b) / 2, reloj=reloj,
    )  # fmt: skip


@respx.mock
def test_pausa_propia_de_la_fuente_manda_sobre_la_global(config, estado, reloj, pausas):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    f = crear_fuente(config, estado, reloj, pausas, pausa_min_s=20, pausa_max_s=45)
    assert (config.red.pausa_min_s, config.red.pausa_max_s) == (4, 10)
    f.ejecutar(lote(3))
    assert pausas == [32.5, 32.5]  # el punto medio de 20-45 s, no el de 4-10 s
    f.cerrar()


@respx.mock
def test_pausa_propia_se_sortea_en_su_rango(config, estado, reloj, pausas):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    rangos = []
    f = crear_fuente(config, estado, reloj, pausas, pausa_min_s=20, pausa_max_s=45)
    f.aleatorio = lambda a, b: rangos.append((a, b)) or a
    f.ejecutar(lote(2))
    assert rangos == [(20, 45)]
    f.cerrar()


@respx.mock
def test_sin_pausa_propia_usa_el_rango_global(config, estado, reloj, pausas):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    rangos = []
    f = crear_fuente(config, estado, reloj, pausas)
    f.aleatorio = lambda a, b: rangos.append((a, b)) or a
    f.ejecutar(lote(2))
    assert rangos == [(4, 10)]
    f.cerrar()


# --- Retry-After ------------------------------------------------------------------------------


def bloquear(fuente, retry_after=None, status=429):
    cabeceras = {} if retry_after is None else {"Retry-After": retry_after}
    respx.get(URL).mock(return_value=httpx.Response(status, headers=cabeceras))
    return fuente.ejecutar(lote(1))


@respx.mock
def test_retry_after_mayor_que_el_escalon_alarga_el_cooldown(fuente, reloj):
    resultado = bloquear(fuente, "14400")  # 4 h contra un escalón de 2 h
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=4)


@respx.mock
def test_retry_after_menor_que_el_escalon_se_ignora(fuente, reloj):
    resultado = bloquear(fuente, "60")
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=2)


@respx.mock
def test_retry_after_absurdo_queda_en_el_tope(fuente, reloj):
    resultado = bloquear(fuente, str(5 * 24 * 3600))  # 5 días, tope de 24 h
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=24)


@respx.mock
def test_retry_after_con_fecha_http(fuente, reloj):
    # El reloj marca 2026-10-03 10:00 en Bogotá (UTC-5) = 15:00 GMT
    resultado = bloquear(fuente, "Sat, 03 Oct 2026 20:00:00 GMT")  # 5 h
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=5)


@respx.mock
@pytest.mark.parametrize("valor", ["pronto", "-30", "0", "Sat, 03 Oct 2026 01:00:00 GMT"])
def test_retry_after_ilegible_o_pasado_se_ignora(fuente, reloj, valor):
    resultado = bloquear(fuente, valor)
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=2)


@respx.mock
@pytest.mark.parametrize("status", [403, 999])
def test_retry_after_aplica_tambien_a_403_y_999(fuente, reloj, status):
    resultado = bloquear(fuente, "14400", status)
    assert resultado.cooldown_hasta == reloj.momento + timedelta(hours=4)


@respx.mock
def test_retry_after_no_cambia_el_escalon_ni_los_fallos(fuente, estado, reloj):
    bloquear(fuente, "14400")
    fila = fila_estado(estado)
    assert fila["escalon"] == 0 and fila["fallos_consecutivos"] == 1


def test_segundos_retry_after():
    from buscador_vacantes.fuentes.base import segundos_retry_after

    ahora = datetime(2026, 10, 3, 10, 0, tzinfo=ZONA)
    assert segundos_retry_after("120", ahora) == 120
    assert segundos_retry_after(" 90 ", ahora) == 90
    assert segundos_retry_after("Sat, 03 Oct 2026 15:01:00 GMT", ahora) == 60
    assert segundos_retry_after("inf", ahora) is None
    assert segundos_retry_after("nan", ahora) is None
    assert segundos_retry_after("", ahora) is None
    assert segundos_retry_after(None, ahora) is None


# --- ritmo adaptativo -------------------------------------------------------------------------

RITMO = {"intervalos_min": [30, 60, 120], "limpias_para_bajar": 3, "tolerancia_min": 5}


def kv(estado, campo):
    return estado.kv_obtener(f"ritmo:falsa:{campo}")


@pytest.fixture
def con_ritmo(config, estado, reloj, pausas):
    f = crear_fuente(config, estado, reloj, pausas, ritmo=RITMO)
    yield f
    f.cerrar()


@respx.mock
def test_sin_bloqueos_el_intervalo_es_el_primero_y_se_consulta_siempre(con_ritmo, estado, reloj):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    assert con_ritmo.ritmo_espera(reloj.momento) is None  # nunca se ha consultado
    con_ritmo.ejecutar(lote(1))
    assert kv(estado, "nivel") == "0"
    reloj.momento += timedelta(minutes=30)
    assert con_ritmo.ritmo_espera(reloj.momento) is None


@respx.mock
def test_un_bloqueo_sube_el_intervalo_y_la_corrida_adelantada_se_omite(con_ritmo, estado, reloj):
    bloquear(con_ritmo)
    assert kv(estado, "nivel") == "1" and kv(estado, "limpias") == "0"
    reloj.momento += timedelta(hours=2)  # termina el cooldown
    assert con_ritmo.ritmo_espera(reloj.momento) is None
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    con_ritmo.ejecutar(lote(1))
    reloj.momento += timedelta(minutes=30)
    assert con_ritmo.ritmo_espera(reloj.momento) == 60  # a los 30 min aún no toca
    reloj.momento += timedelta(minutes=26)
    assert con_ritmo.ritmo_espera(reloj.momento) is None  # 56 min: dentro de la tolerancia


@respx.mock
def test_la_tolerancia_absorbe_la_demora_del_timer(con_ritmo, estado, reloj):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    con_ritmo.ejecutar(lote(1))
    reloj.momento += timedelta(minutes=29)  # intervalo de 30 y tolerancia de 5
    assert con_ritmo.ritmo_espera(reloj.momento) is None
    estado.kv_guardar("ritmo:falsa:nivel", "1")
    reloj.momento -= timedelta(minutes=5)  # 24 min contra 60 - 5
    assert con_ritmo.ritmo_espera(reloj.momento) == 60


@respx.mock
def test_los_bloqueos_no_pasan_del_ultimo_nivel(con_ritmo, estado, reloj):
    for _ in range(5):
        bloquear(con_ritmo)
        reloj.momento += timedelta(hours=24)
    assert kv(estado, "nivel") == "2"


@respx.mock
def test_las_exitosas_seguidas_bajan_el_intervalo_un_nivel(con_ritmo, estado, reloj):
    estado.kv_guardar("ritmo:falsa:nivel", "2")
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    con_ritmo.ejecutar(lote(2))  # 2 de las 3 necesarias
    assert (kv(estado, "nivel"), kv(estado, "limpias")) == ("2", "2")
    reloj.momento += timedelta(hours=2)
    con_ritmo.ejecutar(lote(1))
    assert (kv(estado, "nivel"), kv(estado, "limpias")) == ("1", "0")  # 120 → 60
    reloj.momento += timedelta(minutes=30)
    assert con_ritmo.ritmo_espera(reloj.momento) == 60


@respx.mock
def test_un_bloqueo_reinicia_el_conteo_de_exitosas(con_ritmo, estado):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    con_ritmo.ejecutar(lote(2))
    assert kv(estado, "limpias") == "0"  # en el primer nivel no hay nada que recuperar
    estado.kv_guardar("ritmo:falsa:nivel", "1")
    con_ritmo.ejecutar(lote(2))
    assert kv(estado, "limpias") == "2"
    bloquear(con_ritmo)
    assert (kv(estado, "nivel"), kv(estado, "limpias")) == ("2", "0")


@respx.mock
def test_un_error_no_cuenta_como_exitosa_ni_reinicia(con_ritmo, estado):
    estado.kv_guardar("ritmo:falsa:nivel", "1")
    estado.kv_guardar("ritmo:falsa:limpias", "2")
    respx.get(URL).mock(return_value=httpx.Response(503))
    con_ritmo.ejecutar(lote(1))
    assert (kv(estado, "nivel"), kv(estado, "limpias")) == ("1", "2")


@respx.mock
def test_el_dry_run_no_cambia_el_estado_del_ritmo(con_ritmo, estado):
    con_ritmo.persistir_estado = False
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    con_ritmo.ejecutar(lote(2))
    bloquear(con_ritmo)
    assert [kv(estado, c) for c in ("nivel", "limpias", "ultima")] == [None, None, None]


@respx.mock
def test_sin_ritmo_configurado_no_se_omite_ni_se_guarda_nada(fuente, estado, reloj):
    respx.get(URL).mock(return_value=httpx.Response(200, text=HTML_OK))
    fuente.ejecutar(lote(1))
    assert fuente.config.ritmo is None
    assert fuente.ritmo_espera(reloj.momento) is None
    assert kv(estado, "ultima") is None
