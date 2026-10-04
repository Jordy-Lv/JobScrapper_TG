import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from clasificador import Clasificador, Dudosa
from config import cargar_configuracion
from estado import Estado
from filtros import Filtros
from ia_cliente import ClienteIA, RespuestaIA
from modelo import Categoria, Vacante
from normalizar import huella

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
    assert {"titulo", "empresa", "ubicacion", "modalidad", "palabra_clave"} <= set(item)


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


@pytest.mark.parametrize(("politica", "aceptadas"), [("descartar", 0), ("aceptar", 1)])
def test_clasificador_desactivado(config, estado, politica, aceptadas):
    ia = IAFalsa()
    clasificador = crear(config, estado, ia, activo=False, politica_sin_ia=politica)
    resultado = clasificador.clasificar([dudosa("Analista Junior")], AHORA)
    assert ia.lotes == []
    assert len(resultado.aceptadas) == aceptadas
    assert len(resultado.rechazadas) == 1 - aceptadas


@pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"), reason="prueba real: requiere DEEPSEEK_API_KEY"
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
