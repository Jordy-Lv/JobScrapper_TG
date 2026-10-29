## MODIFIED Requirements

### Requirement: Respaldo sin IA
Si no hay clave de IA, o la IA falla al redactar o al clasificar preguntas, el asistente MUST seguir sin bloquearse. Si la falla es temporal (el proveedor saturado o sin contacto), el asistente SHALL reintentar la resolución del formulario con esperas configurables y sin que el navegador se dé por caído, antes de preguntar. Si no hay clave, la clave es inválida o la cuota o el tope se agotaron, MUST NOT reintentar. Cada pregunta de texto que no es dato simple y que sigue sin respuesta SHALL preguntarse en la card como pregunta del formulario, para escribirla, y lo escrito se envía tal cual.

#### Scenario: Sin clave de IA
- **WHEN** el usuario no tiene proveedor de IA y el formulario trae una pregunta de motivación
- **THEN** la card pide escribir la respuesta y se envía tal cual, sin reintentos

#### Scenario: Falla la redacción
- **WHEN** la llamada del redactor falla y los reintentos también
- **THEN** las preguntas de texto pasan a la card para escribirse y la postulación no se pierde

#### Scenario: La IA se recupera
- **WHEN** el proveedor responde saturado en la primera pasada y bien en un reintento
- **THEN** el formulario se resuelve con la IA, el usuario no recibe ninguna pregunta que la IA pudiera responder y la espera no cuenta como navegador caído

#### Scenario: Cuota agotada
- **WHEN** la cuota o el tope diario de la IA del usuario se agotó
- **THEN** no se reintenta y las preguntas pasan a la card como hoy

## ADDED Requirements

### Requirement: Aval de la institución recordado
El catálogo de campos SHALL incluir el aval de la institución educativa para iniciar las prácticas (`aval_institucion`), con preguntas sembradas en el banco para sus formulaciones frecuentes. La primera vez que el usuario lo responde en la card, el asistente SHALL guardarlo en su cuestionario como dato del perfil y MUST usarlo desde entonces en cualquier vacante cuya pregunta el banco o la IA clasifique en ese campo, sin volver a preguntar. El asistente MUST NOT inventar el aval: sin respuesta del usuario, la pregunta se le hace.

#### Scenario: Primera vez
- **WHEN** una vacante pregunta «¿Cuentas con el aval por parte de tu institución educativa…?» y el usuario nunca lo respondió
- **THEN** la card le pregunta con los botones «Sí» y «No» y, al responder, el dato queda guardado en su cuestionario

#### Scenario: Otra vacante con otra redacción
- **WHEN** el usuario ya respondió «Sí» y otra vacante pregunta «¿Tienes carta de tu universidad que autorice tus prácticas?», clasificada en el campo del aval
- **THEN** el formulario recibe «Sí» sin preguntar de nuevo

#### Scenario: Pregunta con opciones del portal
- **WHEN** el campo del aval se pide con las opciones «Sí» y «No» del portal
- **THEN** se elige la opción que corresponde al dato guardado

#### Scenario: Prefiero no decirlo
- **WHEN** el usuario marca el aval como reservado
- **THEN** el dato no se envía como valor y la pregunta obligatoria se le vuelve a pedir para escribirla
