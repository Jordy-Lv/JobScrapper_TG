## Why

La mayoría de las invitaciones a entrevista, pruebas, ofertas y rechazos llegan por correo, del portal o del reclutador directamente, y a cualquier hora, aunque el navegador esté cerrado. Si el usuario no ve ese correo a tiempo («confírmanos tu disponibilidad antes del jueves»), pierde la oportunidad. El reenvío con filtro permite que el asistente lea solo esos correos, sin acceso al resto del buzón. Funciona con Gmail y Outlook, no tiene límite de usuarios y no necesita verificación de Google. Es la vía principal de correo del seguimiento. `gmail-api-y-calendario` agrega después la conexión directa opcional.

## What Changes

- **Buzón del bot con una dirección por usuario**: una cuenta de correo dedicada del asistente, leída por IMAP desde el servidor, con alias `usuario+<token>@…` (token aleatorio, no deducible).
- **Alta guiada en Telegram (`/correo`)**:
  - el bot da la dirección, los pasos para Gmail y Outlook y el texto del filtro para copiar (remitentes de portales y palabras como «entrevista», «proceso de selección», «citación», «prueba», «hoja de vida», «vacante»);
  - cuando Gmail manda el código de confirmación del reenvío, el bot se lo pasa al usuario. El bot no confirma nada por su cuenta.
- **Procesamiento de cada correo**:
  1. descarte barato (alias desconocido, duplicado, sin señales);
  2. lectura exacta de invitaciones de calendario adjuntas (`.ics`);
  3. clasificación con la IA del usuario en un esquema fijo: tipo, empresa, cargo, fecha y hora, modalidad, lugar, contacto, si pide respuesta y su plazo;
  4. asociación con un proceso (enlace de la oferta, dominio del remitente, empresa y cargo);
  5. registro del evento de origen `correo` con su seguridad.
- **Avisos según la seguridad**: alta → aviso y card actualizada. Media → pregunta «¿Esta entrevista es de X?» con botones. Sin proceso → «Parece un proceso nuevo con Z. ¿Lo sigo?».
- **Pedido de respuesta**: si el correo pide confirmar algo con plazo, llega un aviso urgente con un borrador de respuesta para que el usuario lo envíe, y se repite antes del plazo hasta que toque «Ya respondí». El asistente nunca responde correos.
- **Seguridad ante correos maliciosos**:
  - el contenido es dato, nunca instrucción;
  - solo se muestran enlaces de reuniones de dominios conocidos (Meet, Zoom, Teams…);
  - los correos que no vienen del reenvío confirmado del usuario bajan a seguridad media.
- **Sin IA disponible** (sin clave o con el tope agotado): los correos de portales con plantillas conocidas se leen por reglas, y los demás generan «Recibí un correo que parece de un proceso: ¿qué es?» con botones.
- **Privacidad**: se guardan solo los datos extraídos y un fragmento corto del texto. El correo se borra del buzón del bot apenas se procesa (o a las 48 h si no se pudo). `/correo desconectar` y la baja borran el alias, y el bot recuerda quitar el filtro.

## Capabilities

### New Capabilities
- `correo-seguimiento-asistente`: la recepción por reenvío de los correos del proceso de selección y su conversión en eventos, preguntas y avisos del seguimiento, con sus garantías de seguridad y privacidad. La comparten la vía de reenvío y la conexión directa de `gmail-api-y-calendario`.

### Modified Capabilities
<!-- Ninguna en openspec/specs/: el seguimiento (`seguimiento-proceso-asistente`) llega con `seguimiento-proceso-postulacion`, que se archiva antes. -->

## Impact

- Módulos nuevos `buscador_vacantes/asistente/correo/`:
  - `buzon.py`: IMAP, alias y borrado;
  - `analisis.py`: descarte, `.ics`, reglas de portales y clasificación con IA;
  - `asociacion.py`;
  - `alta.py`: alias, confirmación de Gmail y texto del filtro.
- `datos.py`: tablas `buzones` y `correos_procesados` (versión de esquema siguiente).
- `servicio.py`: tarea de lectura del buzón cada `cada_min`. `conversacion.py` y `textos.py`: `/correo`, preguntas y avisos.
- `config.yaml` (`asistente.correo`: servidor IMAP, dominio de alias, remitentes y palabras del filtro, dominios de reuniones, topes, retención), `comun/config.py` y la tarea de IA opcional `clasificar_correo`.
- `.env.example` y `Secretos`: `ASISTENTE_CORREO_USUARIO` y `ASISTENTE_CORREO_CLAVE` (contraseña de aplicación del buzón del bot).
- Dependencia nueva `icalendar`, para leer invitaciones con zonas horarias.
- Texto de privacidad (`config.yaml`), `docs/asistente/guia-usuario.md` y `deploy/INSTALAR.md` (crear el buzón del bot).
- Pruebas con correos de ejemplo en `tests/fixtures/correo/` y `tests/asistente/test_correo_*.py`.
- Depende de `seguimiento-proceso-postulacion`. `gmail-api-y-calendario` reusa este procesamiento.
