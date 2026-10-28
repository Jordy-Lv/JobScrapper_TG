# preguntas-encuesta-asistente Specification

## Purpose
Definir cómo el asistente redacta las respuestas de texto de los formularios de postulación con el CV, los datos del usuario y la vacante; cómo pide en la card de la postulación solo los datos que faltan; y cómo el usuario puede revisar lo redactado antes del envío.

## Requirements

### Requirement: Redactor por formulario
Con IA disponible, el asistente SHALL redactar en **una sola llamada** todas las preguntas de texto del formulario que no se resuelven como dato simple. La llamada MUST incluir el perfil del CV sin datos de contacto, el cuestionario del alta, los datos aprendidos del usuario y la vacante. Cada respuesta SHALL:
- estar en primera persona, en español y con tono natural y profesional;
- responder **todo** lo que pide la pregunta;
- tener una longitud proporcional a la pregunta: una o dos frases para un dato, varias para motivación o experiencia;
- no copiar el CV literalmente.

La IA MUST NOT inventar datos que no estén en el perfil, el cuestionario o los datos aprendidos. Los datos aprendidos SHALL prevalecer sobre el CV.

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

### Requirement: Datos simples sin redacción
Las preguntas de correo, teléfono, número y fecha, y las de opciones que el banco, los datos aprendidos o el perfil resuelven, SHALL resolverse sin pasar por el redactor. Una pregunta de texto que el banco clasifica como dato simple, como «Ciudad de residencia», SHALL enviarse con el valor exacto. La opción elegida en una pregunta con opciones MUST enviarse tal cual.

#### Scenario: Campo de dato simple
- **WHEN** el formulario trae «Aspiración salarial» como campo numérico
- **THEN** se envía el número guardado, sin llamar al redactor

#### Scenario: Pregunta con opciones
- **WHEN** el formulario pregunta «¿Nivel de inglés?» con las opciones Básico, Intermedio y Avanzado
- **THEN** se marca la opción que corresponde al perfil, sin redacción

### Requirement: Opciones elegidas en la misma llamada
En cualquier portal, una pregunta con opciones que no se resuelve con los datos aprendidos, el banco, el perfil ni la confirmación de interés SHALL ir a la misma llamada del redactor, que MUST elegir una de las opciones del portal sin redactar texto. Una opción fuera de rango o ausente MUST llevar la pregunta a la card. Las autorizaciones y aceptaciones MUST NOT pasar por la IA.

#### Scenario: Encuesta de Magneto
- **WHEN** la encuesta de Magneto pregunta «¿Prefieres trabajo en equipo?» con «Si» y «No», y no hay dato guardado
- **THEN** la IA elige la opción en la misma llamada que redacta las preguntas abiertas y la card no la pregunta

#### Scenario: Opción inválida
- **WHEN** la IA devuelve una opción que no existe
- **THEN** la pregunta se pregunta en la card con sus opciones

#### Scenario: Tratamiento de datos
- **WHEN** la encuesta pide autorizar el tratamiento de datos y el usuario no lo ha decidido
- **THEN** se pregunta en la card y no se le envía a la IA

### Requirement: Límite de caracteres del campo
Si la extensión informa el máximo de caracteres de un campo, la redacción MUST respetarlo. El asistente SHALL recortar en el último límite de frase cualquier respuesta que aun así lo supere.

#### Scenario: Campo con límite
- **WHEN** un campo de texto tiene un máximo de 150 caracteres
- **THEN** la respuesta enviada tiene 150 caracteres o menos y termina en una frase completa

### Requirement: Datos faltantes en la card
Cuando para responder una pregunta falta un dato que solo el usuario conoce, el redactor SHALL devolverlo como una pregunta corta de dato, con 2 a 4 sugerencias cortas generadas en la misma llamada. La card de la postulación SHALL preguntar **ese dato**, no la pregunta original del portal, con un botón por sugerencia y los botones «✍️ Escribir yo» y «Prefiero no decirlo». Con todos los datos respondidos, la postulación SHALL volver a la cola, y en la siguiente pasada el redactor MUST escribir la respuesta completa con esos datos.

