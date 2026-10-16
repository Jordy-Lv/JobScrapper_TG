## ADDED Requirements

### Requirement: Cuenta regresiva antes de postular
Al tocar «Postular», el asistente SHALL mostrar en la card de la postulación una cuenta regresiva animada, de 5 segundos por defecto, con un botón «Cancelar», y MUST NOT encolar la vacante ni avisar a la extensión hasta que la cuenta termine sin cancelarse. La animación SHALL editar la misma card (una edición por segundo) y no enviar mensajes nuevos. La duración SHALL ser configurable, y con 0 segundos el toque encola de inmediato como antes.

#### Scenario: Toque y cuenta
- **WHEN** un usuario con el alta terminada toca «Postular» en una vacante disponible
- **THEN** la card muestra el título, la empresa, los segundos restantes con una barra que avanza cada segundo y el botón «Cancelar», y la postulación aún no existe en la cola

#### Scenario: La cuenta termina
- **WHEN** pasan los 5 segundos sin que el usuario cancele
- **THEN** la vacante se encola y la card pasa a «En cola» (o a «Esperando navegador» o al respaldo, según corresponda), en el mismo mensaje

#### Scenario: Toque desde el canal
- **WHEN** el usuario toca ⚡ en un mensaje del canal
- **THEN** el aviso corto responde de inmediato que tiene 5 segundos para cancelar en el bot, y la cuenta corre en la card del bot

#### Scenario: Vacante pendiente del alta
- **WHEN** el usuario termina el alta con una vacante pendiente
- **THEN** la cuenta regresiva corre en la tarjeta del alta, bajo el bloque de conexión, antes de encolar

#### Scenario: Cuenta desactivada
- **WHEN** la duración configurada es 0
- **THEN** el toque encola de inmediato y la card muestra «En cola», sin cuenta ni botón «Cancelar»

### Requirement: Cancelar durante la cuenta
Mientras corre la cuenta, el botón «Cancelar» SHALL detenerla sin encolar nada, y la card SHALL pasar a un estado cerrado que diga que no se envió nada y ofrezca «Postular» para volver a empezar.

#### Scenario: Cancelar a tiempo
- **WHEN** el usuario toca «Cancelar» antes de que termine la cuenta
- **THEN** no se crea ninguna postulación en la cola y la card dice «Cancelaste la postulación. No envié nada.» con el botón «Postular»

#### Scenario: Postular otra vez tras cancelar
- **WHEN** el usuario toca «Postular» en la card cancelada
- **THEN** la misma card vuelve a mostrar una cuenta regresiva nueva, sin crear otro mensaje

#### Scenario: Cancelar tarde
- **WHEN** el usuario toca «Cancelar» después de que la cuenta terminó
- **THEN** el aviso corto dice que ya se está postulando, la card sigue su curso y no se cancela nada

### Requirement: Un solo toque activo por vacante
El asistente SHALL permitir una sola cuenta regresiva por usuario y vacante a la vez.

#### Scenario: Doble toque
- **WHEN** el usuario toca «Postular» en la misma vacante mientras su cuenta corre
- **THEN** no se abre otra cuenta ni otra card, y el aviso corto dice que ya está contando

#### Scenario: Toque en una vacante ya existente
- **WHEN** el usuario toca «Postular» en una vacante que ya está en la cola
- **THEN** no hay cuenta regresiva: se muestra el estado actual como hasta ahora

### Requirement: Cuenta interrumpida por reinicio
Si el asistente se reinicia con una cuenta en curso, SHALL descartarla sin postular y dejar la card en un estado que avise que se interrumpió y ofrezca «Postular».

#### Scenario: Reinicio durante la cuenta
- **WHEN** el bot se reinicia a mitad de una cuenta regresiva
- **THEN** no se encola la vacante y la card dice que la cuenta se interrumpió y ofrece «Postular»
