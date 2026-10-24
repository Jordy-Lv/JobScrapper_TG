## Purpose

Reúne una sola vez los datos y documentos que piden los formularios de postulación además del CV, y permite
resolver un formulario conocido de antemano antes de encolar, para que la postulación no se detenga a la mitad.

## ADDED Requirements

### Requirement: Datos de postulación ampliados
El catálogo de datos SHALL incluir, además de los actuales: nombre de pila, apellido, país de residencia,
enlace de LinkedIn, enlace de GitHub o portafolio, autorización para trabajar (con el país como parámetro),
salario esperado en COP y en USD, promedio académico y fuente de la vacante. La fuente de la vacante MUST
responderse con la plataforma de donde vino la vacante («LinkedIn», «Computrabajo»…) sin preguntarle al
usuario. Nombre de pila y apellido SHALL derivarse del nombre completo cuando el usuario no los dio por
separado. Un dato que el perfil no tiene MUST preguntarse una sola vez en la card y recordarse, como hoy.

#### Scenario: ¿Cómo te enteraste?
- **WHEN** un formulario de una vacante de LinkedIn pregunta «How did you hear about this opportunity?» con la opción «LinkedIn»
- **THEN** se elige «LinkedIn» sin preguntarle al usuario

#### Scenario: Autorización para trabajar
- **WHEN** el formulario pregunta «Are you legally authorized to work in Colombia?» y el usuario nunca lo respondió
- **THEN** la card lo pregunta una vez y la respuesta se reutiliza en las siguientes postulaciones que pregunten por Colombia

#### Scenario: Salario con moneda
- **WHEN** la pregunta pide el salario esperado «Please include currency» y el usuario dio su aspiración en COP
- **THEN** la respuesta lleva el valor y la moneda, por ejemplo «COP 2.500.000»

### Requirement: Documentos extra del usuario
El usuario SHALL poder enviar por Telegram documentos PDF distintos del CV, cada uno con un tipo (certificado de
notas, carta de presentación, portafolio u otro con nombre), y verlos o borrarlos. Los documentos MUST
guardarse cifrados, contar en la retención de datos y borrarse con la cuenta. Un formulario que pide un
archivo SHALL recibir el documento cuyo tipo corresponde a la etiqueta del campo. Si un campo de archivo
**obligatorio** no tiene documento, la card MUST pedirlo con la opción de enviarlo o de dejar esa vacante en
el respaldo. Un campo de archivo opcional sin documento MUST quedar vacío.

#### Scenario: Certificado de notas
- **WHEN** el formulario pide «Please upload a copy of your unofficial university transcripts» como obligatorio y el usuario guardó un certificado de notas
- **THEN** se adjunta ese PDF en ese campo y el CV en el campo del CV

#### Scenario: Documento que no existe
- **WHEN** el campo obligatorio pide el certificado de notas y el usuario no tiene ninguno guardado
- **THEN** la card pide enviarlo; si el usuario elige dejarla, la vacante va al respaldo con el motivo `documento_faltante`

### Requirement: Esquema anticipado
Si el trabajo de una vacante llega con el esquema del formulario leído antes de abrir la página, el servidor
SHALL resolver todas sus preguntas al tocar ⚡, antes de encolar, en una sola llamada al redactor. Lo que falte
MUST preguntarse en la misma card de la postulación antes de que la extensión abra la pestaña. Al abrir la
página, la extensión SHALL emparejar cada pantalla con ese esquema y solo consultar al servidor por campos que
no estaban en él.

#### Scenario: Formulario resuelto de antemano
- **WHEN** el esquema anticipado de una vacante trae 12 preguntas y falta solo el promedio
- **THEN** la card pide el promedio al tocar ⚡, y la extensión abre la vacante ya con las 12 respuestas y no se detiene a preguntar

#### Scenario: Campo nuevo en la página
- **WHEN** la página muestra una pregunta que no estaba en el esquema anticipado
- **THEN** solo esa pregunta se resuelve en el momento, como en un formulario sin esquema