#### Scenario: Falta la institución
- **WHEN** la pregunta pide programa e institución y el CV solo trae el programa
- **THEN** la card pregunta «¿En qué institución estudias?» con sugerencias y «✍️ Escribir yo»; al responder «SENA», el formulario recibe una frase con el programa y el SENA

#### Scenario: Sugerencias sin llamada extra
- **WHEN** la card muestra o repinta una pregunta de dato
- **THEN** usa las sugerencias que vinieron con la redacción, sin llamar de nuevo a la IA

#### Scenario: El usuario escribe
- **WHEN** el usuario toca «✍️ Escribir yo» y escribe el dato
- **THEN** el mensaje escrito se borra del chat y el dato se guarda

#### Scenario: Prefiero no decirlo
- **WHEN** el usuario toca «Prefiero no decirlo»
- **THEN** el dato queda marcado como reservado, y en la siguiente pasada la IA redacta la respuesta sin él; si la pregunta es obligatoria y no tiene sentido sin el dato, la card la vuelve a preguntar como pregunta del formulario para escribirla

### Requirement: Datos aprendidos reutilizables
Lo que el usuario responde a una pregunta de dato SHALL guardarse como dato corto, con la pregunta corta y su respuesta, y no como la redacción final. Los datos aprendidos MUST entrar en las redacciones de cualquier vacante posterior, y una pregunta de dato ya respondida MUST NOT volver a preguntarse.

#### Scenario: Otra vacante
- **WHEN** el usuario ya dijo que estudia en el SENA y otra vacante pregunta por su institución
- **THEN** la respuesta se redacta con el SENA sin preguntar de nuevo

### Requirement: Banco compartido sin preguntas compuestas
Al clasificar una pregunta nueva, la IA SHALL indicar si pide un dato simple del catálogo o una redacción. El banco compartido SHALL guardar el campo solo en los datos simples. Las preguntas compuestas o de redacción MUST guardarse como `redactar`, sin datos personales, para ir directo al redactor sin volver a clasificarse. Al aplicar la migración, el asistente SHALL borrar las entradas del banco creadas por la IA y conservar las sembradas.

#### Scenario: Pregunta compuesta en el banco
- **WHEN** se clasifica por primera vez una pregunta que pide programa e institución
- **THEN** el banco la guarda como `redactar` y no como `programa`

#### Scenario: Limpieza al migrar
- **WHEN** el asistente arranca con la migración nueva
- **THEN** las entradas del banco con origen `ia` se borran y las de origen `semilla` siguen

### Requirement: Reutilizar redacciones de la misma postulación
Las respuestas redactadas para una postulación SHALL guardarse por pregunta. Si el mismo formulario se vuelve a resolver, por ejemplo tras responder datos faltantes, el asistente MUST reutilizar las redacciones que no dependían de los datos nuevos y redactar solo las que faltaban.

#### Scenario: Segunda pasada
- **WHEN** de cuatro preguntas redactadas una quedó esperando un dato y el usuario lo responde
- **THEN** en la segunda pasada se redacta solo esa pregunta y las otras tres se envían igual

### Requirement: Revisión antes de enviar
Cada portal SHALL tener la preferencia «Revisar respuestas antes de enviar», apagada por defecto y editable en la vista del portal en el popup de la extensión. Si está encendida y el formulario tiene al menos una respuesta redactada por la IA, la postulación MUST esperar al usuario antes del envío. La card SHALL mostrar las respuestas redactadas con «✅ Enviar» y «✏️ Corregir». Al corregir, el usuario elige la respuesta y escribe el texto nuevo, que reemplaza la redacción tal cual. Lo aprobado MUST enviarse sin volver a llamar a la IA.

