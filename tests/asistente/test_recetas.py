import json
from datetime import UTC, datetime

import pytest

pytest.importorskip("pypdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.asistente.recetas import (  # noqa: E402
    BotonReceta,
    PantallaReceta,
    Receta,
    Trazas,
    aplicar_parches,
    barrera_de,
    barreras,
    clave_campo,
    familia_de_host,
    guardar_receta,
    host_de,
    marcar_barrera,
    parches_aplicables,
    proponer_parche,
    quitar_barrera,
    receta_para,
    registrar_resultado_receta,
    resultado_parches,
    ruta_patron,
    similitud,
)

AHORA = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
HOST = "job-boards.greenhouse.io"
URL = f"https://{HOST}/acme/jobs/4455667/apply?gh_src=abc"
CLAVES = ["first_name", "last_name", "email", "phone", "question_101", "question_102"]


@pytest.fixture
def base(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "a.db")
    yield base
    base.cerrar()


def receta(claves=CLAVES, senal="texto", boton="Submit application"):
    return Receta(
        pantallas=[PantallaReceta(
            firma=sorted(claves),
            mapeo={"first_name": "nombre_pila", "last_name": "apellido", "email": "correo",
                   "question_101": "redactar"},
            boton=BotonReceta(texto=boton, clase="enviar", selector="button[type=submit]"),
        )],
        senal=senal,
    )  # fmt: skip


def guardar(base, claves=CLAVES, **extra):
    datos = {"host": HOST, "ruta": ruta_patron(URL), "familia": "greenhouse",
             "receta": receta(claves), "origen": "real", "ahora": AHORA,
             "enviada": True}  # fmt: skip
    return guardar_receta(base, **{**datos, **extra})


# --- hosts, rutas y firmas ---------------------------------------------------------------------


def test_host_ruta_y_familia():
    assert host_de(URL) == HOST
    assert host_de("https://www.empresa.co/x") == "empresa.co"
    assert host_de(None) == ""
    assert ruta_patron(URL) == "/acme/jobs/*/apply"
    assert ruta_patron("https://x.co/p/3f2a9c1e-77b4-4c1a-9d0e-0a1b2c/aplicar") == "/p/*/aplicar"
    assert familia_de_host("job-boards.greenhouse.io") == "greenhouse"
    assert familia_de_host("empresa.wd5.myworkdayjobs.com") == "workday"
    assert familia_de_host("empresa.co", "computrabajo") == "computrabajo"
    assert familia_de_host("empresa.co") == "empresa.co"


def test_clave_de_campo_usa_el_name_o_la_etiqueta():
    assert clave_campo("First_Name", "First Name") == "first_name"
    assert clave_campo(None, "¿Cuál es tu aspiración salarial?") == "cual es tu aspiracion salarial"
    assert clave_campo("", "Email *") == "email"


def test_similitud_de_firmas():
    assert similitud({"a", "b", "c", "d", "e"}, {"a", "b", "c", "d", "x"}) == 0.8
    assert similitud({"a"}, {"b"}) == 0.0
    assert similitud(set(), set()) == 1.0
    assert similitud({"a"}, set()) == 0.0


# --- guardar y entregar recetas ----------------------------------------------------------------


def test_receta_se_guarda_solo_con_envio_y_senal_explicita(base):
    assert guardar(base, enviada=False) is None
    assert guardar(base, receta=receta(senal=None)) is None
    assert guardar(base, receta=Receta(pantallas=[], senal="texto")) is None
    assert guardar(base, receta=receta(senal="invento")) is None  # la señal no es de la lista
    assert base.cx.execute("SELECT COUNT(*) FROM recetas").fetchone()[0] == 0
    assert guardar(base) == 1


def test_receta_no_guarda_valores_ni_contacto(base):
    r = Receta.model_validate({
        "pantallas": [{
            "firma": ["first_name", "email"],
            "mapeo": {"first_name": "nombre_pila", "email": "ana@gmail.com",
                      "phone": "3105551234", "city": "Bogotá", "q": "redactar"},
            "boton": {"texto": "Submit", "clase": "enviar", "selector": "x" * 600},
        }],
        "senal": "texto",
    })  # fmt: skip
    guardar(base, receta=r)
    guardado = base.cx.execute("SELECT receta_json FROM recetas").fetchone()[0]
    for valor in ("ana@gmail.com", "3105551234", "Bogotá", "xxxxx"):
        assert valor not in guardado
    pantalla = json.loads(guardado)["pantallas"][0]
    assert pantalla["mapeo"] == {"first_name": "nombre_pila", "q": "redactar"}
    assert pantalla["boton"]["selector"] is None


