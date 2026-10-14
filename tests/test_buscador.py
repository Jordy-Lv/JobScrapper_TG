import json
import logging
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from buscador_vacantes import corrida as buscador
from buscador_vacantes import rotacion
from buscador_vacantes.config import Fuente as ConfFuente
from buscador_vacantes.config import Secretos, cargar_configuracion
from buscador_vacantes.corrida import Corrida, Modo, es_sin_red
from buscador_vacantes.estado import Estado, EstadoNoInicializado, a_texto
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import Fuente, Intento, Peticion, TipoError
from buscador_vacantes.ia_cliente import RespuestaIA
from buscador_vacantes.modelo import Categoria, Vacante
from buscador_vacantes.notificador_telegram import ResultadoEnvio

AHORA = datetime(2026, 10, 3, 10, 0, tzinfo=ZONA)
URL = "https://falsa.test/buscar"
SECRETOS = Secretos(telegram_bot_token="1:x", telegram_chat_id="-100REAL",
                    telegram_chat_prueba="-100PRUEBA", deepseek_api_key="sk-x")  # fmt: skip

OFERTAS = [
    {"id": "1", "titulo": "Aprendiz SENA Desarrollo de Software", "empresa": "Redeban"},
    {"id": "2", "titulo": "Desarrollador Java Senior", "empresa": "Globant"},
    {"id": "3", "titulo": "Auxiliar Contable", "empresa": "Éxito"},
    {"id": "4", "titulo": "Analista Junior", "empresa": "Bancolombia"},  # dudosa
    {"id": "5", "titulo": "QA Junior", "empresa": "Lima Tech", "ubicacion": "Lima, Perú"},
    {"id": "6", "titulo": "Soporte IT Junior", "empresa": "Viejo", "dias": 20},
]


