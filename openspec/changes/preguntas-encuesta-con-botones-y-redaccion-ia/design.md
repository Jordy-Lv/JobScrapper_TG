## Context

La extensión lee el formulario del portal y lo envía a `/formulario` (`api.py`). `nucleo.resolver_formulario` resuelve las preguntas **una por una** con `respuestas.resolver`, en este orden:

1. Tipo estándar (correo, teléfono).
2. Respuesta aprendida del usuario.
3. Banco compartido.
4. Clasificación con IA en un solo campo, que se guarda en el banco.
5. `_redactar`, si la pregunta no encaja en ningún campo. Usa el modelo «lite», un máximo de 3 frases y `suficiente=false` si falta algo.

Lo que no se resuelve queda en `pendientes_usuario`. La card (`tarjeta_postulacion._pregunta`) lo pregunta y `responder_pendiente` lo guarda con `recordar` como respuesta aprendida literal. Con todo respondido, la postulación vuelve a la cola, la extensión abre otra vez la vacante y llama de nuevo a `/formulario`.

Así falló la pregunta compuesta de Computrabajo del 2026-10-17: se clasificó como `programa`, se envió el valor pelado y el banco quedó con ese error para todos. Ver proposal.md.

Todas las plataformas automáticas (Computrabajo y Magneto) pasan por el mismo `/formulario`, así que el cambio vive en el servidor y vale para las dos. elempleo sigue en respaldo manual.

## Goals / Non-Goals

**Goals:**
- Respuestas de texto completas y naturales, apoyadas en el CV, con una sola llamada de IA por formulario.
- Pedir en la card solo el dato que falta, con sugerencias, y redactar después la respuesta completa.
- Que el usuario pueda revisar lo redactado antes del envío, por portal.
- Que una falla de IA nunca bloquee la postulación.

**Non-Goals:**
- Redactar texto para las preguntas con opciones: la IA solo elige una de las opciones del portal (decisión 11).
- Redactar los datos de contacto o enviárselos a la IA.
- Editar en el portal una respuesta ya enviada.
- Cambiar el flujo de elempleo, que sigue en respaldo manual.
- Una pantalla para administrar los datos aprendidos. Queda para otro change.

## Decisions

1. **Clasificación con formato.** `Clasificacion` suma `formato: "dato" | "redactar"`.
   - Es `dato` cuando la pregunta pide **solo** el valor de **un** campo del catálogo y se contesta con ese valor, como «Ciudad de residencia» o «¿Nivel de inglés?».
   - Es `redactar` cuando está formulada para responderse en prosa, pide varios datos o no encaja en el catálogo.
   - El banco guarda `campo=<campo>` para `dato` y `campo="redactar"` para el resto (`parametro` nulo). Así la siguiente vez no hace falta clasificar. Alternativa descartada: no guardar las de redacción, porque obligaría a clasificarlas en cada formulario.
   - Las preguntas de tipo `numero`, `fecha`, `correo` y `telefono` nunca van al redactor. Si su campo no se conoce, pasan a dato faltante de tipo `formulario`. Las de `opciones` sin campo conocido van a la misma llamada del redactor para elegir una opción (decisión 11).

2. **Redactor por formulario: `redactar_formulario(preguntas, ctx)` en `respuestas.py`.**
   - `resolver_formulario` se hace en dos fases. Primero resuelve sin redactar todo lo que es dato u opción. Luego junta las preguntas de texto marcadas `redactar` (o sin campo conocido) que no tienen redacción reutilizable y hace **una** llamada con la tarea `responder`.
   - **Entrada:** el perfil y el cuestionario (`DatosUsuario.para_ia()`, sin contacto), los datos aprendidos del usuario y la vacante. Los datos aprendidos van como lista `pregunta → respuesta`: los de tipo dato completos y, de los demás, los 40 más recientes. Las preguntas van numeradas, con su `maximo` si existe.
   - **Esquema de salida:** `RedaccionFormulario(respuestas: list[RespuestaRedactada])`. Cada `RespuestaRedactada` tiene `indice`, `respuesta: str | None` y `faltan: list[DatoFaltante]`. Cada `DatoFaltante` tiene `pregunta` (corta, en segunda persona) y `sugerencias: list[str]` (de 2 a 4, de hasta 40 caracteres cada una).
   - **Instrucción** (`INSTRUCCION_REDACTAR_FORMULARIO`):
     - primera persona, natural, profesional y sin muletillas de plantilla;
     - responder cada parte de la pregunta;
     - longitud proporcional a la pregunta;
     - conectar con la vacante cuando aporte;
     - los datos del usuario mandan sobre el CV;
     - no inventar nada: si falta un dato que solo el usuario sabe, dejar `respuesta=null` y listarlo en `faltan`;
     - respetar `maximo`;
     - un dato marcado como reservado no se pide de nuevo.
   - Se reutiliza la tarea `responder` en lugar de crear otra, porque `ProveedorIA` exige definir todas las tareas en cada proveedor. `_redactar` por pregunta desaparece. Su único uso pasa al redactor por formulario.

