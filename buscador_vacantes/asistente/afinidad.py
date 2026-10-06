"""Requisitos de la vacante (una vez por vacante, compartidos) y afinidad determinista.

La afinidad es informativa: nunca impide una postulación pedida con ⚡. Solo decide en el modo
automático de cada usuario.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from buscador_vacantes.asistente.cv_lectura import PerfilExtraido
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.ia import ClienteIA, ErrorIA, Parte, datos
from buscador_vacantes.asistente.tecnologias import Diccionario, diccionario
from buscador_vacantes.normalizar import normalizar_texto

log = logging.getLogger(__name__)

MAX_REQUISITOS = 12


class Requisitos(BaseModel):
    obligatorios: list[str] = Field(default_factory=list, description="conocimientos exigidos")
    deseables: list[str] = Field(default_factory=list, description="conocimientos deseables")
    palabras_clave: list[str] = Field(default_factory=list)
    nivel: str | None = Field(None, description="practicante, aprendiz, junior u otro")
    modalidad: str | None = None


INSTRUCCION_REQUISITOS = (
    "Extrae de la vacante los conocimientos técnicos y herramientas que pide, separando los "
    "obligatorios de los deseables (los que dicen 'deseable', 'plus' o 'valorado'). Usa "
    "nombres cortos (por ejemplo 'Python', 'SQL', 'Excel avanzado'). Como máximo 12 en total. "
    "No incluyas requisitos que no estén en el texto."
)


def requisitos_por_diccionario(texto: str, dicc: Diccionario | None = None) -> Requisitos:
    """Respaldo sin IA: las tecnologías del diccionario mencionadas en el texto."""
    encontradas = (dicc or diccionario()).buscar(texto)[:MAX_REQUISITOS]
    return Requisitos(obligatorios=encontradas, palabras_clave=encontradas)


async def obtener_requisitos(
    base: BaseAsistente,
    id_corto: str,
    texto_vacante: str,
    *,
    cliente: ClienteIA | None = None,
    clave: str | None = None,
    usuario_id: int | None = None,
) -> Requisitos:
    """Requisitos en caché compartida. Los del diccionario se mejoran con IA cuando se pueda."""
    fila = base.cx.execute(
        "SELECT requisitos_json FROM vacantes WHERE id_corto = ?", (id_corto,)
    ).fetchone()
    guardado = json.loads(fila["requisitos_json"]) if fila and fila["requisitos_json"] else None
    if guardado and (guardado["origen"] == "ia" or not (cliente and clave)):
        return Requisitos.model_validate(guardado["requisitos"])

    origen, requisitos = "diccionario", None
    if cliente and clave:
        try:
            requisitos = await cliente.generar(
                "requisitos", clave, usuario_id, INSTRUCCION_REQUISITOS,
                [Parte(datos("vacante", texto_vacante))], Requisitos,
            )  # fmt: skip
            origen = "ia"
        except ErrorIA as exc:
            log.info("Requisitos sin IA para %s: %s", id_corto, exc)
    if requisitos is None:
        requisitos = requisitos_por_diccionario(texto_vacante)
    with base.transaccion() as cx:
        cx.execute(
            "UPDATE vacantes SET requisitos_json = ? WHERE id_corto = ?",
            (
                json.dumps(
                    {"origen": origen, "requisitos": requisitos.model_dump()}, ensure_ascii=False
                ),
                id_corto,
            ),
        )
    return requisitos


@dataclass
class Afinidad:
    porcentaje: int
    cumple: list[str] = field(default_factory=list)
    faltan: list[str] = field(default_factory=list)


def habilidades_del_perfil(perfil: PerfilExtraido) -> list[str]:
    habilidades = list(perfil.habilidades_tecnicas)
    for proyecto in perfil.proyectos:
        habilidades.extend(proyecto.tecnologias)
    habilidades.extend(c.nombre for c in perfil.certificaciones)
    habilidades.extend(i.idioma for i in perfil.idiomas)
    return habilidades


def _tiene(requisito: str, canonicas: set[str], textos: set[str], dicc: Diccionario) -> bool:
    canonica = dicc.canonica(requisito)
    if canonica is not None:
        return canonica in canonicas
    norma = normalizar_texto(requisito)
    return any(norma == t or (len(norma) > 3 and norma in t) for t in textos)


def calcular_afinidad(
    requisitos: Requisitos, perfil: PerfilExtraido, dicc: Diccionario | None = None
) -> Afinidad | None:
    """(obligatorios cumplidos × 2 + deseables cumplidos) / (obligatorios × 2 + deseables)."""
    dicc = dicc or diccionario()
    habilidades = habilidades_del_perfil(perfil)
    canonicas = {c for h in habilidades if (c := dicc.canonica(h))}
    for h in habilidades:  # "Excel avanzado", "Python 3"… también cuentan por diccionario
        canonicas.update(dicc.buscar(h))
    textos = {normalizar_texto(h) for h in habilidades}
    total = 2 * len(requisitos.obligatorios) + len(requisitos.deseables)
    if total == 0:
        return None
    puntos, cumple, faltan = 0, [], []
    for peso, lista in ((2, requisitos.obligatorios), (1, requisitos.deseables)):
        for requisito in lista:
            if _tiene(requisito, canonicas, textos, dicc):
                puntos += peso
                cumple.append(requisito)
            else:
                faltan.append(requisito)
    return Afinidad(round(100 * puntos / total), cumple, faltan)
