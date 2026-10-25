## Purpose

Define cuándo el asistente de Telegram pide al usuario confirmar la cuenta que tiene abierta en un portal, cuándo vuelve a pedirlo y cuándo retira ese mensaje, para que una cuenta sin confirmar no deje al usuario sin saber por qué sus postulaciones esperan.

## ADDED Requirements

### Requirement: Volver a pedir la confirmación al reabrir la sesión
Cuando la sesión de un portal pasa de «sin sesión» a abierta y la cuenta que tiene abierta sigue por confirmar o es distinta de la registrada, el asistente SHALL volver a mostrarle al usuario la confirmación con sus botones, aunque ya la hubiera recibido antes. La confirmación MUST ir en el mensaje de conexión que el usuario ya tenga, editándolo; solo si ese mensaje no existe o no se puede editar, el asistente SHALL enviar uno nuevo. Mientras la sesión siga abierta y la cuenta no cambie, el asistente MUST NOT repetir el aviso.

#### Scenario: La sesión se cierra y se vuelve a abrir con la cuenta sin confirmar
- **WHEN** la cuenta de un portal quedó por confirmar y el usuario cierra y vuelve a abrir su sesión en ese portal
- **THEN** el usuario recibe de nuevo «¿Es tu cuenta?» con los botones «Confirmar» y «Cancelar» para ese portal

#### Scenario: Ya hay un mensaje de conexión
- **WHEN** vuelve a pedirse la confirmación y el usuario aún tiene su mensaje de conexión en el chat
- **THEN** ese mismo mensaje se edita con la confirmación y no se envía otro

#### Scenario: El mensaje de conexión ya no existe
- **WHEN** vuelve a pedirse la confirmación y el mensaje de conexión fue borrado o no se puede editar
- **THEN** se envía un mensaje de conexión nuevo con la confirmación

#### Scenario: Sesión abierta sin cambios
- **WHEN** el navegador reporta la misma sesión abierta y la misma cuenta por confirmar en latidos seguidos
- **THEN** no se envía ni se edita ningún mensaje

#### Scenario: Cuenta distinta al reabrir la sesión
- **WHEN** el usuario reabre la sesión de un portal con una cuenta distinta de la registrada
- **THEN** el asistente le avisa de nuevo que no postulará con ella y le ofrece «Es mi cuenta nueva» y «No es mía»

#### Scenario: Cuenta ya confirmada
- **WHEN** el usuario reabre la sesión de un portal cuya cuenta ya está confirmada y es la misma
- **THEN** el asistente no muestra ninguna confirmación

### Requirement: Retirar el mensaje al confirmar la cuenta
Cuando el usuario confirma la cuenta de un portal, el asistente SHALL borrar el mensaje de conexión que solo servía para esa confirmación. El asistente MUST NOT borrarlo si es parte del alta del usuario o el bloque «Conexión» de la card de una postulación, ni mientras en ese mensaje quede otra cuenta por confirmar o distinta.

#### Scenario: Confirmar en un mensaje de conexión suelto
- **WHEN** el usuario ya terminó su alta, no tiene una card con ese mensaje y toca «Confirmar» en la confirmación de un portal
- **THEN** la cuenta queda confirmada y el mensaje de conexión desaparece del chat

#### Scenario: Confirmar con otra cuenta pendiente en el mismo mensaje
- **WHEN** el mensaje de conexión muestra dos portales por confirmar y el usuario confirma uno
- **THEN** el mensaje se edita para mostrar el confirmado y el que falta, con los botones del que falta, y no se borra

#### Scenario: Confirmar durante el alta
- **WHEN** el usuario confirma una cuenta en el paso de plataformas del alta
- **THEN** la tarjeta del alta se edita y sigue su camino, sin borrarse

#### Scenario: Confirmar dentro de la card de una postulación
- **WHEN** el usuario confirma la cuenta en el bloque «Conexión» de la card de una postulación
- **THEN** la card se edita y sigue su camino, sin borrarse

#### Scenario: Confirmar en el mensaje de conexión aparte
- **WHEN** hay una card abierta de otro portal, el usuario confirma la cuenta en el mensaje de conexión aparte y no queda nada más por confirmar en él
- **THEN** ese mensaje aparte se borra y la card abierta no cambia

#### Scenario: Borrar el mensaje no es posible
- **WHEN** Telegram no deja borrar el mensaje de conexión (por ejemplo, ya no existe)
- **THEN** la cuenta queda confirmada igualmente y el asistente no muestra ningún error al usuario
