## Why

Las respuestas que el asistente escribe en los formularios de los portales salen pobres o incompletas. El 2026-10-17, en una postulación de Computrabajo, la pregunta «¿Qué programa técnico o tecnológico estás estudiando […] y en qué institución?» se respondió solo con «Tecnología en Desarrollo de Software»: la institución quedó por fuera.

Las causas están en `respuestas.py`:

- **Una pregunta, un campo.** La IA clasifica cada pregunta nueva en un solo campo del catálogo, y en las preguntas de texto se envía el valor pelado. Una pregunta que pide dos datos queda a medias, y una pregunta formulada en prosa recibe un dato suelto.
- **El banco compartido perpetúa el error.** Esa clasificación se guarda para todos los usuarios, así que la misma pregunta seguirá respondiéndose incompleta.
- **Redacción mínima.** Cuando la pregunta se redacta, se usa un modelo «lite», con un máximo de 3 frases y sin pautas de tono. Si al perfil le falta un dato, la pregunta entera pasa al usuario en vez de pedirse solo lo que falta.
- **Lo del usuario va tal cual.** Lo que el usuario escribe en la card («no», «SENA») se guarda como respuesta aprendida y se envía literal al formulario, y en otras vacantes se reutiliza igual.

El dueño quiere respuestas completas y naturales, que aprovechen el CV, que en la misma card se pregunte solo lo que el CV no tiene y que haya más control sobre lo que se envía en todos los portales activos.

## What Changes

- **Redactor por formulario.** Las preguntas de texto que no son un dato simple (correo, teléfono, número, fecha, una opción) se redactan con **una sola llamada** a la IA del usuario. La llamada recibe todas esas preguntas juntas, con el perfil del CV, el cuestionario del alta, los datos que el usuario ya dio y la vacante. La IA responde todo lo que pide cada pregunta, incluidas las compuestas, en primera persona, con un tono natural y profesional y con una longitud que depende de la pregunta. Respeta el límite de caracteres del campo cuando el portal lo informa y no inventa nada.
- **Datos faltantes en la misma card.** Si para responder bien falta un dato que el CV no tiene, la IA lo devuelve como una pregunta corta («¿En qué institución estudias?») con 2 a 4 sugerencias. La card pregunta **ese dato** y no la pregunta original del portal, y ofrece los botones de sugerencia, «✍️ Escribir yo» y «Prefiero no decirlo». Al responder, la postulación vuelve a la cola y el redactor escribe la respuesta completa con ese dato.
- **Datos aprendidos, no redacciones.** Lo que el usuario responde en la card se guarda como dato corto y reutilizable, y la IA lo vuelve a redactar para cada vacante. Esos datos mandan sobre el CV.
- **Banco compartido solo para datos simples.** La clasificación indica si la pregunta pide un dato simple o una redacción. El banco guarda el campo solo para los datos simples. Las preguntas compuestas o de redacción se guardan como `redactar` y van directo al redactor sin reclasificarse. Al desplegar se borran las entradas del banco creadas por la IA para que se reclasifiquen con el nuevo esquema; las sembradas se conservan.
- **Modo «Revisar respuestas antes de enviar» por portal.** Es un interruptor nuevo en la vista de cada portal del popup y viene **apagado** por defecto. Si está encendido y el formulario trae respuestas redactadas por la IA, la card las muestra antes del envío con «✅ Enviar» y «✏️ Corregir». Lo aprobado o corregido se envía sin volver a llamar a la IA.
- **Modelo de la tarea `responder` de más calidad.** Gemini pasa de `gemini-flash-lite-latest` a `gemini-flash-latest`, Groq de `llama-3.1-8b-instant` a `llama-3.3-70b-versatile` y Anthropic de `claude-haiku-4-5-20251001` a `claude-sonnet-5-5`. OpenAI, OpenRouter y DeepSeek siguen con su modelo. Por ser una llamada por formulario, la temperatura sube a 0.5 y `max_tokens` a 3000.
- **Sin cambios:** las preguntas con opciones se marcan tal cual, sin IA. Sin clave de IA, o si la IA falla, el flujo es el de hoy: se pregunta en la card y lo escrito se envía tal cual.
- El resumen «Tus respuestas» sigue marcando con 🤖 lo redactado por la IA, también cuando se redactó con datos que dio el usuario.

## Capabilities

### New Capabilities
- `preguntas-encuesta-asistente`: cubre cómo se redactan las respuestas de texto de los formularios (redactor por formulario, preguntas compuestas, límite de caracteres), cómo la card pide los datos faltantes, cómo se guardan los datos aprendidos y el banco, y el modo de revisión antes de enviar.

### Modified Capabilities
- `tarjeta-postulacion-asistente`: el requisito «Estados de la card» suma el estado *revisión de respuestas*.

## Impact

- **Código Python:**
  - `buscador_vacantes/asistente/respuestas.py`: clasificación con formato, redactor por formulario y datos faltantes.
  - `campos.py`: datos aprendidos para la IA.
  - `nucleo.py`: `resolver_formulario`, `responder_pendiente`, reutilizar redacciones y revisión.
  - `api.py`: `Campo.maximo` y la preferencia `revisar_respuestas`.
  - `preferencias.py`, `datos.py`: migración v4.
  - `conversacion.py`, `tarjeta_postulacion.py`, `resumen_postulacion.py`, `textos.py`: botones de dato y fase de revisión.
- **Extensión:**
  - `motor.js`: envía `maximo`, leído de `maxlength`.
  - `popup.html` / `popup.js`: interruptor «Revisar respuestas».
  - Esta parte va después de cerrar `magneto-confirmar-y-leer-encuesta`, que tiene `motor.js` modificado.
- **Configuración:** `config.yaml`, modelos y topes de la tarea `responder` en cada proveedor.
- **Esquema:** pasa a v4 con estas columnas:
  - `pendientes_usuario.tipo`
  - `preferencias_portal.revisar_respuestas`
  - `respuestas.estado` y `respuestas.pregunta_norm`
- **Costo de IA:** baja de una llamada por pregunta abierta a **una llamada por formulario**, más una por cada vuelta con datos faltantes. Las sugerencias vienen en la misma llamada. Lo usa la clave de cada usuario dentro de su tope diario.
- **Plataformas:** todo pasa por `/formulario`, así que aplica a Computrabajo y Magneto (automáticas). elempleo sigue en respaldo manual.
- **Pruebas:** `tests/asistente/test_respuestas.py`, `test_nucleo.py`, `test_api.py`, `test_datos.py`, `test_tarjeta_postulacion.py`, `test_bot.py`, `test_resumen_postulacion.py`, `test_extension.py`.
- **Despliegue:** reiniciar `buscador-asistente` en el servidor Fedora. La migración v4 y la limpieza del banco corren solas al arrancar. Hay que recargar la extensión.
