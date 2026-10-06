from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="requiere uv sync --group asistente")
pytest.importorskip("cryptography", reason="requiere uv sync --group asistente")

from fastapi.testclient import TestClient  # noqa: E402

from buscador_vacantes.asistente import vinculos  # noqa: E402
from buscador_vacantes.asistente.api import (  # noqa: E402
    LIMITE_PING_POR_MINUTO,
    MAX_CUERPO,
    ResultadoFormulario,
    crear_app,
    sin_valores,
)
from buscador_vacantes.asistente.cifrado import Cifrador, generar_clave  # noqa: E402
from buscador_vacantes.asistente.cola import Cola, E  # noqa: E402
from buscador_vacantes.asistente.cuentas_portal import CuentasPortal  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.asistente.preferencias import Preferencias  # noqa: E402
from buscador_vacantes.asistente.respuestas import Origen, Respuesta  # noqa: E402
from buscador_vacantes.config import cargar_configuracion  # noqa: E402

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
CT = "computrabajo"
CORREO = "ana.perez@gmail.com"


class NucleoFalso:
    def __init__(self, tmp_path: Path):
        self.base = BaseAsistente.abrir(tmp_path / "a.db")
        self.config = cargar_configuracion().asistente
        self.cola = Cola(self.base, self.config)
        self.cuentas = CuentasPortal(self.base, Cifrador(generar_clave()))
        self.preferencias = Preferencias(self.base)
        self.archivos = tmp_path / "archivos"
        self.momento = T0
        self.eventos: list = []
        self.faltan = False
        self.cv = tmp_path / "CV_Ana_Perez.pdf"
        self.cv.write_bytes(b"%PDF-1.4 cv")
        with self.base.transaccion() as cx:
            for uid in (1, 2):
                cx.execute(
                    "INSERT INTO usuarios(id, telegram_id, directorio, creado, estado) "
                    "VALUES (?, ?, ?, 'x', 'activo')",
                    (uid, uid, f"u{uid}"),
                )
            cx.execute(
                "INSERT INTO vacantes(id_corto, clave, fuente, plataforma, url, titulo, "
                "indexada_en) VALUES ('abc', 'computrabajo:1', 'computrabajo', 'computrabajo', "
                "'https://co.computrabajo.com/ofertas-de-trabajo/oferta-1', 'Practicante', 'x')"
            )

    def ahora(self):
        return self.momento

    def vacante(self, id_corto):
        fila = self.base.cx.execute("SELECT * FROM vacantes WHERE id_corto = ?", (id_corto,))
        fila = fila.fetchone()
        return dict(fila) if fila else None

    def selectores(self, plataforma):
        return ("1", {"postular": "#postular"}) if plataforma == CT else None

    async def resolver_formulario(self, postulacion, preguntas):
        if self.faltan:
            return ResultadoFormulario(faltan=[Respuesta(preguntas[0], falta=True)])
        respuestas = [Respuesta(p, valor="Sí", origen=Origen.PERFIL) for p in preguntas]
        return ResultadoFormulario(respuestas=respuestas, cv=self.cv)

    async def notificar(self, evento):
        self.eventos.append(evento)


@pytest.fixture
def entorno(tmp_path):
    nucleo = NucleoFalso(tmp_path)
    cliente = TestClient(crear_app(nucleo))
    yield nucleo, cliente
    nucleo.base.cerrar()


def vincular(nucleo, cliente, usuario_id=1):
    codigo = vinculos.crear_codigo(nucleo.base, usuario_id, nucleo.momento)
    cuerpo = {"codigo": vinculos.mostrar_codigo(codigo), "nombre": "Edge casa", "version": "1.0.0"}
    r = cliente.post("/api/v1/vincular", json=cuerpo)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def latido(cliente, cabeceras, estado="listo", correo=CORREO, version="1.0.0"):
    return cliente.post(
        "/api/v1/latido",
        headers=cabeceras,
        json={"version": version, "portales": {CT: {"estado": estado, "correo": correo}}},
    ).json()


