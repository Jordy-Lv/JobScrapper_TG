# Ficha en la tienda de complementos de Microsoft Edge

Material para el envío en Partner Center (Microsoft Edge → Crear extensión). El paquete se arma
con `uv run --group asistente buscador.py asistente empaquetar-extension` →
`dist/asistente-postulacion-<versión>.zip`.

## Disponibilidad

- **Visibilidad:** oculta (solo con el enlace directo; el bot lo entrega a los miembros del canal).
- **Mercados:** Colombia (o todos).

## Propiedades

- **Categoría:** Productividad.
- **Política de privacidad:** sí, `https://fedora.tailf6cdf1.ts.net/api/v1/privacidad`
- **Sitio web:** `https://fedora.tailf6cdf1.ts.net/api/v1/privacidad`
- **Contacto de soporte:** el correo de la cuenta de Partner Center.
- **Contenido para adultos:** no.

## Ficha (idioma: español)

**Nombre** (lo toma del manifest): Asistente de postulación

**Descripción breve** (lo toma del manifest):
Postula desde tu navegador, con tu propia sesión, a las vacantes del canal JOBS - PRÁCTICAS/APRENDIZ.

**Descripción:**

Asistente privado para los miembros del canal de Telegram «JOBS - PRÁCTICAS/APRENDIZ».

Cuando tocas «Postularme» en una vacante del canal, esta extensión hace la postulación por ti
desde tu propio navegador, con tu sesión de Computrabajo o Magneto:

• Abre la vacante en una pestaña en segundo plano.
• Lee las preguntas del formulario y las responde con los datos de tu perfil, que confirmaste en
  el bot.
• Adjunta tu hoja de vida, levemente adaptada a la vacante.
• Envía la postulación y te confirma en Telegram qué respondió.

Seguridad y privacidad:
• Nunca pide, lee ni guarda contraseñas ni cookies de los portales.
• Solo funciona en Computrabajo, Magneto y el servidor del asistente.
• Antes de postular comprueba que la sesión abierta sea tu cuenta.
• Si el portal pide un captcha o una verificación, te muestra la pestaña para que la resuelvas tú.
• No ejecuta código descargado: solo recibe datos del servidor.

Requiere estar en el canal y vincular el navegador desde el bot con /vincular.

**Logotipo de la tienda:** `logo_300.png` (300 × 300).
**Mosaico promocional pequeño:** `mosaico_440x280.png` (440 × 280).
**Capturas** (1280 × 800): `captura_1_vinculado.png`, `captura_2_postulando.png`,
`captura_3_sin_vincular.png`.

## Notas para la certificación (para el revisor)

This extension is the browser companion of a private Telegram bot used by the members of a
private job-offers channel in Colombia. It only works after the user links it from the bot
(the bot shows a one-time link/code), so without an invitation the popup only shows the
"not linked" screen with a code field.

What it does: when the user taps "Apply" on a job in the Telegram channel, the extension opens
that job page on computrabajo.com or magneto365.com in a background tab, reads the form
questions, sends them to the bot's server (fedora.tailf6cdf1.ts.net) to get the user's own
answers, fills the form, attaches the user's CV (PDF) and submits it.

Permissions:
- storage: link token and portal status.
- tabs, scripting: open the job page in a background tab and run the bundled form-filler
  (motor.js) on it.
- alarms: heartbeat every 30 s to fetch the user's queue.
- host permissions: only computrabajo.com, magneto365.com and the bot server. Optional
  *.ts.net only if the administrator moves the server (asked to the user in Options).

No remote code: the server only sends data (CSS selectors and texts as JSON), interpreted by
the bundled scripts. No passwords, cookies, history or screenshots are collected. Privacy
policy: https://fedora.tailf6cdf1.ts.net/api/v1/privacidad
