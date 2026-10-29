## Why

En el Chrome del dueño (extensión 1.3.2, la última, y servidor al día) la tarjeta de LinkedIn se queda para siempre en «Buscando correo»: el latido llega con `linkedin: listo` y `cuenta: sin_correo`. Verificado en vivo el 2026-10-28 con la sesión del dueño:

- `/in/me/` NO recarga la página hacia el perfil: LinkedIn (ahora una app de React Server Components, `/flagship-web/rsc-action/…`) cambia la URL con `history.replaceState` dentro del mismo documento (`redirectCount: 0`, la entrada de navegación sigue siendo `/in/me/`). La 1.3.2 suponía una navegación que destruía el script, así que su reintento atacaba una causa que no existe.
- El correo no viene en el HTML como `<a href="mailto:">`: viene dentro del payload de RSC (`"url":"mailto:…"`) y el `<dialog>` con el enlace solo existe cuando el JavaScript de LinkedIn termina de pintar.
- La extensión revisa el portal en una pestaña en segundo plano (`active: false`). Tanto el salto al perfil como el pintado del diálogo dependen del JavaScript de LinkedIn en esa pestaña oculta; si cualquiera de los dos no ocurre en 10 s, la revisión termina «listo, sin correo» sin error, y además no se repite hasta pasadas 6 h.

Con la pestaña visible todo aparece; en la de la extensión no. Hace falta una lectura que no dependa del pintado.

## What Changes

- La extensión lee el correo de LinkedIn pidiendo el HTML desde la propia pestaña del portal (petición del mismo origen, con la sesión del usuario, solo `GET`): toma el usuario del perfil de la URL o, si LinkedIn aún no saltó, del HTML de `/in/me/`, y extrae el único `mailto:` del HTML de `/in/<usuario>/overlay/contact-info/`. No espera a que LinkedIn pinte nada, así que funciona en segundo plano.
- Es declarativo: `linkedin.json` gana un bloque `cuenta.html` (página de inicio, expresión del usuario, URL de contacto y expresión del correo). Los portales sin ese bloque no cambian. La lectura por la página pintada (1.3.2) queda como respaldo.
- Cuando no encuentra el correo, la revisión informa el motivo en el latido (`sin_perfil`, `sin_correo`, `varios_correos`, `sin_sesion`) para diagnosticarlo desde el servidor sin abrir el navegador del usuario.
- Un portal con sesión y sin correo se vuelve a revisar a los 10 minutos, no a las 6 h.
- Extensión 1.3.3; `linkedin.json` con versión nueva.

## Capabilities

### New Capabilities

### Modified Capabilities
- `extension-navegador`: nuevo requisito «Correo de la cuenta de LinkedIn» (lectura sin depender del pintado, con un único correo del propio contacto y motivo cuando falta) y nuevo requisito de reintento pronto de un portal sin correo.

## Impact

- `extension/motor.js` (lectura por HTML), `extension/servicio.js` (orden de lectura, motivo y reintento), `extension/manifest.json` (1.3.3).
- `assets/asistente/selectores/linkedin.json` (bloque `cuenta.html`, versión). Se despliega en el Fedora para que el servidor lo entregue.
- `tests/asistente/test_extension.py`: prueba con una página que nunca pinta el diálogo ni salta al perfil.
- `docs/asistente/portales.md`: corrige la nota de la cuenta de LinkedIn.
- `buscador_vacantes/asistente/api.py`: guarda el `motivo` de un portal con sesión y sin correo en `navegadores.portales_json` (antes lo borraba). Sin cambios de API ni de base de datos: `motivo` ya viaja en el latido.