def preparar_cuenta(nucleo, cliente, cab):
    latido(cliente, cab)  # primera vez: por confirmar
    nucleo.cuentas.confirmar(1, CT, T0)


def test_codigo_vencido_o_usado(entorno):
    nucleo, cliente = entorno
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    nucleo.momento = T0 + timedelta(minutes=11)
    assert cliente.post("/api/v1/vincular", json={"codigo": codigo}).status_code == 400
    nucleo.momento = T0
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    assert cliente.post("/api/v1/vincular", json={"codigo": codigo}).status_code == 200
    assert cliente.post("/api/v1/vincular", json={"codigo": codigo}).status_code == 400


def test_pagina_de_vinculo_lleva_el_codigo(entorno):
    nucleo, cliente = entorno
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    r = cliente.get(f"/api/v1/vincular/{codigo}")
    assert r.status_code == 200 and f'data-codigo="{codigo}"' in r.text


def test_pagina_de_vinculo_vuelve_al_bot_de_telegram(entorno):
    nucleo, cliente = entorno
    nucleo.config.bot_usuario = "mi_bot"
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    texto = cliente.get(f"/api/v1/vincular/{codigo}").text
    assert 'href="https://t.me/mi_bot"' in texto and "Volver a Telegram" in texto
    assert "¡Navegador vinculado con éxito!" in texto and vinculos.mostrar_codigo(codigo) in texto


def test_pagina_de_vinculo_sin_bot_configurado_no_ofrece_el_boton(entorno):
    nucleo, cliente = entorno
    nucleo.config.bot_usuario = ""
    codigo = vinculos.crear_codigo(nucleo.base, 1, T0)
    assert "Volver a Telegram" not in cliente.get(f"/api/v1/vincular/{codigo}").text


def test_politica_de_privacidad_publica(entorno):
    _, cliente = entorno
    r = cliente.get("/api/v1/privacidad")
    assert r.status_code == 200 and "contraseñas" in r.text and "/borrarme" in r.text


def test_ping_publico_sin_token(entorno):
    _, cliente = entorno
    r = cliente.get("/api/v1/ping")
    assert r.status_code == 200 and r.json() == {"ok": True}  # sin versión ni datos


