## MODIFIED Requirements

### Requirement: Confirmación, vistas y seguimiento en la card
Al confirmarse la postulación, la card SHALL mostrar el título, la empresa y, en un `<blockquote>`, el portal, la fecha, si hubo encuesta y qué hoja de vida recibió el portal. Debajo MUST mostrar el estado del proceso de selección y hasta tres eventos recientes con su fecha y su origen (✍️ usuario, 🌐 portal, 📧 correo, 📌 vacante, ⏱ reloj) y, si hay una entrevista próxima, su fecha y hora. «Respuestas» y «De qué trata» MUST abrirse como vistas de la misma card con un botón «Volver», y la oferta como enlace. La fila de seguimiento SHALL tener «Me contactaron», «Entrevista», «Me descartaron» y «Más». El avance que corresponde al estado actual queda marcado con ✓ y puede cambiarse, y el estado se refleja en `/historial` y `/procesos`. Los eventos que llegan después de la confirmación, de cualquier origen, MUST editar la misma card, y si la card ya no se puede editar se envía una nueva con el estado actual. La hoja de vida adjunta sigue enviándose como documento aparte.

#### Scenario: Ver respuestas
- **WHEN** el usuario toca «Respuestas» en una card confirmada
- **THEN** la card muestra cada pregunta con su respuesta y su origen, y «Volver» regresa a la confirmación

#### Scenario: Vista larga
- **WHEN** el contenido de una vista excede el límite de Telegram
- **THEN** la vista se recorta con «…» o se acorta sin enviar mensajes nuevos

#### Scenario: Marcar seguimiento
- **WHEN** el usuario toca «Me contactaron»
- **THEN** se guarda un evento `contacto` con origen usuario, la card marca «Me contactaron» con ✓, muestra el estado `contacto` en la línea de tiempo y los demás botones siguen disponibles para corregir

#### Scenario: Evento posterior de otra fuente
- **WHEN** llega un evento `cv_visto` de origen portal para una postulación confirmada
- **THEN** la card se edita en su lugar con el estado y el evento nuevos, sin sonido

#### Scenario: Botones de tarjetas anteriores
- **WHEN** el usuario toca «Entrevista» o «Rechazada» en una card enviada antes de este cambio
- **THEN** se registra el evento `entrevista` (sin fecha) o `descartado` y la card se repinta con los botones nuevos
