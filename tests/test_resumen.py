import json
from datetime import datetime, timedelta

import pytest

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado, a_texto
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.ia_cliente import RespuestaIA
from buscador_vacantes.notificador_telegram import ResultadoEnvio
from buscador_vacantes.resumen import Resumen, calcular_metricas, calcular_metricas_asistente

AHORA = datetime(2026, 10, 4, 8, 0, tzinfo=ZONA)


class NotificadorFalso:
    def __init__(self):
        self.mensajes = []

    def enviar_mensaje(self, chat_id, texto):
        self.mensajes.append((chat_id, texto))
        return ResultadoEnvio(True)

    def enviar_foto(self, chat_id, ruta):
        return ResultadoEnvio(True)

    def cerrar(self):
        pass


class IAFalsa:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = []

    def chat_json(self, proposito, prompt, payload, **kwargs):
        self.llamadas.append((proposito, payload))
        return self.respuesta

    def saldo(self):
        return 10.0


RECOMENDACIONES = RespuestaIA(True, {
    "titular": "Día estable con 3 vacantes enviadas",
    "recomendaciones": ["Revisar 'semillero': 0 resultados en 7 días en todas las fuentes."],
})  # fmt: skip


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    hace = lambda **kw: a_texto(AHORA - timedelta(**kw))  # noqa: E731
    with e.transaccion() as cx:
        for clave, fuente, categoria, horas in [
            ("linkedin:1", "linkedin", "practicas", 3), ("linkedin:2", "linkedin", "desarrollo", 5),
            ("magneto:9", "magneto", "practicas", 10), ("computrabajo:X", "computrabajo", None, 30),
        ]:  # fmt: skip
            cx.execute(
                "INSERT INTO vistas(clave, huella, fuente, categoria, primera_vez, enviada_en) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (clave, clave, fuente, categoria, hace(hours=horas), hace(hours=horas)),
            )
        for horas, modo in [(2, "normal"), (4, "normal"), (6, "dry-run")]:
            corrida_id = cx.execute(
                "INSERT INTO corridas(inicio, modo, crudas, descartes_json, duplicadas, dudosas, "
                "ia_aceptadas, ia_rechazadas, pendientes, enviadas) "
                "VALUES (?, ?, 50, ?, 5, 4, 2, 1, 1, 2)",
                (hace(hours=horas), modo,
                 json.dumps({"seniority": 3, "antiguedad": 1, "ubicacion": 0, "no_ti": 20})),
            ).lastrowid  # fmt: skip
            for keyword, items in [("semillero", 0), ("practicante TI", 12)]:
                cx.execute(
                    "INSERT INTO intentos(ts, corrida_id, fuente, keyword, url, status, items) "
                    "VALUES (?, ?, 'linkedin', ?, 'https://x', 200, ?)",
                    (hace(hours=horas), corrida_id, keyword, items),
                )
        cx.execute("INSERT INTO incidentes(fuente, tipo, abierto_desde) VALUES "
                   "('elempleo', 'cambio_html', ?)", (hace(hours=12),))  # fmt: skip
        cx.execute("INSERT INTO incidentes(fuente, tipo, abierto_desde, cerrado_en) VALUES "
                   "('linkedin', 'bloqueo', ?, ?)", (hace(hours=20), hace(hours=15)))  # fmt: skip
        cx.execute("INSERT INTO ia_uso(ts, proposito, tokens_in, tokens_out, ok) VALUES "
                   "(?, 'clasificador', 1200, 300, 1)", (hace(hours=2),))  # fmt: skip
    yield e
    e.cerrar()


@pytest.fixture
def config():
    return cargar_configuracion().resumen


def crear(config, estado, ia, notificador, **kwargs):
    return Resumen(config, ia, estado, notificador, "-100REAL", reloj=lambda: AHORA, **kwargs)


def test_metricas_de_24h(estado):
    m = calcular_metricas(estado, AHORA)
    assert m.enviadas == 3  # la de hace 30 h queda fuera
    assert dict(m.enviadas_por_fuente) == {"linkedin": 2, "magneto": 1}
    assert dict(m.enviadas_por_categoria) == {"practicas": 2, "desarrollo": 1}
    assert m.corridas == 2  # el dry-run no cuenta
    assert m.crudas == 100 and m.duplicadas == 10 and m.dudosas == 8
    assert (m.ia_aceptadas, m.ia_rechazadas, m.pendientes) == (4, 2, 1)
    assert m.descartes["no_ti"] == 40
    assert m.requests_por_fuente["linkedin"] == 4
    assert m.incidentes_abiertos == ["elempleo:cambio_html"]
    assert m.incidentes_cerrados == ["linkedin:bloqueo"]
    assert m.ia_llamadas["clasificador"] == 1 and m.tokens_in == 1200
    assert m.keywords_sin_resultados_7d == ["semillero"]


