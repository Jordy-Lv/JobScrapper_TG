## MODIFIED Requirements

### Requirement: Lectura de la encuesta en página
Cuando, tras pulsar «Aplicar», Magneto muestra una encuesta de preguntas —ya sea el cuestionario conversacional por turnos en el cajón lateral (`detailChatQuestionnaireChat_container` / `mg_chat_questionnaire_questionnaire`) o la encuesta clásica en la misma página (`job-offer-questionnaire`)—, la extensión SHALL leer cada pregunta con su enunciado exacto y sus opciones o límite de caracteres y enviarlas al servidor por el canal de formularios. En el cuestionario conversacional, la extensión MUST esperar a que termine el indicador de carga de cada turno antes de leerlo, MUST tomar como enunciado únicamente el título de la pregunta sin concatenar la instrucción genérica de ayuda, y MUST marcar como selección múltiple las preguntas de casillas. Toda pregunta de la encuesta MUST tratarse como obligatoria, porque el portal no deja enviar sin responderlas. Los botones de «Cancelar», «Guardar» y «Enviar respuestas» MUST NOT contarse como preguntas ni como opciones. Cuando aparece el modal de confirmación o de cuestionario ya respondido sin que haya encuesta, la espera opcional de preguntas SHALL cortarse de inmediato.

#### Scenario: Encuesta clásica de dos preguntas Si/No
- **WHEN** la página muestra en línea dos preguntas, cada una con los botones «Si» y «No»
- **THEN** el servidor recibe dos preguntas obligatorias, cada una con las opciones «Si» y «No» y con el texto exacto del título que ve el usuario

#### Scenario: Encuesta conversacional por turnos en cajón lateral
- **WHEN** Magneto abre el cajón de chat y muestra secuencialmente cada pregunta tras su animación de carga, con enunciado e instrucción de ayuda separados
- **THEN** la extensión espera cada turno, envía al servidor solo el enunciado limpio en `texto` y la instrucción en `ayuda`, e identifica si la pregunta es de opción única, opción múltiple o texto abierto con su límite de caracteres

#### Scenario: Vacante sin encuesta
- **WHEN** Magneto no muestra preguntas tras pulsar «Aplicar» y abre el modal de confirmación
- **THEN** la extensión corta la espera de preguntas en cuanto aparece el modal, no pide nada al servidor, no falla por la ausencia de formulario y pasa a confirmar el envío

### Requirement: Respuesta de la encuesta
La extensión SHALL responder cada pregunta según su formato —pulsando la opción elegida en selección única, marcando una o varias casillas y pulsando «Guardar» en selección múltiple, o normalizando los caracteres al alfabeto permitido por Magneto, escribiendo el texto y pulsando el botón de envío del turno en preguntas abiertas del chat— comprobando que el portal registró cada respuesta antes de continuar, y MUST pulsar «Enviar respuestas» solo cuando todas las preguntas estén respondidas y el botón quede habilitado. Si el servidor no puede responder una pregunta, el asistente MUST preguntársela al usuario por Telegram y no enviar nada hasta tener la respuesta. El asistente MUST NOT aceptar por su cuenta el tratamiento de datos ni consentimientos del portal o de la empresa: esas preguntas las decide el usuario. Cuando se abre una encuesta sin enviar tras pulsar «Aplicar», el estado de envío previo MUST restablecerse hasta pulsar «Enviar respuestas».

#### Scenario: Todas las preguntas con respuesta en encuesta clásica o conversacional
- **WHEN** el servidor devuelve respuestas válidas para preguntas de opción única, opción múltiple y texto abierto (incluyendo signos tipográficos como `/` o `—`)
- **THEN** la extensión responde cada turno normalizando signos no admitidos por el campo abierto, comprueba que cada respuesta quedó registrada en el portal y pulsa «Enviar respuestas» cuando se habilita

#### Scenario: Pregunta sin respuesta conocida
- **WHEN** el servidor no tiene respuesta para una pregunta obligatoria en cualquier turno de la encuesta
- **THEN** la postulación queda esperando al usuario con `envio_pulsado` en falso, la pregunta le llega por Telegram y la extensión no pulsa «Enviar respuestas»

#### Scenario: Pregunta que no se pudo marcar o registrar
- **WHEN** tras responder una pregunta el portal no marca la opción, borra el texto o no registra el turno como respondido
- **THEN** la extensión no envía la encuesta y reporta el formulario como desconocido conservando en la evidencia sin valores la cabecera y el pie propios del diálogo o formulario

### Requirement: Vacante ya postulada
Antes de pulsar «Aplicar» y también durante la confirmación posterior, la extensión SHALL revisar si la vacante muestra «Ya aplicaste a este empleo» o el aviso de cuestionario ya respondido (`alreadyAnsweredQuestionnaire`) y, en ese caso, MUST terminar la postulación como `ya_postulada` sin volver a enviar respuestas. Si la vacante muestra «Proceso abandonado» en el lugar del botón de postulación, la extensión MUST terminar sin pulsar nada y el asistente SHALL informar en la tarjeta de respaldo que ese proceso había sido abandonado en el portal, sin enviar alerta de fallo al dueño.

#### Scenario: Banner de ya aplicaste o cuestionario ya respondido
- **WHEN** la vacante muestra «Ya aplicaste a este empleo» o el modal de cuestionario ya respondido
- **THEN** la postulación termina como `ya_postulada` sin pulsar «Enviar respuestas»

#### Scenario: Vacante con proceso abandonado
- **WHEN** la vacante muestra «Proceso abandonado» en la etiqueta de estado en lugar del botón «Aplicar»
- **THEN** la extensión termina como `bloqueada` con motivo `proceso_abandonado` sin hacer ningún clic, la tarjeta explica el motivo al usuario y no se envía alerta al dueño
