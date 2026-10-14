## Why

Hoy las preguntas rápidas del alta (documento, salario, disponibilidad, modalidades, etc.) llegan como un mensaje nuevo por pregunta, y cada respuesta que el usuario escribe queda en el chat: son unas 10 preguntas y otros tantos mensajes de texto que llenan la conversación de spam. Además, al terminar no hay forma de revisar lo contestado ni de corregir una respuesta sin repetir todo el cuestionario.

## What Changes

- Las preguntas rápidas se muestran en **una sola tarjeta**: un único mensaje que se edita en el lugar con el progreso («Faltan N» / «Última»), la pregunta actual y sus botones, en vez de un mensaje nuevo por pregunta.
- Los mensajes de texto que el usuario escribe como respuesta (número de documento, «Otro valor» del salario, respuestas libres) se **borran del chat** apenas el bot guarda la respuesta. El aviso «Escribe el valor…» deja de ser un mensaje aparte: se pinta dentro de la misma tarjeta.
- Al contestar la última pregunta, la tarjeta pasa a un **resumen** con cada pregunta y la respuesta dada, y dos botones: **✅ Confirmar** y **✏️ Editar**.
- **Editar** muestra la lista de preguntas para elegir cuál corregir; la elegida se pregunta enseguida en la misma tarjeta y, al contestarla, se vuelve al resumen para confirmar.
- **Confirmar** cierra la tarjeta (queda como una línea breve de «Preguntas guardadas») y el alta sigue con el paso siguiente.
- Se conserva que lo que el usuario respondió manda sobre el banco de preguntas y sobre lo derivado del CV.

## Capabilities

### New Capabilities
- `preguntas-rapidas-asistente`: flujo de las preguntas rápidas del asistente en Telegram: tarjeta única, limpieza del chat, resumen con confirmar/editar.

### Modified Capabilities
<!-- Ninguna: no hay specs principales en openspec/specs/; el cuestionario se define aquí por primera vez como capacidad propia. -->

## Impact

- Código: `buscador_vacantes/asistente/conversacion.py` (`_preguntar_cuestionario`, `_preguntar_faltante`, `_siguiente_cuestionario`, `al_texto`, callbacks `cuest`/`resumen`), `textos.py` (textos del resumen y botones), posible módulo nuevo `preguntas_tarjeta.py` con funciones puras de texto y botones (como `tarjeta.py`).
- Estado: nueva clave en la tabla clave-valor para el estado de la tarjeta de preguntas (sin migración de esquema).
- Pruebas: pruebas nuevas del flujo (tarjeta única, borrado del texto del usuario, resumen, edición).
- Sin dependencias nuevas ni cambios en la extensión ni en la API.
