"""Lectura de la hoja de vida: texto local con pypdf, enmascarado y perfil con Gemini.

A Gemini nunca llegan el correo, el teléfono, el documento ni la dirección: si el PDF tiene
texto, se enmascaran antes de enviarlo. Un PDF escaneado (sin texto) solo se envía completo
con la confirmación del usuario.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.gemini import ClienteGemini, Parte, datos

MIN_CARACTERES_TEXTO = 200  # menos que esto: PDF escaneado o sin texto útil
TIEMPO_MAXIMO_LECTURA_S = 20  # un PDF hecho para colgar al lector no bloquea el servicio

RE_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_TELEFONO = re.compile(
    r"(?<![\w])(?:\+?57[\s.-]?)?(?:\(?\d{1,3}\)?[\s.-]?)?\d{3}[\s.-]?\d{2,4}[\s.-]?\d{2,4}(?![\w])"
)
RE_DOCUMENTO = re.compile(
    r"\b(?:C\.?\s?C\.?|c[eé]dula(?:\s+de\s+ciudadan[ií]a)?|documento(?:\s+de\s+identidad)?|"
    r"T\.?\s?I\.?|C\.?\s?E\.?|NIT|pasaporte)\s*(?:No\.?|N[°º]|#|:)?\s*[\d.\s-]{6,15}\d",
    re.IGNORECASE,
)
RE_DIRECCION = re.compile(
    r"\b(?:calle|cl|carrera|cra|kr|cr|avenida|av|diagonal|dg|transversal|tv|autopista)"
    r"\.?\s*\d+[a-z]?(?:\s*bis)?\s*(?:#|n[°º]?|no\.?)\s*\d+[a-z]?\s*-\s*\d+[^\n,;]*",
    re.IGNORECASE,
)


class CVInvalido(Exception):
    """El archivo no es un PDF legible, supera los límites o no es una hoja de vida."""


class RequiereConfirmacion(Exception):
    """PDF escaneado: enviarlo completo a Gemini necesita la confirmación del usuario."""


# --- Perfil extraído (esquema de salida de Gemini) ----------------------------------


class Formacion(BaseModel):
    institucion: str
    programa: str
    nivel: str | None = Field(None, description="técnico, tecnólogo, profesional, etc.")
    semestre: str | None = None
    estado: str | None = Field(None, description="en curso, finalizado, aplazado")
    inicio: str | None = None
    fin: str | None = None


class Experiencia(BaseModel):
    empresa: str
    cargo: str
    inicio: str | None = None
    fin: str | None = None
    logros: list[str] = Field(default_factory=list)


class Proyecto(BaseModel):
    nombre: str
    descripcion: str | None = None
    tecnologias: list[str] = Field(default_factory=list)


class Idioma(BaseModel):
    idioma: str
    nivel: str | None = Field(None, description="A1-C2, nativo, básico, intermedio, avanzado")


class Certificacion(BaseModel):
    nombre: str
    entidad: str | None = None
    anio: str | None = None


class Enlace(BaseModel):
    tipo: str = Field(description="github, portafolio, linkedin u otro")
    url: str


class Enfoque(BaseModel):
    roles: list[str] = Field(default_factory=list, description="roles que busca")
    tecnologias_destacar: list[str] = Field(default_factory=list)
    objetivo: str | None = None


class PerfilExtraido(BaseModel):
    es_cv: bool = Field(description="false si el documento no es una hoja de vida")
    nombre: str | None = None
    ciudad: str | None = None
    resumen: str | None = None
    formacion: list[Formacion] = Field(default_factory=list)
    experiencia: list[Experiencia] = Field(default_factory=list)
    proyectos: list[Proyecto] = Field(default_factory=list)
    habilidades_tecnicas: list[str] = Field(default_factory=list)
    habilidades_blandas: list[str] = Field(default_factory=list)
    idiomas: list[Idioma] = Field(default_factory=list)
    certificaciones: list[Certificacion] = Field(default_factory=list)
    enlaces: list[Enlace] = Field(default_factory=list)
    enfoque: Enfoque = Field(default_factory=Enfoque)


INSTRUCCION = (
    "Eres un asistente que convierte hojas de vida en español en un perfil estructurado. "
    "Extrae solo lo que está escrito en el documento; si un dato no aparece, déjalo vacío o "
    "null, nunca lo inventes. Los datos de contacto aparecen enmascarados y no debes "
    "reconstruirlos. Propón el enfoque (roles que busca y tecnologías a destacar) solo a "
    "partir de lo que el documento muestra. Si el documento no es una hoja de vida, responde "
    "es_cv=false."
)


# --- Texto local y enmascarado ------------------------------------------------------


@dataclass
class DatosLocales:
    """Datos de contacto detectados en el PDF: se ofrecen en el cuestionario, nunca a la IA."""

    correo: str | None = None
    telefono: str | None = None
    documento: str | None = None


@dataclass
class TextoCV:
    texto: str
    paginas: int
    escaneado: bool
    locales: DatosLocales = field(default_factory=DatosLocales)


def validar_archivo(contenido: bytes, limites: cfg.AsistenteCV) -> None:
    if len(contenido) > limites.max_mb * 1024 * 1024:
        raise CVInvalido(f"El archivo supera {limites.max_mb:g} MB.")
    if not contenido.startswith(b"%PDF"):
        raise CVInvalido("El archivo no es un PDF.")


def extraer_texto(contenido: bytes, limites: cfg.AsistenteCV) -> TextoCV:
    validar_archivo(contenido, limites)
    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted:
            raise CVInvalido("El PDF está protegido con contraseña.")
        paginas = len(lector.pages)
        if paginas > limites.max_paginas:
            raise CVInvalido(f"El PDF tiene {paginas} páginas; el máximo es {limites.max_paginas}.")
        texto = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    except CVInvalido:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise CVInvalido("No se pudo leer el PDF; puede estar dañado.") from exc
    texto = texto.strip()
    escaneado = len(re.sub(r"\s+", "", texto)) < MIN_CARACTERES_TEXTO
    return TextoCV(texto=texto, paginas=paginas, escaneado=escaneado)


def enmascarar(texto: str) -> tuple[str, DatosLocales]:
    """Quita correo, teléfono, documento y dirección. Devuelve el texto y lo detectado."""
    locales = DatosLocales()
    if m := RE_CORREO.search(texto):
        locales.correo = m.group(0)
    texto = RE_CORREO.sub("[correo]", texto)
    if m := RE_DOCUMENTO.search(texto):
        locales.documento = re.sub(r"\D", "", m.group(0)) or None
    texto = RE_DOCUMENTO.sub("[documento]", texto)
    texto = RE_DIRECCION.sub("[dirección]", texto)
    for m in RE_TELEFONO.finditer(texto):
        digitos = re.sub(r"\D", "", m.group(0))
        if 7 <= len(digitos) <= 13 and not re.fullmatch(r"(19|20)\d{2}", digitos):
            locales.telefono = locales.telefono or m.group(0).strip()
    texto = RE_TELEFONO.sub(_reemplazo_telefono, texto)
    return texto, locales


def _reemplazo_telefono(m: re.Match) -> str:
    digitos = re.sub(r"\D", "", m.group(0))
    return "[teléfono]" if 7 <= len(digitos) <= 13 else m.group(0)


# --- Lectura con Gemini -------------------------------------------------------------


@dataclass
class LecturaCV:
    perfil: PerfilExtraido
    locales: DatosLocales
    escaneado: bool


async def leer_cv(
    cliente: ClienteGemini,
    clave: str,
    usuario_id: int,
    contenido: bytes,
    limites: cfg.AsistenteCV,
    *,
    permitir_archivo_completo: bool = False,
) -> LecturaCV:
    """Extrae el perfil. Lanza RequiereConfirmacion si es escaneado y no hay permiso."""
    try:
        cv = await asyncio.wait_for(
            asyncio.to_thread(extraer_texto, contenido, limites), TIEMPO_MAXIMO_LECTURA_S
        )
    except TimeoutError as exc:
        raise CVInvalido("El PDF tardó demasiado en leerse; prueba con otro archivo.") from exc
    if cv.escaneado:
        if not permitir_archivo_completo:
            raise RequiereConfirmacion(
                "Tu hoja de vida parece escaneada: para leerla hay que enviar el archivo "
                "completo a Gemini, incluidos tus datos de contacto."
            )
        partes = [Parte(pdf=contenido)]
        locales = DatosLocales()
    else:
        texto, locales = enmascarar(cv.texto)
        partes = [Parte(datos("hoja_de_vida", texto))]
    perfil = await cliente.generar(
        "leer_cv", clave, usuario_id, INSTRUCCION, partes, PerfilExtraido
    )
    if not perfil.es_cv:
        raise CVInvalido("El documento no parece una hoja de vida. Envía tu CV en PDF.")
    return LecturaCV(perfil=perfil, locales=locales, escaneado=cv.escaneado)
