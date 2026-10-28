## Why

Magneto reemplazó su encuesta estática en línea (`job-offer-questionnaire`) por un cuestionario conversacional paso a paso dentro de un cajón lateral (`detailChatQuestionnaireChat_container` / `mg_chat_questionnaire_questionnaire`). En producción (postulaciones 89, 94 y 96, como `Auxiliar TI 1626549825-1`), pulsar «Aplicar» abre ese cajón con una sola pregunta visible tras una animación de carga de 2 s (`loading_dots`), cuatro formatos distintos de respuesta (opción única, opción múltiple con botón «Guardar», texto corto y texto largo con filtro estricto de caracteres y botón de envío por turno) y el botón final «Enviar respuestas» deshabilitado en el `<footer>` del cajón hasta completar todas las preguntas. Como los selectores solo buscaban `job-offer-questionnaire`, el paso opcional `preguntas` expiraba sin leer nada, `enviar` no hallaba el botón y `confirmar` terminaba tras 20 s sin el modal ni el botón «Aplicar», marcando falsamente `incierta` o `formulario_desconocido` («el formulario del portal cambió»).

Además, la auditoría forense de producción reveló tres brechas sistémicas conexas:
1. **Evidencia recortada**: `htmlSinValores` en `extension/motor.js` eliminaba todo `<header>` y `<footer>` sin distinguir entre la cabecera/pie globales del sitio y la cabecera o pie internos de un diálogo o cajón (`[role="dialog"]`, `[aria-modal="true"]`, `<form>`), borrando el `<footer class="detailChatQuestionnaireChat_chat__footer__...">` con el botón «Enviar respuestas» de la evidencia guardada en la postulación 96.
2. **Estados propios del portal**: Magneto muestra «Proceso abandonado» (`renderApplyButton_status-label`) sin botón «Aplicar» cuando el candidato retiró o abandonó antes ese proceso (postulación 74), y el modal `alreadyAnsweredQuestionnaire` cuando ya respondió el cuestionario; ambos terminaban como `formulario_desconocido` y disparaban alertas falsas al dueño.
3. **Respaldo genérico bloqueado y alcance de modales**: como el paso `aplicar` de Magneto registra `envia: true` por precaución ante vacantes sin encuesta, `contexto.envio` y `envio_pulsado` permanecían verdaderos incluso cuando se abría en pantalla una encuesta aún sin enviar, impidiendo que `respaldo_declarado` (`bucleGenerico`) rescatara un cambio futuro del cuestionario y provocando `incierta` si el navegador se cerraba antes de enviar. A su vez, el motor genérico escaneaba controles y botones del fondo detrás de un `[aria-modal="true"]`, excluía `<footer>` dentro de diálogos y separaba `<input type="radio">` sin atributo `name`.

## What Changes

- **Soporte nativo declarativo para el cuestionario tipo chat de Magneto (`chat`)** en `assets/asistente/selectores/magneto.json`, `extension/motor.js` y `extension/servicio.js`, manteniendo compatibilidad total con la encuesta clásica en línea (`job-offer-questionnaire`) y con las vacantes sin encuesta:
  - Lectura y respuesta turno por turno esperando a que termine `loading_dots` y aparezca la burbuja del bot (`article[role="bot"]`), extrayendo únicamente el enunciado (`:first-child`) como `texto` y la instrucción (`:nth-child(2)`) como `ayuda`.
  - Soporte para los cuatro widgets reales del portal: opción única (`unique_choice_answers_option`), opción múltiple (`multiple_choice_answers_option` + botón «Guardar» `multiple_choice_continue-button`), respuesta abierta corta y larga (`open_short_input` + normalización de puntuación al alfabeto permitido por Magneto + botón `open_short_button`), comprobando que cada turno pase a estado respondido (`article[role="candidate"]`) antes de avanzar y habilitando «Enviar respuestas» al cierre.
  - Salida anticipada (`cortar_si`) en la espera opcional de `preguntas` cuando ya apareció el modal de confirmación o de cuestionario ya respondido.
- **Selección múltiple en el canal de formularios** (`buscador_vacantes/asistente/{api.py,respuestas.py,pantalla.py,nucleo.py}`): `Campo` y `Pregunta` aceptan `multiple: bool = False` y `Respuesta` / `respuestas_de` admiten `opciones: list[int]` manteniendo `opcion: int` para compatibilidad completa.
- **Reconocimiento de «Proceso abandonado» y «Ya respondiste»**:
  - `magneto.json` detecta `{ "css": "[class*='renderApplyButton_status-label']", "texto": "proceso abandonado" }` como `bloqueada` con `motivo: "proceso_abandonado"` y `[class*='alreadyAnsweredQuestionnaire']` como `ya_postulada`.
  - `textos.py` incorpora `"proceso_abandonado"` en `MOTIVOS_RESPALDO` y `MOTIVOS_SIN_ALERTA` para explicar con claridad en la tarjeta por qué Magneto no permite volver a postular y sin alertar falsamente al dueño ni al vigía.
- **Evidencia íntegra, desmarcado de envío previo y mejoras del motor genérico**:
  - `htmlSinValores` y `enZonaExcluida` conservan `<header>` y `<footer>` cuando pertenecen a `[role="dialog"]`, `[aria-modal="true"]`, `<dialog>`, `<form>` o `<article>`.
  - `abre_sin_enviar: true` en `preguntas` y el reinicio de `envio_pulsado` al recibir un formulario o esperar al usuario restablecen el estado «aún no enviado» cuando se abre una encuesta tras pulsar «Aplicar», reactivando `respaldo_declarado` ante cambios futuros sin arriesgar doble envío en vacantes sin encuesta.
  - `motor.js` acota `buscarControles` y `leerBotones` al modal activo (`[aria-modal="true"], dialog[open]`) cuando existe y agrupa `<input type="radio">` sin `name` que comparten contenedor de opciones.

## Capabilities

### New Capabilities
- *(ninguna: amplía la capacidad existente `postulacion-magneto`)*

### Modified Capabilities
- `postulacion-magneto`: cubre el cuestionario conversacional por turnos en cajón lateral (selección única, selección múltiple, texto corto/largo con normalización de caracteres), el reconocimiento de «Proceso abandonado» y «Ya respondiste», la preservación de cabeceras/pies de diálogos en la evidencia sin valores y la habilitación segura del respaldo genérico cuando una encuesta se abre sin haber enviado aún la postulación.

## Impact

- `assets/asistente/selectores/magneto.json`: nueva versión `2026.10.27-1` con selectores del cajón de chat, casos `proceso_abandonado` y `alreadyAnsweredQuestionnaire`, `abre_sin_enviar`, `cortar_si` y `no_enviado` ampliado.
- `extension/motor.js` y `extension/servicio.js`: acciones declarativas `chat_turno` y `chat_llenar`, `cortar_si` en `esperar`, corrección de `htmlSinValores` / `enZonaExcluida`, alcance de `[aria-modal="true"]` y agrupación de radios sin `name` (requiere recargar la extensión desempaquetada o subir versión).
- `buscador_vacantes/asistente/{api.py,cola.py,nucleo.py,pantalla.py,respuestas.py,textos.py}`: soporte de `multiple` / `opciones`, motivo `proceso_abandonado` y limpieza de `envio_pulsado` cuando se abre encuesta o queda `esperando_usuario`.
- `tests/fixtures/extension/` y `tests/asistente/`: nuevos fixtures realistas (`mg_chat_cuestionario.html`, `mg_proceso_abandonado.html`) y pruebas integrales de extensión, motor genérico, cola, respuestas y tarjeta.