def test_resumen_activado_una_llamada_y_un_envio(config, estado):
    ia, notificador = IAFalsa(RECOMENDACIONES), NotificadorFalso()
    assert crear(config, estado, ia, notificador).enviar()
    assert len(ia.llamadas) == 1 and ia.llamadas[0][0] == "resumen"
    [(chat, texto)] = notificador.mensajes
    assert chat == "-100REAL"
    assert "📊 <b>Resumen diario · 4 oct</b>" in texto
    assert "<i>Día estable con 3 vacantes enviadas</i>" in texto
    assert "📨 Enviadas: 3 (LinkedIn 2 · Magneto 1)" in texto
    assert "🗂 Por categoría: Prácticas 2 · Desarrollo 1" in texto
    assert "🧹 Descartes: seniority 6 · antigüedad 2 · ubicación 0 · no TI 40" in texto
    assert "🤖 Dudosas: 8 → 4 aceptadas · 2 rechazadas · 1 pendientes" in texto
    assert "elempleo:cambio_html" in texto and "cerrados hoy: 1" in texto
    assert "💡 <b>Recomendaciones</b>\n1. Revisar 'semillero'" in texto


def test_payload_solo_metricas_agregadas(config, estado):
    ia = IAFalsa(RECOMENDACIONES)
    crear(config, estado, ia, NotificadorFalso()).enviar()
    payload = json.dumps(ia.llamadas[0][1])
    assert "semillero" in payload  # dato para recomendar revisar la palabra clave
    assert "https://" not in payload and "-100REAL" not in payload


def test_resumen_ya_enviado_hoy(config, estado):
    crear(config, estado, IAFalsa(RECOMENDACIONES), NotificadorFalso()).enviar()
    ia, notificador = IAFalsa(RECOMENDACIONES), NotificadorFalso()
    assert not crear(config, estado, ia, notificador).enviar()
    assert notificador.mensajes == [] and ia.llamadas == []


def test_resumen_desactivado(config, estado):
    ia, notificador = IAFalsa(RECOMENDACIONES), NotificadorFalso()
    desactivado = config.model_copy(update={"activo": False})
    assert not crear(desactivado, estado, ia, notificador).enviar()
    assert notificador.mensajes == [] and ia.llamadas == []


@pytest.mark.parametrize(
    ("respuesta", "motivo"),
    [
        (
            RespuestaIA(False, motivo="error del servidor (HTTP 503)"),
            "error del servidor (HTTP 503)",
        ),
        (RespuestaIA(False, motivo="saldo bajo", realizada=False), "saldo bajo"),
        (RespuestaIA(True, {"titular": "x", "recomendaciones": []}), "respuesta inválida"),
    ],
)
def test_respaldo_sin_ia(config, estado, respuesta, motivo):
    notificador = NotificadorFalso()
    assert crear(config, estado, IAFalsa(respuesta), notificador).enviar()
    texto = notificador.mensajes[0][1]
    assert "📨 Enviadas: 3" in texto and "🧹 Descartes" in texto
    assert f"Recomendaciones IA no disponibles (motivo: {motivo})" in texto
    assert "💡" not in texto


def test_dry_run_no_registra_el_envio(config, estado):
    crear(config, estado, IAFalsa(RECOMENDACIONES), NotificadorFalso()).enviar(registrar=False)
    assert estado.kv_obtener("ultimo_resumen") is None


def test_chat_de_prueba_no_bloquea_el_resumen_real(config, estado):
    crear(config, estado, IAFalsa(RECOMENDACIONES), NotificadorFalso(), prueba=True).enviar()
    notificador = NotificadorFalso()
    assert crear(config, estado, IAFalsa(RECOMENDACIONES), notificador).enviar()


def test_resumen_de_prueba_cuenta_los_envios_de_prueba(config, estado):
    with estado.transaccion() as cx:
        cx.execute("INSERT INTO vistas(clave, huella, fuente, categoria, primera_vez, prueba_en) "
                   "VALUES ('magneto:5', 'h5', 'magneto', 'qa', ?, ?)",
                   (a_texto(AHORA - timedelta(hours=1)),) * 2)  # fmt: skip
    assert calcular_metricas(estado, AHORA, prueba=True).enviadas == 1
    assert calcular_metricas(estado, AHORA).enviadas == 3
    # Tras promover-prueba, lo de la fase de prueba no cuenta como enviado al canal
    estado.promover_prueba()
    assert calcular_metricas(estado, AHORA).enviadas == 3


# --- métricas del asistente (tarea 9.1) -------------------------------------------------------


