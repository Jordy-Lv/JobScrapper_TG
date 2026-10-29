"""Catálogo cerrado de campos que piden los formularios y su valor desde los datos del usuario.

El banco compartido de preguntas guarda solo la correspondencia pregunta → campo (sin
respuestas personales). El valor sale siempre de los datos del propio usuario.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from buscador_vacantes.asistente.cv_lectura import PerfilExtraido
from buscador_vacantes.asistente.tecnologias import diccionario
from buscador_vacantes.comun.normalizar import normalizar_texto

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
    "enlace_portafolio": "enlace a GitHub o portafolio",
    "nombre_pila": "nombre de pila (first name, given name)",
    "apellido": "apellido o apellidos (last name, family name)",
    "pais": "país de residencia",
    "enlace_linkedin": "enlace al perfil de LinkedIn",
    "salario_usd": "aspiración salarial en dólares (USD)",
    "promedio": "promedio académico (GPA, nota media)",
    "fuente_vacante": "cómo o dónde se enteró de la vacante (la plataforma de la que vino)",
    "aval_institucion": "si cuenta con el aval de su institución educativa para iniciar prácticas "
    "(sí/no)",
}
CAMPOS_PARAMETRO = {
    "conoce": "si tiene conocimiento de una herramienta o tecnología (parámetro: cuál)",
    "idioma": "nivel en un idioma distinto del inglés (parámetro: cuál)",
    "autorizacion_trabajo": "si está legalmente autorizado para trabajar en un país (parámetro: "
    "el país)",
}
# nunca van a la IA
CONTACTO = {
    "nombre", "nombre_pila", "apellido", "correo", "telefono", "documento", "enlace_linkedin",
}  # fmt: skip
RESERVADO = "__reservado__"  # «Prefiero no decirlo»: nunca se muestra ni se envía como valor


# Clave de la plataforma (`postulaciones.plataforma`) → cómo se llama en «¿cómo te enteraste?»
NOMBRES_FUENTE = {
    "computrabajo": "Computrabajo",
    "magneto": "Magneto",
    "elempleo": "elempleo",
    "linkedin": "LinkedIn",
}
_PARTICULAS = {"de", "del", "la", "las", "los", "y", "san", "santa", "da", "dos"}
_SEGUNDO_NOMBRE = {
    "maria", "jose", "juan", "luis", "carlos", "andres", "ana", "camila", "alejandra", "fernanda",
    "paola", "isabel", "sofia", "david", "felipe", "alberto", "antonio", "eduardo", "fernando",
    "javier", "miguel", "angel", "esteban", "daniela", "valentina", "nicolas", "sebastian",
    "santiago", "manuel", "jesus", "stephanie", "katherine", "lucia", "paula",
}  # fmt: skip


def es_campo_valido(campo: str, parametro: str | None) -> bool:
    if campo in CAMPOS:
        return True
    return campo in CAMPOS_PARAMETRO and bool(parametro)


def clave_cuestionario(campo: str, parametro: str | None = None) -> str:
    """Clave con la que se guarda el dato en el cuestionario: la autorización para trabajar es
    una por país («autorizacion_trabajo:colombia»)."""
    if campo == "autorizacion_trabajo" and parametro:
        return f"{campo}:{normalizar_texto(parametro)}"
    return campo


def es_guardable(campo: str | None) -> bool:
    """True si la respuesta a una pregunta de este campo se guarda en el cuestionario."""
    if not campo:
        return False
    base, _, pais = campo.partition(":")
    return campo in CAMPOS or (base == "autorizacion_trabajo" and bool(pais))


def nombre_fuente(plataforma: str | None) -> str | None:
    if not plataforma:
        return None
    return NOMBRES_FUENTE.get(plataforma, plataforma)


def separar_nombre(completo: str | None) -> tuple[str | None, str | None]:
    """(nombre de pila, apellidos) de un nombre completo, con la convención hispana: «Ana María
    Pérez Gómez» → («Ana María», «Pérez Gómez»). Es una heurística: el usuario puede dar
    cada parte por separado en su cuestionario y eso manda."""
    palabras = (completo or "").split()
    unidades: list[str] = []
    pendiente: list[str] = []
    for palabra in palabras:  # «de la Cruz» es una sola unidad
        pendiente.append(palabra)
        if normalizar_texto(palabra) not in _PARTICULAS:
            unidades.append(" ".join(pendiente))
            pendiente = []
    if pendiente:
        unidades.append(" ".join(pendiente))
    if not unidades:
        return None, None
    if len(unidades) == 1:
        return unidades[0], None
    if len(unidades) == 2:
        return unidades[0], unidades[1]
    if len(unidades) == 3:
        if normalizar_texto(unidades[1]) in _SEGUNDO_NOMBRE:
            return f"{unidades[0]} {unidades[1]}", unidades[2]
        return unidades[0], f"{unidades[1]} {unidades[2]}"
    return " ".join(unidades[:2]), " ".join(unidades[2:])


@dataclass
class DatosUsuario:
    perfil: PerfilExtraido
    cuestionario: dict[str, str] = field(default_factory=dict)  # incluye el contacto

    def valor(self, campo: str, parametro: str | None = None) -> str | None:
        """Valor del campo para este usuario, o None si no se conoce (nunca se inventa)."""
        directo = self.cuestionario.get(clave_cuestionario(campo, parametro))
        if directo == RESERVADO:
            return None
        if directo not in (None, ""):
            return str(directo)
        p = self.perfil
        formacion = p.formacion[0] if p.formacion else None
        match campo:
            case "nombre":
                return p.nombre
            case "nombre_pila":
                return separar_nombre(self.cuestionario.get("nombre") or p.nombre)[0]
            case "apellido":
                return separar_nombre(self.cuestionario.get("nombre") or p.nombre)[1]
            case "enlace_linkedin":
                for enlace in p.enlaces:
                    if normalizar_texto(enlace.tipo) == "linkedin" or "linkedin.com" in enlace.url:
                        return enlace.url
                return None
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
            if k not in CONTACTO and not k.startswith(("_", "sugerido_")) and v != RESERVADO
        }
        return {"perfil": perfil, "cuestionario": cuestionario}
