from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from buscador_vacantes.asistente import espera as e
from buscador_vacantes.asistente.cola import Restriccion
from buscador_vacantes.asistente.espera import Causa, Entrada, NavegadorLatido, causa

AHORA = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
PORTALES = ("computrabajo", "magneto", "elempleo")


def portal(estado="listo", cuenta="ok", motivo=None):
    return {"estado": estado, "cuenta": cuenta, "motivo": motivo}


def navegador(plataforma, *, id=1, hace=timedelta(seconds=20), version="1.4.0", pausado=False, **p):
    portales = {plataforma: portal(**p), "_pausado": pausado}
    return NavegadorLatido(id, AHORA - hace, version, portales)


def entrada(plataforma, navegadores, **cambios):
    base = Entrada(
        plataforma=plataforma,
        navegadores=navegadores,
        ahora=AHORA,
        version_minima="1.4.0",
        navegador_caido=timedelta(minutes=2),
        plataforma_encendida=True,
    )
    return replace(base, **cambios)


@pytest.mark.parametrize("plataforma", PORTALES)
def test_sin_causa_si_todo_esta_listo(plataforma):
    assert causa(entrada(plataforma, [navegador(plataforma)])) is None


@pytest.mark.parametrize("plataforma", PORTALES)
def test_sin_navegador_vinculado(plataforma):
    assert causa(entrada(plataforma, [])) == Causa(e.SIN_NAVEGADOR, plataforma)


@pytest.mark.parametrize("plataforma", PORTALES)
def test_sin_latido_reciente_lleva_la_hora_del_ultimo_contacto(plataforma):
    viejo = navegador(plataforma, hace=timedelta(minutes=30))
    resultado = causa(entrada(plataforma, [viejo]))
    assert resultado.codigo == e.SIN_LATIDO
    assert resultado.datos == {"ultimo": viejo.ultimo_latido.isoformat()}


def test_navegador_que_nunca_dio_latido_no_esta_reciente():
    nuevo = NavegadorLatido(1, None, "1.4.0", {})
    resultado = causa(entrada("magneto", [nuevo]))
    assert resultado == Causa(e.SIN_LATIDO, "magneto")


@pytest.mark.parametrize("plataforma", PORTALES)
def test_extension_desactualizada_lleva_las_dos_versiones(plataforma):
    n = navegador(plataforma, version="1.3.0")
    resultado = causa(entrada(plataforma, [n]))
    assert resultado == Causa(
        e.EXTENSION_DESACTUALIZADA, plataforma, {"version": "1.3.0", "minima": "1.4.0"}
    )


@pytest.mark.parametrize("plataforma", PORTALES)
def test_extension_en_pausa(plataforma):
    n = navegador(plataforma, pausado=True)
    assert causa(entrada(plataforma, [n])) == Causa(e.EXTENSION_EN_PAUSA, plataforma)


@pytest.mark.parametrize("plataforma", PORTALES)
def test_plataforma_apagada(plataforma):
    n = navegador(plataforma)
    resultado = causa(entrada(plataforma, [n], plataforma_encendida=False))
    assert resultado == Causa(e.PLATAFORMA_APAGADA, plataforma)


@pytest.mark.parametrize("plataforma", PORTALES)
def test_sin_permiso_de_dominio(plataforma):
    n = navegador(plataforma, estado="sin_permiso")
    assert causa(entrada(plataforma, [n])) == Causa(e.SIN_PERMISO, plataforma)


def test_portal_que_nunca_aparecio_se_toma_como_sin_permiso():
    n = NavegadorLatido(1, AHORA, "1.4.0", {"_pausado": False})
    assert causa(entrada("elempleo", [n])) == Causa(e.SIN_PERMISO, "elempleo")


@pytest.mark.parametrize("plataforma", PORTALES)
def test_sin_sesion(plataforma):
    n = navegador(plataforma, estado="sin_sesion", motivo="enlace_ingresar")
    assert causa(entrada(plataforma, [n])) == Causa(e.SIN_SESION, plataforma)


@pytest.mark.parametrize("plataforma", PORTALES)
@pytest.mark.parametrize(
    ("cuenta", "esperada"),
    [
        ("por_confirmar", e.CUENTA_POR_CONFIRMAR),
        ("distinta", e.CUENTA_DISTINTA),
        ("sin_correo", e.CORREO_ILEGIBLE),
    ],
)
def test_cuenta_sin_confirmar(plataforma, cuenta, esperada):
    n = navegador(plataforma, cuenta=cuenta)
    assert causa(entrada(plataforma, [n])) == Causa(esperada, plataforma)


