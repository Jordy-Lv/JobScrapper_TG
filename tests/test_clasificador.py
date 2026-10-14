import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from buscador_vacantes.comun.config import cargar_configuracion
from buscador_vacantes.comun.estado import Estado
from buscador_vacantes.comun.modelo import Categoria, Vacante
from buscador_vacantes.comun.normalizar import huella
from buscador_vacantes.radar.clasificador import Clasificador, Dudosa
from buscador_vacantes.radar.filtros import Filtros
from buscador_vacantes.radar.ia_cliente import ClienteIA, RespuestaIA

AHORA = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
FIXTURE = Path(__file__).parent / "fixtures" / "dudosas_reales.json"


class IAFalsa:
    """Responde con lo programado y registra cada lote recibido."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.lotes = []

    def chat_json(self, proposito, prompt, payload, *, temperatura, max_tokens):
        self.lotes.append(payload["vacantes"])
        respuesta = self.respuestas.pop(0) if self.respuestas else RespuestaIA(True, {})
        return respuesta(payload) if callable(respuesta) else respuesta


def aceptar_todas(categoria="desarrollo"):
    def responder(payload):
        return RespuestaIA(True, {"vacantes": [
            {"id": v["id"], "aceptar": True, "categoria": categoria, "motivo": "TI junior"}
            for v in payload["vacantes"]
        ]})  # fmt: skip

    return responder


@pytest.fixture
def config():
    return cargar_configuracion()


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


def crear(config, estado, ia, **cambios):
    conf = config.clasificador.model_copy(update=cambios)
    return Clasificador(conf, ia, estado, Filtros(config.filtros))


def dudosa(titulo, fuente="linkedin", id_fuente=None, empresa="Empresa"):
    vacante = Vacante(fuente=fuente, id_fuente=id_fuente or titulo, titulo=titulo,
                      empresa=empresa, url="https://x", keyword="kw")  # fmt: skip
    return Dudosa(vacante, huella(titulo, empresa, vacante.clave))


def pendientes(estado):
    return estado.cx.execute("SELECT COUNT(*) FROM pendientes").fetchone()[0]


def test_dudosas_clasificadas_en_una_llamada(config, estado):
    ia = IAFalsa(lambda p: RespuestaIA(True, {"vacantes": [
        {"id": 0, "aceptar": True, "categoria": "datos", "motivo": "datos junior"},
        {"id": 1, "aceptar": False, "categoria": None, "motivo": "no es TI"},
        {"id": 2, "aceptar": True, "categoria": "practicas", "motivo": "práctica TI"},
        {"id": 3, "aceptar": False, "motivo": "senior"},
        {"id": 4, "aceptar": True, "categoria": "qa", "motivo": "QA"},
    ]}))  # fmt: skip
    titulos = ["Analista Junior", "Practicante", "Pasante", "Analista", "Tester"]
    resultado = crear(config, estado, ia).clasificar([dudosa(t) for t in titulos], AHORA)
    assert len(ia.lotes) == 1 and len(ia.lotes[0]) == 5
    assert resultado.llamadas == 1
    assert [d.vacante.titulo for d in resultado.aceptadas] == [
        "Analista Junior",
        "Pasante",
        "Tester",
    ]
    assert [d.vacante.categoria for d in resultado.aceptadas] == [
        Categoria.DATOS,
        Categoria.PRACTICAS,
        Categoria.QA,
    ]
    assert len(resultado.rechazadas) == 2
    assert pendientes(estado) == 0


def test_payload_sin_url_y_con_ids_cortos(config, estado):
    ia = IAFalsa(aceptar_todas())
    crear(config, estado, ia).clasificar([dudosa("Analista Junior")], AHORA)
    [item] = ia.lotes[0]
    assert item["id"] == 0
    assert "url" not in item
    assert {"titulo", "empresa", "ubicacion", "modalidad", "salario", "palabra_clave"} <= set(item)
    assert item["ciudad_base"] == "Cartagena"
    assert item["exige_modalidad"] is None


def test_payload_no_dice_que_la_fuente_filtro_por_nivel(config, estado):
    ia = IAFalsa(aceptar_todas())
    crear(config, estado, ia).clasificar([dudosa("Frontend Developer")], AHORA)
    assert "nivel_filtrado_por_fuente" not in json.dumps(ia.lotes[0])


def test_payload_trae_la_condicion_de_modalidad(config, estado):
    ia = IAFalsa(aceptar_todas())
    remoto_o_hibrido, solo_remoto, sin_condicion = (
        dudosa("Analista de datos Jr", id_fuente="1"),
        dudosa("Asesor de soporte técnico", id_fuente="2"),
        dudosa("Analista", id_fuente="3"),
    )
    remoto_o_hibrido.vacante.exige_modalidad = "remoto_o_hibrido"
    solo_remoto.vacante.exige_modalidad = "remoto"
    crear(config, estado, ia).clasificar([remoto_o_hibrido, solo_remoto, sin_condicion], AHORA)
    assert [v["exige_modalidad"] for v in ia.lotes[0]] == ["remoto o híbrido", "solo remoto", None]


def test_sin_dudosas_no_llama(config, estado):
    ia = IAFalsa()
    resultado = crear(config, estado, ia).clasificar([], AHORA)
    assert ia.lotes == [] and resultado.llamadas == 0


def test_cache_en_otra_fuente(config, estado):
    ia = IAFalsa(aceptar_todas("soporte"))
    clasificador = crear(config, estado, ia)
    clasificador.clasificar([dudosa("Auxiliar TI", "linkedin", "1")], AHORA)
    resultado = clasificador.clasificar([dudosa("Auxiliar TI", "computrabajo", "ABC")], AHORA)
    assert len(ia.lotes) == 1
    assert resultado.desde_cache == 1 and resultado.llamadas == 0
    assert resultado.aceptadas[0].vacante.categoria == Categoria.SOPORTE
    assert resultado.aceptadas[0].vacante.fuente == "computrabajo"


def test_ia_caida_deja_pendientes_y_reintenta(config, estado):
    ia = IAFalsa(RespuestaIA(False, motivo="timeout"), aceptar_todas())
    clasificador = crear(config, estado, ia)
    resultado = clasificador.clasificar([dudosa("Analista Junior"), dudosa("Pasante")], AHORA)
    assert len(resultado.pendientes) == 2 and resultado.aceptadas == []
    assert resultado.motivo_fallo == "timeout"
    assert pendientes(estado) == 2
    # La siguiente corrida reintenta las pendientes aunque no lleguen de nuevo
    siguiente = clasificador.clasificar([], AHORA + timedelta(minutes=30))
    assert len(siguiente.aceptadas) == 2
    assert pendientes(estado) == 0


def test_pendiente_vencida(config, estado):
    ia = IAFalsa(RespuestaIA(False, motivo="timeout"))
    clasificador = crear(config, estado, ia)
    clasificador.clasificar([dudosa("Analista Junior")], AHORA)
    resultado = clasificador.clasificar([], AHORA + timedelta(hours=25))
    assert [d.vacante.titulo for d in resultado.vencidas] == ["Analista Junior"]
    assert len(ia.lotes) == 1  # no se volvió a llamar
    assert pendientes(estado) == 0


def test_tope_diario_deja_pendientes(config, estado):
    ia = IAFalsa(RespuestaIA(False, motivo="tope diario alcanzado", realizada=False))
    resultado = crear(config, estado, ia).clasificar([dudosa("Analista Junior")], AHORA)
    assert resultado.llamadas == 0
    assert len(resultado.pendientes) == 1


def test_respuesta_incompleta(config, estado):
    ia = IAFalsa(lambda p: RespuestaIA(True, {"vacantes": [
        {"id": 0, "aceptar": True, "categoria": "inventada", "motivo": "x"},
    ]}))  # fmt: skip
    resultado = crear(config, estado, ia).clasificar(
        [dudosa("Desarrollador web"), dudosa("Analista")], AHORA
    )
    # Categoría inválida → la de términos; id faltante → pendiente
    assert resultado.aceptadas[0].vacante.categoria == Categoria.DESARROLLO
    assert [d.vacante.titulo for d in resultado.pendientes] == ["Analista"]


def test_respuesta_con_forma_invalida(config, estado):
    ia = IAFalsa(RespuestaIA(True, {"resultado": "todo bien"}))
    resultado = crear(config, estado, ia).clasificar([dudosa("Analista")], AHORA)
    assert len(resultado.pendientes) == 1
    assert resultado.motivo_fallo == "respuesta inválida"


def test_lotes_segun_maximo(config, estado):
    ia = IAFalsa(aceptar_todas(), aceptar_todas())
    nuevas = [dudosa(f"Analista {i}") for i in range(35)]
    resultado = crear(config, estado, ia).clasificar(nuevas, AHORA)
    assert [len(lote) for lote in ia.lotes] == [30, 5]
    assert resultado.llamadas == 2 and len(resultado.aceptadas) == 35


def clasificaciones_guardadas(estado):
    return [dict(f) for f in estado.cx.execute("SELECT * FROM clasificaciones")]


def test_clasificacion_guarda_la_version_del_prompt(config, estado):
    clasificador = crear(config, estado, IAFalsa(aceptar_todas()))
    clasificador.clasificar([dudosa("Auxiliar TI")], AHORA)
    [fila] = clasificaciones_guardadas(estado)
    assert fila["version_prompt"] == clasificador.version_prompt
    assert len(clasificador.version_prompt) == 12


def test_mismo_prompt_reutiliza_la_clasificacion(config, estado):
    ia = IAFalsa(aceptar_todas())
    crear(config, estado, ia).clasificar([dudosa("Auxiliar TI")], AHORA)
    resultado = crear(config, estado, ia).clasificar([dudosa("Auxiliar TI", "magneto")], AHORA)
    assert len(ia.lotes) == 1 and resultado.desde_cache == 1


def test_prompt_cambiado_vuelve_a_clasificar(config, estado):
    ia = IAFalsa(aceptar_todas(), aceptar_todas())
    crear(config, estado, ia).clasificar([dudosa("Auxiliar TI")], AHORA)
    nuevo = crear(config, estado, ia, prompt_sistema=config.clasificador.prompt_sistema + " Más.")
    resultado = nuevo.clasificar([dudosa("Auxiliar TI", "magneto")], AHORA)
    assert len(ia.lotes) == 2 and resultado.desde_cache == 0 and resultado.llamadas == 1
    [fila] = clasificaciones_guardadas(estado)  # se reemplaza, sigue una por huella
    assert fila["version_prompt"] == nuevo.version_prompt


def test_clasificacion_sin_version_no_se_reutiliza(config, estado):
    ia = IAFalsa(aceptar_todas())
    clasificador = crear(config, estado, ia)
    h = dudosa("Auxiliar TI").huella
    with estado.transaccion() as cx:  # fila del esquema 1: sin versión de prompt
        cx.execute(
            "INSERT INTO clasificaciones(huella, aceptar, categoria, motivo, ts) "
            "VALUES (?, 1, 'soporte', 'viejo', '2026-10-01T00:00:00+00:00')",
            (h,),
        )
    resultado = clasificador.clasificar([dudosa("Auxiliar TI")], AHORA)
    assert len(ia.lotes) == 1 and resultado.desde_cache == 0


@pytest.mark.parametrize(("politica", "aceptadas"), [("descartar", 0), ("aceptar", 1)])
def test_clasificador_desactivado(config, estado, politica, aceptadas):
    ia = IAFalsa()
    clasificador = crear(config, estado, ia, activo=False, politica_sin_ia=politica)
    resultado = clasificador.clasificar([dudosa("Analista Junior")], AHORA)
    assert ia.lotes == []
    assert len(resultado.aceptadas) == aceptadas
    assert len(resultado.rechazadas) == 1 - aceptadas


@pytest.mark.skipif(
    not (os.environ.get("PRUEBA_REAL") and os.environ.get("DEEPSEEK_API_KEY")),
    reason="prueba real: requiere PRUEBA_REAL=1 y DEEPSEEK_API_KEY",
)
def test_real_20_dudosas_contra_deepseek(config, estado):
    ia = ClienteIA(config.ia, os.environ["DEEPSEEK_API_KEY"], estado)
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    nuevas = []
    for d in datos:
        vacante = Vacante(keyword="hermes", **d)
        nuevas.append(Dudosa(vacante, huella(vacante.titulo, vacante.empresa, vacante.clave)))
    resultado = crear(config, estado, ia).clasificar(nuevas, AHORA)
    ia.cerrar()
    print("\nACEPTADAS")
    for d in resultado.aceptadas:
        print(f"  {d.vacante.titulo} → {d.vacante.categoria}")
    print("RECHAZADAS")
    for d in resultado.rechazadas:
        print(f"  {d.vacante.titulo}")
    assert resultado.llamadas == 1
    assert len(resultado.aceptadas) + len(resultado.rechazadas) == 20


def test_payload_trae_la_descripcion_recortada_con_la_frase_de_modalidad(config, estado):
    ia = IAFalsa(aceptar_todas())
    relleno = "Responsabilidades: documentar, probar y desplegar servicios internos. " * 80
    d = dudosa("Analista de datos Jr")
    d.vacante.descripcion = relleno + "Esta posición es 100% remota. Beneficios de ley."
    d.vacante.exige_modalidad = "remoto_o_hibrido"
    corta = dudosa("Tester Jr", id_fuente="2")
    corta.vacante.descripcion = "Pruebas manuales."
    sin = dudosa("Soporte Jr", id_fuente="3")
    crear(config, estado, ia).clasificar([d, corta, sin], AHORA)
    largo, breve, vacio = (v["descripcion"] for v in ia.lotes[0])
    maximo = config.clasificador.max_caracteres_descripcion
    assert len(largo) <= maximo + 1000 + 3
    assert "100% remota" in largo and "Beneficios de ley" not in largo
    assert (breve, vacio) == ("Pruebas manuales.", None)


def test_el_prompt_distingue_la_modalidad_del_puesto_de_la_de_la_empresa(config):
    prompt = " ".join(config.clasificador.prompt_sistema.split())
    assert "modalidad de ESTE puesto" in prompt
    assert "equipos remotos" in prompt and "oficinas remotas" in prompt
