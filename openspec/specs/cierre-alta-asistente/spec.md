# cierre-alta-asistente Specification

## Purpose

Define el mensaje con el que el asistente de Telegram cierra el alta y orienta al usuario hacia el grupo de vacantes.

## Requirements

### Requirement: Mensaje de cierre del alta
Cuando el alta termina, es decir, cuando el paso de plataformas se cumple o se omite (no al vincular el navegador), el asistente SHALL enviar un mensaje nuevo (no una edición de la tarjeta de conexión) que explique que, para empezar, el usuario debe ir al grupo, ver las vacantes y tocar el botón **⚡ Postularme** de la vacante a la que quiere aplicar, y que con ese toque comienza el proceso. Si hay un enlace al grupo, el mensaje MUST incluir un botón «Ir al grupo» que lo abra. La tarjeta de conexión MUST NOT repetir el cierre.

#### Scenario: Alta completa sin vacante pendiente
- **WHEN** el usuario completa el paso de plataformas (o lo omite), sin haber tocado una vacante antes
- **THEN** el bot envía el mensaje que lo manda al grupo a tocar ⚡ Postularme, con el botón «Ir al grupo»

#### Scenario: Sin enlace al grupo
- **WHEN** no hay invitación configurada ni chat con formato `-100…`
- **THEN** el mensaje se envía igual, sin el botón

#### Scenario: Alta con vacante pendiente
- **WHEN** el paso de plataformas se cumple o se omite y el usuario ya había tocado una vacante
- **THEN** no se envía el mensaje de cierre y la postulación de esa vacante arranca en la tarjeta

#### Scenario: Navegador vinculado no cierra el alta
- **WHEN** el usuario vincula el navegador y el paso de plataformas aún no se cumple ni se omite
- **THEN** el alta sigue abierta y no arranca ninguna postulación
