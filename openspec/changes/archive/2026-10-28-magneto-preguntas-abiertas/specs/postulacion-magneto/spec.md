## MODIFIED Requirements

### Requirement: Lectura de la encuesta en página
Cuando, tras pulsar «Aplicar», Magneto muestra en la misma página una encuesta (sin formulario HTML ni diálogo), la extensión SHALL leer cada pregunta con su texto y enviarla al servidor por el mismo canal que usan los demás portales. Una pregunta con botones de respuesta SHALL enviarse como pregunta de opciones con el texto de cada botón; una pregunta con un campo de texto abierto SHALL enviarse como pregunta de texto con su límite de caracteres, tomado del atributo `maxlength` o, si no lo tiene, del contador que muestra el portal («0 de 140»). Toda pregunta de la encuesta MUST tratarse como obligatoria, porque el portal no deja enviar sin responderlas. Los botones de «Cancelar» y «Enviar respuestas» MUST NOT contarse como preguntas ni como opciones. Una pregunta sin botones ni campo abierto MUST reportarse como formulario desconocido con la evidencia sin valores.

#### Scenario: Encuesta de dos preguntas Si/No
- **WHEN** la página muestra dos preguntas, cada una con los botones «Si» y «No»
- **THEN** el servidor recibe dos preguntas obligatorias, cada una con las opciones «Si» y «No» y con el texto exacto del título que ve el usuario

#### Scenario: Encuesta con preguntas abiertas
- **WHEN** la encuesta mezcla preguntas de botones con preguntas de texto abierto que muestran el contador «0 de 140» y no tienen `maxlength`
- **THEN** el servidor recibe las preguntas en el orden de la página: las de botones como opciones y las abiertas como texto obligatorio con máximo 140

#### Scenario: Pregunta sin forma de responderla
- **WHEN** un bloque de pregunta no tiene botones de respuesta ni campo abierto
- **THEN** la postulación termina como formulario desconocido nombrando la pregunta, sin pulsar «Enviar respuestas»

#### Scenario: Vacante sin encuesta
- **WHEN** Magneto no muestra preguntas tras pulsar «Aplicar»
- **THEN** la extensión no pide nada al servidor, no falla por la ausencia de formulario y pasa a esperar la confirmación

### Requirement: Respuesta de la encuesta
La extensión SHALL responder cada pregunta de botones pulsando el botón de la opción que eligió el servidor y cada pregunta abierta escribiendo el texto que devolvió el servidor, y MUST comprobar que la opción quedó marcada o el texto quedó escrito. La extensión MUST pulsar «Enviar respuestas» solo cuando el portal lo habilite; si sigue deshabilitado, MUST NOT pulsarlo y reportará el formulario como desconocido. Si el servidor no puede responder una pregunta, el asistente MUST preguntársela al usuario por Telegram y no enviar nada hasta tener la respuesta. El asistente MUST NOT aceptar por su cuenta el tratamiento de datos ni consentimientos del portal o de la empresa: esas preguntas las decide el usuario.

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
