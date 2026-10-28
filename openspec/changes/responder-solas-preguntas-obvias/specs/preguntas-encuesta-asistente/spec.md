## ADDED Requirements

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

## MODIFIED Requirements

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
