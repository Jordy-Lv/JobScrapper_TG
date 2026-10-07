## Why

Cuando el usuario termina los pasos del alta y vincula su navegador, hoy el cierre («¡Listo! Ya puedes tocar ⚡ Postularme…») se pinta dentro de la tarjeta de conexión, editando un mensaje que ya existía. Una edición no genera aviso en Telegram y la frase es corta, así que el usuario no sabe qué hacer después: no entiende que el proceso empieza en el grupo, tocando el botón de la vacante que le interesa.

## What Changes

- Al terminar el alta (navegador vinculado y pasos completos), el bot envía **un mensaje nuevo** que explica qué sigue: ir al grupo, ver las vacantes y tocar el botón **⚡ Postularme** de la que quiera, porque con ese toque empieza todo el proceso (el bot prepara la hoja de vida, llena el formulario y avisa el resultado).
- El mensaje lleva un botón **«Ir al grupo»** cuando hay un enlace al grupo (invitación configurada o `t.me/c/…`).
- La tarjeta de conexión deja de repetir el cierre del alta: solo muestra el estado de la conexión.
- Si el alta termina con una vacante pendiente (el usuario ya tocó una), no se envía el mensaje: la postulación arranca sola dentro de la tarjeta.

## Capabilities

### New Capabilities
- `cierre-alta-asistente`: mensaje de cierre del alta que orienta al usuario hacia el grupo y el botón de postulación.

### Modified Capabilities
<!-- Ninguna en openspec/specs/. El cierre dentro de la tarjeta (change asistente-postulacion-telegram) deja de aplicar. -->

## Impact

- Código: `buscador_vacantes/asistente/textos.py` (`ALTA_LISTA`), `tarjeta.py` (quita el cierre), `conversacion.py` (`_terminar_alta`).
- Pruebas: `tests/test_asistente_bot.py` y `tests/test_asistente_tarjeta.py`.
- Sin cambios en la extensión, la API ni la configuración (reutiliza `Nucleo.enlace_grupo`).
