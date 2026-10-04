import json
import logging
from datetime import datetime, timedelta

import httpx
import pytest
import respx

import buscador
from buscador import Corrida, Modo, es_sin_red
from config import Fuente as ConfFuente
from config import Secretos, cargar_configuracion
from estado import Estado, EstadoNoInicializado
from fechas import ZONA
from fuentes.base import Fuente, Intento, Peticion, TipoError
from ia_cliente import RespuestaIA
from modelo import Vacante
from notificador_telegram import ResultadoEnvio

AHORA = datetime(2026, 10, 3, 10, 0, tzinfo=ZONA)
URL = "https://falsa.test/buscar"
SECRETOS = Secretos(telegram_bot_token="1:x", telegram_chat_id="-100REAL",
                    telegram_chat_prueba="-100PRUEBA", deepseek_api_key="sk-x")  # fmt: skip

OFERTAS = [
    {"id": "1", "titulo": "Aprendiz SENA Desarrollo de Software", "empresa": "Redeban"},
    {"id": "2", "titulo": "Desarrollador Java Senior", "empresa": "Globant"},
    {"id": "3", "titulo": "Practicante Contable", "empresa": "Éxito"},
    {"id": "4", "titulo": "Analista Junior", "empresa": "Bancolombia"},  # dudosa
    {"id": "5", "titulo": "QA Junior", "empresa": "Lima Tech", "ubicacion": "Lima, Perú"},
    {"id": "6", "titulo": "Soporte IT Junior", "empresa": "Viejo", "dias": 20},
]


class FuenteFalsa(Fuente):
    nombre = "falsa"

    def construir_peticion(self, keyword):
        return Peticion(URL, params={"q": keyword})

    def parsear(self, respuesta, keyword, ahora):
        return [
            Vacante(
                fuente=self.nombre, id_fuente=o["id"], titulo=o["titulo"], empresa=o["empresa"],
                url=f"https://falsa.test/{o['id']}", keyword=keyword,
                ubicacion=o.get("ubicacion", "Bogotá"),
                publicada=ahora - timedelta(days=o.get("dias", 1)),
            )
            for o in respuesta.json()
        ]  # fmt: skip


class FuenteRota(FuenteFalsa):
    nombre = "rota"

    def ejecutar(self, lote):
        raise RuntimeError("explota")


class NotificadorFalso:
    def __init__(self):
        self.mensajes = []
        self.fotos = []

    def enviar_mensaje(self, chat_id, texto):
        self.mensajes.append((chat_id, texto))
        return ResultadoEnvio(True, message_id=len(self.mensajes))

    def enviar_foto(self, chat_id, ruta):
        self.fotos.append((chat_id, ruta))
        return ResultadoEnvio(True)

    def cerrar(self):
        pass


class IAFalsa:
    def __init__(self, respuesta=None):
        self.respuesta = respuesta
        self.llamadas = 0

    def saldo(self):
        return 0.4

    def chat_json(self, proposito, prompt, payload, **kwargs):
        self.llamadas += 1
        if self.respuesta is not None:
            return self.respuesta
        return RespuestaIA(True, {"vacantes": [
            {"id": v["id"], "aceptar": True, "categoria": "otros_ti", "motivo": "TI"}
            for v in payload["vacantes"]
        ]})  # fmt: skip


@pytest.fixture
def config():
    base = cargar_configuracion()
    fuentes = {
        "falsa": ConfFuente(presupuesto=2, reservado_nucleo=1),
        "rota": ConfFuente(presupuesto=1, reservado_nucleo=1),
    }
    return base.model_copy(update={"fuentes": fuentes})


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


def corrida(config, estado, modo=None, ia=None, notificador=None, fuentes=None, salida=None):
    return Corrida(
        config, SECRETOS, estado, modo or Modo(),
        notificador=notificador or NotificadorFalso(), ia=ia or IAFalsa(),
        fuentes=fuentes or {"falsa": FuenteFalsa}, reloj=lambda: AHORA,
        dormir=lambda s: None, salida=salida or (lambda s: None),
    )  # fmt: skip


def mock_ofertas(ofertas=OFERTAS):
    return respx.get(URL).mock(return_value=httpx.Response(200, json=ofertas))


