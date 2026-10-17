## ADDED Requirements

### Requirement: Aviso de entrada y salida del grupo
El bot asistente SHALL procesar los avisos `chat_member` del grupo configurado (`asistente.grupo.chat_id`, o el del buscador si está vacío):
- **Salida de un usuario del bot**: lo suspende en el acto con el motivo «salió del grupo» y cancela sus pendientes, igual que la comprobación periódica.
- **Regreso de un usuario suspendido por ese motivo**: lo reactiva.
- **Entrada o salida de cualquiera**: registra un evento de entrada o salida con su hora y si la persona es usuario del bot.

Ese evento MUST NOT guardar id de Telegram, nombre ni usuario de quien no es usuario del bot. Los avisos de otros chats se ignoran.

#### Scenario: Usuario del bot sale del grupo
- **WHEN** llega un `chat_member` con estado `left` de un usuario activo del bot
- **THEN** queda suspendido con el motivo «salió del grupo», sus pendientes se cancelan y se registra una salida

#### Scenario: Vuelve al grupo
- **WHEN** ese usuario vuelve al grupo
- **THEN** recupera su estado anterior y se registra una entrada

#### Scenario: Entra alguien que no usa el bot
- **WHEN** entra al grupo una persona que nunca escribió al bot
- **THEN** se registra solo una entrada con su hora, sin ningún dato de la persona
