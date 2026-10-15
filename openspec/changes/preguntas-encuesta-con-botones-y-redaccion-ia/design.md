## Context

Hoy cada pregunta sin respuesta queda en `pendientes_usuario` y la card (`tarjeta_postulacion._pregunta`) la pinta: botones si hay opciones, «Escribe tu respuesta» si no. El texto se guarda con `responder_pendiente` (`nucleo.py`) → `recordar`, como respuesta aprendida del usuario. `respuestas._redactar` ya sabe redactar con perfil y vacante, pero solo se usa antes de preguntar. Ver proposal.md.

## Goals / Non-Goals

**Goals:**
- Reutilizar la fase `pregunta` de la card y el mecanismo de pendientes; añadir sugerencias y redacción.
- Un fallo de IA nunca bloquea la postulación.

**Non-Goals:**
- Cambiar la extensión o la API.
- Redactar las preguntas con opciones.
- Pedir confirmación de la redacción antes de guardarla (se ve después en «Tus respuestas»).

## Decisions

1. **Sugerencias generadas una vez y cacheadas en `kv`** (clave por pendiente, lista de textos). Se generan al pintar la pregunta por primera vez. Alternativa: generarlas al detectar el pendiente en la cola; se descarta porque gastaría IA en preguntas que el usuario quizá nunca vea.
2. **Nueva función `sugerir` en `respuestas.py`** con esquema pydantic `Sugerencias(opciones: list[str])` (2–4, máx. ~40 caracteres), operación de IA `sugerir_respuestas`. Reutiliza `Contexto`, el cliente y las claves del usuario como `_redactar`.
3. **`_redactar` acepta una semilla opcional.** Instrucción nueva: mantener el sentido de la semilla, no inventar datos, primera persona, máx. 3 frases, conservar cifras exactas. Sin semilla se comporta como hoy. Alternativa: dos funciones; se descarta por duplicar el contexto.
4. **La redacción es lo que se guarda.** `responder_pendiente` recibe el texto final (redactado, o la semilla si la IA falló). Así el formulario, el banco de «aprendidas» y el resumen coinciden. Riesgo asumido: la redacción pensada para una vacante se reutiliza en otra; para preguntas que no mencionan la empresa es aceptable.
5. **Origen 🤖:** se registra que la respuesta salió de IA para que el resumen muestre 🤖. El mecanismo exacto se decide al leer cómo `resumen_postulacion.py` asigna `ICONOS_ORIGEN` (hoy `aprendida` se muestra como 💬).
6. **Botones:** callbacks `pend` con subacciones `sug:<id>:<n>`, `esc:<id>` (activa la espera de texto) e `ia:<id>`. Hoy la espera de texto se activa siempre al preguntar; pasa a activarse solo tras «Escribir yo» cuando hay sugerencias, y de inmediato cuando no las hay.
7. **Mientras la IA redacta**, la card muestra «✍️ Redactando…» (una edición) para que el toque no parezca ignorado.

## Risks / Trade-offs

- [La IA contradice la semilla] → la instrucción exige mantener el sentido y se prueba con semillas «no»/«sí».
- [Latencia de dos llamadas por pregunta] → sugerencias cacheadas y aviso «Redactando…».
- [Respuesta numérica reformulada de forma rara] → la instrucción dice conservar cifras exactas; el dueño eligió redactar todo lo de texto.
- [Costo de IA en la cuenta del usuario] → una llamada para sugerir y otra para redactar; sin clave no se llama.
