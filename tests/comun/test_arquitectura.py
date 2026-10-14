"""Dirección de las dependencias entre paquetes: comun ← asistente ← radar."""

import ast
from pathlib import Path

import pytest

PAQUETE = Path(__file__).resolve().parents[2] / "buscador_vacantes"

# Paquete → paquetes del proyecto que NO puede importar
PROHIBIDO = {
    "comun": {"radar", "asistente"},
    "asistente": {"radar"},
    "radar": set(),
}


def importados(archivo: Path) -> set[str]:
    """Paquetes de primer nivel (dentro de buscador_vacantes) que importa el archivo."""
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    destinos = set()
    for nodo in ast.walk(arbol):
        modulos = []
        if isinstance(nodo, ast.Import):
            modulos = [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            base = nodo.module
            modulos = [base] + [f"{base}.{a.name}" for a in nodo.names]
        for modulo in modulos:
            partes = modulo.split(".")
            if partes[0] == "buscador_vacantes" and len(partes) > 1:
                destinos.add(partes[1])
    return destinos


@pytest.mark.parametrize("paquete", sorted(PROHIBIDO))
def test_las_dependencias_van_en_un_solo_sentido(paquete):
    archivos = sorted((PAQUETE / paquete).rglob("*.py"))
    assert archivos, f"el paquete {paquete} no tiene módulos"
    violaciones = [
        f"{a.relative_to(PAQUETE)} importa {destino}"
        for a in archivos
        for destino in importados(a) & PROHIBIDO[paquete]
    ]
    assert not violaciones, "\n".join(violaciones)


def test_no_quedan_modulos_planos_fuera_de_los_paquetes():
    sueltos = sorted(p.name for p in PAQUETE.glob("*.py") if p.name != "__init__.py")
    assert not sueltos, f"módulos sin paquete: {sueltos}"
