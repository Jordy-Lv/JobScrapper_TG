"""Textos del bot asistente (HTML de Telegram) y cuestionario base."""

from __future__ import annotations

import html
from dataclasses import dataclass

AYUDA = (
    "<b>Asistente de postulación</b>\n"
    "Toca <b>⚡ Postularme</b> en una vacante del grupo y yo me encargo del resto.\n\n"
    "/estado · tu navegador, tus portales y tus postulaciones de hoy\n"
    "/historial · tus postulaciones\n"
    "/detalle N · todo lo que se hizo en una postulación\n"
    "/perfil · ver y editar tu perfil\n"
    "/cuestionario · cambiar tus respuestas base\n"
    "/cv · descargar tu CV base\n"
    "/clave · cambiar o borrar tu clave de Gemini\n"
    "/vincular · vincular un navegador · /navegadores · ver o revocar\n"
    "/automatico [umbral] · postular solo a lo que encaja contigo\n"
    "/pausa · pausar o reanudar tus postulaciones\n"
    "/borrarme · borrar todos tus datos"
)

AYUDA_ADMIN = (
    "\n\n<b>Administración</b>\n/usuarios · /suspender ID · /reactivar ID · /stats · "
    "/plataformas [nombre on|off]"
)

NO_MIEMBRO = (
    "Este asistente es exclusivo para los miembros del grupo <b>JOBS - PRÁCTICAS/APRENDIZ</b>. "
    "No guardé ningún dato tuyo."
)
ALTAS_CERRADAS = (
    "Las inscripciones están cerradas temporalmente. Inténtalo más tarde; el administrador "
    "ya fue avisado."
)
SUSPENDIDO = "Tu acceso al asistente está suspendido."
EN_GRUPO = "Escríbeme en privado para usar el asistente: {enlace}"

PEDIR_CLAVE = (
    "<b>Paso 2 de 5 · Tu clave gratuita de Gemini</b>\n"
    "La IA usa <b>tu propia clave</b> (gratis):\n"
    "1. Entra a aistudio.google.com con tu cuenta de Google.\n"
    "2. Abre <b>Get API key</b> y pulsa <b>Crear clave de API</b>.\n"
    "3. Pégala aquí. La borro del chat al instante y la guardo cifrada.\n\n"
    "Sin clave también funciona, pero sin CV adaptado ni redacción de respuestas abiertas."
)
PEDIR_CV = (
    "<b>Paso 3 de 5 · Tu hoja de vida</b>\n"
    "Envíame tu CV en <b>PDF</b> (máximo {max_mb:g} MB). Con él armo tu perfil."
)
CV_ADJUNTAR = "📎 Adjunta aquí tu hoja de vida en <b>PDF</b> (máximo {max_mb:g} MB)."
CV_DESDE_CERO = (
    "🛠 <b>Próximamente</b>\n"
    "Estamos trabajando para que puedas crear tu hoja de vida desde cero aquí mismo. "
    "Por ahora, adjunta la que tengas en PDF."
)
CV_ESCANEADO = (
    "Tu hoja de vida parece escaneada (es una imagen). Para leerla tengo que enviar el archivo "
    "completo a Gemini, <b>incluidos tus datos de contacto</b>. ¿Lo envío?"
)
PEDIR_ENFOQUE = (
    "<b>Editar · Tu enfoque</b>\nEsto propongo según tu CV:\n"
    "• Roles: {roles}\n• Tecnologías a destacar: {tecnologias}\n• Objetivo: {objetivo}"
)
NAVEGADOR = (
    "<b>Paso 5 de 5 · Postulación automática</b>\n"
    "Para que yo postule por ti en Computrabajo y Magneto:\n"
    "1. Instala la extensión en <b>Edge</b>{tienda} (o en Chrome/Brave con el paquete que te "
    "envío con /vincular).\n"
    "2. Toca <b>Vincular mi navegador</b>.\n"
    "3. Inicia sesión en Computrabajo y Magneto en ese navegador.\n"
    "Tu PC debe estar encendido con el navegador abierto (puede estar minimizado)."
)
ALTA_LISTA = (
    "✅ <b>¡Listo!</b> Ya puedes tocar <b>⚡ Postularme</b> en cualquier vacante del grupo.\n"
    "Usa /ayuda para ver todo lo que puedo hacer."
)

MOTIVOS_RESPALDO = {
    "plataforma_no_soportada": "esta plataforma todavía no admite postulación automática",
    "plataforma_no_automatica": "la postulación automática en esta plataforma está pausada",
    "sin_navegador": "aún no tienes un navegador vinculado (usa /vincular)",
    "navegador_desconectado": "tu navegador estuvo desconectado más de 24 horas",
    "sin_respuesta": "faltó una respuesta tuya",
    "sin_sesion": "no iniciaste sesión en el portal a tiempo",
    "bloqueada": "el portal pidió una verificación que no se completó",
    "formulario_desconocido": "el formulario del portal cambió",
    "fallida": "el portal rechazó el envío",
}