class FuenteFalsa(Fuente):
    nombre = "falsa"

    def construir_peticion(self, keyword, pagina=1):
        return Peticion(URL, params={"q": keyword})

    def parsear(self, respuesta, keyword, ahora):
        return [
            Vacante(
                fuente=self.nombre, id_fuente=o["id"], titulo=o["titulo"], empresa=o["empresa"],
                url=f"https://falsa.test/{o['id']}", keyword=keyword,
                ubicacion=o.get("ubicacion", "Cartagena, Bolívar"),
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
        "lista_negra": 0,
        "seniority": 2,
        "antiguedad": 2,
        "ubicacion": 2,
        "presencial_fuera": 0,
        "call_center": 0,
        "no_ti": 2,
    }
    assert (fila["practicas_recategorizadas"], fila["practicas_rechazadas"]) == (0, 0)
    assert (fila["dudosas"], fila["ia_aceptadas"], fila["ia_rechazadas"]) == (1, 1, 0)
    assert fila["enviadas"] == 2 and fila["fin"] is not None and fila["modo"] == "normal"
    assert (
        "descartes={'lista_negra': 0, 'seniority': 2, 'antiguedad': 2, 'ubicacion': 2, "
        "'presencial_fuera': 0, 'call_center': 0, 'no_ti': 2}" in caplog.text
    )
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


# --- Regresiones de la revisión de código ---------------------------------------------------


class FuenteColgada(FuenteFalsa):
    nombre = "colgada"

    def ejecutar(self, lote):
        raise buscador._TiempoAgotado("La corrida superó 25 minutos")


def test_limite_de_tiempo_no_lo_traga_ninguna_fuente(config, estado):
    estado.marcar_inicializada()
    config = config.model_copy(update={"fuentes": {
        "colgada": ConfFuente(presupuesto=1, reservado_nucleo=1),
        "falsa": ConfFuente(presupuesto=1, reservado_nucleo=1)}})  # fmt: skip
    with pytest.raises(buscador._TiempoAgotado):
        corrida(config, estado, fuentes={"colgada": FuenteColgada, "falsa": FuenteFalsa}).ejecutar()
    fila = estado.cx.execute("SELECT fin, error FROM corridas").fetchone()
    assert fila["fin"] is not None and "_TiempoAgotado" in fila["error"]


@respx.mock
def test_dry_run_no_avanza_la_rotacion(config, estado):
    mock_ofertas()
    corrida(config, estado, Modo(dry_run=True)).ejecutar()
    assert estado.cx.execute("SELECT COUNT(*) FROM rotacion").fetchone()[0] == 0


@respx.mock
def test_sembrar_una_fuente_no_inicializa_la_base(config, estado):
    mock_ofertas()
    resumen = corrida(config, estado, Modo(seed=True, fuente="falsa")).ejecutar()
    assert resumen.sembradas > 0
    assert not estado.inicializada()


def test_deduplicar_por_clave_y_huella():
    a = Vacante(fuente="linkedin", id_fuente="1", titulo="Practicante TI", empresa="Redeban",
                url="u", keyword="k")  # fmt: skip
    b = Vacante(fuente="computrabajo", id_fuente="X", titulo="Practicante TI",
                empresa="Redeban S.A.S.", url="u", keyword="k")  # fmt: skip
    c = Vacante(fuente="linkedin", id_fuente="1", titulo="Otro", empresa="Otra", url="u",
                keyword="k")  # fmt: skip
    d = Vacante(fuente="magneto", id_fuente="7", titulo="QA Junior", empresa="Z", url="u",
                keyword="k")  # fmt: skip
    assert buscador.deduplicar([a, b, c, d]) == [a, d]


def test_subcomando_con_lock_ocupado_falla_visible(tmp_path, capsys, monkeypatch):
    from buscador_vacantes.lock import Lock

    texto = (buscador.cfg.RAIZ / "config.yaml").read_text(encoding="utf-8")
    texto = texto.replace("base_datos: data/vacantes.db", f"base_datos: {tmp_path}/v.db")
    texto = texto.replace("lock: data/buscador.lock", f"lock: {tmp_path}/b.lock")
    texto = texto.replace("logs: logs", f"logs: {tmp_path}/logs")
    ruta = tmp_path / "config.yaml"
    ruta.write_text(texto, encoding="utf-8")
    monkeypatch.setattr(buscador, "ESPERA_LOCK_RESUMEN_S", 0.2)
    with Lock(tmp_path / "b.lock"):
        codigo = buscador.main(["--config", str(ruta), "promover-prueba"])
    assert codigo == 1
    assert "No se ejecutó 'promover-prueba'" in capsys.readouterr().err
    assert buscador.main(["--config", str(ruta), "promover-prueba"]) == 0


class FuentePaginadaFalsa(FuenteFalsa):
    soporta_paginas = True
    tamano_pagina = len(OFERTAS)  # cada respuesta simulada es una página completa


def config_paginada(config):
    fuentes = {"falsa": ConfFuente(presupuesto=4, reservado_nucleo=1, paginas_nucleo=3)}
    return config.model_copy(update={"fuentes": fuentes})


@respx.mock
def test_corrida_pagina_el_nucleo(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    fuentes = {"falsa": FuentePaginadaFalsa}
    resumen = corrida(config_paginada(config), estado, fuentes=fuentes).ejecutar()
    ejecutadas = resumen.resultados[0].ejecutadas
    assert [(c.grupo, c.pagina) for c in ejecutadas] == [
        ("nucleo", 1), ("nucleo", 2), ("nucleo", 3), ("cola_larga", 1),
    ]  # fmt: skip
    assert rotacion.obtener_indice(estado, "falsa", rotacion.NUCLEO) == 1


@respx.mock
def test_fuente_sin_paginacion_lee_solo_la_primera_pagina(config, estado, caplog):
    estado.marcar_inicializada()
    mock_ofertas()
    resumen = corrida(config_paginada(config), estado).ejecutar()
    ejecutadas = resumen.resultados[0].ejecutadas
    assert [(c.grupo, c.pagina) for c in ejecutadas] == [
        ("nucleo", 1), ("cola_larga", 1), ("cola_larga", 1), ("cola_larga", 1),
    ]  # fmt: skip
    assert "no soporta paginación" in caplog.text


class FuenteFijaFalsa(FuentePaginadaFalsa):
    consulta_fija = "plazas de práctica"


@respx.mock
def test_consulta_fija_lee_sus_paginas_sin_rotar(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    fuentes_conf = {"falsa": ConfFuente(presupuesto=2, reservado_nucleo=1)}
    resumen = corrida(
        config.model_copy(update={"fuentes": fuentes_conf}), estado,
        fuentes={"falsa": FuenteFijaFalsa},
    ).ejecutar()  # fmt: skip
    ejecutadas = resumen.resultados[0].ejecutadas
    assert [(c.keyword, c.pagina) for c in ejecutadas] == [
        ("plazas de práctica", 1), ("plazas de práctica", 2),
    ]  # fmt: skip
    assert estado.cx.execute("SELECT COUNT(*) FROM rotacion").fetchone()[0] == 0


class FuenteConVariantes(FuenteFalsa):
    """Envía la variante de la corrida como parámetro, para ver cuál se usó."""

    def construir_peticion(self, keyword, pagina=1):
        return Peticion(URL, params={"q": keyword, **(self.variante or {})})


def config_con_variantes(config, presupuesto=2):
    variantes = [{"v": "a"}, {"v": "b"}]
    fuentes = {
        "falsa": ConfFuente(
            presupuesto=presupuesto, reservado_nucleo=1, opciones={"variantes": variantes}
        )
    }
    return config.model_copy(update={"fuentes": fuentes})


def variantes_pedidas(ruta):
    return [llamada.request.url.params["v"] for llamada in ruta.calls]


@respx.mock
def test_dos_corridas_seguidas_usan_variantes_distintas(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    conf = config_con_variantes(config)
    fuentes = {"falsa": FuenteConVariantes}
    corrida(conf, estado, fuentes=fuentes).ejecutar()
    corrida(conf, estado, fuentes=fuentes).ejecutar()
    corrida(conf, estado, fuentes=fuentes).ejecutar()
    # 2 peticiones por corrida (el presupuesto no cambia); la variante rota a, b, a
    assert variantes_pedidas(ruta) == ["a", "a", "b", "b", "a", "a"]
    assert rotacion.obtener_indice(estado, "falsa", "variante") == 1


@respx.mock
def test_dry_run_no_avanza_la_variante(config, estado):
    ruta = mock_ofertas()
    conf = config_con_variantes(config)
    fuentes = {"falsa": FuenteConVariantes}
    corrida(conf, estado, Modo(dry_run=True), fuentes=fuentes).ejecutar()
    corrida(conf, estado, Modo(dry_run=True), fuentes=fuentes).ejecutar()
    assert variantes_pedidas(ruta) == ["a", "a", "a", "a"]
    assert rotacion.obtener_indice(estado, "falsa", "variante") == 0


@respx.mock
def test_fuente_sin_variantes_no_toca_la_rotacion_de_variantes(config, estado):
    estado.marcar_inicializada()
    mock_ofertas()
    corrida(config, estado).ejecutar()
    existe = estado.cx.execute("SELECT 1 FROM rotacion WHERE grupo = 'variante'").fetchone()
    assert existe is None


def config_combinada(config, consulta=None, ritmo=None, **campos):
    variantes = [{"v": "a"}, {"v": "b"}]
    opciones = {"variantes": variantes, "consulta": {"modo": "or", **(consulta or {})}}
    fuentes = {
        "falsa": ConfFuente(
            presupuesto=2, reservado_nucleo=1, opciones=opciones, ritmo=ritmo, **campos
        )
    }
    return config.model_copy(update={"fuentes": fuentes})


def consultas_pedidas(ruta):
    return [llamada.request.url.params["q"] for llamada in ruta.calls]


@respx.mock
def test_modo_or_hace_una_sola_peticion_con_la_consulta_combinada(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    resumen = corrida(
        config_combinada(config), estado, fuentes={"falsa": FuenteConVariantes}
    ).ejecutar()
    assert ruta.call_count == 1
    [consulta] = consultas_pedidas(ruta)
    assert consulta.count(" OR ") == 13 and consulta.startswith('"practicante sistemas" OR ')
    assert [(c.grupo, c.pagina) for c in resumen.resultados[0].ejecutadas] == [("nucleo", 1)]


@respx.mock
def test_modo_or_alterna_variantes_y_lee_la_cola_en_la_cuarta_corrida(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    conf = config_combinada(config, {"cola_cada": 4})
    for _ in range(8):
        corrida(conf, estado, fuentes={"falsa": FuenteConVariantes}).ejecutar()
    nucleo, cola, *_ = consultas_pedidas(ruta)[0], consultas_pedidas(ruta)[3]
    assert cola.startswith('"desarrollador junior" OR ')  # el primer grupo de la cola larga
    assert consultas_pedidas(ruta) == [nucleo] * 3 + [cola] + [nucleo] * 3 + [cola]
    # Núcleo y cola llevan su propio contador de variantes: a, b, a | b, a, b | y la cola a, b
    assert variantes_pedidas(ruta) == ["a", "b", "a", "a", "b", "a", "b", "b"]
    assert rotacion.obtener_indice(estado, "falsa", "variante") == 0  # no se usa en este modo


@respx.mock
def test_modo_simple_conserva_el_comportamiento_por_palabra_clave(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    conf = config_combinada(config, {"modo": "simple"})
    for _ in range(2):
        corrida(conf, estado, fuentes={"falsa": FuenteConVariantes}).ejecutar()
    assert consultas_pedidas(ruta) == [
        "practicante sistemas", "desarrollador junior",
        "practicante TI", "programador junior",
    ]  # fmt: skip
    assert variantes_pedidas(ruta) == ["a", "a", "b", "b"]
    assert rotacion.obtener_indice(estado, "falsa", "variante") == 0


@respx.mock
def test_fuente_sin_seccion_consulta_conserva_el_comportamiento_anterior(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    corrida(config_con_variantes(config), estado, fuentes={"falsa": FuenteConVariantes}).ejecutar()
    assert consultas_pedidas(ruta) == ["practicante sistemas", "desarrollador junior"]


@respx.mock
def test_modo_or_en_dry_run_no_mueve_ninguna_rotacion_ni_ritmo(config, estado):
    ruta = mock_ofertas()
    conf = config_combinada(config, ritmo={"intervalos_min": [30, 60]})
    for _ in range(2):
        corrida(conf, estado, Modo(dry_run=True), fuentes={"falsa": FuenteConVariantes}).ejecutar()
    assert variantes_pedidas(ruta) == ["a", "a"]
    assert estado.cx.execute("SELECT COUNT(*) FROM rotacion").fetchone()[0] == 0
    claves = estado.cx.execute("SELECT clave FROM kv WHERE clave LIKE 'ritmo:%'").fetchall()
    assert claves == []


@respx.mock
def test_modo_or_no_avanza_si_la_fuente_estaba_en_cooldown(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    estado.cx.execute(
        "INSERT INTO fuentes_estado(fuente, cooldown_hasta, escalon, fallos_consecutivos) "
        "VALUES ('falsa', ?, 0, 1)",
        (a_texto(AHORA + timedelta(hours=1)),),
    )
    resumen = corrida(
        config_combinada(config), estado, fuentes={"falsa": FuenteConVariantes}
    ).ejecutar()
    assert not ruta.called and "cooldown" in resumen.omitidas["falsa"]
    assert estado.cx.execute("SELECT COUNT(*) FROM rotacion").fetchone()[0] == 0


class FuenteOtra(FuenteFalsa):
    nombre = "otra"


RITMO = {"intervalos_min": [30, 60, 120], "tolerancia_min": 5}


@respx.mock
def test_ritmo_adaptado_omite_la_fuente_y_deja_el_motivo(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    fuentes_conf = {
        "falsa": ConfFuente(presupuesto=1, reservado_nucleo=1, ritmo=RITMO),
        "otra": ConfFuente(presupuesto=1, reservado_nucleo=1),
    }
    conf = config.model_copy(update={"fuentes": fuentes_conf})
    estado.kv_guardar("ritmo:falsa:nivel", "1")  # un bloqueo previo: cada 60 min
    estado.kv_guardar("ritmo:falsa:ultima", a_texto(AHORA - timedelta(minutes=30)))
    resumen = corrida(conf, estado, fuentes={"falsa": FuenteFalsa, "otra": FuenteOtra}).ejecutar()
    assert resumen.omitidas == {"falsa": "ritmo adaptado a 60 min"}
    assert ruta.call_count == 1  # solo la otra fuente consultó
    assert [r.fuente for r in resumen.resultados] == ["otra"]
    # Omitir no avanza ninguna rotación ni mueve el ritmo
    assert estado.cx.execute("SELECT 1 FROM rotacion WHERE fuente='falsa'").fetchone() is None
    assert estado.kv_obtener("ritmo:falsa:ultima") == a_texto(AHORA - timedelta(minutes=30))


@respx.mock
def test_ritmo_cumplido_consulta_y_anota_la_peticion(config, estado):
    estado.marcar_inicializada()
    ruta = mock_ofertas()
    conf = config.model_copy(update={"fuentes": {
        "falsa": ConfFuente(presupuesto=1, reservado_nucleo=1, ritmo=RITMO)}})  # fmt: skip
    estado.kv_guardar("ritmo:falsa:nivel", "1")
    estado.kv_guardar("ritmo:falsa:ultima", a_texto(AHORA - timedelta(minutes=56)))
    resumen = corrida(conf, estado).ejecutar()
    assert ruta.call_count == 1 and not resumen.omitidas
    assert estado.kv_obtener("ritmo:falsa:ultima") == a_texto(AHORA)


class IAAceptaComoPracticas(IAFalsa):
    """Acepta todo lo dudoso con categoría «practicas», como hacía el prompt viejo."""

    def chat_json(self, proposito, prompt, payload, **kwargs):
        self.llamadas += 1
        return RespuestaIA(True, {"vacantes": [
            {"id": v["id"], "aceptar": True, "categoria": "practicas", "motivo": "práctica"}
            for v in payload["vacantes"]
        ]})  # fmt: skip


def config_una_peticion(config):
    fuentes = {"falsa": ConfFuente(presupuesto=1, reservado_nucleo=1)}
    return config.model_copy(update={"fuentes": fuentes})


@respx.mock
def test_guardarrail_recategoriza_lo_que_acepta_la_ia(config, estado, caplog):
    estado.marcar_inicializada()
    mock_ofertas([
        {"id": "1", "titulo": "Programador Staff CELLS", "empresa": "Santander"},
        {"id": "2", "titulo": "Software Engineer Intern", "empresa": "Acme"},
        {"id": "3", "titulo": "Ingeniero de Procesos", "empresa": "Planta"},
    ])  # fmt: skip
    notificador, ia = NotificadorFalso(), IAAceptaComoPracticas()
    with caplog.at_level(logging.INFO, logger="buscador"):
        resumen = corrida(
            config_una_peticion(config), estado, ia=ia, notificador=notificador
        ).ejecutar()
    categorias = {v.titulo: v.categoria for v in resumen.a_publicar}
    assert categorias == {
        "Programador Staff CELLS": Categoria.DESARROLLO,  # sin evidencia de práctica
        "Software Engineer Intern": Categoria.PRACTICAS,  # con evidencia: no se toca
    }
    assert (resumen.practicas_recategorizadas, resumen.practicas_rechazadas) == (1, 1)
    assert "Ingeniero de Procesos" not in notificador.mensajes[0][1]
    assert "practicas_recategorizadas=1 practicas_rechazadas=1" in caplog.text
    assert "Guardarraíl de prácticas recategoriza: Programador Staff CELLS" in caplog.text
    fila = estado.cx.execute("SELECT * FROM corridas").fetchone()
    assert (fila["practicas_recategorizadas"], fila["practicas_rechazadas"]) == (1, 1)
    guardada = estado.cx.execute(
        "SELECT categoria, ubicacion FROM vistas WHERE clave = 'falsa:1'"
    ).fetchone()
    assert (guardada["categoria"], guardada["ubicacion"]) == ("desarrollo", "Cartagena, Bolívar")


class IACapturaPayload(IAFalsa):
    def __init__(self):
        super().__init__()
        self.payloads = []

    def chat_json(self, proposito, prompt, payload, **kwargs):
        self.payloads.append(payload)
        return super().chat_json(proposito, prompt, payload, **kwargs)


class FuenteMedellin(FuenteFalsa):
    """Vacantes de otra ciudad, sin modalidad y con descripción."""

    def parsear(self, respuesta, keyword, ahora):
        vacantes = super().parsear(respuesta, keyword, ahora)
        for v in vacantes:
            v.ubicacion, v.descripcion = "Medellín", "Analizarás datos con SQL."
        return vacantes


@respx.mock
def test_vacante_con_condicion_de_modalidad_la_envia_a_la_ia(config, estado):
    estado.marcar_inicializada()
    mock_ofertas([{"id": "1", "titulo": "Analista de datos Jr", "empresa": "Acme"}])
    ia = IACapturaPayload()
    fuentes = {"falsa": FuenteMedellin}
    corrida(config_una_peticion(config), estado, ia=ia, fuentes=fuentes).ejecutar()
    [item] = ia.payloads[0]["vacantes"]
    assert item["exige_modalidad"] == "remoto o híbrido"
    assert item["ciudad_base"] == "Cartagena"