def test_ping_no_cuenta_como_latido(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    latido(cliente, cab)
    consulta = "SELECT ultimo_latido FROM navegadores"
    antes = nucleo.base.cx.execute(consulta).fetchone()[0]
    nucleo.momento = T0 + timedelta(minutes=5)
    assert cliente.get("/api/v1/ping", headers=cab).status_code == 200
    assert nucleo.base.cx.execute(consulta).fetchone()[0] == antes


def test_ping_limitado_por_ip(entorno):
    nucleo, cliente = entorno
    for _ in range(LIMITE_PING_POR_MINUTO):
        assert cliente.get("/api/v1/ping").status_code == 200
    assert cliente.get("/api/v1/ping").status_code == 429
    otra_ip = TestClient(cliente.app, client=("10.0.0.2", 50000))
    assert otra_ip.get("/api/v1/ping").status_code == 200


def test_token_invalido_401(entorno):
    _, cliente = entorno
    cab = {"Authorization": "Bearer x"}
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1"})
    assert r.status_code == 401


def test_cuerpo_grande_413(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post(
        "/api/v1/latido", headers={**cab, "Content-Type": "application/json"},
        content=b"{" + b" " * (MAX_CUERPO + 1) + b"}",
    )  # fmt: skip
    assert r.status_code == 413


def test_fuera_de_la_api_404(entorno):
    _, cliente = entorno
    assert cliente.get("/").status_code == 404
    assert cliente.get("/docs").status_code == 404


def test_primera_cuenta_pide_confirmar_y_no_da_trabajo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    nucleo.cola.encolar(1, "abc", CT, T0)
    respuesta = latido(cliente, cab)
    assert respuesta["trabajo"] is None and respuesta["cuentas"][CT] is False
    assert any(
        e.get("tipo") == "cuenta_por_confirmar" for e in nucleo.eventos if isinstance(e, dict)
    )


def test_flujo_completo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    trabajo = latido(cliente, cab)["trabajo"]
    assert trabajo["id"] == p.id and trabajo["url"].startswith("https://co.computrabajo.com")
    assert cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab).status_code == 200
    r = cliente.post(
        f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
        json={"campos": [{"texto": "¿Tienes computador?", "tipo": "opciones",
                          "opciones": ["Sí", "No"]}]},
    ).json()  # fmt: skip
    assert r["respuestas"][0]["valor"] == "Sí" and r["cv_nombre"] == "CV_Ana_Perez.pdf"
    pdf = cliente.get(r["cv_url"], headers=cab)
    assert pdf.content == b"%PDF-1.4 cv"
    assert cliente.get(r["cv_url"], headers=cab).status_code == 404  # un solo uso
    assert cliente.post(f"/api/v1/postulaciones/{p.id}/envio", headers=cab).status_code == 200
    html = '<form><input name="correo" value="ana@x.com"><textarea>hola</textarea></form>'
    cuerpo = {"estado": "enviada", "html": html, "confirmacion": "¡Postulado!"}
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/resultado", headers=cab, json=cuerpo)
    assert r.status_code == 200
    assert nucleo.cola.obtener(p.id).estado == E.ENVIADA
    archivo = nucleo.base.cx.execute("SELECT archivo FROM evidencia").fetchone()[0]
    guardado = Path(archivo).read_text(encoding="utf-8")
    assert "ana@x.com" not in guardado and "hola" not in guardado


def test_dos_tomar_simultaneos_uno_gana(entorno):
    nucleo, cliente = entorno
    cab1 = vincular(nucleo, cliente)
    cab2 = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab1)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    codigos = [
        cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=c).status_code
        for c in (cab1, cab2)
    ]
    assert sorted(codigos) == [200, 409]


def test_otro_usuario_no_ve_la_postulacion(entorno):
    nucleo, cliente = entorno
    cab_luis = vincular(nucleo, cliente, usuario_id=2)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    assert cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab_luis).status_code == 404


