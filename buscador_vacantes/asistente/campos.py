"""Catálogo cerrado de campos que piden los formularios y su valor desde los datos del usuario.

El banco compartido de preguntas guarda solo la correspondencia pregunta → campo (sin
respuestas personales). El valor sale siempre de los datos del propio usuario.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from buscador_vacantes.asistente.cv_lectura import PerfilExtraido
from buscador_vacantes.asistente.tecnologias import diccionario
from buscador_vacantes.normalizar import normalizar_texto

# Campo → descripción (se envía a la IA para clasificar preguntas nuevas)
CAMPOS: dict[str, str] = {
    "nombre": "nombre completo del candidato",
    "correo": "correo electrónico",
    "telefono": "teléfono o celular",
    "documento": "número de documento de identidad",
    "salario": "aspiración o pretensión salarial mensual",
    "disponibilidad_inicio": "cuándo puede empezar a trabajar",
    "horario": "disponibilidad horaria (tiempo completo, medio tiempo, horarios)",
    "modalidades": "modalidades aceptadas (presencial, híbrido, remoto)",
    "ciudad": "ciudad de residencia",
    "traslado": "disponibilidad para trasladarse o viajar",
    "estudia_actualmente": "si estudia actualmente (sí/no)",
    "institucion": "institución educativa",
    "programa": "carrera o programa que estudia",
    "semestre": "semestre o nivel que cursa",
    "tipo_practica": "tipo de práctica que busca (contrato de aprendizaje, práctica, pasantía)",
    "ingles_nivel": "nivel de inglés",
    "equipo_propio": "si tiene computador propio y conexión a internet",
    "experiencia_meses": "meses o años de experiencia laboral",
    "enlace_portafolio": "enlace a GitHub, portafolio o LinkedIn",
}
CAMPOS_PARAMETRO = {
    "conoce": "si tiene conocimiento de una herramienta o tecnología (parámetro: cuál)",
    "idioma": "nivel en un idioma distinto del inglés (parámetro: cuál)",
}
CONTACTO = {"nombre", "correo", "telefono", "documento"}  # nunca van a la IA


def es_campo_valido(campo: str, parametro: str | None) -> bool:
    if campo in CAMPOS:
        return True
    return campo in CAMPOS_PARAMETRO and bool(parametro)


@dataclass
class DatosUsuario:
    perfil: PerfilExtraido
    cuestionario: dict[str, str] = field(default_factory=dict)  # incluye el contacto

    def valor(self, campo: str, parametro: str | None = None) -> str | None:
        """Valor del campo para este usuario, o None si no se conoce (nunca se inventa)."""
        directo = self.cuestionario.get(campo)
        if directo not in (None, ""):
            return str(directo)
        p = self.perfil
        formacion = p.formacion[0] if p.formacion else None
        match campo:
            case "nombre":
                return p.nombre
            case "ciudad":
                return p.ciudad
            case "institucion":
                return formacion.institucion if formacion else None
            case "programa":
                return formacion.programa if formacion else None
            case "semestre":
                return formacion.semestre if formacion else None
            case "estudia_actualmente":
                if formacion and formacion.estado:
                    return "Sí" if "curso" in normalizar_texto(formacion.estado) else "No"
                return None
            case "ingles_nivel":
                return self._nivel_idioma("ingles")
            case "enlace_portafolio":
                for tipo in ("github", "portafolio", "linkedin"):
                    for enlace in p.enlaces:
                        if normalizar_texto(enlace.tipo) == tipo:
                            return enlace.url
                return None
            case "conoce":
                return self._conoce(parametro or "")
            case "idioma":
                return self._nivel_idioma(normalizar_texto(parametro)) or "No"
        return None

    def _nivel_idioma(self, idioma: str) -> str | None:
        for i in self.perfil.idiomas:
            if normalizar_texto(i.idioma) in (idioma, idioma.replace("ingles", "english")):
                return i.nivel or "Sí"
        return None

    def _conoce(self, herramienta: str) -> str:
        dicc = diccionario()
        objetivo = dicc.canonica(herramienta)
        habilidades = list(self.perfil.habilidades_tecnicas)
        for proyecto in self.perfil.proyectos:
            habilidades.extend(proyecto.tecnologias)
        for h in habilidades:
            if objetivo and (dicc.canonica(h) == objetivo or objetivo in dicc.buscar(h)):
                return "Sí"
            if normalizar_texto(h) == normalizar_texto(herramienta):
                return "Sí"
        return "No"

    def para_ia(self) -> dict:
        """Perfil y cuestionario sin datos de contacto, para las tareas de redacción."""
        perfil = self.perfil.model_dump(exclude={"es_cv", "nombre", "enlaces"})
        cuestionario = {
            k: v
            for k, v in self.cuestionario.items()
            if k not in CONTACTO and not k.startswith(("_", "sugerido_"))
        }
        return {"perfil": perfil, "cuestionario": cuestionario}
