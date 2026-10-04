# Spec Delta

## ADDED Requirements

### Requirement: Enlace al asistente en cada ficha
Cuando el asistente está activo y `asistente.enlace_canal` está habilitado, cada ficha del mensaje del canal SHALL incluir al final un enlace "⚡ Postularme". El enlace abre el chat privado con el bot asistente sobre esa vacante, identificada con un id corto derivado de su clave.

El enlace MUST NOT llevar datos personales ni el texto de la vacante, y su longitud MUST contarse en la división de mensajes por tamaño. Si el asistente o el enlace están deshabilitados, las fichas MUST quedar idénticas a las de antes, para poder probar el bot sin mostrarlo en el canal.

#### Scenario: Enlace habilitado
- **WHEN** se publica un mensaje con 3 vacantes y el enlace está habilitado
- **THEN** cada una de las 3 fichas termina con su enlace ⚡ Postularme hacia el bot asistente

#### Scenario: Enlace deshabilitado
- **WHEN** `asistente.enlace_canal` es falso
- **THEN** las fichas no incluyen el enlace

#### Scenario: Id estable
- **WHEN** la misma vacante se reenvía al canal tras un error de envío
- **THEN** su enlace lleva el mismo id