# Bloqueos que solo el usuario resuelve en su cuenta del portal. No llevan paquete: el portal
# tampoco acepta la postulación hecha a mano hasta que se resuelvan.
BLOQUEOS_PORTAL = {
    "portal_correo_incorrecto": (
        "{portal} dice que no puede enviarte correos al email de tu cuenta y no acepta "
        "postulaciones hasta que lo corrijas. Entra a {portal}, revisa el aviso «Email "
        "incorrecto» y corrige o confirma tu correo."
    ),
    "portal_cuenta_sin_verificar": (
        "{portal} tiene tu cuenta pendiente de verificar y no acepta postulaciones hasta "
        "entonces. Abre el correo que te envió {portal} y toca el enlace de verificación "
        "(revisa también spam y promociones)."
    ),
    "portal_redirige_inicio": (
        "{portal} me devolvió a tu inicio en vez de abrir la postulación. Suele pasar cuando "
        "pide algo en tu cuenta (verificar el correo, aceptar condiciones…). Entra a {portal} "
        "y resuelve los avisos de tu inicio."
    ),
}

ESTADOS = {
    "en_cola": "⏳ En cola",
    "esperando_navegador": "💻 Esperando que abras tu navegador",
    "tomada": "🚀 Postulando…",
    "en_curso": "🚀 Postulando…",
    "esperando_usuario": "❓ Esperando tu respuesta",
    "esperando_sesion": "🔑 Esperando que inicies sesión en el portal",
    "verificacion": "🧩 Esperando que completes una verificación",
    "cuenta_distinta": "⚠️ La cuenta abierta en el portal no es la tuya",
    "enviada": "✅ Enviada",
    "ya_postulada": "✅ Ya estabas postulado",
    "vacante_cerrada": "🚫 Vacante cerrada",
    "bloqueada": "🧩 Bloqueada por una verificación",
    "formulario_desconocido": "⚠️ No reconocí el formulario",
    "incierta": "❔ Sin confirmación: verifícala en el portal",
    "fallida": "❌ El portal rechazó el envío",
    "respaldo": "📋 Paquete para postular a mano",
    "cancelada": "🚫 Cancelada",
    "completado": "✅ Perfil completado",
}

NOMBRES_PLATAFORMA = {"computrabajo": "Computrabajo", "magneto": "Magneto"}
# Página de inicio de cada portal (el registro exacto se confirma en el reconocimiento)
URL_REGISTRO = {
    "computrabajo": "https://co.computrabajo.com/",
    "magneto": "https://www.magneto365.com/co",
}


def e(texto: object) -> str:
    return html.escape(str(texto or ""), quote=False)


def bloque(texto: str) -> str:
    """Texto copiable con un toque en Telegram."""
    return f"<code>{e(texto)}</code>"


@dataclass
class ItemCuestionario:
    clave: str
    pregunta: str
    opciones: tuple[str, ...] = ()
    opcional: bool = False
    valores: tuple[str, ...] = ()  # lo que se guarda por cada opción (si difiere de su botón)
    por_fila: int = 4  # botones por fila
    otro: str = ""  # texto del botón «escribir otro valor» (vacío: sin ese botón)


# Salario mínimo legal vigente 2026 (Colombia); actualizar cada enero
SMMLV = 1750905

CUESTIONARIO: tuple[ItemCuestionario, ...] = (
    ItemCuestionario("nombre", "¿Cuál es tu nombre completo?"),
    ItemCuestionario("correo", "¿Cuál es tu correo electrónico?"),
    ItemCuestionario("telefono", "¿Cuál es tu número de celular?"),
    ItemCuestionario("documento", "Número de documento (opcional, algunos formularios lo piden)",
                     opcional=True),
    ItemCuestionario("ciudad", "¿En qué ciudad vives?"),
    ItemCuestionario("salario", "¿Cuál es tu aspiración salarial mensual? Elige un rango o "
                                "toca «Otro valor» y escríbelo (solo el número, en pesos; por "
                                "ejemplo 1300000)",
                     ("Salario mínimo", "$2.000.000", "$2.500.000", "$3.000.000", "$4.000.000"),
                     valores=(str(SMMLV), "2000000", "2500000", "3000000", "4000000"),
                     por_fila=2, otro="✏️ Otro valor"),
    ItemCuestionario("disponibilidad_inicio", "¿Cuándo puedes empezar?",
                     ("Inmediata", "En 15 días", "En 1 mes")),
    ItemCuestionario("horario", "¿Qué disponibilidad de horario tienes?",
                     ("Tiempo completo", "Medio tiempo", "Flexible")),
    ItemCuestionario("modalidades", "¿Qué modalidades aceptas?",
                     ("Presencial", "Híbrido y remoto", "Cualquiera")),
    ItemCuestionario("estudia_actualmente", "¿Estudias actualmente?", ("Sí", "No")),
    ItemCuestionario("tipo_practica", "¿Qué buscas?",
                     ("Contrato de aprendizaje", "Práctica universitaria", "Pasantía",
                      "Empleo junior")),
    ItemCuestionario("ingles_nivel", "¿Cuál es tu nivel de inglés?",
                     ("Ninguno", "A1", "A2", "B1", "B2", "C1", "C2")),
    ItemCuestionario("equipo_propio", "¿Tienes computador propio y conexión a internet?",
                     ("Sí", "No")),
    ItemCuestionario("traslado", "¿Puedes trasladarte o viajar si la vacante lo pide?",
                     ("Sí", "No")),
    ItemCuestionario("experiencia_meses", "¿Cuánta experiencia laboral tienes?",
                     ("Ninguna", "Menos de 6 meses", "6 a 12 meses", "Más de 1 año")),
    ItemCuestionario("actualizar_cv_portal",
                     "¿Permites que actualice la hoja de vida de tus perfiles en los portales "
                     "con la versión adaptada a cada vacante?", ("Sí", "No")),
)  # fmt: skip
