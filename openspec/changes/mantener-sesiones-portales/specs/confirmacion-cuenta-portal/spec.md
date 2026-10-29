## ADDED Requirements

### Requirement: Avisar cuando se pierde la sesión de un portal
Cuando la sesión de un portal pasa de abierta a «sin sesión», el asistente SHALL avisar al usuario una sola vez por Telegram, con el nombre del portal y, si la extensión informó un motivo, una frase que lo explique y qué hacer (por ejemplo, activar «Mantener la sesión» o permitir las cookies del portal en Chrome). Mientras la sesión siga cerrada, el asistente MUST NOT repetir el aviso. El aviso MUST NOT enviarse al reabrir la sesión ni cuando el portal nunca tuvo sesión desde que se vinculó el navegador. Si una postulación está esperando esa sesión, el aviso SHALL ir en el mensaje de espera de esa postulación y no en uno aparte.

#### Scenario: La sesión se cierra
- **WHEN** el latido informa `sin_sesion` en elempleo y el latido anterior lo informaba con sesión abierta
- **THEN** el usuario recibe un aviso de que su sesión de elempleo se cerró

#### Scenario: Sesión cerrada durante varios latidos
- **WHEN** el portal sigue sin sesión en los latidos siguientes
- **THEN** no se envía otro aviso

#### Scenario: Nunca tuvo sesión
- **WHEN** el navegador recién vinculado informa `sin_sesion` en un portal que nunca estuvo con sesión
- **THEN** no se envía el aviso de sesión perdida

#### Scenario: Motivo conocido
- **WHEN** la extensión informa el motivo `borrada_al_cerrar`
- **THEN** el aviso explica que Chrome borra las cookies al cerrar y cómo permitir las de ese portal

#### Scenario: Postulación esperando la sesión
- **WHEN** la sesión se cierra y hay una postulación en cola para ese portal
- **THEN** el aviso va en el mensaje de espera de esa postulación y no se envía un mensaje aparte