3. **Modelo de `responder`.** En `config.yaml`:
   - Gemini pasa a `gemini-flash-latest` y Groq a `llama-3.3-70b-versatile`.
   - Anthropic pasa a `claude-sonnet-5-5`, el mismo de `carta`.
   - OpenAI (`gpt-4.1-mini`), OpenRouter (70b) y DeepSeek (`deepseek-chat`) no cambian.
   - En todos los proveedores, `temperatura: 0.5` y `max_tokens: 3000`, porque una respuesta cubre todo el formulario.
   - La cadena de respaldo de modelos de cada proveedor se conserva.

4. **Límite de caracteres.** La extensión lee `maxlength` del `input` o `textarea` y lo envía como `maximo` (`api.Campo.maximo: int | None`). `Pregunta` suma `maximo`. Si la IA se pasa, `recortar_a_limite` corta en el último `.`, `!` o `?` dentro del límite, o en el último espacio si no hay ninguno.

5. **Datos faltantes como pendientes de tipo `dato`.**
   - `pendientes_usuario.tipo` puede ser `formulario` (la pregunta del portal, como hoy, con sus opciones exactas) o `dato` (la pregunta corta del redactor, con sus sugerencias en `opciones_json`).
   - Un pendiente de `dato` se deduplica por `pregunta_norm` entre preguntas de la misma postulación.
   - Al responderlo, `responder_pendiente` guarda el dato corto con `recordar`, igual que hoy. La siguiente pasada lo recibe como dato aprendido.
   - Ya no se redacta en el momento de responder. La redacción final la hace la siguiente pasada del formulario. Esto ahorra una llamada por pregunta y mantiene una sola fuente de redacción.

6. **«Prefiero no decirlo».** Guarda el dato aprendido con el valor reservado `__reservado__`. El redactor lo recibe como «el usuario prefiere no darlo» y redacta sin él.
   - Si aun así devuelve `faltan` para ese mismo dato en una pregunta obligatoria, la pregunta del portal pasa a pendiente de tipo `formulario` para escribirla.
   - `DatosUsuario.para_ia` y el resumen nunca muestran el valor reservado como respuesta.

7. **Reutilizar redacciones por postulación.**
   - `respuestas` suma `pregunta_norm` y `estado`, que puede ser `enviada`, `propuesta` o `aprobada`.
   - `_guardar_respuestas` deja de borrar todo. Hace upsert por `(postulacion_id, pregunta_norm)` y conserva las redacciones.
   - En una pasada nueva del mismo formulario, `resolver_formulario` toma las redacciones de origen `ia`, `usuario` o `aprobada` ya guardadas para esa postulación y solo redacta las que no tienen.

