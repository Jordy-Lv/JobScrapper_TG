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
    "/ia nivel · cuánta IA usan tus postulaciones (Ahorro, Normal o Máximo)\n"
    "/documentos · tu certificado de notas, carta y otros PDF para los formularios\n"
    "/borrarme · borrar todos tus datos"
)

NOMBRES_NIVEL_IA = {"ahorro": "Ahorro", "normal": "Normal", "maximo": "Máximo"}
AVISO_RESPUESTAS_REVISADAS = "🔎 El revisor de IA ajustó {n} respuesta(s) antes de enviar"
AVISO_NIVEL_BAJADO = "Usé el nivel {nivel} porque se agotó tu cuota de IA de hoy"

DOCUMENTOS_VACIO = (
    "No tienes documentos guardados.\n"
    "Algunos formularios piden además del CV un certificado de notas, una carta o un "
    "portafolio. Guárdalos aquí una vez y los adjunto donde corresponda; los guardo cifrados y "
    "puedes borrarlos cuando quieras."
)
DOCUMENTOS_ELEGIR_TIPO = "¿Qué documento vas a guardar?"
DOCUMENTOS_PEDIR_NOMBRE = "¿Cómo se llama este documento? (por ejemplo «Certificado de inglés»)"
DOCUMENTOS_PEDIR_PDF = (
    "Envíame el PDF como archivo (máximo {max_mb:g} MB). Para cancelar usa /documentos."
)

AYUDA_ADMIN = (
    "\n\n<b>Administración</b>\n/usuarios · /suspender ID · /reactivar ID · /stats · "
    "/plataformas [nombre on|off|ensayo|real] · /ensayo [on|off] · /barreras [quitar dominio]"
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
    "<b>Paso 2 de 6 · Tu clave gratuita de Gemini</b>\n"
    "La IA usa <b>tu propia clave</b> (gratis):\n"
    "1. Entra a aistudio.google.com con tu cuenta de Google.\n"
    "2. Abre <b>Get API key</b> y pulsa <b>Crear clave de API</b>.\n"
    "3. Pégala aquí. La borro del chat al instante y la guardo cifrada.\n\n"
    "Otros proveedores de IA llegarán pronto:"
)
PEDIR_CV = (
    "<b>Paso 3 de 6 · Tu hoja de vida</b>\n"
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
    "<b>Paso 5 de 6 · Vincula tu navegador</b>\n"
    "Para que yo postule por ti en Computrabajo, Magneto y elempleo:\n"
    "1. Instala la extensión en <b>Edge</b>{tienda} (o en Chrome/Brave con el paquete que te "
    "envío con /vincular).\n"
    "2. Toca <b>Vincular mi navegador</b>.\n"
    "Tu PC debe estar encendido con el navegador abierto (puede estar minimizado)."
)
PLATAFORMAS = (
    "<b>Paso 6 de 6 · Inicia sesión en tus portales</b>\n"
    "En el navegador que acabas de vincular, inicia sesión con tu cuenta en los portales de "
    "abajo (en elempleo, activa también la extensión). Cuando aparezca tu cuenta, confírmala "
    "aquí; puede tardar unos segundos."
)
PLATAFORMAS_CON_VACANTE = (
    "Tu vacante es de <b>{portal}</b>: no la postulo hasta que confirmes esa cuenta. Los demás "
    "portales son opcionales."
)
PLATAFORMAS_SIN_VACANTE = "Con confirmar la cuenta de un portal basta para terminar."
YA_VINCULADO = (
    "✅ <b>Dispositivo ya vinculado</b>\n{navegadores}\n"
    "No necesitas vincular de nuevo. Si cambiaste de navegador o reinstalaste la extensión, "
    "revoca el anterior con /navegadores y vuelve a usar /vincular."
)
ALTA_LISTA = (
    "✅ <b>¡Todo listo!</b> Así empiezas a postular:\n"
    "1. Ve al <b>grupo</b> y mira las vacantes que publico.\n"
    "2. En la vacante a la que quieras aplicar, toca el botón <b>⚡ Postularme</b>.\n\n"
    "Con ese toque empiezo yo: preparo tu hoja de vida, lleno el formulario del portal y te "
    "aviso aquí el resultado.\n"
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
    # Lo que el motor genérico no resuelve por ti (motor-generico-autorreparable)
    "ats_con_cuenta": "esta empresa pide crear una cuenta en su portal de empleo y yo no creo "
    "cuentas por ti",
    "captcha": "el sitio pidió resolver un captcha y eso solo lo puedes hacer tú",
    "oauth": "el sitio solo deja postular entrando con una cuenta de Google, LinkedIn u otro "
    "servicio",
    "codigo_verificacion": "el sitio pidió un código de verificación que te llega al correo o "
    "al teléfono",
    "sin_ia": "para entender este formulario necesito tu clave de IA y no la tienes configurada "
    "o se agotó su cuota",
    "documento_faltante": "el formulario pide un documento obligatorio que no tengo guardado",
    "nivel_ahorro": "tu nivel de IA es Ahorro y para entender este formulario hacía falta usarla",
    "plataforma_en_ensayo": "esta postulación estaba en modo ensayo y no se envió nada",
}
# Motivos que no son un fallo del asistente: el dueño no necesita revisar su evidencia
MOTIVOS_SIN_ALERTA = (
    "ats_con_cuenta", "captcha", "oauth", "codigo_verificacion", "sin_ia", "documento_faltante",
    "nivel_ahorro",
)  # fmt: skip

