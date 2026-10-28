## Context

En octubre de 2026 Magneto migró la encuesta posterior a pulsar «Aplicar» desde un listado estático en la misma página (`job-offer-questionnaire`) hacia un componente React conversacional (`detailChatQuestionnaireChat_container` / `mg_chat_questionnaire_questionnaire`) montado dentro de un cajón Ant Design (`.ant-drawer-open` con `[aria-modal="true"]`) o en pestaña embebida.

Del análisis de los paquetes compilados de Magneto (`9122-2bf165f8259017dc.js` y `159-13ac7d37c8801d85.js`) y de las evidencias reales de producción (postulaciones 74, 89, 93, 94 y 96) se desprenden cinco restricciones técnicas exactas:
1. **Montaje secuencial con espera por turno**: el hook `useChat` inserta una pregunta a la vez. Cada bloque `div[class*='mg_chat_questionnaire_question_question']` renderiza durante 2 000 ms `<div class="mg_chat_questionnaire_loading_dots">` antes de montar la burbuja `<article role="bot">` y el control de respuesta hermano.
2. **Colisión de subcadena CSS**: el contenedor externo del turno es `<div class="mg_chat_questionnaire_question_question_...">` y la burbuja interna del bot es `<article class="... mg_chat_questionnaire_question_question_bot_..." role="bot">`. Usar `[class*='mg_chat_questionnaire_question_question']` sin fijar la etiqueta `div` captura también el `<article>`, cuyo árbol no contiene los controles de respuesta hermanos.
3. **Separación entre enunciado e instrucción**: dentro de `[class*='bubble-message']`, el primer hijo contiene `titleQuestion` (la pregunta real) y el segundo hijo contiene `caption` («Selecciona una opción», «Escribe una respuesta de máximo 140 caracteres»…). Concatenar ambos ensuciaría la clave normalizada del banco de preguntas (`pregunta_norm`).
4. **Cuatro tipos de control y filtro estricto de texto**:
   - `unique` (`0`): `label[class*='unique_choice_answers_option']` con `<input type="radio">` sin `name`; al hacer clic guarda la respuesta de inmediato y reemplaza el control por `<article role="candidate">`.
   - `multiple` (`1`): `label[class*='multiple_choice_answers_option']` con `<input type="checkbox">` más el botón `button[class*='multiple_choice_continue-button']` («Guardar»), deshabilitado hasta marcar al menos una opción.
   - `openShort` (`2`) y `openLong` (`3`): `textarea[class*='open_short_input']` cuyo `onChange` aplica `value.replaceAll(/[^a-zA-ZÀ-ÿ0-9\s.,¿¡!?@$%^&*()_+\-=;:'"|`´]/g, "")`, acompañado de un botón de envío de solo ícono (`button[class*='open_short_button']`). Caracteres habituales en redacciones (`/`, `—`, `–`, comillas tipográficas `«»“”‘’`, `…`) son eliminados al vuelo por el portal.
5. **Pie del cajón y estado del envío**: el botón final «Enviar respuestas» (`button[class*='detailChatQuestionnaireChat_chat__submit']`) vive dentro de `<footer class="detailChatQuestionnaireChat_chat__footer__...">` y permanece `disabled` hasta que `useChat` marca el cuestionario como completado (`isCompleted`).

## Goals / Non-Goals

**Goals:**
- Resolver de extremo a extremo el cuestionario conversacional de Magneto en sus cuatro tipos de pregunta manteniendo intactos el flujo clásico en línea (`job-offer-questionnaire`) y el flujo sin encuesta (`mg_application_summary_summary-modal`).
- Acumular todas las respuestas del chat en la tabla `respuestas` de la postulación para el resumen de Telegram («Encuesta de N» y vista «Respuestas») y reutilizarlas sin pérdida si una pregunta intermedia requiere `esperar_usuario`.
- Reconocer con precisión «Proceso abandonado» y «Ya respondiste» sin disparar alertas falsas al dueño ni penalizar al vigía diario.
- Conservar `<header>` y `<footer>` internos de diálogos/formularios tanto en `htmlSinValores` (evidencia diagnóstica) como en `enZonaExcluida` del motor genérico.
- Permitir que `respaldo_declarado` (`bucleGenerico`) rescate cualquier cambio futuro del cuestionario de Magneto una vez confirmado que «Aplicar» abrió una encuesta sin enviar todavía, y dotar al motor genérico de alcance modal (`[aria-modal="true"]`) y agrupación de radios sin `name`.

**Non-Goals:**
- Ejecutar código remoto o lógica específica cableada por dominio fuera de las primitivas declarativas de `motor.js`.
- Responder automáticamente preguntas de consentimiento o tratamiento de datos personales (siguen reservadas exclusivamente a la decisión explícita del usuario).

## Decisions

### 1. Primitiva declarativa por turnos (`chat_turno` y `chat_llenar`) dirigida desde `magneto.json`
En lugar de escribir un adaptador imperativo acoplado a Magneto, `paso.accion === "formulario"` detecta si el contenedor hallado corresponde a `paso.chat.contenedor` y devuelve `{ chat: true }`. `servicio.js` ejecuta entonces un bucle acotado (`max_preguntas`, por defecto 40):
- `chat_turno` espera hasta `espera_turno_ms` (8 000 ms, suficiente para los 2 000 ms de `loading_dots` más holgura de red/renderizado) a que exista un turno pendiente con su burbuja del bot y sus controles listos, o bien a que todos los turnos tengan `[role="candidate"]` y `enviar_final` esté habilitado (`{ listo: true }`).
- Cada turno se resuelve contra `POST /postulaciones/{id}/formulario` enviando un único `Campo` (`campos: [campo]`). Como `nucleo._guardar_respuestas` usa `ON CONFLICT(postulacion_id, pregunta_norm) DO UPDATE`, cada llamada conserva las respuestas de los turnos anteriores en SQLite sin cambiar el contrato HTTP existente.
- `chat_llenar` ejecuta la acción correspondiente al tipo de turno (`unica`, `multiple`, `abierta`) dentro del tope `llenado_max_ms` y verifica que el bloque del turno transicione a `def.respondida` (`article[role="candidate"]`), reportando `llenado_1`, `llenado_2`, …, y finalmente `llenado` al quedar habilitado «Enviar respuestas».

*Alternativa descartada*: delegar Magneto directamente al `bucleGenerico` (`POST /pantalla` por cada pregunta). Se descartó como vía principal porque los botones de envío por turno en preguntas abiertas carecen de texto visible (solo tienen un `<svg>`), lo que obligaría a invocar al árbitro con IA en cada pregunta abierta y perdería la normalización determinista del filtro de caracteres de Magneto. Sin embargo, el motor genérico sí queda habilitado como red de seguridad (`respaldo_declarado`).

### 2. Normalización previa al alfabeto de Magneto (`caracteres_permitidos: "magneto_texto"`)
Antes de llamar a `asignarValor` en preguntas abiertas con `caracteres_permitidos: "magneto_texto"`, `motor.js` reemplaza signos tipográficos equivalentes (`—`/`–` → `-`, `/` y `\` → `-`, `«»“”` → `"`, `‘’` → `'`, `…` → `...`, `•` → `-`, `[`/`]` → `(`/`)`), elimina cualquier carácter fuera de `[a-zA-ZÀ-ÿ0-9\s.,¿¡!?@$%^&*()_+\-=;:'"|`´]`, colapsa espacios repetidos y recorta a `maximo`. Luego comprueba `campo.el.value === texto` antes de pulsar `open_short_button`. Así se evita tanto el rechazo silencioso de caracteres como el fallo de verificación por diferencias entre el texto original y el filtrado por React.

