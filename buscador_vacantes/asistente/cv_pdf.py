"""PDF de la hoja de vida apto para ATS: una columna, sin foto, texto real y 2 páginas máximo."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from fpdf import FPDF

from buscador_vacantes.asistente.cv_adaptado import CVFinal
from buscador_vacantes.config import RAIZ

FUENTES = RAIZ / "assets" / "fuentes"
MAX_PAGINAS = 2
GRIS = (90, 98, 112)
AZUL = (31, 58, 95)


@dataclass
class Contacto:
    nombre: str
    ciudad: str | None = None
    correo: str | None = None
    telefono: str | None = None
    enlaces: tuple[str, ...] = ()


def nombre_archivo(nombre: str) -> str:
    """CV_<Nombre>_<Apellido>.pdf, sin tildes ni caracteres especiales (igual en toda oferta)."""
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    partes = [p for p in re.split(r"[^A-Za-z0-9]+", ascii_) if p]
    if not partes:
        return "CV.pdf"
    seleccion = [partes[0]] + ([partes[2]] if len(partes) >= 4 else partes[1:2])
    return "CV_" + "_".join(p.capitalize() for p in seleccion) + ".pdf"


class _Documento(FPDF):
    def __init__(self) -> None:
        super().__init__(format="Letter")
        self.add_font("Liberation", "", str(FUENTES / "LiberationSans-Regular.ttf"))
        self.add_font("Liberation", "B", str(FUENTES / "LiberationSans-Bold.ttf"))
        self.add_font("Liberation", "I", str(FUENTES / "LiberationSans-Italic.ttf"))
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, 16)
        self.set_title("Hoja de vida")
        self.set_creator("Asistente de postulación")

    def seccion(self, titulo: str) -> None:
        self.ln(3)
        self.set_font("Liberation", "B", 11.5)
        self.set_text_color(*AZUL)
        self.cell(0, 6, titulo.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*AZUL)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.5)
        self.set_text_color(0, 0, 0)

    def parrafo(self, texto: str, estilo: str = "", tamano: float = 10) -> None:
        self.set_font("Liberation", estilo, tamano)
        self.multi_cell(0, 5, texto, new_x="LMARGIN", new_y="NEXT")

    def vineta(self, texto: str) -> None:
        self.set_font("Liberation", "", 10)
        self.set_x(self.l_margin + 3)
        self.multi_cell(0, 5, f"• {texto}", new_x="LMARGIN", new_y="NEXT")


def _periodo(inicio: str | None, fin: str | None) -> str:
    if inicio and fin:
        return f"{inicio} – {fin}"
    return inicio or fin or ""


def _render(cv: CVFinal, contacto: Contacto, logros_max: int, proyectos_max: int) -> bytes:
    p = cv.perfil
    doc = _Documento()
    doc.add_page()
    doc.set_font("Liberation", "B", 18)
    doc.cell(0, 9, contacto.nombre, new_x="LMARGIN", new_y="NEXT")
    datos = [d for d in (contacto.ciudad, contacto.correo, contacto.telefono) if d]
    datos += list(contacto.enlaces)
    if datos:
        doc.set_text_color(*GRIS)
        doc.parrafo(" · ".join(datos), tamano=9.5)
        doc.set_text_color(0, 0, 0)

    if cv.resumen:
        doc.seccion("Perfil")
        doc.parrafo(cv.resumen)
    if p.formacion:
        doc.seccion("Formación")
        for f in p.formacion:
            detalle = " · ".join(
                x for x in (f.nivel, f.estado, f.semestre and f"Semestre {f.semestre}") if x
            )
            doc.parrafo(f"{f.programa} — {f.institucion}", "B")
            linea = " · ".join(x for x in (_periodo(f.inicio, f.fin), detalle) if x)
            if linea:
                doc.parrafo(linea, tamano=9.5)
    if p.experiencia:
        doc.seccion("Experiencia")
        for e in p.experiencia:
            doc.parrafo(f"{e.cargo} — {e.empresa}", "B")
            if periodo := _periodo(e.inicio, e.fin):
                doc.parrafo(periodo, tamano=9.5)
            for logro in e.logros[:logros_max]:
                doc.vineta(logro)
    if p.proyectos and proyectos_max:
        doc.seccion("Proyectos")
        for pr in p.proyectos[:proyectos_max]:
            doc.parrafo(pr.nombre, "B")
            texto = pr.descripcion or ""
            if pr.tecnologias:
                texto = f"{texto} Tecnologías: {', '.join(pr.tecnologias)}.".strip()
            if texto:
                doc.parrafo(texto)
    if cv.habilidades or p.habilidades_blandas:
        doc.seccion("Habilidades")
        if cv.habilidades:
            doc.parrafo("Técnicas: " + ", ".join(cv.habilidades))
        if p.habilidades_blandas:
            doc.parrafo("Blandas: " + ", ".join(p.habilidades_blandas))
    if p.idiomas:
        doc.seccion("Idiomas")
        doc.parrafo(
            ", ".join(f"{i.idioma} ({i.nivel})" if i.nivel else i.idioma for i in p.idiomas)
        )
    if p.certificaciones:
        doc.seccion("Certificaciones")
        for c in p.certificaciones:
            doc.vineta(" — ".join(x for x in (c.nombre, c.entidad, c.anio) if x))
    return bytes(doc.output()), doc.page_no()


def generar_pdf(cv: CVFinal, contacto: Contacto) -> bytes:
    """Recorta primero lo menos relevante (viñetas y proyectos) hasta caber en 2 páginas."""
    logros, proyectos = 6, len(cv.perfil.proyectos)
    while True:
        contenido, paginas = _render(cv, contacto, logros, proyectos)
        if paginas <= MAX_PAGINAS or (logros <= 2 and proyectos == 0):
            return contenido
        if logros > 3:
            logros -= 1
        elif proyectos > 0:
            proyectos -= 1
        else:
            logros -= 1
