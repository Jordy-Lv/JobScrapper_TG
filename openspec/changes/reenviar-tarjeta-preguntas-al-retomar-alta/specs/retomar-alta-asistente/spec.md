## ADDED Requirements

### Requirement: Retomar el cuestionario por /start muestra un mensaje nuevo
Cuando un usuario con el alta a medias en el cuestionario (paso `faltantes:N` o `cuestionario:N`) envía `/start`, con o sin vacante, el asistente MUST enviar un mensaje nuevo con un aviso de que tiene el registro a medias, seguido de la tarjeta de preguntas como mensaje nuevo al final del chat. El asistente MUST NOT limitarse a editar la tarjeta antigua.

#### Scenario: /start con la tarjeta antigua más arriba en el chat
- **WHEN** el usuario con el alta en `faltantes:0` y una tarjeta de preguntas ya enviada envía `/start v_<id>`
- **THEN** recibe un aviso de registro a medias y una tarjeta de preguntas nueva al final del chat
- **AND** la tarjeta guardada pasa a ser la nueva, de modo que los botones siguientes editan esa

#### Scenario: la tarjeta antigua se retira
- **WHEN** se envía la tarjeta nueva
- **THEN** el asistente intenta borrar la tarjeta antigua
- **AND** si el borrado falla (mensaje vencido o ya borrado), el flujo continúa sin error

#### Scenario: /start sin vacante
- **WHEN** el usuario con el alta a medias envía `/start` sin carga
- **THEN** recibe el aviso de registro a medias y la tarjeta nueva, sin mención de vacante

### Requirement: El aviso confirma que la vacante quedó guardada
Si el `/start` traía una vacante, el aviso MUST decir que la vacante quedó guardada y se abrirá al terminar el registro. La vacante MUST seguir guardada como pendiente del usuario.

#### Scenario: /start con vacante
- **WHEN** el usuario con el alta a medias envía `/start v_<id>`
- **THEN** el aviso menciona que la vacante queda guardada
- **AND** `vacante_pendiente` del usuario vale `<id>`

### Requirement: Las interacciones dentro de la tarjeta no reenvían
Responder, omitir o editar una pregunta desde los botones de la tarjeta MUST seguir editando esa tarjeta en su sitio, sin mensajes nuevos.

#### Scenario: responder una pregunta
- **WHEN** el usuario toca una opción de la tarjeta de preguntas
- **THEN** la tarjeta se edita en el mismo mensaje con la siguiente pregunta