# Avisos al dueño del vigía diario (ensayo de cada plataforma en su navegador)
VIGIA_REPARADO = (
    "🛠 El vigía encontró que {portal} cambió y el asistente lo reparó solo. Quedó un parche "
    "candidato: revísalo en la tabla parches_flujo."
)
VIGIA_BLOQUEADA = (
    "🧩 El vigía no pudo ensayar {portal}: el portal pidió una verificación ({motivo}). "
    "Revisa tu sesión en ese portal."
)
VIGIA_FALLO = (
    "⚠️ El vigía no pudo ensayar {portal}: {motivo}. Nadie lo reparó, así que dejé la plataforma "
    "en ensayo para todos hasta que la revises. Mira la evidencia en data/asistente/postulaciones/ "
    "y, cuando esté lista, usa /plataformas {id} real."
)

# Avisos al dueño de lo que aprende el motor genérico (eventos del núcleo sin usuario)
AVISO_RECETA_APAGADA = (
    "🧾 La receta de <b>{host}</b> se apagó: falló 2 veces seguidas (la última, la postulación "
    "{pid}). Las próximas postulaciones de ese sitio usan las reglas hasta que un envío "
    "la reactive."
)
AVISO_PARCHE_NUEVO = (
    "🩹 Parche candidato para <b>{portal}</b>, paso «{paso}» (postulación {pid}):\n"
    "<code>{selector}</code>\n"
    "Lo usan como candidato las próximas postulaciones; con un éxito pasa a firme. Evidencia en "
    "data/asistente/postulaciones/{pid}/."
)
AVISO_PARCHE_FIRME = (
    "✅ Parche firme para <b>{portal}</b>, paso «{paso}»:\n<code>{selector}</code>\n"
    "Cópialo al JSON revisado de la plataforma para dejarlo fijo."
)
AVISO_DOMINIO_BARRERA = (
    "🚧 <b>{host}</b> quedó como dominio barrera ({motivo}). Sus vacantes irán al respaldo sin "
    "abrir la página. Para quitarlo: /barreras quitar {host}"
)
AVISOS_DUENIO = ("receta_apagada", "parche_nuevo", "parche_firme", "dominio_barrera")
BARRERAS_VACIAS = "No hay dominios barrera."

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
    "portal_perfil_incompleto": (
        "{portal} dice que tu hoja de vida está incompleta y no acepta postulaciones hasta que "
        "la completes. Entra a {portal}, abre «Hoja de vida» y completa las secciones que "
        "marca como pendientes."
    ),
    "aplicar_sin_efecto": (
        "{portal} no cargó la postulación: tras pulsar «Aplicar» no mostró la encuesta ni "
        "la confirmación. Puedes reintentar; si la vacante ya la habías aplicado y retirado, "
        "suele pasar y conviene aplicarla a mano en {portal}."
    ),
}
# El llenado de la encuesta que no responde se explica igual: no se envió nada
BLOQUEOS_PORTAL["llenado_sin_respuesta"] = BLOQUEOS_PORTAL["aplicar_sin_efecto"]
# Bloqueos que no piden nada en la cuenta del portal: el portal falló, no el usuario
SIN_PROCESAR = ("aplicar_sin_efecto", "llenado_sin_respuesta")

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
    "ensayada": "🧪 Ensayada: no se envió nada",
    "cancelada": "🚫 Cancelada",
    "completado": "✅ Perfil completado",
}

# Efecto de mensaje de Telegram (🎉 confeti, a pantalla completa); solo funciona en chats privados
EFECTO_CONFETI = "5046509860389126442"