def test_otra_postulacion_con_firma_parecida_refuerza_la_misma_receta(base):
    primera = guardar(base)
    parecida = guardar(base, claves=[*CLAVES[:5], "question_999"])  # 5 de 6: 83 %
    distinta = guardar(base, claves=["nombre", "cedula", "ciudad"])
    assert parecida == primera and distinta != primera
    fila = base.cx.execute("SELECT exitos FROM recetas WHERE id = ?", (primera,)).fetchone()
    assert fila["exitos"] == 2


def test_el_trabajo_lleva_la_receta_del_host_o_la_de_su_familia(base):
    guardar(base)
    del_host = receta_para(base, HOST, "greenhouse", ruta_patron(URL))
    assert del_host["alcance"] == "host" and del_host["senal"] == "texto"
    assert del_host["pantallas"][0]["boton"]["texto"] == "Submit application"
    de_la_familia = receta_para(base, "boards.greenhouse.io", "greenhouse")
    assert de_la_familia["alcance"] == "familia" and de_la_familia["id"] == del_host["id"]
    assert receta_para(base, "empresa.co", "otra") is None


def test_receta_de_ensayo_sirve_para_mapeo_y_botones_pero_no_para_la_senal(base):
    guardar(base, origen="ensayo", enviada=False, receta=receta(senal=None))
    entregada = receta_para(base, HOST, "greenhouse")
    assert entregada["origen"] == "ensayo" and entregada["senal"] is None
    assert entregada["pantallas"][0]["mapeo"]["email"] == "correo"
    guardar(base)  # un envío real la vuelve real y trae señal
    assert receta_para(base, HOST, "greenhouse")["senal"] == "texto"


def test_dos_fallos_seguidos_apagan_la_receta_y_un_exito_los_reinicia(base):
    rid = guardar(base)
    assert registrar_resultado_receta(base, rid, False) is False
    assert registrar_resultado_receta(base, rid, True) is False  # reinicia la cuenta
    assert registrar_resultado_receta(base, rid, False) is False
    assert registrar_resultado_receta(base, rid, False) is True  # el segundo seguido la apaga
    assert receta_para(base, HOST, "greenhouse") is None
    assert registrar_resultado_receta(base, rid, False) is False  # ya apagada: sin aviso doble


def test_un_envio_exitoso_reactiva_la_receta_apagada(base):
    rid = guardar(base)
    registrar_resultado_receta(base, rid, False)
    registrar_resultado_receta(base, rid, False)
    assert receta_para(base, HOST, "greenhouse") is None
    assert guardar(base) == rid
    assert receta_para(base, HOST, "greenhouse")["id"] == rid


# --- trazas ---------------------------------------------------------------------------------------


def test_trazas_arman_la_receta_en_orden_y_la_vuelta_de_correccion_reemplaza():
    trazas = Trazas()
    p1 = PantallaReceta(firma=["a"], mapeo={"a": "ciudad"})
    p2 = PantallaReceta(firma=["b"], mapeo={"b": "redactar"})
    corregida = PantallaReceta(firma=["b"], mapeo={"b": "ciudad"})
    trazas.agregar(7, 2, "https://x.co/2", p2)
    trazas.agregar(7, 1, "https://x.co/1", p1)
    trazas.agregar(7, 2, "https://x.co/2", corregida)
    trazas.senal(7, "invento")
    trazas.senal(7, "url")
    url, receta_armada = trazas.sacar(7)
    assert url == "https://x.co/2" and receta_armada.senal == "url"  # la url de la primera llamada
    assert [p.mapeo for p in receta_armada.pantallas] == [{"a": "ciudad"}, {"b": "ciudad"}]
    assert trazas.sacar(7) is None  # se olvida al sacarla


def test_trazas_acota_cuantas_postulaciones_recuerda():
    trazas = Trazas()
    for pid in range(Trazas.MAX_POSTULACIONES + 5):
        trazas.agregar(pid, 1, "https://x.co", PantallaReceta())
    assert trazas.sacar(0) is None and trazas.sacar(Trazas.MAX_POSTULACIONES + 4) is not None


# --- dominios barrera --------------------------------------------------------------------------