@respx.mock
def test_vacantes_nuevas_se_envian(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    notificador, ia = NotificadorFalso(), IAFalsa()
    resumen = corrida(config, estado, notificador=notificador, ia=ia).ejecutar()
    assert len(notificador.fotos) == 1  # banner del día
    [(chat, texto)] = notificador.mensajes
    assert chat == "-100REAL"
    assert "🔔 <b>2 vacantes nuevas</b>" in texto
    assert "Aprendiz SENA Desarrollo de Software" in texto
    assert "Analista Junior" in texto  # aceptada por la IA
    assert "Senior" not in texto and "Contable" not in texto
    assert ia.llamadas == 1
    assert resumen.enviadas == 2
    assert estado.contar_vistas(enviadas=True) == 2


@respx.mock
def test_metricas_de_la_corrida(config, estado, caplog):
    estado.marcar_inicializada()
    mock_ofertas()
    with caplog.at_level(logging.INFO, logger="buscador"):
        resumen = corrida(config, estado).ejecutar()
    # 2 requests × 6 ofertas; la segunda tanda son duplicadas de la primera
    assert resumen.crudas == 12
    assert dict(resumen.descartes) == {"seniority": 2, "no_ti": 2, "ubicacion": 2,
                                       "antiguedad": 2}  # fmt: skip
    assert resumen.duplicadas == 2
    fila = dict(estado.cx.execute("SELECT * FROM corridas").fetchone())
    assert fila["crudas"] == 12 and fila["duplicadas"] == 2
    assert json.loads(fila["descartes_json"]) == {
        "seniority": 2,
        "antiguedad": 2,
        "ubicacion": 2,
        "no_ti": 2,
    }
    assert (fila["dudosas"], fila["ia_aceptadas"], fila["ia_rechazadas"]) == (1, 1, 0)
    assert fila["enviadas"] == 2 and fila["fin"] is not None and fila["modo"] == "normal"
    assert "descartes={'seniority': 2, 'antiguedad': 2, 'ubicacion': 2, 'no_ti': 2}" in caplog.text
    assert "ia_aceptadas=1" in caplog.text and "enviadas=2" in caplog.text


@respx.mock
def test_sin_novedades_no_envia_nada(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    corrida(config, estado).ejecutar()
    notificador = NotificadorFalso()
    resumen = corrida(config, estado, notificador=notificador).ejecutar()
    assert notificador.mensajes == [] and notificador.fotos == []
    assert resumen.enviadas == 0


@respx.mock
def test_seed_no_envia_y_marca_todo_visto(config, estado):
    mock_ofertas()
    notificador, ia = NotificadorFalso(), IAFalsa()
    resumen = corrida(config, estado, Modo(seed=True), ia=ia, notificador=notificador).ejecutar()
    assert notificador.mensajes == [] and ia.llamadas == 0
    assert resumen.sembradas == 2  # la aceptada y la dudosa
    assert estado.contar_vistas() == 2 and estado.contar_vistas(enviadas=True) == 0
    assert estado.inicializada()
    # La primera corrida real no reenvía lo sembrado
    notificador = NotificadorFalso()
    corrida(config, estado, notificador=notificador).ejecutar()
    assert notificador.mensajes == []


def test_sin_inicializar_no_envia(config, estado):
    with pytest.raises(EstadoNoInicializado):
        corrida(config, estado).ejecutar()


@respx.mock
def test_dry_run_imprime_y_no_marca(config, estado):
    mock_ofertas()
    lineas = []
    notificador = NotificadorFalso()
    corrida(config, estado, Modo(dry_run=True, fuente="falsa"), notificador=notificador,
            salida=lineas.append).ejecutar()  # fmt: skip
    salida = "\n".join(lineas)
    assert "Dry-run" in salida
    assert "HTTP 200" in salida
    assert "Crudas: 12" in salida
    assert "? Analista Junior" in salida
    assert "Aprendiz SENA Desarrollo de Software" in salida
    assert notificador.mensajes == []
    assert estado.contar_vistas() == 0


@respx.mock
def test_chat_de_prueba(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    notificador = NotificadorFalso()
    corrida(config, estado, Modo(chat_prueba=True), notificador=notificador).ejecutar()
    assert notificador.mensajes[0][0] == "-100PRUEBA"
    assert estado.contar_vistas(enviadas=True) == 0


@respx.mock
def test_ia_caida_igual_envia_las_aceptadas_por_reglas(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    notificador = NotificadorFalso()
    ia = IAFalsa(RespuestaIA(False, motivo="timeout"))
    resumen = corrida(config, estado, ia=ia, notificador=notificador).ejecutar()
    assert resumen.enviadas == 1 and resumen.pendientes == 1
    assert "Aprendiz SENA" in notificador.mensajes[0][1]


@respx.mock
def test_fuente_rota_no_detiene_las_demas(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    resumen = corrida(config, estado, fuentes={"rota": FuenteRota, "falsa": FuenteFalsa}).ejecutar()
    assert resumen.omitidas == {"rota": "error inesperado"}
    assert resumen.enviadas == 2


@respx.mock
def test_fuente_desactivada_no_recibe_requests(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    fuentes = dict(config.fuentes)
    fuentes["falsa"] = fuentes["falsa"].model_copy(update={"activa": False})
    config = config.model_copy(update={"fuentes": fuentes})
    corrida(config, estado).ejecutar()
    assert not ruta.called


@respx.mock
def test_sin_red(config, estado):
    estado.marcar_inicializada()
    respx.get(URL).mock(side_effect=httpx.ConnectError("Name or service not known"))
    resumen = corrida(config, estado).ejecutar()
    assert resumen.sin_red
    assert estado.cx.execute("SELECT sin_red FROM corridas").fetchone()[0] == 1
    assert estado.cx.execute("SELECT COUNT(*) FROM fuentes_estado WHERE cooldown_hasta "
                             "IS NOT NULL").fetchone()[0] == 0  # fmt: skip


def test_es_sin_red():
    conexion = Intento(AHORA, "a", "k", "u", tipo_error=TipoError.CONEXION)
    respuesta = Intento(AHORA, "b", "k", "u", status=503, tipo_error=TipoError.SERVIDOR)
    assert es_sin_red([conexion, conexion])
    assert not es_sin_red([conexion, respuesta])
    assert not es_sin_red([])


def test_cli_rechaza_seed_con_dry_run():
    assert buscador.main(["--seed", "--dry-run"]) == 2


def test_cli_config_invalida(tmp_path, capsys):
    ruta = tmp_path / "config.yaml"
    ruta.write_text("red: 3\n")
    assert buscador.main(["--config", str(ruta), "--dry-run"]) == 2
    assert "Configuración inválida" in capsys.readouterr().err


@respx.mock
def test_cambio_html_genera_aviso_de_incidente(config, estado):
    estado.marcar_inicializada()
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>nuevo diseño</html>"))
    notificador = NotificadorFalso()
    ia = IAFalsa(RespuestaIA(False, motivo="saldo bajo", realizada=False))
    resumen = corrida(config, estado, ia=ia, notificador=notificador).ejecutar()
    assert [i.clave for i in resumen.incidentes.nuevos] == ["falsa:cambio_html"]
    [(chat, texto)] = notificador.mensajes
    assert chat == "-100REAL"
    assert "🚨 Incidente: falsa · cambio_html" in texto
    assert "Diagnóstico IA no disponible (motivo: saldo bajo)" in texto


@respx.mock
def test_excepcion_del_reportero_no_afecta_las_vacantes(config, estado, monkeypatch, caplog):
    estado.marcar_inicializada()
    mock_ofertas()

    def explota(self, *args):
        raise RuntimeError("reportero roto")

    monkeypatch.setattr(buscador.Reportero, "notificar", explota)
    monkeypatch.setattr(buscador.Detector, "evaluar", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("detector roto")))  # fmt: skip
    notificador = NotificadorFalso()
    resumen = corrida(config, estado, notificador=notificador).ejecutar()
    assert resumen.enviadas == 2
    assert estado.contar_vistas(enviadas=True) == 2
    assert "Error en el detector o el reportero" in caplog.text
    fila = estado.cx.execute("SELECT enviadas, error FROM corridas").fetchone()
    assert fila["enviadas"] == 2 and fila["error"] is None