### 3. Soporte limpio de selección múltiple (`multiple: bool` + `opciones: list[int]`)
`Campo` y `Pregunta` incorporan `multiple: bool = False`. Cuando `multiple` es verdadero, `elegir_opciones` y el redactor con IA pueden devolver uno o varios índices válidos en `opciones: list[int]`, manteniendo siempre `opcion: int` con el primer índice elegido y serializando `"opciones"` en `pantalla.respuestas_de` únicamente cuando hay lista (`if r.opciones`), preservando el 100 % de compatibilidad con pruebas y clientes existentes. `Respuesta.texto` concatena las opciones elegidas con `", "` para que la tarjeta de Telegram y la reutilización de respuestas muestren todas las casillas marcadas.

### 4. Desmarcado seguro del envío cuando se abre una encuesta (`abre_sin_enviar: true`)
`aplicar` conserva `envia: true` para que: (a) en modo ensayo se detenga antes de pulsar «Aplicar» (evitando enviar por accidente vacantes sin encuesta), y (b) si el navegador muere justo tras «Aplicar» en una vacante sin encuesta, quede `incierta`. Cuando `preguntas` (`abre_sin_enviar: true`) confirma que efectivamente se abrió en pantalla el contenedor de la encuesta (aún sin enviar), `servicio.js` restablece `contexto.envio = false` y el servidor limpia `envio_pulsado = 0` al recibir `POST /formulario` (y al pasar a `esperando_usuario`), volviendo a marcar `POST /envio` y `contexto.envio = true` justo antes de pulsar «Enviar respuestas» en el paso `enviar`.

### 5. Distinción quirúrgica de «Proceso abandonado» y alcance modal en `motor.js`
Magneto reutiliza `div[class*='renderApplyButton_status-label']` tanto para «Ya aplicaste a este empleo» como para «Proceso abandonado». Por ello `revisar_vacante.casos` evalúa primero `ya_postulado` y usa el selector compuesto `{ "css": "[class*='renderApplyButton_status-label']", "texto": "proceso abandonado" }` para reportar `bloqueada` con `motivo: "proceso_abandonado"`. En `motor.js`, `htmlSinValores` y `enZonaExcluida` solo descartan `header, nav, footer` globales (fuera de `[role="dialog"], [aria-modal="true"], dialog, form, article`), `modalActivo` restringe el motor genérico al modal visible superior y los `<input type="radio">` sin `name` se agrupan por su contenedor común cercano.

## Risks / Trade-offs

- **[Riesgo] Preguntas del chat que tarden más de 2 s en cargar** → Mitigación: `espera_turno_ms` se fija en 8 000 ms por turno (4× la animación de 2 000 ms de `useChat`).
- **[Riesgo] Recarga manual necesaria de la extensión en el navegador vinculado** → Mitigación: se actualiza `extension/manifest.json` a `1.2.1` y se documenta explícitamente como tarea `👤 Del dueño` recargar la extensión además de desplegar en Fedora.
