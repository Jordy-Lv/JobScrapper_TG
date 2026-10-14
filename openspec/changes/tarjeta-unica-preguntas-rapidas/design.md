## Context

El cuestionario vive en `textos.CUESTIONARIO` (16 ítems). En el alta, tras el resumen del CV, se pregunta solo lo que el CV no respondió (`_faltantes`, paso `faltantes:N`); `/cuestionario` recorre todos. Cada pregunta se envía con `_enviar` (mensaje nuevo) y la respuesta de texto llega a `al_texto` sin borrarse. «Otro valor» envía un mensaje extra. Ya existe un patrón de mensaje único que se edita en el lugar: la tarjeta de conexión (`tarjeta.py` + `_actualizar_tarjeta`/`_pintar_tarjeta`, estado en `kv` por usuario, con reenvío si el mensaje fue borrado). `Salida` ya expone `editar` y `borrar`.

## Goals / Non-Goals

**Goals:**
- Un solo mensaje para todo el bloque de preguntas, también el resumen y la edición.
- Chat limpio: la respuesta escrita se borra al guardarse; sin mensajes auxiliares.
- Resumen con Confirmar/Editar y edición puntual de una pregunta.

**Non-Goals:**
- No cambia el banco de preguntas, `CUESTIONARIO`, ni la derivación desde el CV.
- No toca las preguntas de los formularios de postulación (`pendiente`, `pegar`, `editar`).
- No cambia la extensión ni la API.

## Decisions

1. **Tarjeta propia, mismo patrón que la de conexión.** Estado en `kv` (`preguntas:{usuario.id}`): `mensaje_id`, `fase` (`preguntando` | `otro` | `resumen` | `lista`), `indices` (preguntas del bloque), `actual`, `editando` (bool). Texto y botones como funciones puras en un módulo nuevo `preguntas_tarjeta.py`; la conversación solo guarda estado y edita. *Alternativa*: reutilizar `Tarjeta` de conexión; se descarta porque mezcla dos ciclos de vida (la de conexión llega hasta la postulación y se pinta después).
2. **Edición en el lugar con reenvío de respaldo.** `editar`; si falla (mensaje borrado por el usuario o expirado) se envía una tarjeta nueva y se guarda el nuevo `mensaje_id`. Si el texto no cambió, Telegram rechaza la edición: se trata como éxito.
3. **Borrado del texto del usuario tras guardar.** `al_texto` ya recibe `mensaje_id`; tras `_guardar_respuesta_cuestionario` se borra con `Salida.borrar` en modo «mejor esfuerzo» (como ya se hace con la clave): un fallo se registra y no interrumpe. Telegram solo permite borrar mensajes de usuarios en privado dentro de 48 h; es el caso normal aquí.
4. **«Otro valor» sin mensaje extra.** El toque cambia la fase a `otro` y la tarjeta pasa a mostrar «Escribe el valor…» con un botón «↩️ Volver» a las opciones. Un valor no numérico en la pregunta de salario se rechaza con el aviso dentro de la tarjeta (no como mensaje nuevo) y el texto escrito también se borra.
5. **Resumen y edición en la misma tarjeta.** Al terminar `indices`, `fase = resumen`: lista «pregunta → respuesta» (las omitidas como «—») y botones Confirmar/Editar. Editar → `fase = lista` con un botón por pregunta; elegir una → `editando = True`, se pinta esa pregunta con sus botones; al guardar, vuelve a `resumen`. Confirmar → la tarjeta queda como línea breve y se ejecuta el paso siguiente del alta (`navegador`). El resumen se pinta editando la misma tarjeta (no un mensaje nuevo) para mantener el chat limpio.
6. **Callbacks nuevos bajo el prefijo `cuest`**: `cuest ok`, `cuest editar`, `cuest campo <i>`, `cuest volver`. Los `cuest <i> <n>` actuales se conservan. Caben en el límite de 64 bytes de Telegram.
7. **Alcance del bloque.** `indices` = las preguntas que se hacen en el paso (faltantes en el alta; todas en `/cuestionario`). El resumen lista solo las del bloque, no las que el CV ya respondió. Fuera del alta, Confirmar solo cierra la tarjeta.
8. **Reanudación.** Si el usuario vuelve a escribir `/start` o el servicio se reinicia a medias, `_continuar_alta` repinta la tarjeta según la `fase` guardada en vez de reiniciar el bloque. Si no hay estado, se calcula con `_faltantes`.

## Risks / Trade-offs

- [El usuario borra la tarjeta o pasan más de 48 h] → reenvío de una tarjeta nueva con el estado guardado.
- [El texto del usuario no se puede borrar (permisos, antigüedad)] → mejor esfuerzo; la respuesta ya está guardada y la tarjeta sigue funcionando.
- [Toques antiguos sobre una tarjeta vieja] → cada callback valida `fase` e índice contra el estado; si no corresponde, se ignora y se repinta la tarjeta actual.
- [Texto en la fase equivocada] → solo se acepta texto cuando la fase espera uno (documento, «Otro valor»); en otra fase se borra y se ignora sin responder.
- [Tarjeta larga] → 16 preguntas caben en el límite de 4096 caracteres de Telegram con respuestas cortas; el resumen recorta respuestas largas.