8. **Revisión antes de enviar.**
   - **Preferencia:** `preferencias_portal.revisar_respuestas` (INTEGER, por defecto 0). Se expone en `GET` y `POST /preferencias/{plataforma}`. En el popup va como un interruptor más en la vista del portal, junto a «Avisar».
   - **Cuándo espera:** la preferencia está encendida y la pasada produce al menos una respuesta de origen `ia` que aún no está `aprobada`. En ese caso `resolver_formulario` guarda las respuestas como `propuesta`, `/formulario` responde `esperar_usuario` y se notifica `revision_respuestas`.
   - **Card:** entra en la fase nueva `REVISION`. Muestra las respuestas redactadas completas, partidas con `resumen_postulacion.partir` si no caben, con «✅ Enviar» y «✏️ Corregir».
   - **Corregir:** abre la lista de respuestas. Se elige una y se escribe el texto nuevo, que queda con origen `usuario` y estado `aprobada`, y la card vuelve a la revisión.
   - **Enviar:** marca todo como `aprobada` y reanuda la cola. La pasada siguiente las reutiliza (decisión 7), no llama a la IA y no vuelve a esperar.
   - **Sin respuesta:** se aplica `espera_usuario_h` (12 h) como a los pendientes de hoy.

9. **Migración v4** (`datos.py`, `ESQUEMA_VERSION = 4`):
   - `ALTER TABLE` de `pendientes_usuario.tipo` (por defecto `formulario`), `preferencias_portal.revisar_respuestas`, `respuestas.pregunta_norm` y `respuestas.estado` (por defecto `enviada`);
   - `DELETE FROM banco_preguntas WHERE origen = 'ia'`, para reclasificar con el nuevo esquema; las sembradas se conservan;
   - un índice único `(postulacion_id, pregunta_norm)` en `respuestas`. Las filas viejas se completan con `normalizar_pregunta` en Python dentro de la migración.

10. **Orden de entrega.** El servidor (decisiones 1 a 9) no depende de la extensión: sin `maximo`, solo se omite el límite. Los cambios a `motor.js` y al popup van al final y después de cerrar `magneto-confirmar-y-leer-encuesta`, que hoy tiene `motor.js` modificado sin subir.

11. **Opciones en la misma llamada (todos los portales).** La encuesta de Magneto es de botones Si/No y elempleo tiene preguntas cerradas (`[n].IsCloseAnswer`). Antes de este change, `_redactar` elegía la opción de una pregunta fuera del catálogo; quitarlo las mandaba todas a la card. Por eso:
   - una pregunta con opciones que no resuelven los datos aprendidos, el banco ni el perfil entra a `redactar_formulario` junto con las abiertas, con sus opciones numeradas desde 0;
   - `RespuestaRedactada` suma `opcion: int | None`. Para una pregunta con opciones solo vale `opcion` dentro del rango; si falta o se sale, la pregunta pasa a la card como pendiente `formulario`;
   - las autorizaciones y aceptaciones (tratamiento de datos, términos) siguen sin pasar por la IA;
   - al reutilizar una respuesta guardada, el texto de la opción se vuelve a buscar entre las opciones con `elegir_opcion`; si ya no está, se resuelve de nuevo.
   - elempleo no necesita nada más: su cuestionario y la nota de presentación VIP ya pasan por `/formulario`. Las preguntas de Magneto sin botones (texto libre) siguen terminando `formulario_desconocido` hasta ver una real.

## Risks / Trade-offs

- **[La IA mete un dato que no está en los datos]** La instrucción lo prohíbe, y las pruebas con IA simulada verifican que lo que falta llega como `faltan` y no como respuesta. Para más control está el modo revisión.
- **[Redacción genérica o con frases de plantilla]** La instrucción pide conectar con la vacante y lo prohíbe. El modelo de `responder` sube de nivel.
- **[Más latencia en un formulario grande]** Es una sola llamada con `max_tokens: 3000`. Las pausas entre postulaciones (45 a 120 s) la absorben.
- **[Costo en la clave del usuario]** Baja frente a hoy, porque pasa de una llamada por pregunta a una por formulario más una por vuelta con datos. Sonnet y Flash cuestan más por token que los modelos lite, pero el tope diario de 60 llamadas no cambia.
- **[Borrar el banco de origen `ia` cuesta reclasificar]** Es una llamada `clasificar_pregunta` (modelo lite) por pregunta vista de nuevo, una sola vez.
- **[La revisión frena el modo automático]** Viene apagada por defecto y se activa por portal.
- **[El portal cambia el texto de la pregunta entre pasadas]** La reutilización es por `pregunta_norm`. Si el texto cambia, se redacta de nuevo y no se rompe nada.