def test_dato_faltante_libera_la_postulacion(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    p, _ = nucleo.cola.encolar(1, "abc", CT, T0)
    cliente.post(f"/api/v1/postulaciones/{p.id}/tomar", headers=cab)
    nucleo.faltan = True
    r = cliente.post(f"/api/v1/postulaciones/{p.id}/formulario", headers=cab,
                     json={"campos": [{"texto": "¿Licencia de conducción?"}]}).json()  # fmt: skip
    assert r == {"esperar_usuario": True}
    assert nucleo.cola.obtener(p.id).estado == E.ESPERANDO_USUARIO


def test_cuenta_distinta_no_da_trabajo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    respuesta = latido(cliente, cab, correo="luis.g@hotmail.com")
    assert respuesta["trabajo"] is None
    evento = [e for e in nucleo.eventos if isinstance(e, dict) and e["tipo"] == "cuenta_distinta"]
    assert evento and evento[0]["encontrado"] == "l***@hotmail.com"
    fila = nucleo.base.cx.execute("SELECT correo_cifrado FROM cuentas_portal").fetchone()
    assert "luis" not in fila[0]


def test_extension_desactualizada_no_recibe_trabajo(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    nucleo.cola.encolar(1, "abc", CT, T0)
    nucleo.config.extension.version_minima = "1.2.0"
    respuesta = latido(cliente, cab, version="1.1.9")
    assert respuesta["actualizar"] is True and respuesta["trabajo"] is None


def test_perfil_incompleto_encola_completar_perfil(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    trabajo = latido(cliente, cab, estado="incompleto")["trabajo"]
    assert trabajo["tipo"] == "completar_perfil"


def test_token_revocado(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    vinculos.revocar(nucleo.base, 1)
    assert cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).status_code == 401


def test_sin_valores():
    texto = sin_valores('<input type="text" value="secreto"><textarea id=x>dato</textarea>')
    assert "secreto" not in texto and "dato" not in texto


def test_latido_entrega_los_enlaces_del_bot_y_el_grupo(entorno):
    nucleo, cliente = entorno
    nucleo.enlace_grupo = "https://t.me/c/4429829042/1"
    cab = vincular(nucleo, cliente)
    r = cliente.post("/api/v1/latido", headers=cab, json={"version": "1.0.0"}).json()
    assert r["enlaces"]["grupo"] == "https://t.me/c/4429829042/1"
    bot = nucleo.config.bot_usuario
    assert r["enlaces"]["bot"] == (f"https://t.me/{bot}" if bot else None)


def test_enlace_del_grupo():
    from buscador_vacantes.asistente.servicio import enlace_grupo

    config = cargar_configuracion().asistente
    secretos = type("S", (), {"telegram_chat_id": "-1004429829042"})()
    assert enlace_grupo(config, secretos) == "https://t.me/c/4429829042/1"
    con_invitacion = config.model_copy(
        update={"grupo": config.grupo.model_copy(update={"enlace": "https://t.me/+abc"})}
    )
    assert enlace_grupo(con_invitacion, secretos) == "https://t.me/+abc"
    secretos.telegram_chat_id = "@canal"
    assert enlace_grupo(config, secretos) is None


# --- engranaje de cada portal: preferencias y cuenta ---------------------------------------


def test_preferencias_por_defecto(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.get(f"/api/v1/preferencias/{CT}", headers=cab)
    assert r.status_code == 200
    datos = r.json()
    assert datos["automatico"] is True
    assert datos["umbral"] is None
    assert datos["avisar"] is True
    assert datos["cuenta"] is None


def test_guardar_y_leer_preferencias(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post(
        f"/api/v1/preferencias/{CT}", headers=cab,
        json={"automatico": False, "umbral": 85, "avisar": False},
    )  # fmt: skip
    assert r.status_code == 200
    r = cliente.get(f"/api/v1/preferencias/{CT}", headers=cab)
    datos = r.json()
    assert datos == {
        "automatico": False, "umbral": 85, "avisar": False, "cuenta": None,
    }  # fmt: skip


def test_preferencias_con_cuenta_confirmada_muestra_el_detalle(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    r = cliente.get(f"/api/v1/preferencias/{CT}", headers=cab)
    cuenta = r.json()["cuenta"]
    assert cuenta["correo"] == CORREO
    assert cuenta["estado"] == "confirmada"
    assert cuenta["confirmada_en"]


def test_preferencias_plataforma_no_soportada_404(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    assert cliente.get("/api/v1/preferencias/elempleo", headers=cab).status_code == 404
    assert cliente.post("/api/v1/preferencias/elempleo", headers=cab, json={}).status_code == 404


def test_preferencias_umbral_fuera_de_rango_422(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    r = cliente.post(f"/api/v1/preferencias/{CT}", headers=cab, json={"umbral": 150})
    assert r.status_code == 422


def test_olvidar_cuenta(entorno):
    nucleo, cliente = entorno
    cab = vincular(nucleo, cliente)
    preparar_cuenta(nucleo, cliente, cab)
    assert nucleo.cuentas.asociado(1, CT) is not None
    r = cliente.post(f"/api/v1/cuenta/{CT}/olvidar", headers=cab)
    assert r.status_code == 200
    assert nucleo.cuentas.asociado(1, CT) is None


def test_preferencias_sin_token_401(entorno):
    _, cliente = entorno
    assert cliente.get(f"/api/v1/preferencias/{CT}").status_code == 401
