## Purpose

Define cómo el asistente de Telegram hace las preguntas rápidas que piden los formularios de las vacantes y que el CV no responde: en una sola tarjeta, sin llenar el chat y con resumen para confirmar o corregir.

## ADDED Requirements

### Requirement: Tarjeta única de preguntas
El asistente SHALL mostrar todo el bloque de preguntas rápidas en un solo mensaje que se edita en el lugar. La tarjeta MUST indicar el progreso («Faltan N», o «Última» en la final), la pregunta actual y sus botones. El asistente MUST NOT enviar un mensaje nuevo por cada pregunta.

#### Scenario: Avance entre preguntas
- **WHEN** el usuario contesta una pregunta con un botón y quedan más
- **THEN** el mismo mensaje se edita y muestra la siguiente pregunta con el progreso actualizado

#### Scenario: Primera pregunta
- **WHEN** empieza el bloque de preguntas rápidas
- **THEN** el asistente envía un único mensaje con la primera pregunta y su progreso

#### Scenario: Tarjeta borrada
- **WHEN** el mensaje de la tarjeta ya no existe al intentar editarlo
- **THEN** el asistente envía una tarjeta nueva con el estado actual y continúa desde ahí

### Requirement: Limpieza de las respuestas escritas
Cuando el usuario responde una pregunta escribiendo texto, el asistente SHALL borrar ese mensaje del chat apenas guarde la respuesta. El aviso para escribir un valor («Otro valor») MUST mostrarse dentro de la tarjeta y no como un mensaje aparte. Si el mensaje no se puede borrar, el asistente MUST seguir sin interrumpir el flujo.

#### Scenario: Número de documento
- **WHEN** el usuario escribe su número de documento
- **THEN** la respuesta se guarda, el mensaje escrito se borra del chat y la tarjeta muestra la siguiente pregunta

#### Scenario: Otro valor de salario
- **WHEN** el usuario toca «Otro valor» y escribe un número
- **THEN** la tarjeta pidió el valor sin mensajes extra, el texto escrito se borra y la respuesta queda guardada

#### Scenario: Valor de salario inválido
- **WHEN** el usuario escribe un texto que no es un número en el salario
- **THEN** el mensaje escrito se borra y la tarjeta muestra el aviso de formato sin guardar nada

#### Scenario: No se puede borrar
- **WHEN** Telegram rechaza el borrado del mensaje del usuario
- **THEN** la respuesta queda guardada y el flujo continúa sin error visible

### Requirement: Resumen con confirmar o editar
Al contestar todas las preguntas del bloque, la tarjeta SHALL pasar a un resumen con cada pregunta y la respuesta dada (las omitidas como «—») y dos botones: «Confirmar» y «Editar». Mientras el usuario no confirme, las respuestas MUST poder cambiarse.

#### Scenario: Fin del bloque
- **WHEN** el usuario contesta la última pregunta
- **THEN** la tarjeta muestra el resumen con las preguntas y respuestas y los botones Confirmar y Editar

#### Scenario: Confirmar
- **WHEN** el usuario toca «Confirmar»
- **THEN** la tarjeta queda como una línea breve de preguntas guardadas y el alta sigue con el paso siguiente

### Requirement: Edición puntual de una respuesta
Al tocar «Editar», la tarjeta SHALL mostrar la lista de preguntas del bloque para elegir cuál corregir. La pregunta elegida MUST preguntarse enseguida en la misma tarjeta y, al guardar la nueva respuesta, la tarjeta MUST volver al resumen.

#### Scenario: Corregir una respuesta
- **WHEN** el usuario toca «Editar», elige «¿Cuándo puedes empezar?» y toca «En 1 mes»
- **THEN** la respuesta se actualiza y la tarjeta vuelve al resumen con el valor nuevo

#### Scenario: Corregir con texto
- **WHEN** el usuario edita el número de documento y escribe uno nuevo
- **THEN** se guarda el valor, se borra el mensaje escrito y la tarjeta vuelve al resumen

#### Scenario: Volver sin cambiar
- **WHEN** el usuario toca «Editar» y luego regresa sin elegir una pregunta
- **THEN** la tarjeta vuelve al resumen sin cambios

### Requirement: Toques y textos fuera de turno
El asistente SHALL ignorar los toques de botones de preguntas que ya no corresponden al estado de la tarjeta y MUST repintar la tarjeta vigente. Un texto escrito cuando la tarjeta no espera uno MUST borrarse sin guardarse.

#### Scenario: Botón viejo
- **WHEN** el usuario toca un botón de una pregunta que ya contestó y la tarjeta está en otra
- **THEN** no se guarda nada y la tarjeta muestra el estado actual

### Requirement: La respuesta del usuario manda
Lo que el usuario respondió en las preguntas rápidas SHALL prevalecer sobre lo derivado del CV y sobre el banco de preguntas. Las preguntas que el CV ya respondió MUST NOT aparecer en el bloque del alta.

#### Scenario: Pregunta ya respondida por el CV
- **WHEN** el CV ya dio la respuesta a una pregunta
- **THEN** esa pregunta no se hace ni aparece en el resumen del alta

#### Scenario: Corrección del usuario
- **WHEN** el usuario edita una respuesta
- **THEN** el valor nuevo reemplaza al anterior y se usa en adelante en los formularios
