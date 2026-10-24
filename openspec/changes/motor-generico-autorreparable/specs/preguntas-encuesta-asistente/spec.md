## MODIFIED Requirements

### Requirement: Redactor por formulario
Con IA disponible, el asistente SHALL redactar en **una sola llamada** todas las preguntas de texto del formulario que no se resuelven como dato simple. La llamada MUST incluir el perfil del CV sin datos de contacto, el cuestionario del alta, los datos aprendidos del usuario, la vacante y el idioma del formulario. Cada respuesta SHALL:
- estar en primera persona, con tono natural y profesional;
- estar en el **idioma del formulario** (el que informa la extensión o el de la pregunta), y en español si no se puede saber;
- responder **todo** lo que pide la pregunta;
- tener una longitud proporcional a la pregunta: una o dos frases para un dato, varias para motivación o experiencia;
- no copiar el CV literalmente.

La IA MUST NOT inventar datos que no estén en el perfil, el cuestionario o los datos aprendidos. Los datos aprendidos SHALL prevalecer sobre el CV. Un dato aprendido en un idioma MAY reutilizarse traducido en un formulario de otro idioma, sin cambiar su contenido.

#### Scenario: Pregunta compuesta
- **WHEN** el formulario pregunta «¿Qué programa técnico o tecnológico estás estudiando relacionado con Sistemas o Informática y en qué institución?» y el CV trae el programa y la institución
- **THEN** la respuesta enviada menciona el programa y la institución en una frase redactada, por ejemplo «Estudio Tecnología en Desarrollo de Software en el SENA»

#### Scenario: Pregunta de motivación
- **WHEN** el formulario pregunta «¿Por qué te interesa esta vacante?»
- **THEN** la IA la redacta con el perfil y la vacante sin preguntarle nada al usuario

#### Scenario: Varias preguntas de texto
- **WHEN** el formulario trae cuatro preguntas de texto que requieren redacción
- **THEN** se hace una sola llamada a la IA para las cuatro

#### Scenario: Dato aprendido contra CV
- **WHEN** el CV dice una ciudad y el usuario respondió otra en la card
- **THEN** la redacción usa la que dio el usuario

#### Scenario: Formulario en inglés
- **WHEN** el formulario está en inglés y pregunta «Tell us a bit about your background in Technical Support»
- **THEN** la respuesta se redacta en inglés con los datos del perfil

### Requirement: Datos simples sin redacción
Las preguntas de correo, teléfono, número y fecha, y las de opciones que el banco, los datos aprendidos o el perfil resuelven, SHALL resolverse sin pasar por el redactor. Un campo cuyo `autocomplete` o cuyo nombre identifica un dato del catálogo (por ejemplo `given-name`, `family-name`, `email`, `tel`, `country`, `first_name`, `last_name`, `linkedin`) SHALL resolverse con ese dato antes de consultar el banco o la IA. Una pregunta de texto que el banco clasifica como dato simple, como «Ciudad de residencia», SHALL enviarse con el valor exacto. La opción elegida en una pregunta con opciones MUST enviarse tal cual. El banco SHALL reconocer también las formulaciones en inglés y portugués de las preguntas sembradas.

#### Scenario: Campo de dato simple
- **WHEN** el formulario trae «Aspiración salarial» como campo numérico
- **THEN** se envía el número guardado, sin llamar al redactor

#### Scenario: Pregunta con opciones
- **WHEN** el formulario pregunta «¿Nivel de inglés?» con las opciones Básico, Intermedio y Avanzado
- **THEN** se marca la opción que corresponde al perfil, sin redacción

#### Scenario: Campo por autocomplete
- **WHEN** un campo con la etiqueta «First Name» tiene `autocomplete="given-name"`
- **THEN** se llena con el nombre de pila del usuario sin consultar el banco ni la IA

#### Scenario: Pregunta en portugués
- **WHEN** el formulario pregunta «Pretensão salarial»
- **THEN** el banco la reconoce como salario y se envía el dato guardado
