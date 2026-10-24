# Spec Delta

## ADDED Requirements

### Requirement: Lote de cada mensaje publicado
Al confirmarse el envío de un mensaje de ofertas al canal real, el estado MUST guardar su lote: un identificador opaco, las claves de sus vacantes en el orden del mensaje, cuáles son destacadas y la fecha. Los lotes MUST borrarse con la misma retención que las vistas. Los envíos en modo prueba MUST NOT guardar lotes del canal real.

#### Scenario: Envío confirmado
- **WHEN** Telegram confirma un mensaje con 6 vacantes
- **THEN** el estado guarda un lote con esas 6 claves en orden y su identificador va en el botón del mensaje

#### Scenario: Envío rechazado
- **WHEN** Telegram rechaza el mensaje
- **THEN** no se guarda ningún lote para él

### Requirement: Datos de consulta de las vacantes publicadas
Para cada vacante enviada, el estado MUST guardar, además de lo que ya guarda: la fecha de publicación en la fuente, si fue destacada y el área de TI detectada. Así el asistente puede filtrar por esos datos.

#### Scenario: Vacante destacada enviada
- **WHEN** se envía una vacante destacada del área de soporte
- **THEN** su registro en vistas indica que fue destacada, su área «soporte» y su fecha de publicación