@pytest.fixture
def base_asistente():
    b = BaseAsistente.abrir(":memory:")
    hace = lambda **kw: a_texto(AHORA - timedelta(**kw))  # noqa: E731
    with b.transaccion() as cx:
        for tid, nombre, estado, creado in [
            (111, "Ana Gómez", "activo", hace(days=9)),
            (222, "Luis Pérez", "activo", hace(hours=5)),
            (333, "Eva Ríos", "suspendido", hace(days=20)),
        ]:
            cx.execute(
                "INSERT INTO usuarios(telegram_id, nombre, estado, directorio, creado) "
                "VALUES (?, ?, ?, ?, ?)",
                (tid, nombre, estado, f"dir-{tid}", creado),
            )
        for usuario, token, latido, revocado in [
            (1, "t1", hace(seconds=30), 0),  # en línea
            (2, "t2", hace(minutes=10), 0),  # caído
            (1, "t3", hace(seconds=10), 1),  # revocado
        ]:
            cx.execute(
                "INSERT INTO navegadores(usuario_id, token_hash, creado, ultimo_latido, revocado) "
                "VALUES (?, ?, ?, ?, ?)",
                (usuario, token, hace(days=1), latido, revocado),
            )
        for usuario, corta, estado, terminada in [
            (1, "a", "enviada", hace(hours=2)),
            (1, "b", "enviada", hace(hours=4)),
            (2, "c", "respaldo", hace(hours=3)),
            (2, "d", "enviada", hace(hours=40)),  # fuera de las 24 h
            (2, "e", "cancelada", hace(hours=1)),
        ]:
            cx.execute(
                "INSERT INTO postulaciones(usuario_id, id_corto, plataforma, estado, creada, "
                "actualizada, terminada_en) VALUES (?, ?, 'computrabajo', ?, ?, ?, ?)",
                (usuario, corta, estado, terminada, terminada, terminada),
            )
        cx.execute(
            "INSERT INTO postulacion_pasos(postulacion_id, ts, estado, paso) "
            "VALUES (1, ?, 'verificacion', 'estado')",
            (hace(hours=2),),
        )
        for pid, origen in [(1, "perfil"), (1, "banco"), (1, "perfil"), (2, "ia")]:
            cx.execute(
                "INSERT INTO respuestas(postulacion_id, pregunta, respuesta, origen) "
                "VALUES (?, 'p', 'r', ?)",
                (pid, origen),
            )
        for pregunta, origen, creada in [
            ("a", "ia", hace(hours=3)),
            ("b", "ia", hace(days=3)),  # vieja
            ("c", "semilla", hace(hours=3)),  # no cuenta
        ]:
            cx.execute(
                "INSERT INTO banco_preguntas(pregunta_norm, campo, origen, creada) "
                "VALUES (?, 'x', ?, ?)",
                (pregunta, origen, creada),
            )
    yield b
    b.cerrar()


def test_metricas_del_asistente_en_un_dia_con_actividad(base_asistente):
    m = calcular_metricas_asistente(base_asistente, AHORA, navegador_caido_min=2)
    assert (m.usuarios_activos, m.altas, m.navegadores_en_linea) == (2, 1, 1)
    assert (m.enviadas, m.respaldo, m.verificaciones) == (2, 1, 1)
    assert m.pct_sin_ia == 75
    assert m.preguntas_nuevas_banco == 1


def test_resumen_incluye_el_asistente(config, estado, base_asistente):
    notificador = NotificadorFalso()
    crear(config, estado, IAFalsa(RECOMENDACIONES), notificador, asistente=base_asistente).enviar()
    texto = notificador.mensajes[0][1]
    assert "⚡ Asistente: 2 usuarios activos (1 altas) · 1 navegadores en línea" in texto
    assert (
        "📝 Postulaciones: 2 enviadas · 1 de respaldo · 1 verificaciones · "
        "respuestas: 75 % sin IA · preguntas nuevas del banco: 1"
    ) in texto


def test_asistente_desactivado_deja_el_resumen_identico(config, estado):
    con, sin = NotificadorFalso(), NotificadorFalso()
    crear(config, estado, IAFalsa(RECOMENDACIONES), con, asistente=None).enviar(registrar=False)
    crear(config, estado, IAFalsa(RECOMENDACIONES), sin).enviar(registrar=False)
    assert con.mensajes == sin.mensajes
    assert "Asistente" not in sin.mensajes[0][1]


def test_asistente_sin_actividad_no_agrega_lineas(config, estado):
    vacia = BaseAsistente.abrir(":memory:")
    notificador = NotificadorFalso()
    crear(config, estado, IAFalsa(RECOMENDACIONES), notificador, asistente=vacia).enviar()
    assert "Asistente" not in notificador.mensajes[0][1]
    vacia.cerrar()


def test_el_cuerpo_a_deepseek_no_lleva_ids_ni_nombres(config, estado, base_asistente):
    ia = IAFalsa(RECOMENDACIONES)
    crear(config, estado, ia, NotificadorFalso(), asistente=base_asistente).enviar()
    payload = json.dumps(ia.llamadas[0][1], ensure_ascii=False)
    assert '"asistente"' in payload and "postulaciones_enviadas" in payload
    for prohibido in ("Ana", "Luis", "Eva", "111", "222", "dir-", "t1", "computrabajo"):
        assert prohibido not in payload
