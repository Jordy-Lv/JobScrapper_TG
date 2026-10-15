## Purpose

Define cómo el asistente de Telegram pregunta, dentro de la card de la postulación, las preguntas del formulario que no puede responder solo, y cómo la IA redacta la respuesta final a partir de lo que el usuario elige o escribe.

## ADDED Requirements

### Requirement: Preguntas con opciones en la card
El asistente SHALL preguntar cada pregunta pendiente en la card de la postulación, y si la pregunta trae opciones MUST mostrar un botón por opción. La opción tocada SHALL guardarse tal cual, sin redacción de la IA.

#### Scenario: Pregunta con opciones
- **WHEN** el formulario pregunta «¿Nivel de inglés?» con las opciones Básico, Intermedio y Avanzado
- **THEN** la card muestra tres botones y, al tocar uno, esa opción exacta queda como respuesta

### Requirement: Sugerencias de respuesta en preguntas abiertas
Para una pregunta abierta, con IA disponible, la card SHALL mostrar de 2 a 4 respuestas cortas sugeridas según el perfil y la vacante, y además los botones «✍️ Escribir yo» y «🤖 Que la IA decida». Las sugerencias MUST generarse una sola vez por pregunta y no regenerarse al repintar la card.

#### Scenario: Pregunta abierta con sugerencias
- **WHEN** la card pregunta «¿Vives actualmente en Bogotá?» y la IA sugiere «Sí» y «No»
- **THEN** la card muestra los botones «Sí», «No», «✍️ Escribir yo» y «🤖 Que la IA decida»

#### Scenario: Repintar la card
- **WHEN** la card se repinta mientras la misma pregunta sigue pendiente
- **THEN** muestra las mismas sugerencias sin llamar de nuevo a la IA

### Requirement: Redacción de la respuesta final por la IA
Cuando el usuario toca una sugerencia o escribe su respuesta en una pregunta abierta, el asistente SHALL usar ese texto como semilla y pedirle a la IA que lo redacte de forma completa y profesional en primera persona, con el perfil y la vacante, sin contradecir ni inventar datos distintos a la semilla. La redacción SHALL ser la respuesta final guardada y enviada al formulario. Con «🤖 Que la IA decida» la IA MUST redactar sin semilla usando solo el perfil.

#### Scenario: Semilla corta
- **WHEN** el usuario toca la sugerencia «No» en «¿Manejas Power BI?»
- **THEN** la respuesta guardada es una frase redactada por la IA que mantiene el «no» (por ejemplo, que no lo maneja aún pero está dispuesto a aprenderlo)

#### Scenario: El usuario escribe
- **WHEN** el usuario toca «✍️ Escribir yo» y escribe «5 años en datos»
- **THEN** el mensaje escrito se borra del chat y la respuesta guardada es la redacción de la IA basada en ese texto

#### Scenario: Que la IA decida
- **WHEN** el usuario toca «🤖 Que la IA decida»
- **THEN** la IA redacta la respuesta con el perfil y la vacante, y se guarda sin pedir más

#### Scenario: Datos insuficientes
- **WHEN** la IA no tiene datos suficientes para responder sin semilla
- **THEN** la card sigue preguntando la misma pregunta con «✍️ Escribir yo» y no guarda nada

### Requirement: Respaldo sin IA
Si no hay clave de IA, o la IA falla al sugerir o al redactar, el asistente MUST seguir el flujo sin bloquearse: sin sugerencias la card pide escribir, y si falla la redacción se guarda la semilla tal cual la dio el usuario.

#### Scenario: Sin clave de IA
- **WHEN** el usuario no tiene proveedor de IA configurado y la card hace una pregunta abierta
- **THEN** la card pide escribir la respuesta y, al escribirla, se guarda tal cual

#### Scenario: Falla la redacción
- **WHEN** el usuario toca una sugerencia y la IA falla al redactar
- **THEN** se guarda el texto de la sugerencia y la postulación continúa

### Requirement: Origen visible en el resumen
El resumen «Tus respuestas» SHALL marcar con 🤖 las respuestas redactadas por la IA, incluidas las que partieron de una semilla del usuario.

#### Scenario: Respuesta redactada
- **WHEN** una respuesta se redactó a partir de una sugerencia tocada
- **THEN** el resumen la muestra con 🤖 y la leyenda «redactada con IA»
