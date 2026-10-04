"""CV con adaptación leve a cada oferta y carta de presentación, validados contra el perfil.

La IA propone solo: un resumen orientado al cargo, hasta 6 habilidades a poner primero y hasta
3 reemplazos por sinónimos que usa la oferta. Experiencias, proyectos, formación, fechas e
idiomas se copian del perfil: la IA no puede tocarlos. Todo lo que no pasa el validador se
descarta y se usa la parte equivalente del CV base.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from buscador_vacantes.asistente.afinidad import Requisitos
from buscador_vacantes.asistente.campos import DatosUsuario
from buscador_vacantes.asistente.cv_lectura import PerfilExtraido
from buscador_vacantes.asistente.gemini import ClienteGemini, ErrorIA, Parte, datos
from buscador_vacantes.asistente.tecnologias import Diccionario, diccionario
from buscador_vacantes.normalizar import normalizar_texto

log = logging.getLogger(__name__)

MAX_HABILIDADES_PRIMERO = 6
MAX_REEMPLAZOS = 3
MAX_RESUMEN = 600


class Reemplazo(BaseModel):
    original: str = Field(description="habilidad tal como está en el perfil")
    nuevo: str = Field(description="nombre equivalente que usa la oferta")


class AdaptacionLeve(BaseModel):
    resumen: str | None = Field(None, description="2 a 4 líneas orientadas al cargo")
    habilidades_primero: list[str] = Field(default_factory=list)
    reemplazos: list[Reemplazo] = Field(default_factory=list)


class Carta(BaseModel):
    carta: str


INSTRUCCION_ADAPTAR = (
    "Ajusta levemente una hoja de vida a una oferta. Devuelve: (1) un resumen profesional de "
    "2 a 4 líneas en primera persona, orientado al cargo de la oferta y basado SOLO en el "
    "resumen y el enfoque del candidato; (2) hasta 6 habilidades del candidato que coinciden "
    "con la oferta, copiadas exactamente como están en su lista; (3) hasta 3 reemplazos de "
    "una habilidad del candidato por el nombre equivalente que usa la oferta (por ejemplo "
    "'JS' por 'JavaScript'), solo si son la misma tecnología. No agregues habilidades, "
    "experiencia, títulos ni niveles que el candidato no tenga y no intentes cubrir todo lo "
    "que pide la oferta: el cambio debe ser leve."
)

INSTRUCCION_CARTA = (
    "Escribe un mensaje de presentación breve (máximo {max} caracteres), en primera persona y "
    "en español, para postular a la oferta. Usa solo datos del perfil: no inventes "
    "experiencia, conocimientos ni logros. Tono profesional y cercano, sin saludos genéricos "
    "largos ni datos de contacto."
)


@dataclass
class CVFinal:
    """Contenido listo para el PDF."""

    perfil: PerfilExtraido
    resumen: str | None
    habilidades: list[str]
    adaptado: bool = False
    descartes: list[str] = field(default_factory=list)  # lo que el validador quitó


def tecnologias_del_perfil(perfil: PerfilExtraido, dicc: Diccionario) -> set[str]:
    textos = list(perfil.habilidades_tecnicas)
    textos += [t for p in perfil.proyectos for t in p.tecnologias]
    textos += [p.descripcion or "" for p in perfil.proyectos]
    textos += [logro for e in perfil.experiencia for logro in e.logros]
    textos += [perfil.resumen or ""] + [c.nombre for c in perfil.certificaciones]
    canonicas: set[str] = set()
    for texto in textos:
        if c := dicc.canonica(texto):
            canonicas.add(c)
        canonicas.update(dicc.buscar(texto))
    return canonicas


def cv_base(perfil: PerfilExtraido) -> CVFinal:
    return CVFinal(
        perfil=perfil, resumen=perfil.resumen, habilidades=list(perfil.habilidades_tecnicas)
    )


def validar_adaptacion(
    salida: AdaptacionLeve, perfil: PerfilExtraido, dicc: Diccionario | None = None
) -> CVFinal:
    dicc = dicc or diccionario()
    propias = list(perfil.habilidades_tecnicas)
    por_norma = {normalizar_texto(h): h for h in propias}
    por_canonica = {c: h for h in propias if (c := dicc.canonica(h))}
    descartes: list[str] = []

    def propia(nombre: str) -> str | None:
        if (h := por_norma.get(normalizar_texto(nombre))) is not None:
            return h
        c = dicc.canonica(nombre)
        return por_canonica.get(c) if c else None

    primero: list[str] = []
    for nombre in salida.habilidades_primero:
        h = propia(nombre)
        if h is None:
            descartes.append(f"habilidad ajena: {nombre}")
        elif h not in primero and len(primero) < MAX_HABILIDADES_PRIMERO:
            primero.append(h)
    habilidades = primero + [h for h in propias if h not in primero]

    aplicados = 0
    for r in salida.reemplazos:
        h = propia(r.original)
        if aplicados >= MAX_REEMPLAZOS:
            descartes.append(f"reemplazo de más: {r.original} → {r.nuevo}")
        elif h is None or not dicc.son_sinonimos(h, r.nuevo):
            descartes.append(f"reemplazo no equivalente: {r.original} → {r.nuevo}")
        else:
            habilidades = [r.nuevo if x == h else x for x in habilidades]
            aplicados += 1

    resumen = perfil.resumen
    if salida.resumen:
        propias_canonicas = tecnologias_del_perfil(perfil, dicc)
        ajenas = [t for t in dicc.buscar(salida.resumen) if t not in propias_canonicas]
        if ajenas:
            descartes.append(f"resumen con tecnologías ajenas: {', '.join(ajenas)}")
        elif len(salida.resumen) > MAX_RESUMEN:
            descartes.append("resumen demasiado largo")
        else:
            resumen = salida.resumen.strip()
    adaptado = resumen != perfil.resumen or habilidades != propias
    return CVFinal(perfil, resumen, habilidades, adaptado, descartes)


async def adaptar(
    datos_usuario: DatosUsuario,
    requisitos: Requisitos,
    vacante: str,
    *,
    cliente: ClienteGemini | None,
    clave: str | None,
    usuario_id: int,
) -> CVFinal:
    """CV levemente adaptado; sin IA o si falla, el CV base sin cambios."""
    perfil = datos_usuario.perfil
    if not (cliente and clave):
        return cv_base(perfil)
    entrada = {
        "resumen": perfil.resumen,
        "enfoque": perfil.enfoque.model_dump(),
        "habilidades": perfil.habilidades_tecnicas,
        "requisitos_oferta": requisitos.model_dump(),
    }
    try:
        salida = await cliente.generar(
            "adaptar_cv", clave, usuario_id, INSTRUCCION_ADAPTAR,
            [
                Parte(datos("candidato", json.dumps(entrada, ensure_ascii=False))),
                Parte(datos("oferta", vacante)),
            ],
            AdaptacionLeve,
        )  # fmt: skip
    except ErrorIA as exc:
        log.info("CV sin adaptar: %s", exc)
        return cv_base(perfil)
    resultado = validar_adaptacion(salida, perfil)
    if resultado.descartes:
        log.info("Validador del CV descartó %d elementos", len(resultado.descartes))
    return resultado


def carta_basica(perfil: PerfilExtraido, titulo: str, habilidades: list[str], maximo: int) -> str:
    """Mensaje sin IA, solo con datos del perfil."""
    formacion = perfil.formacion[0] if perfil.formacion else None
    partes = [f"Hola, me interesa postularme a la vacante de {titulo}."]
    if formacion:
        partes.append(f"Estudio {formacion.programa} en {formacion.institucion}.")
    if habilidades:
        partes.append(f"Tengo conocimientos en {', '.join(habilidades[:4])}.")
    partes.append("Quedo atento(a) a su respuesta. ¡Muchas gracias!")
    return " ".join(partes)[:maximo]


async def redactar_carta(
    datos_usuario: DatosUsuario,
    cv: CVFinal,
    titulo: str,
    vacante: str,
    maximo: int,
    *,
    cliente: ClienteGemini | None,
    clave: str | None,
    usuario_id: int,
) -> str:
    perfil = datos_usuario.perfil
    if cliente and clave:
        try:
            salida = await cliente.generar(
                "carta", clave, usuario_id, INSTRUCCION_CARTA.format(max=maximo),
                [
                    Parte(datos("perfil", json.dumps(datos_usuario.para_ia(), ensure_ascii=False))),
                    Parte(datos("oferta", vacante)),
                ],
                Carta,
            )  # fmt: skip
            dicc = diccionario()
            propias = tecnologias_del_perfil(perfil, dicc)
            ajenas = [t for t in dicc.buscar(salida.carta) if t not in propias]
            if not ajenas and 0 < len(salida.carta.strip()) <= maximo:
                return salida.carta.strip()
            log.info("Carta de la IA descartada (tecnologías ajenas o largo)")
        except ErrorIA as exc:
            log.info("Carta sin IA: %s", exc)
    return carta_basica(perfil, titulo, cv.habilidades, maximo)