def test_dominio_barrera_se_recuerda_y_el_dueno_puede_quitarlo(base):
    assert marcar_barrera(base, "ats.example.com", "ats_con_cuenta", AHORA) is True
    assert marcar_barrera(base, "ats.example.com", "ats_con_cuenta", AHORA) is False
    assert barrera_de(base, "ats.example.com") == "ats_con_cuenta"
    assert barreras(base) == [{"host": "ats.example.com", "motivo": "ats_con_cuenta"}]
    assert quitar_barrera(base, "ats.example.com") is True
    assert barrera_de(base, "ats.example.com") is None and quitar_barrera(base, "x") is False


def test_solo_las_barreras_de_cuenta_oauth_o_mensajeria_marcan_el_dominio(base):
    assert marcar_barrera(base, "ats.example.com", "captcha", AHORA) is False
    assert marcar_barrera(base, "", "oauth", AHORA) is False
    assert barrera_de(base, "") is None and barrera_de(base, "ats.example.com") is None


# --- parches candidatos ------------------------------------------------------------------------

CONTENIDO = {
    "version": "1",
    "postular": [
        {"nombre": "revisar_vacante", "accion": "detectar", "casos": []},
        {"nombre": "aplicar", "accion": "ir", "selector": ["a[data-href-offer-apply]"]},
    ],
}


def test_parche_se_antepone_a_los_selectores_del_paso_sin_tocar_el_original(base):
    proponer_parche(base, "computrabajo", "aplicar", "a.btn-apply-v2", AHORA, 5)
    parchado = aplicar_parches(CONTENIDO, parches_aplicables(base, "computrabajo"))
    assert parchado["postular"][1]["selector"] == ["a.btn-apply-v2", "a[data-href-offer-apply]"]
    assert CONTENIDO["postular"][1]["selector"] == ["a[data-href-offer-apply]"]  # no se tocó
    assert parchado["postular"][0] == CONTENIDO["postular"][0]  # no agrega pasos ni toca otros


def test_parche_mas_reciente_queda_primero_y_un_paso_inexistente_se_ignora(base):
    proponer_parche(base, "computrabajo", "aplicar", "a.uno", AHORA)
    proponer_parche(base, "computrabajo", "aplicar", {"css": "a", "texto": "Postular"}, AHORA)
    proponer_parche(base, "computrabajo", "no_existe", "a.otro", AHORA)
    parchado = aplicar_parches(CONTENIDO, parches_aplicables(base, "computrabajo"))
    assert parchado["postular"][1]["selector"][:2] == [{"css": "a", "texto": "Postular"}, "a.uno"]
    assert len(parchado["postular"]) == 2


def test_parche_repetido_o_invalido_no_se_guarda(base):
    assert proponer_parche(base, "computrabajo", "aplicar", "a.btn", AHORA) == 1
    assert proponer_parche(base, "computrabajo", "aplicar", "a.btn", AHORA) is None
    assert proponer_parche(base, "computrabajo", "aplicar", "", AHORA) is None
    assert proponer_parche(base, "computrabajo", "aplicar", "x" * 600, AHORA) is None
    assert proponer_parche(base, "computrabajo", "", "a.btn", AHORA) is None


def test_candidato_pasa_a_firme_con_un_exito_y_se_descarta_con_un_fallo(base):
    bueno = proponer_parche(base, "computrabajo", "aplicar", "a.bueno", AHORA)
    malo = proponer_parche(base, "computrabajo", "aplicar", "a.malo", AHORA)
    cambios = resultado_parches(base, [bueno], True, AHORA)
    assert [(c["id"], c["estado"]) for c in cambios] == [(bueno, "firme")]
    cambios = resultado_parches(base, [malo], False, AHORA)
    assert [(c["id"], c["estado"]) for c in cambios] == [(malo, "descartado")]
    assert [p["id"] for p in parches_aplicables(base, "computrabajo")] == [bueno]
    # Un firme sigue firme aunque la postulación falle por otra causa, y no avisa dos veces
    assert resultado_parches(base, [bueno], False, AHORA) == []
    assert resultado_parches(base, [bueno], True, AHORA) == []
    assert resultado_parches(base, [malo], True, AHORA) == []  # un descartado no revive


def test_parche_y_receta_no_guardan_nada_de_la_persona(base):
    proponer_parche(base, "computrabajo", "aplicar", "a.btn", AHORA, 9)
    guardar(base)
    volcado = json.dumps([
        [tuple(f) for f in base.cx.execute(f"SELECT * FROM {t}").fetchall()]
        for t in ("recetas", "parches_flujo", "dominios_barrera")
    ], ensure_ascii=False, default=str)  # fmt: skip
    assert "@" not in volcado and "310" not in volcado
