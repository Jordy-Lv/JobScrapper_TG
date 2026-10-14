## Why

Una postulación hoy se reparte entre varios mensajes: la tarjeta de conexión (solo en el alta), un «En cola» suelto, el mensaje de progreso, preguntas pendientes sueltas (`_preguntar_pendiente`), un aviso aparte para el bloqueo del portal o el respaldo, la tarjeta de confirmación y mensajes efímeros para «Ver respuestas» y «De qué trata». El usuario ve el chat llenarse y debe reconstruir el estado a partir de varios mensajes. Con las preguntas rápidas y el seguimiento ya en tarjeta, falta unir el resto para que toda la postulación se lea de un vistazo.

## What Changes

- Desde que el usuario toca «Postular» hasta que termina el proceso, la postulación vive en **una sola card de Telegram** que se edita en el lugar: en cola, conexión/cuenta, pregunta rápida, progreso, sesión pendiente, bloqueo del portal, confirmación, incierta y respaldo manual.
- La card nace **siempre al tocar** (también fuera del alta). En el alta, la tarjeta de conexión se convierte en esa misma card.
- Las **preguntas pendientes** del formulario se contestan dentro de la card (botones de opciones o «Escribe tu respuesta»); el texto escrito por el usuario se borra y la card vuelve al progreso.
- «Ver respuestas» y «De qué trata» pasan a **vistas dentro de la card** con «Volver»; dejan de ser mensajes efímeros. El CV adjunto sigue como documento aparte.
- El seguimiento (**Entrevista, Rechazada**) se marca en la card, que muestra la opción elegida y permite cambiarla.
- En el **respaldo manual** la card resume el motivo y ofrece las acciones; el paquete (CV, carta, respuestas) sigue en mensajes propios.
- **Diseño sobrio**: texto con `<blockquote>`, botones en filas ordenadas y pocos emojis, solo los que aportan estado (✅ confirmada, ❔ incierta, 🔒 acción del usuario, ⚠️ cuenta distinta; ✓ y · en las etapas).
- Se eliminan los mensajes sueltos de «En cola», progreso aparte, bloqueo, «Gracias, lo recordaré» y los efímeros de resumen.

## Capabilities

### New Capabilities
- `tarjeta-postulacion-asistente`: la card única de una postulación en Telegram: estados, transiciones, vistas internas, seguimiento, casos de error y estilo visual.

### Modified Capabilities
<!-- Ninguna: openspec/specs/ está vacío; el flujo de preguntas rápidas del alta sigue definido en el change tarjeta-unica-preguntas-rapidas. -->

## Impact

- Código: `buscador_vacantes/asistente/tarjeta.py` (conexión como bloque de la card), nuevo módulo de funciones puras para la card de postulación, `resumen_postulacion.py` (vistas de respuestas y de qué trata como secciones de la card), `conversacion.py` (`procesar_toque`, `_pintar_tarjeta`, `_editar_progreso`, `_enviar_resumen`, `_avisar_evento`, `_preguntar_pendiente`, `_responder_pendiente`, callbacks `res`/`seg`/`rei`/`pend`), `textos.py`.
- Estado: nueva clave en `kv` por postulación; se reutiliza `postulaciones.mensaje_id`. Sin migración de esquema.
- Pruebas: `tests/test_asistente_tarjeta.py`, `tests/test_asistente_resumen_postulacion.py` y las de conversación que esperaban varios mensajes.
- Sin cambios en la extensión ni en la API.
