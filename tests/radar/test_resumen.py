import json
from datetime import datetime, timedelta

import pytest

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.comun.config import cargar_configuracion
from buscador_vacantes.comun.estado import Estado, a_texto
from buscador_vacantes.comun.fechas import ZONA
from buscador_vacantes.radar.ia_cliente import RespuestaIA
from buscador_vacantes.radar.notificador_telegram import ResultadoEnvio
from buscador_vacantes.radar.resumen import (
    Resumen,
    _lineas_asistente,
    calcular_metricas,
    calcular_metricas_asistente,
)

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
        # (horas, modo, prácticas recategorizadas, prácticas rechazadas por el guardarraíl)
        for horas, modo, recategorizadas, rechazadas in [
            (2, "normal", 3, 1), (4, "normal", 1, 0), (6, "dry-run", 9, 9)
        ]:  # fmt: skip
            corrida_id = cx.execute(
                "INSERT INTO corridas(inicio, modo, crudas, descartes_json, duplicadas, dudosas, "
                "ia_aceptadas, ia_rechazadas, pendientes, enviadas, practicas_recategorizadas, "
                "practicas_rechazadas) VALUES (?, ?, 50, ?, 5, 4, 2, 1, 1, 2, ?, ?)",
                (hace(hours=horas), modo,
                 json.dumps({"seniority": 3, "antiguedad": 1, "ubicacion": 0, "no_ti": 20,
                             "presencial_fuera": 15, "call_center": 2}),
                 recategorizadas, rechazadas),
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
    assert m.descartes["presencial_fuera"] == 30 and m.descartes["call_center"] == 4
    assert (m.practicas_recategorizadas, m.practicas_rechazadas) == (4, 1)
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
    assert (
        "🧹 Descartes: lista negra 0 · seniority 6 · antigüedad 2 · ubicación 0 · "
        "presencial fuera de la ciudad base 30 · call center no remoto 4 · no TI 40"
    ) in texto
    assert "🛡️ Guardarraíl de prácticas: 4 recategorizadas · 1 rechazada" in texto
    assert "🤖 Dudosas: 8 → 4 aceptadas · 2 rechazadas · 1 pendientes" in texto
    assert "elempleo:cambio_html" in texto and "cerrados hoy: 1" in texto
    assert "💡 <b>Recomendaciones</b>\n1. Revisar 'semillero'" in texto


def test_payload_solo_metricas_agregadas(config, estado):
    ia = IAFalsa(RECOMENDACIONES)
    crear(config, estado, ia, NotificadorFalso()).enviar()
    payload = json.dumps(ia.llamadas[0][1])
    assert "semillero" in payload  # dato para recomendar revisar la palabra clave
    assert "https://" not in payload and "-100REAL" not in payload
    metricas = ia.llamadas[0][1]["metricas"]
    assert metricas["guardarrail_practicas"] == {"recategorizadas": 4, "rechazadas": 1}
    assert metricas["descartes_por_regla"]["presencial_fuera"] == 30
    assert metricas["descartes_por_regla"]["call_center"] == 4


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


def test_guardarrail_sin_correcciones_se_muestra_en_cero(config, estado):
    with estado.transaccion() as cx:
        cx.execute("UPDATE corridas SET practicas_recategorizadas = 0, practicas_rechazadas = 0")
    notificador = NotificadorFalso()
    crear(config, estado, IAFalsa(RECOMENDACIONES), notificador).enviar()
    assert (
        "🛡️ Guardarraíl de prácticas: 0 recategorizadas · 0 rechazadas" in notificador.mensajes[0][1]
    )


def test_metricas_de_detalle(estado):
    with estado.transaccion() as cx:
        # Las dos corridas normales de las últimas 24 h; el dry-run no cuenta
        normales = cx.execute("SELECT id FROM corridas WHERE modo = 'normal' ORDER BY id")
        ids = [f[0] for f in normales]
        cx.execute(
            "UPDATE corridas SET detalles_pedidos = 40, detalles_fallidos = 3, "
            "detalles_recuperadas = 6, detalles_cerradas = 2, detalles_vencidas = 1 WHERE id = ?",
            (ids[0],),
        )
        cx.execute(
            "UPDATE corridas SET detalles_pedidos = 20, detalles_fallidos = 1, "
            "detalles_recuperadas = 3, detalles_cerradas = 0, detalles_vencidas = 0 WHERE id = ?",
            (ids[1],),
        )
        cx.execute("UPDATE corridas SET detalles_pedidos = 99 WHERE modo = 'dry-run'")
        for n in range(3):
            cx.execute(
                "INSERT INTO pendientes_detalle(clave, huella, vacante_json, desde) "
                "VALUES (?, ?, '{}', ?)",
                (f"linkedin:{n}", f"h{n}", a_texto(AHORA)),
            )
    m = calcular_metricas(estado, AHORA)
    assert (m.detalles_pedidos, m.detalles_fallidos, m.detalles_recuperadas) == (60, 4, 9)
    assert (m.detalles_cerradas, m.detalles_vencidas, m.detalles_en_cola) == (2, 1, 3)
    assert m.para_ia()["detalle_de_ofertas"] == {
        "pedidos": 60, "fallidos": 4, "recuperadas": 9, "cerradas": 2, "vencidas": 1, "en_cola": 3,
    }  # fmt: skip


def test_el_resumen_muestra_la_linea_de_detalle_de_linkedin(config, estado):
    with estado.transaccion() as cx:
        cx.execute(
            "UPDATE corridas SET detalles_pedidos = 30, detalles_fallidos = 2, "
            "detalles_recuperadas = 4, detalles_vencidas = 1, detalles_cerradas = 1 "
            "WHERE modo = 'normal'"
        )
        cx.execute(
            "INSERT INTO pendientes_detalle(clave, huella, vacante_json, desde) "
            "VALUES ('linkedin:1', 'h', '{}', ?)",
            (a_texto(AHORA),),
        )
    notificador, ia = NotificadorFalso(), IAFalsa(RECOMENDACIONES)
    crear(config, estado, ia, notificador).enviar()
    texto = notificador.mensajes[0][1]
    assert (
        "Detalle de LinkedIn: 60 pedidos · 4 fallidos · 8 recuperadas · 1 en cola · 2 vencidas"
        in texto
    )
    assert ia.llamadas[0][1]["metricas"]["detalle_de_ofertas"]["en_cola"] == 1


def test_el_detalle_sin_actividad_se_muestra_en_cero(config, estado):
    notificador = NotificadorFalso()
    crear(config, estado, IAFalsa(RECOMENDACIONES), notificador).enviar()
    assert (
        "Detalle de LinkedIn: 0 pedidos · 0 fallidos · 0 recuperadas · 0 en cola · 0 vencidas"
        in notificador.mensajes[0][1]
    )


def test_las_peticiones_de_detalle_no_cuentan_como_palabras_sin_resultados(estado):
    with estado.transaccion() as cx:
        for horas in (1, 2, 3):
            cx.execute(
                "INSERT INTO intentos(ts, corrida_id, fuente, keyword, url, status, items) "
                "VALUES (?, 1, 'linkedin', 'detalle 123', 'https://x', 200, 0)",
                (a_texto(AHORA - timedelta(hours=horas)),),
            )
    assert calcular_metricas(estado, AHORA).keywords_sin_resultados_7d == ["semillero"]


def sembrar_motor(base):
    """20 postulaciones a un Greenhouse (18 enviadas, 2 de ellas reparadas), 2 ensayos, una
    pantalla que resolvió el árbitro y 2 respaldos de Computrabajo; todo del día."""
    hace = lambda **kw: a_texto(AHORA - timedelta(**kw))  # noqa: E731
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO usuarios(telegram_id, nombre, estado, directorio, creado) "
            "VALUES (1, 'Ana', 'activo', 'd', ?)",
            (hace(days=9),),
        )
        urls = {
            "gh": "https://job-boards.greenhouse.io/acme/jobs/1",
            "ct": "https://co.computrabajo.com/ofertas-de-trabajo/oferta-1",
        }
        contador = iter(range(1000))

        def postulacion(corta, plataforma, estado, motivo=None, tipo="postular", pasos=()):
            id_corto = f"{corta}{next(contador)}"  # una vacante por postulación
            cx.execute(
                "INSERT INTO vacantes(id_corto, clave, fuente, url, indexada_en) "
                "VALUES (?, ?, 'x', ?, ?)",
                (id_corto, id_corto, urls[corta], hace(days=1)),
            )
            pid = cx.execute(
                "INSERT INTO postulaciones(usuario_id, id_corto, tipo, plataforma, estado, "
                "motivo, creada, actualizada, terminada_en) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
                (id_corto, tipo, plataforma, estado, motivo, hace(hours=3), hace(hours=2),
                 hace(hours=2)),
            ).lastrowid  # fmt: skip
            for paso in pasos:
                cx.execute(
                    "INSERT INTO postulacion_pasos(postulacion_id, ts, paso) VALUES (?, ?, ?)",
                    (pid, hace(hours=2), paso),
                )

        for n in range(18):
            reparo = ("reparacion", "arbitro") if n < 2 else ()
            postulacion("gh", "linkedin", "enviada", pasos=reparo)
        postulacion("gh", "linkedin", "ensayada")
        postulacion("gh", "linkedin", "ensayada", tipo="vigia", pasos=("respaldo_generico",))
        postulacion("ct", "computrabajo", "formulario_desconocido", "sin_ia")
        postulacion("ct", "computrabajo", "respaldo", "captcha")
        postulacion("ct", "computrabajo", "incierta")
        postulacion("ct", "computrabajo", "enviada", pasos=("arbitro",))
        cx.execute(
            "INSERT INTO recetas(host, ruta_patron, familia, firma, receta_json, actualizada, "
            "creada) VALUES ('a.com', '/', 'a', '[]', '{}', ?, ?)",
            (hace(hours=1), hace(hours=1)),
        )
        cx.execute(
            "INSERT INTO recetas(host, ruta_patron, familia, firma, receta_json, actualizada, "
            "creada) VALUES ('b.com', '/', 'b', '[]', '{}', ?, ?)",  # vieja, reforzada hoy
            (hace(hours=1), hace(days=5)),
        )
        cx.execute(
            "INSERT INTO recetas(host, ruta_patron, familia, firma, receta_json, actualizada) "
            "VALUES ('c.com', '/', 'c', '[]', '{}', ?)",  # anterior a la columna `creada`
            (hace(days=6),),
        )
        cx.execute(
            "INSERT INTO parches_flujo(plataforma, paso, selector_json, creado, actualizado) "
            "VALUES ('computrabajo', 'p', '{}', ?, ?)",
            (hace(hours=2), hace(hours=2)),
        )


