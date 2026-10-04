from datetime import UTC, datetime, timedelta

import pytest

from buscador_vacantes.asistente.cola import Cola, E
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import a_texto

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)  # 10:00 en Bogotá
CT = "computrabajo"
LISTOS = {CT, "magneto"}


@pytest.fixture
def cola(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "a.db")
    with base.transaccion() as cx:
        cx.execute("INSERT INTO usuarios(id, telegram_id, directorio, creado) VALUES (1,1,'u','x')")
        for nid in (10, 11):
            cx.execute(
                "INSERT INTO navegadores(id, usuario_id, token_hash, creado, ultimo_latido) "
                "VALUES (?, 1, ?, 'x', ?)",
                (nid, f"h{nid}", a_texto(T0)),
            )
    config = cargar_configuracion().asistente
    yield Cola(base, config)
    base.cerrar()


def latido(cola, momento, navegador=10):
    with cola.base.transaccion() as cx:
        cx.execute(
            "UPDATE navegadores SET ultimo_latido = ? WHERE id = ?", (a_texto(momento), navegador)
        )


def ejecutar(cola, pid, momento, resultado=E.ENVIADA, navegador=10):
    assert cola.tomar(pid, navegador, momento)
    assert cola.iniciar(pid, navegador, momento)
    if resultado == E.ENVIADA:
        assert cola.marcar_envio_pulsado(pid, navegador, momento)
    return cola.terminar(pid, navegador, resultado, momento)


def test_doble_toque_una_sola_postulacion(cola):
    p1, creada1 = cola.encolar(1, "abc", CT, T0)
    p2, creada2 = cola.encolar(1, "abc", CT, T0)
    assert creada1 and not creada2 and p1.id == p2.id