@pytest.mark.parametrize("plataforma", PORTALES)
def test_perfil_incompleto(plataforma):
    n = navegador(plataforma, estado="incompleto")
    assert causa(entrada(plataforma, [n])) == Causa(e.PERFIL_INCOMPLETO, plataforma)


@pytest.mark.parametrize("plataforma", PORTALES)
@pytest.mark.parametrize(
    ("restriccion", "esperada", "datos"),
    [
        (Restriccion("en_curso", None), e.OTRA_EN_CURSO, {}),
        (
            Restriccion("tope_diario", AHORA + timedelta(hours=9)),
            e.TOPE_DIARIO,
            {"cuando": (AHORA + timedelta(hours=9)).isoformat()},
        ),
        (
            Restriccion("pausa", AHORA + timedelta(seconds=40)),
            e.PAUSA,
            {"cuando": (AHORA + timedelta(seconds=40)).isoformat()},
        ),
    ],
)
def test_esperas_normales_de_la_cola(plataforma, restriccion, esperada, datos):
    n = navegador(plataforma)
    resultado = causa(entrada(plataforma, [n], restriccion=restriccion))
    assert resultado == Causa(esperada, plataforma, datos)


def test_version_gana_a_la_sesion():
    n = navegador("magneto", version="1.2.0", estado="sin_sesion")
    assert causa(entrada("magneto", [n])).codigo == e.EXTENSION_DESACTUALIZADA


def test_el_orden_completo_de_prioridad():
    # Cada causa le gana a todas las que van después
    n = navegador("magneto", version="1.0.0", pausado=True, estado="sin_sesion", cuenta="distinta")
    restriccion = Restriccion("en_curso", None)
    assert (
        causa(entrada("magneto", [n], restriccion=restriccion)).codigo == e.EXTENSION_DESACTUALIZADA
    )
    n = replace(n, version="1.4.0")
    assert causa(entrada("magneto", [n], restriccion=restriccion)).codigo == e.EXTENSION_EN_PAUSA
    n = replace(n, portales={**n.portales, "_pausado": False})
    apagada = entrada("magneto", [n], plataforma_encendida=False, restriccion=restriccion)
    assert causa(apagada).codigo == e.PLATAFORMA_APAGADA
    sin_sesion = entrada("magneto", [n], restriccion=restriccion)
    assert causa(sin_sesion).codigo == e.SIN_SESION
    n = navegador("magneto", estado="listo", cuenta="distinta")
    assert causa(entrada("magneto", [n], restriccion=restriccion)).codigo == e.CUENTA_DISTINTA
    n = navegador("magneto", estado="incompleto")
    assert causa(entrada("magneto", [n], restriccion=restriccion)).codigo == e.PERFIL_INCOMPLETO
    n = navegador("magneto")
    assert causa(entrada("magneto", [n], restriccion=restriccion)).codigo == e.OTRA_EN_CURSO


def test_dos_navegadores_uno_listo_no_hay_causa_del_navegador():
    sin_sesion = navegador("magneto", id=1, estado="sin_sesion")
    listo = navegador("magneto", id=2)
    assert causa(entrada("magneto", [sin_sesion, listo])) is None


def test_dos_navegadores_uno_listo_sigue_la_restriccion_de_la_cola():
    sin_sesion = navegador("magneto", id=1, estado="sin_sesion")
    listo = navegador("magneto", id=2)
    pausa = Restriccion("pausa", AHORA + timedelta(seconds=30))
    resultado = causa(entrada("magneto", [sin_sesion, listo], restriccion=pausa))
    assert resultado.codigo == e.PAUSA


def test_dos_navegadores_con_causa_gana_el_latido_mas_reciente():
    viejo = navegador("magneto", id=1, hace=timedelta(seconds=90), estado="sin_sesion")
    nuevo = navegador("magneto", id=2, hace=timedelta(seconds=5), estado="incompleto")
    assert causa(entrada("magneto", [viejo, nuevo])).codigo == e.PERFIL_INCOMPLETO


def test_un_navegador_caido_no_tapa_al_vigente_que_esta_listo():
    caido = navegador("magneto", id=1, hace=timedelta(hours=3))
    listo = navegador("magneto", id=2)
    assert causa(entrada("magneto", [caido, listo])) is None


def test_la_causa_se_guarda_y_se_lee_como_diccionario():
    original = Causa(e.TOPE_DIARIO, "magneto", {"cuando": "2026-10-18T05:00:00+00:00"})
    assert Causa.de_dict(original.a_dict()) == original
    assert Causa.de_dict(None) is None
    assert Causa.de_dict({}) is None


def test_todas_las_causas_estan_listadas_una_vez():
    assert len(e.CAUSAS) == len(set(e.CAUSAS)) == 17
