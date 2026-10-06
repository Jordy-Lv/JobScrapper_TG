import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro
from buscador_vacantes.asistente.detalle import Detalles, EstadoPagina, Ritmo, extraer, ficha_de
from buscador_vacantes.asistente.enlaces import id_corto
from buscador_vacantes.asistente.vacantes import Indice, plataforma_de_url
from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado, a_texto
from buscador_vacantes.modelo import Vacante

FIXTURES = Path(__file__).parent / "fixtures" / "detalle"
T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
HOY = date(2026, 10, 4)
URLS = {
    "computrabajo": "https://co.computrabajo.com/ofertas-de-trabajo/"
    "oferta-de-trabajo-de-aprendices-sena-en-bogota-dc-9255E004524C45BA61373E686DCF3405",
    "magneto": "https://www.magneto365.com/co/empleos/practicante-qa-tester-1626385864-5-1085855",
    "elempleo": "https://www.elempleo.com/co/ofertas-trabajo/"
    "auxiliar-de-programacion-de-servicios-de-salud-1886774213",
    "getonboard": "https://www.getonbrd.com/jobs/operador-de-monitoreo-mediastream-bogota-9f68",
    "linkedin": "https://co.linkedin.com/jobs/view/4475512580",
}


def fixture(nombre):
    return (FIXTURES / f"{nombre}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("fuente", list(URLS))
def test_cada_fixture_produce_texto(fuente):
    detalle = extraer(fixture(fuente), URLS[fuente], HOY)
    assert detalle.estado == EstadoPagina.OK
    assert len(detalle.texto) > 200


def test_validthrough_vencido_es_cerrada():
    detalle = extraer(fixture("computrabajo"), URLS["computrabajo"], date(2027, 1, 1))
    assert detalle.estado == EstadoPagina.CERRADA


def test_texto_de_oferta_finalizada_es_cerrada():
    html = "<html><body><main><h1>Oferta finalizada</h1></main></body></html>"
    assert extraer(html, URLS["computrabajo"], HOY).estado == EstadoPagina.CERRADA


@pytest.mark.parametrize(
    ("url", "plataforma"),
    [
        (URLS["computrabajo"], "computrabajo"),
        (URLS["magneto"], "magneto"),
        (URLS["linkedin"], None),
        ("https://computrabajo.com.evil.example/x", None),
    ],
)
def test_plataforma_de_url(url, plataforma):
    assert plataforma_de_url(url) == plataforma


def vac(fuente, id_fuente, url, titulo="Practicante"):
    return Vacante(
        fuente=fuente, id_fuente=id_fuente, titulo=titulo, empresa="X", url=url, keyword="k"
    )


@pytest.fixture
def entorno(tmp_path):
    ruta = tmp_path / "vacantes.db"
    estado = Estado.abrir(ruta)
    for fuente, url in URLS.items():
        estado.registrar_vista(vac(fuente, "1", url), f"h{fuente}", momento=T0, enviada=True)
    vieja = vac("linkedin", "viejo", "https://co.linkedin.com/jobs/view/1", "Vieja")
    estado.registrar_vista(vieja, "hv", momento=T0 - timedelta(days=120), enviada=True)
    prueba = vac("linkedin", "prueba", "https://co.linkedin.com/jobs/view/2", "Prueba")
    estado.registrar_vista(prueba, "hp", momento=T0, prueba=True)
    base = BaseAsistente.abrir(tmp_path / "a.db")
    ro = abrir_vacantes_ro(ruta)
    config = cargar_configuracion()
    yield base, ro, estado, config
    ro.close()
    estado.cerrar()
    base.cerrar()


def test_indice_solo_enviadas_y_dentro_de_la_retencion(entorno):
    base, ro, _, _ = entorno
    indice = Indice(base, ro, 90)
    assert indice.indexar(T0) == 5
    assert indice.obtener(id_corto("computrabajo:1")).plataforma == "computrabajo"
    assert indice.obtener(id_corto("linkedin:prueba")) is None  # solo chat de prueba
    assert indice.resolver(id_corto("linkedin:viejo"), T0) is None  # más de 90 días


def test_id_desconocido_reindexa_una_vez(entorno):
    base, ro, estado, _ = entorno
    indice = Indice(base, ro, 90)
    indice.indexar(T0)
    nueva = vac("magneto", "99", "https://www.magneto365.com/co/empleos/nueva-99", "Nueva")
    estado.registrar_vista(nueva, "hn", momento=T0 + timedelta(minutes=1), enviada=True)
    assert indice.resolver(id_corto("magneto:99"), T0 + timedelta(minutes=2)).titulo == "Nueva"
    assert indice.resolver("noexiste1234", T0) is None


def detalles(entorno):
    base, ro, _, config = entorno

    async def dormir(_):
        return None

    ritmo = Ritmo(config.asistente.detalle.intervalo_dominio_s, reloj=lambda: 0, dormir=dormir)
    return Detalles(base, ro, config.asistente.detalle, config.red, ritmo=ritmo)


def vacante(entorno, fuente):
    base, ro, _, _ = entorno
    indice = Indice(base, ro, 90)
    indice.indexar(T0)
    return indice.obtener(id_corto(f"{fuente}:1"))


@respx.mock
def test_una_sola_consulta_por_dia_compartida(entorno):
    d = detalles(entorno)
    ruta = respx.get(URLS["magneto"]).mock(
        return_value=httpx.Response(200, text=fixture("magneto"))
    )
    v = vacante(entorno, "magneto")
    primero = asyncio.run(d.obtener(v, T0))
    otra_lectura = Indice(entorno[0], entorno[1], 90).obtener(v.id_corto)
    segundo = asyncio.run(d.obtener(otra_lectura, T0 + timedelta(hours=1)))
    assert primero.estado == segundo.estado == EstadoPagina.OK
    assert ruta.call_count == 1


@respx.mock
def test_403_es_bloqueada(entorno):
    d = detalles(entorno)
    respx.get(URLS["linkedin"]).mock(return_value=httpx.Response(403))
    resultado = asyncio.run(d.obtener(vacante(entorno, "linkedin"), T0))
    assert resultado.estado == EstadoPagina.BLOQUEADA


@respx.mock
def test_404_es_cerrada(entorno):
    d = detalles(entorno)
    respx.get(URLS["elempleo"]).mock(return_value=httpx.Response(404))
    resultado = asyncio.run(d.obtener(vacante(entorno, "elempleo"), T0))
    assert resultado.estado == EstadoPagina.CERRADA


@respx.mock
def test_captcha_sin_descripcion_es_bloqueada_y_con_descripcion_no(entorno):
    d = detalles(entorno)
    pagina_captcha = "<html><body>Please complete the captcha</body></html>"
    respx.get(URLS["getonboard"]).mock(return_value=httpx.Response(200, text=pagina_captcha))
    resultado = asyncio.run(d.obtener(vacante(entorno, "getonboard"), T0))
    assert resultado.estado == EstadoPagina.BLOQUEADA
    con_recaptcha = fixture("magneto").replace("</body>", "<script>grecaptcha</script></body>")
    respx.get(URLS["magneto"]).mock(return_value=httpx.Response(200, text=con_recaptcha))
    assert asyncio.run(d.obtener(vacante(entorno, "magneto"), T0)).estado == EstadoPagina.OK


@respx.mock
def test_fuente_en_cooldown_no_hace_request(entorno):
    _, _, estado, _ = entorno
    with estado.transaccion() as cx:
        cx.execute(
            "INSERT INTO fuentes_estado(fuente, cooldown_hasta) VALUES ('computrabajo', ?)",
            (a_texto(T0 + timedelta(hours=2)),),
        )
    d = detalles(entorno)
    ruta = respx.get(URLS["computrabajo"]).mock(return_value=httpx.Response(200, text="x"))
    resultado = asyncio.run(d.obtener(vacante(entorno, "computrabajo"), T0))
    assert resultado.estado == EstadoPagina.BLOQUEADA and ruta.call_count == 0


def test_ritmo_por_dominio():
    esperas, tiempo = [], [0.0]

    async def dormir(s):
        esperas.append(s)
        tiempo[0] += s

    ritmo = Ritmo(5, reloj=lambda: tiempo[0], dormir=dormir)
    asyncio.run(ritmo.esperar_turno("a.com"))
    asyncio.run(ritmo.esperar_turno("b.com"))
    asyncio.run(ritmo.esperar_turno("a.com"))
    assert esperas == [5]


def test_ficha_del_jobposting_para_el_resumen():
    detalle = extraer(fixture("computrabajo"), URLS["computrabajo"], HOY)
    assert detalle.ficha == {
        "empresa": "Multiempleos S.A.",
        "salario": "$ 1.300.000 mensual",
        "ubicacion": "Bogotá, D.C.",
        "tipo": "Tiempo completo",
        "publicada": "2026-10-02",
        "vence": "2026-12-01",
    }


def test_ficha_con_rango_salarial_y_sin_datos():
    rango = {"baseSalary": {"value": {"minValue": 1300000, "maxValue": 1800000,
                                      "unitText": "MONTH"}}}  # fmt: skip
    assert ficha_de(rango) == {"salario": "$ 1.300.000 – $ 1.800.000 mensual"}
    assert ficha_de({"employmentType": "OTHER", "baseSalary": {"value": 0}}) == {}