def test_dos_navegadores_un_solo_toma(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    assert cola.tomar(p.id, 10, T0)
    assert not cola.tomar(p.id, 11, T0)
    assert not cola.iniciar(p.id, 11, T0)  # el otro navegador no puede operarla


def test_flujo_completo_registra_pasos(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    evento = ejecutar(cola, p.id, T0)
    assert evento.estado == E.ENVIADA
    pasos = [
        f[0]
        for f in cola.base.cx.execute(
            "SELECT paso FROM postulacion_pasos WHERE postulacion_id = ? ORDER BY id", (p.id,)
        )
    ]
    assert pasos[0] == "encolada" and "envio_pulsado" in pasos


def test_completar_perfil_va_primero_y_no_se_duplica(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    c1 = cola.encolar_completar_perfil(1, CT, T0 + timedelta(seconds=1))
    c2 = cola.encolar_completar_perfil(1, CT, T0 + timedelta(seconds=2))
    assert c1 == c2
    assert cola.siguiente(1, LISTOS, T0).id == c1


def test_solo_portales_listos(cola):
    cola.encolar(1, "abc", "magneto", T0)
    assert cola.siguiente(1, {CT}, T0) is None
    assert cola.siguiente(1, {"magneto"}, T0) is not None


def test_de_a_una_y_pausa_entre_postulaciones(cola):
    a, _ = cola.encolar(1, "a", CT, T0)
    b, _ = cola.encolar(1, "b", CT, T0)
    assert cola.tomar(a.id, 10, T0)
    assert cola.siguiente(1, LISTOS, T0) is None  # hay una activa
    cola.iniciar(a.id, 10, T0)
    cola.marcar_envio_pulsado(a.id, 10, T0)
    cola.terminar(a.id, 10, E.ENVIADA, T0)
    assert cola.siguiente(1, LISTOS, T0 + timedelta(seconds=10)) is None  # pausa mínima 45 s
    assert cola.siguiente(1, LISTOS, T0 + timedelta(seconds=121)).id == b.id


def test_tope_diario(cola):
    cola.config.topes.usuario_dia = 2
    momento = T0
    for i in range(2):
        p, _ = cola.encolar(1, f"v{i}", CT, momento)
        ejecutar(cola, p.id, momento)
        momento += timedelta(minutes=5)
    cola.encolar(1, "v9", CT, momento)
    assert cola.siguiente(1, LISTOS, momento) is None
    assert cola.siguiente(1, LISTOS, momento + timedelta(days=1)) is not None


def test_navegador_cerrado_antes_de_enviar_vuelve_a_la_cola(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    cola.iniciar(p.id, 10, T0)
    latido(cola, T0 - timedelta(minutes=5))
    eventos = cola.vigilar(T0)
    assert cola.obtener(p.id).estado == E.EN_COLA
    assert eventos[0].tipo == "reencolada"


def test_navegador_cerrado_despues_de_enviar_es_incierta(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    cola.iniciar(p.id, 10, T0)
    cola.marcar_envio_pulsado(p.id, 10, T0)
    latido(cola, T0 - timedelta(minutes=5))
    cola.vigilar(T0)
    assert cola.obtener(p.id).estado == E.INCIERTA


def test_sesion_tras_envio_pulsado_es_incierta(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    cola.iniciar(p.id, 10, T0)
    cola.marcar_envio_pulsado(p.id, 10, T0)
    assert cola.terminar(p.id, 10, E.ESPERANDO_SESION, T0).estado == E.INCIERTA


def test_dato_faltante_pregunta_y_luego_se_reencola(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    cola.iniciar(p.id, 10, T0)
    assert cola.esperar_usuario(p.id, 10, T0)
    assert cola.obtener(p.id).navegador_id is None
    assert cola.reanudar(p.id, T0, (E.ESPERANDO_USUARIO,))
    assert cola.siguiente(1, LISTOS, T0).id == p.id


def test_dato_faltante_sin_respuesta_va_a_respaldo(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    cola.iniciar(p.id, 10, T0)
    cola.esperar_usuario(p.id, 10, T0)
    latido(cola, T0 + timedelta(hours=13))
    eventos = cola.vigilar(T0 + timedelta(hours=13))
    assert cola.obtener(p.id).estado == E.RESPALDO
    assert eventos[0].detalle == "sin_respuesta"


def test_pc_apagado_espera_y_luego_respaldo(cola):
    latido(cola, T0 - timedelta(hours=1))
    latido(cola, T0 - timedelta(hours=1), navegador=11)
    p, _ = cola.encolar(1, "abc", CT, T0)
    eventos = cola.vigilar(T0)
    assert cola.obtener(p.id).estado == E.ESPERANDO_NAVEGADOR
    assert eventos[0].tipo == "navegador_desconectado"
    # El navegador vuelve: se reanuda sola
    assert cola.portales_actualizados(1, LISTOS, T0 + timedelta(hours=2)) == [p.id]
    assert cola.obtener(p.id).estado == E.EN_COLA
    # Si no vuelve en 24 h: paquete de respaldo
    q, _ = cola.encolar(1, "def", CT, T0)
    cola.vigilar(T0)
    cola.vigilar(T0 + timedelta(hours=25))
    assert cola.obtener(q.id).estado == E.RESPALDO


def test_sesion_iniciada_reanuda_lo_que_esperaba_sesion(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    cola.iniciar(p.id, 10, T0)
    cola.terminar(p.id, 10, E.ESPERANDO_SESION, T0)
    assert cola.portales_actualizados(1, {"magneto"}, T0) == []
    assert cola.portales_actualizados(1, {CT}, T0) == [p.id]


def test_verificacion_sin_resolver_queda_bloqueada(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    cola.iniciar(p.id, 10, T0)
    assert cola.verificacion(p.id, 10, T0)
    latido(cola, T0 + timedelta(hours=3))
    cola.vigilar(T0 + timedelta(hours=3))
    assert cola.obtener(p.id).estado == E.BLOQUEADA


def test_modo_automatico_solo_sobre_el_umbral(cola):
    assert cola.debe_encolar_automatico(70, 82, CT, 1, T0)
    assert not cola.debe_encolar_automatico(70, 60, CT, 1, T0)
    assert not cola.debe_encolar_automatico(None, 90, CT, 1, T0)  # modo desactivado
    assert not cola.debe_encolar_automatico(70, 90, "linkedin", 1, T0)


def test_reinicio_decide_por_envio_pulsado(cola):
    a, _ = cola.encolar(1, "a", CT, T0)
    cola.tomar(a.id, 10, T0)
    cola.iniciar(a.id, 10, T0)
    cola.marcar_envio_pulsado(a.id, 10, T0)
    cola.config.topes.usuario_dia = 10
    eventos = cola.recuperar_al_arrancar(T0)
    assert cola.obtener(a.id).estado == E.INCIERTA and eventos


def test_resultado_no_permitido(cola):
    p, _ = cola.encolar(1, "abc", CT, T0)
    cola.tomar(p.id, 10, T0)
    with pytest.raises(ValueError):
        cola.terminar(p.id, 10, E.EN_COLA, T0)