def test_metricas_del_motor_por_plataforma_y_familia():
    base = BaseAsistente.abrir(":memory:")
    sembrar_motor(base)
    m = calcular_metricas_asistente(base, AHORA, navegador_caido_min=2)
    gh = m.por_familia["greenhouse"]
    assert gh["enviadas"] == 18 and gh["ensayadas"] == 2 and gh["reparadas"] == 3
    assert gh["arbitro"] == 2 and gh["respaldo"] == 0
    # La plataforma de origen (LinkedIn) reúne lo mismo; Computrabajo, lo suyo
    assert m.por_plataforma["linkedin"] == gh
    ct = m.por_plataforma["computrabajo"]
    assert ct == {"enviadas": 1, "ensayadas": 0, "formulario_desconocido": 1, "incierta": 1,
                  "reparadas": 0, "arbitro": 1, "respaldo": 2}  # fmt: skip
    assert m.respaldos_por_motivo == {"sin_ia": 1, "captcha": 1}
    assert (m.recetas_nuevas, m.parches_nuevos) == (1, 1)
    assert m.total_motor("ensayadas") == 2 and m.total_motor("arbitro") == 3
    base.cerrar()


def test_el_mensaje_del_dueno_trae_el_motor_y_la_ia_solo_los_totales():
    base = BaseAsistente.abrir(":memory:")
    sembrar_motor(base)
    m = calcular_metricas_asistente(base, AHORA, navegador_caido_min=2)
    texto = "\n".join(_lineas_asistente(m))
    assert "• Linkedin: 18 enviadas · 2 ensayadas · 0 sin reconocer · 0 inciertas · " in texto
    assert "3 reparadas · 2 con árbitro · 0 de respaldo" in texto
    assert "• Computrabajo: 1 enviadas · 0 ensayadas · 1 sin reconocer · 1 inciertas" in texto
    assert "🧬 Por familia de ATS:\n• greenhouse: 18 enviadas" in texto
    assert "📦 Respaldos por motivo: sin_ia 1 · captcha 1" in texto
    assert "🧠 Aprendió hoy: 1 receta nueva · 1 parche nuevo" in texto
    para_ia = json.dumps(m.para_ia())
    assert '"motor_reparadas": 3' in para_ia and '"recetas_nuevas": 1' in para_ia
    assert "linkedin" not in para_ia and "greenhouse" not in para_ia  # nada por plataforma
    base.cerrar()
