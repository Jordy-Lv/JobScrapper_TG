"""Rotación de palabras clave por fuente: lote núcleo + cola larga, con posición persistente."""

from __future__ import annotations

from dataclasses import dataclass

from buscador_vacantes.estado import Estado

NUCLEO = "nucleo"
COLA_LARGA = "cola_larga"


@dataclass(frozen=True)
class Consulta:
    keyword: str
    grupo: str
    pagina: int = 1


def _tomar(lista: list[str], inicio: int, cantidad: int) -> list[str]:
    """Toma ``cantidad`` elementos desde ``inicio`` dando la vuelta, sin repetir en un lote."""
    if not lista:
        return []
    cantidad = min(cantidad, len(lista))
    return [lista[(inicio + i) % len(lista)] for i in range(cantidad)]


def obtener_indice(estado: Estado, fuente: str, grupo: str) -> int:
    fila = estado.cx.execute(
        "SELECT indice FROM rotacion WHERE fuente = ? AND grupo = ?", (fuente, grupo)
    ).fetchone()
    return fila["indice"] if fila else 0


def calcular_lote(
    estado: Estado,
    fuente: str,
    nucleo: list[str],
    cola_larga: list[str],
    presupuesto: int,
    reservado_nucleo: int,
    paginas_nucleo: int = 1,
) -> list[Consulta]:
    """Lote de la corrida: primero las consultas núcleo reservadas y luego la cola larga.

    El presupuesto cuenta requests: cada palabra clave del núcleo ocupa ``paginas_nucleo``
    requests (páginas 1..N consecutivas) y la cola larga lee solo la primera página.
    Si un grupo está vacío, su parte del presupuesto pasa al otro.
    """
    paginas = max(1, paginas_nucleo)
    n_nucleo = min(reservado_nucleo, presupuesto // paginas, len(nucleo))
    libre = presupuesto - n_nucleo * paginas
    n_cola = min(libre, len(cola_larga))
    if n_cola < libre:
        n_nucleo = min((presupuesto - n_cola) // paginas, len(nucleo))
    lote = [
        Consulta(k, NUCLEO, pagina)
        for k in _tomar(nucleo, obtener_indice(estado, fuente, NUCLEO), n_nucleo)
        for pagina in range(1, paginas + 1)
    ]
    lote += [
        Consulta(k, COLA_LARGA)
        for k in _tomar(cola_larga, obtener_indice(estado, fuente, COLA_LARGA), n_cola)
    ]
    return lote


def avanzar(estado: Estado, fuente: str, grupo: str, cantidad: int, total: int) -> None:
    """Avanza la posición de un grupo según las consultas realmente ejecutadas."""
    if cantidad <= 0 or total <= 0:
        return
    nuevo = (obtener_indice(estado, fuente, grupo) + cantidad) % total
    with estado.transaccion() as cx:
        cx.execute(
            "INSERT INTO rotacion(fuente, grupo, indice) VALUES (?, ?, ?) "
            "ON CONFLICT(fuente, grupo) DO UPDATE SET indice = excluded.indice",
            (fuente, grupo, nuevo),
        )


def avanzar_lote(
    estado: Estado,
    fuente: str,
    ejecutadas: list[Consulta],
    total_nucleo: int,
    total_cola: int,
) -> None:
    # El núcleo avanza por palabra clave, no por página
    nucleo = sum(c.grupo == NUCLEO and c.pagina == 1 for c in ejecutadas)
    avanzar(estado, fuente, NUCLEO, nucleo, total_nucleo)
    avanzar(estado, fuente, COLA_LARGA, sum(c.grupo == COLA_LARGA for c in ejecutadas), total_cola)
