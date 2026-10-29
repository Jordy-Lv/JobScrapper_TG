## MODIFIED Requirements

### Requirement: Preguntas rápidas dentro de la card
Cuando la postulación necesita un dato del usuario, la card SHALL cambiar a «Pregunta rápida» con la pregunta, el avance si hay más de una y los botones de opciones, o la indicación de escribir la respuesta. Una pregunta sin opciones del portal cuyo enunciado es claramente de sí o no SHALL mostrar los botones «Sí» y «No» y «✍️ Escribir yo», en cualquier plataforma. Una pregunta que ya trae opciones del portal MUST conservar esas opciones, y una pregunta que pide un dato abierto («cuántos», «cuál», «por qué», «describe») MUST seguir pidiendo escribir. Al guardar la respuesta, la card MUST volver al estado anterior y el texto escrito por el usuario SHALL borrarse del chat sin interrumpir el flujo si no se puede. Cuando la pregunta llega a la card porque la IA no respondió tras los reintentos, la card SHALL decirlo en una línea.

#### Scenario: Pregunta con opciones
- **WHEN** hay una pregunta pendiente con opciones
- **THEN** la card muestra las opciones como botones y, al elegir una, pasa a la siguiente pregunta o regresa al progreso

#### Scenario: Pregunta de texto libre
- **WHEN** la pregunta pendiente exige escribir
- **THEN** la card pide la respuesta, y al recibir el texto lo guarda, lo borra del chat y avanza

#### Scenario: Pregunta de sí o no que el portal dio como texto
- **WHEN** la pregunta pendiente es «¿Cuentas con el aval por parte de tu institución educativa para iniciar proceso de prácticas de inmediato?» y el portal la dio como campo de texto
- **THEN** la card muestra los botones «Sí» y «No» y «✍️ Escribir yo»; al tocar «Sí» se guarda «Sí» como respuesta y la card avanza

#### Scenario: Escribir en vez de tocar
- **WHEN** el usuario toca «✍️ Escribir yo» en una pregunta de sí o no y escribe su respuesta
- **THEN** el texto se guarda tal cual, el mensaje escrito se borra del chat y la card avanza

#### Scenario: Pregunta abierta no es de sí o no
- **WHEN** la pregunta pendiente es «¿Por qué te interesa esta vacante?» o «¿Cuántos años de experiencia tienes?»
- **THEN** la card pide escribir la respuesta y no muestra los botones «Sí» y «No»

#### Scenario: La IA no respondió
- **WHEN** las preguntas llegan a la card después de agotar los reintentos por una IA saturada o sin contacto
- **THEN** la card indica que la IA no respondió esta vez y pregunta como siempre

#### Scenario: Texto fuera de turno
- **WHEN** el usuario escribe cuando la card no espera texto
- **THEN** el asistente no cambia la card ni responde con un mensaje nuevo