#### Scenario: Revisión encendida
- **WHEN** el usuario encendió la revisión en Computrabajo y el formulario trae respuestas redactadas
- **THEN** la card muestra las respuestas con «✅ Enviar» y «✏️ Corregir», y no se envía nada hasta que el usuario toca «✅ Enviar»

#### Scenario: Revisión apagada
- **WHEN** la revisión está apagada, como viene por defecto
- **THEN** la postulación se envía sola, como hoy

#### Scenario: Corregir una respuesta
- **WHEN** el usuario toca «✏️ Corregir», elige una respuesta y escribe otra
- **THEN** la card vuelve a la revisión con el texto nuevo, y al enviar se usa ese texto con origen del usuario

#### Scenario: Formulario sin redacciones
- **WHEN** la revisión está encendida pero todas las respuestas son datos simples u opciones
- **THEN** la postulación se envía sin esperar

### Requirement: Respaldo sin IA
Si no hay clave de IA, o la IA falla al redactar, el asistente MUST seguir sin bloquearse. Cada pregunta de texto que no es dato simple SHALL preguntarse en la card como pregunta del formulario, para escribirla, y lo escrito se envía tal cual, como hoy.

#### Scenario: Sin clave de IA
- **WHEN** el usuario no tiene proveedor de IA y el formulario trae una pregunta de motivación
- **THEN** la card pide escribir la respuesta y se envía tal cual

#### Scenario: Falla la redacción
- **WHEN** la llamada del redactor falla
- **THEN** las preguntas de texto pasan a la card para escribirse y la postulación no se pierde

### Requirement: Origen visible en el resumen
El resumen «Tus respuestas» SHALL marcar con 🤖 las respuestas redactadas por la IA, incluidas las que usan datos que dio el usuario, y con 💬 las que el usuario escribió o corrigió tal cual.

#### Scenario: Redactada con un dato del usuario
- **WHEN** una respuesta se redactó con la institución que el usuario dio en la card
- **THEN** el resumen la muestra con 🤖 y la leyenda «redactada con IA»

### Requirement: Confirmación de interés sin IA
Una pregunta con opciones que pide confirmar el interés o la participación del usuario en el proceso, la vacante o la postulación a la que ya se está postulando SHALL responderse sola con la opción afirmativa («Si», «Sí», «Yes»), sin llamar a la IA y sin importar el nivel de IA ni si el usuario tiene clave. Solo aplica cuando la pregunta combina una fórmula de confirmación o interés con una referencia al proceso, la vacante o la postulación, y las opciones traen una afirmativa y una negativa claras. Lo que el usuario respondió o aprendió MUST prevalecer sobre esta regla, y una pregunta que pida autorizar o aceptar algo (tratamiento de datos, términos, consentimiento) MUST NOT responderse con ella. La respuesta SHALL quedar con origen de perfil.

#### Scenario: Pregunta de ánimo en Magneto
- **WHEN** la encuesta de Magneto pregunta «¿Te animas a dar el siguiente paso en tu camino laboral y participar en este proceso que podría abrirte nuevas oportunidades?» con «Si» y «No»
- **THEN** se marca «Si» sin pasar por la card ni por la IA

#### Scenario: Usuario sin IA
- **WHEN** el usuario no tiene proveedor de IA y la encuesta pregunta «¿Confirmas tu participación en el proceso?»
- **THEN** se marca «Si» y la card no pregunta nada

#### Scenario: El usuario ya respondió distinto
- **WHEN** el usuario respondió «No» a esa misma pregunta en una postulación anterior
- **THEN** se usa su respuesta y no la regla

#### Scenario: Pregunta de autorización
- **WHEN** la pregunta pide «¿Autorizas el tratamiento de tus datos personales para participar en este proceso?»
- **THEN** no se responde sola y se pregunta en la card

#### Scenario: Pregunta que no es de confirmación
- **WHEN** la pregunta es «¿Tienes experiencia previa en soporte técnico?» con «Si» y «No»
- **THEN** la regla no aplica y sigue el camino de siempre
