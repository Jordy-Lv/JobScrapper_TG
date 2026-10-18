# postulacion-magneto Specification

## Purpose
Define cómo el asistente postula en Magneto con la extensión: responde la encuesta que el portal muestra en la misma página, reconoce cuándo el portal aceptó la postulación y deja las respuestas disponibles para la tarjeta de Telegram, igual que en Computrabajo.

## Requirements

### Requirement: Lectura de la encuesta en página
Cuando, tras pulsar «Aplicar», Magneto muestra en la misma página una encuesta de preguntas con botones de respuesta (sin formulario HTML ni diálogo), la extensión SHALL leer cada pregunta con su texto y sus opciones y enviarlas al servidor por el mismo canal que usan los demás portales. Toda pregunta de la encuesta MUST tratarse como obligatoria, porque el portal no deja enviar sin responderlas. Los botones de «Cancelar» y «Enviar respuestas» MUST NOT contarse como preguntas ni como opciones.

#### Scenario: Encuesta de dos preguntas Si/No
- **WHEN** la página muestra dos preguntas, cada una con los botones «Si» y «No»
- **THEN** el servidor recibe dos preguntas obligatorias, cada una con las opciones «Si» y «No» y con el texto exacto del título que ve el usuario

#### Scenario: Vacante sin encuesta
- **WHEN** Magneto no muestra preguntas tras pulsar «Aplicar»
- **THEN** la extensión no pide nada al servidor, no falla por la ausencia de formulario y pasa a esperar la confirmación

### Requirement: Respuesta de la encuesta
La extensión SHALL responder cada pregunta pulsando el botón de la opción que eligió el servidor y MUST pulsar «Enviar respuestas» solo cuando todas las preguntas estén respondidas. Si el servidor no puede responder una pregunta, el asistente MUST preguntársela al usuario por Telegram y no enviar nada hasta tener la respuesta. El asistente MUST NOT aceptar por su cuenta el tratamiento de datos ni consentimientos del portal o de la empresa: esas preguntas las decide el usuario.

#### Scenario: Todas las preguntas con respuesta
- **WHEN** el servidor devuelve una opción para cada pregunta
- **THEN** la extensión pulsa el botón de cada opción, comprueba que quedaron marcadas y pulsa «Enviar respuestas»

#### Scenario: Pregunta sin respuesta conocida
- **WHEN** el servidor no tiene respuesta para una pregunta obligatoria
- **THEN** la postulación queda esperando al usuario, la pregunta le llega por Telegram y la extensión no pulsa «Enviar respuestas»

#### Scenario: Pregunta que no se pudo marcar
- **WHEN** tras pulsar el botón de una opción esa opción no queda marcada
- **THEN** la extensión no envía la encuesta y reporta el formulario como desconocido con la evidencia sin valores

### Requirement: Confirmación por el modal de resumen
La extensión SHALL dar la postulación por confirmada cuando Magneto muestra el aviso «Se ha enviado tu aplicación» en el modal de resumen de la aplicación, que aparece varios segundos después del envío. La extensión MUST esperar ese aviso el tiempo suficiente antes de declarar la postulación incierta. Si tras enviar la encuesta sigue en pantalla y no aparece el aviso, la extensión MUST reportar que el portal no aceptó el envío y no darla por enviada.

#### Scenario: El modal tarda en aparecer
- **WHEN** el modal con «Se ha enviado tu aplicación» aparece unos 5 s después de pulsar «Enviar respuestas»
- **THEN** la postulación queda `enviada` con ese texto como confirmación

#### Scenario: La encuesta sigue en pantalla
- **WHEN** pasa el tiempo de espera, no aparece el aviso y las preguntas siguen visibles
- **THEN** el asistente reporta que el portal no aceptó el envío y la postulación no queda como `enviada`

#### Scenario: Vacante sin encuesta
- **WHEN** el clic en «Aplicar» envía la postulación sin preguntas y aparece el modal
- **THEN** la postulación queda `enviada` sin pasar por «Enviar respuestas»

### Requirement: Vacante ya postulada
Antes de pulsar «Aplicar», la extensión SHALL revisar si la vacante muestra «Ya aplicaste a este empleo» y, en ese caso, MUST terminar la postulación como ya postulada sin pulsar nada ni enviar preguntas.

#### Scenario: Banner de ya aplicaste
- **WHEN** la vacante muestra «Ya aplicaste a este empleo»
- **THEN** la postulación termina como `ya_postulada` y no se hace ningún clic de envío

### Requirement: Respuestas de la encuesta en Telegram
Las respuestas que la extensión envió en la encuesta de Magneto SHALL guardarse con su pregunta, su texto y su origen, y la tarjeta de la postulación confirmada MUST mostrarlas en «Respuestas» y contar la encuesta en su resumen («Encuesta de N»), igual que para Computrabajo. Una postulación de Magneto sin encuesta MUST mostrarse como «Sin encuesta».

#### Scenario: Postulación confirmada con encuesta
- **WHEN** una postulación de Magneto con dos preguntas queda `enviada`
- **THEN** la tarjeta dice «Encuesta de 2» y el botón «Respuestas» muestra cada pregunta con la respuesta enviada y su origen

#### Scenario: Postulación confirmada sin encuesta
- **WHEN** una postulación de Magneto sin preguntas queda `enviada`
- **THEN** la tarjeta dice «Sin encuesta» y no ofrece «Respuestas»

### Requirement: Verificación de la postulación contra el portal
La configuración de Magneto SHALL marcar `verificado.postulacion` solo después de una postulación real que haya terminado `enviada` y aparezca en «Procesos activos» de `https://web.magneto365.com/profile/processes`.

#### Scenario: Prueba real aprobada
- **WHEN** una postulación real termina `enviada` y la vacante aparece en «Procesos activos»
- **THEN** `verificado.postulacion` pasa a verdadero en la nueva versión de los selectores