NOMBRES_PLATAFORMA = {"computrabajo": "Computrabajo", "magneto": "Magneto", "elempleo": "elempleo"}
# Solo para la cabecera de la card y el bloque «Conexión»; botones y prosa usan el nombre plano.
EMOJI_PLATAFORMA = {"computrabajo": "🔵", "magneto": "🟢", "elempleo": "🩵"}
# Página de inicio de cada portal (el registro exacto se confirma en el reconocimiento)
URL_REGISTRO = {
    "computrabajo": "https://co.computrabajo.com/",
    "magneto": "https://www.magneto365.com/co",
    "elempleo": "https://www.elempleo.com/co/",
}

# Página para iniciar sesión en cada portal. La de elempleo se confirma en el reconocimiento;
# mientras tanto abre la portada
URL_INGRESO = {
    "computrabajo": "https://candidato.co.computrabajo.com/acceso/",
    "magneto": "https://web.magneto365.com/sign-in",
    "elempleo": "https://www.elempleo.com/co/",
}
# Dominio que la extensión pide como permiso para operar en cada portal
DOMINIOS = {
    "computrabajo": "computrabajo.com",
    "magneto": "magneto365.com",
    "elempleo": "elempleo.com",
}

# Causas de espera que el bloque «Conexión» de la card ya explica con sus botones
ESPERAS_DE_CUENTA = ("cuenta_por_confirmar", "cuenta_distinta")
ESPERA_CUENTA_EN_CONEXION = "Sale en cuanto resuelvas la cuenta de arriba."

# Por qué una postulación sigue en cola (una por causa de espera.py). Valores disponibles:
# {portal}, {dominio}, {version}, {minima}, {desde} (« desde las 10:42» o vacío) y {hora}.
# Nunca llevan motivos internos del latido ni el correo de una cuenta ajena
ESPERAS = {
    "sin_navegador": (
        "Falta vincular tu navegador para postular en {portal}. Cuando lo vincules, la "
        "postulación sale sola."
    ),
    "sin_latido": (
        "Tu navegador no responde{desde}. Ábrelo con la extensión activa y la postulación en "
        "{portal} sigue sola."
    ),
    "extension_desactualizada": (
        "Tu extensión está en la versión {version} y necesito la {minima} o una más nueva. "
        "Actualízala y la postulación sale sola."
    ),
    "extension_en_pausa": (
        "Tus postulaciones están en pausa en la extensión. Se reanudan solas al quitar la "
        "pausa desde su ventana."
    ),
    "plataforma_apagada": (
        "La postulación automática en {portal} está pausada por ahora. Tu postulación sigue en "
        "cola y sale sola cuando se reactive."
    ),
    "sin_permiso": (
        "Abre la ventana de la extensión y activa el permiso de {dominio}; después la "
        "postulación en {portal} sale sola."
    ),
    "sin_sesion": (
        "🔒 Inicia sesión en {portal} en tu navegador vinculado; la postulación sale sola después."
    ),
    "cuenta_por_confirmar": (
        "Hay una sesión abierta en {portal}. Confirma que esa cuenta es tuya para que pueda "
        "postular con ella."
    ),
    "cuenta_distinta": (
        "La cuenta abierta en {portal} no es la que me diste y no postularé con ella. Dime si "
        "es tu cuenta nueva o vuelve a iniciar sesión con la tuya."
    ),
    "correo_ilegible": (
        "No pude leer el correo de tu cuenta de {portal}. Lo intento de nuevo en la próxima "
        "revisión y no postulo hasta comprobar que la cuenta es tuya."
    ),
    "perfil_incompleto": (
        "Estoy completando tu perfil en {portal} con tus datos y tu CV; en cuanto termine "
        "sigue tu postulación."
    ),
    "otra_en_curso": "Primero termino otra postulación tuya; esta sigue después.",
    "tope_diario": "Llegaste al tope de postulaciones de hoy; esta saldrá mañana.",
    "pausa": "Hago una pausa entre postulaciones; esta saldrá hacia las {hora}.",
}


def e(texto: object) -> str:
    return html.escape(str(texto or ""), quote=False)


def nombre_con_emoji(plataforma: str | None) -> str:
    """«🟢 Magneto»; el nombre solo si la plataforma no tiene emoji; «» si no hay plataforma.
    No escapa: lo hace quien arma la línea."""
    nombre = NOMBRES_PLATAFORMA.get(plataforma or "", plataforma or "")
    emoji = EMOJI_PLATAFORMA.get(plataforma or "")
    return f"{emoji} {nombre}" if emoji and nombre else nombre


def linea_empresa(empresa: str | None, plataforma: str | None) -> str | None:
    """«Empresa · 🟢 Plataforma» para la cabecera de la card; None si no hay ninguna."""
    partes = [e(p) for p in (empresa, nombre_con_emoji(plataforma)) if p]
    return " · ".join(partes) or None


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
