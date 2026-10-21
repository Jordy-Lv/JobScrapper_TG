## MODIFIED Requirements

### Requirement: Confirmación por el modal de resumen
La extensión SHALL dar la postulación por confirmada cuando Magneto muestra el aviso «Se ha enviado tu aplicación» en el modal de resumen de la aplicación, que aparece varios segundos después del envío. La extensión MUST esperar ese aviso el tiempo suficiente antes de declarar la postulación incierta. Si tras enviar la encuesta sigue en pantalla y no aparece el aviso, la extensión MUST reportar que el portal no aceptó el envío y no darla por enviada. Si tras pulsar «Aplicar» no aparece ni la encuesta ni el modal ni un aviso de vacante ya postulada o cerrada, y la vacante sigue mostrando su botón «Aplicar», la extensión MUST reportar que Magneto no procesó «Aplicar» y MUST NOT declarar la postulación incierta, porque no se envió nada.

#### Scenario: El modal tarda en aparecer
- **WHEN** el modal con «Se ha enviado tu aplicación» aparece unos 5 s después de pulsar «Enviar respuestas»
- **THEN** la postulación queda `enviada` con ese texto como confirmación

#### Scenario: La encuesta sigue en pantalla
- **WHEN** pasa el tiempo de espera, no aparece el aviso y las preguntas siguen visibles
- **THEN** el asistente reporta que el portal no aceptó el envío y la postulación no queda como `enviada`

#### Scenario: Vacante sin encuesta
- **WHEN** el clic en «Aplicar» envía la postulación sin preguntas y aparece el modal
- **THEN** la postulación queda `enviada` sin pasar por «Enviar respuestas»

#### Scenario: Aplicar no hace nada
- **WHEN** tras pulsar «Aplicar» pasa el tiempo de espera, la página no muestra encuesta, modal, aviso de ya postulada ni de cerrada, y el botón «Aplicar» sigue en la vacante (por ejemplo, el portal se queda con el indicador de carga en una vacante que el usuario retiró antes)
- **THEN** la postulación termina sin enviarse con el motivo «Magneto no procesó “Aplicar”», con la evidencia sin valores, y no queda como `incierta`

### Requirement: Respuesta de la encuesta
La extensión SHALL responder cada pregunta de botones pulsando el botón de la opción que eligió el servidor y cada pregunta abierta escribiendo el texto que devolvió el servidor, y MUST comprobar que la opción quedó marcada o el texto quedó escrito. La extensión MUST pulsar «Enviar respuestas» solo cuando el portal lo habilite; si sigue deshabilitado, MUST NOT pulsarlo y reportará el formulario como desconocido. Si el servidor no puede responder una pregunta, el asistente MUST preguntársela al usuario por Telegram y no enviar nada hasta tener la respuesta. El asistente MUST NOT aceptar por su cuenta el tratamiento de datos ni consentimientos del portal o de la empresa: esas preguntas las decide el usuario. La extensión MUST reportar al servidor, como paso de la postulación, cada respuesta que quedó escrita o marcada, con el número de pregunta, para que un llenado que se corta muestre hasta dónde llegó. El reporte MUST NOT incluir el texto de la respuesta.

#### Scenario: Todas las preguntas con respuesta
- **WHEN** el servidor devuelve una opción para cada pregunta de botones y un texto para cada pregunta abierta
- **THEN** la extensión pulsa el botón de cada opción, escribe cada texto, comprueba que quedaron y pulsa «Enviar respuestas» ya habilitado

#### Scenario: Pregunta sin respuesta conocida
- **WHEN** el servidor no tiene respuesta para una pregunta obligatoria
- **THEN** la postulación queda esperando al usuario, la pregunta le llega por Telegram y la extensión no pulsa «Enviar respuestas»

#### Scenario: Pregunta que no se pudo marcar
- **WHEN** tras pulsar el botón de una opción esa opción no queda marcada
- **THEN** la extensión no envía la encuesta y reporta el formulario como desconocido con la evidencia sin valores

#### Scenario: Enviar respuestas sigue deshabilitado
- **WHEN** tras llenar la encuesta el portal mantiene «Enviar respuestas» deshabilitado
- **THEN** la extensión no lo pulsa y la postulación termina como formulario desconocido indicando que el portal no dio por respondidas todas las preguntas

#### Scenario: Registro de cada respuesta
- **WHEN** la extensión llena una encuesta de nueve preguntas
- **THEN** el historial de pasos de la postulación muestra un registro por pregunta llenada, de la 1 a la 9, sin el texto de las respuestas, antes de pulsar «Enviar respuestas»

#### Scenario: Llenado que se corta
- **WHEN** el llenado se interrumpe tras la pregunta 4
- **THEN** el historial termina en el registro de la pregunta 4, de modo que se ve dónde quedó

#### Scenario: Llenado que se cuelga
- **WHEN** el llenado de la encuesta no termina en 30 s
- **THEN** la extensión lo da por fallido, la postulación termina sin enviarse con el motivo «el llenado de la encuesta no respondió» y con la evidencia sin valores, y la card ofrece «Reintentar» en vez de esperar minutos
