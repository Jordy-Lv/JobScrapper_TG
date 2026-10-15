## Why

Cuando un formulario trae preguntas que el asistente no puede responder con el perfil, la card solo pide «Escribe tu respuesta» cuando la pregunta es abierta. El usuario escribe un «no» o una frase corta y eso es lo que llega al formulario, sin redacción: se ve pobre frente al reclutador. Además, escribir cada respuesta es lento; con botones sería un toque.

## What Changes

- Las preguntas pendientes de una postulación se siguen preguntando **dentro de la misma card**. Las que traen opciones muestran un botón por opción (sin cambios).
- Las preguntas **abiertas** (texto libre, cortas o numéricas) muestran botones con **2–4 respuestas cortas sugeridas por la IA** según el perfil y la vacante, más **✍️ Escribir yo** y **🤖 Que la IA decida**.
- Lo que el usuario toca o escribe es una **semilla**: la IA del usuario la redacta mejor y completa, con el perfil y la vacante, y esa redacción es la respuesta final que se envía al formulario. «Que la IA decida» redacta sin semilla.
- Las preguntas con opciones se marcan tal cual, sin redacción.
- Sin clave de IA, o si la IA falla, la card se comporta como hoy: solo escribir, y la respuesta va tal cual la dio el usuario.
- El resumen «Tus respuestas» marca con 🤖 lo redactado por la IA.

## Capabilities

### New Capabilities
- `preguntas-encuesta-asistente`: cómo la card pregunta las preguntas pendientes de los formularios (botones, sugerencias, escribir, que la IA decida) y cómo se redacta la respuesta final.

### Modified Capabilities

(ninguna: en `openspec/specs/` solo existe `destino-mensajes-telegram`)

## Impact

- Código: `buscador_vacantes/asistente/respuestas.py` (sugerir respuestas y redactar desde una semilla), `conversacion.py` (`_preguntar_pendiente`, `_texto_pendiente`, `_responder_pendiente`, callbacks `pend`), `tarjeta_postulacion.py` (`_pregunta` y botones), `nucleo.py` (`responder_pendiente`), `textos.py`.
- Estado: sugerencias guardadas en la tabla clave-valor por pendiente; sin migración de esquema.
- Costo: una llamada a la IA para sugerir (por pregunta abierta, una sola vez) y otra para redactar la respuesta final.
- Pruebas: `tests/asistente/test_respuestas.py`, `test_asistente_tarjeta_postulacion.py`, `test_asistente_bot.py`.
- Despliegue: reiniciar `buscador-asistente` en el servidor Fedora.
