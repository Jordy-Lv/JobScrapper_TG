## Purpose

Define el mensaje con el que el asistente de Telegram cierra el alta y orienta al usuario hacia el grupo de vacantes.

## ADDED Requirements

### Requirement: Mensaje de cierre del alta
Cuando el alta termina, el asistente SHALL enviar un mensaje nuevo (no una edición de la tarjeta de conexión) que explique que, para empezar, el usuario debe ir al grupo, ver las vacantes y tocar el botón **⚡ Postularme** de la vacante a la que quiere aplicar, y que con ese toque comienza el proceso. Si hay un enlace al grupo, el mensaje MUST incluir un botón «Ir al grupo» que lo abra. La tarjeta de conexión MUST NOT repetir el cierre.

#### Scenario: Alta completa sin vacante pendiente
- **WHEN** el usuario completa los pasos y su navegador queda vinculado, sin haber tocado una vacante antes
- **THEN** el bot envía el mensaje que lo manda al grupo a tocar ⚡ Postularme, con el botón «Ir al grupo»

#### Scenario: Sin enlace al grupo
- **WHEN** no hay invitación configurada ni chat con formato `-100…`
- **THEN** el mensaje se envía igual, sin el botón

#### Scenario: Alta con vacante pendiente
- **WHEN** el alta termina y el usuario ya había tocado una vacante
- **THEN** no se envía el mensaje de cierre y la postulación de esa vacante arranca en la tarjeta
