# vinculacion-plataformas-alta Specification

## Purpose
Define el paso del alta que, tras vincular el navegador, guía al usuario a iniciar sesión en los portales y espera la confirmación de su cuenta antes de postular.

## Requirements

### Requirement: Paso de plataformas tras vincular el navegador
Cuando el usuario con el alta en curso vincula su navegador, el asistente SHALL pasar a un paso de plataformas en lugar de cerrar el alta. El paso MUST mostrar, en la tarjeta de conexión, cada plataforma con postulación automática y su estado, e indicar que debe iniciar sesión en ellas en el navegador vinculado. El alta MUST NOT cerrarse ni arrancar la vacante pendiente mientras el paso no se cumpla ni se omita.

#### Scenario: Navegador recién vinculado
- **WHEN** el usuario con el alta en curso vincula el navegador
- **THEN** la tarjeta muestra «Navegador vinculado» y las plataformas automáticas como pendientes de iniciar sesión
- **AND** no se envía el mensaje de cierre ni arranca ninguna postulación

#### Scenario: Solo se listan plataformas automáticas
- **WHEN** una plataforma está con postulación automática apagada
- **THEN** no aparece en la lista del paso

### Requirement: Cuándo se cumple el paso
Con una vacante pendiente, el paso SHALL cumplirse cuando la cuenta de la plataforma de esa vacante queda confirmada (por el aviso de portal listo o por el botón «Confirmar»). Sin vacante pendiente, SHALL cumplirse cuando cualquier plataforma queda confirmada. Las demás plataformas MUST mostrarse como opcionales y no bloquear.

#### Scenario: Cuenta de la vacante confirmada
- **WHEN** hay una vacante pendiente de elempleo y la cuenta de elempleo queda confirmada
- **THEN** el alta se cierra y la postulación de esa vacante arranca en la tarjeta

#### Scenario: Se confirma otra plataforma
- **WHEN** hay una vacante pendiente de elempleo y solo se confirma Magneto
- **THEN** el paso sigue abierto y la vacante no arranca

#### Scenario: Sin vacante pendiente
- **WHEN** no hay vacante pendiente y se confirma cualquier plataforma
- **THEN** el alta se cierra con el mensaje que manda al grupo

#### Scenario: Cuenta por confirmar
- **WHEN** el navegador reporta una sesión cuya cuenta aún no está confirmada
- **THEN** la tarjeta pide confirmarla con los botones de siempre y el paso sigue abierto hasta que la confirme

### Requirement: Omitir el paso
El paso MUST ofrecer el botón «Omitir por ahora». Al tocarlo, el asistente SHALL cerrar el alta y, si hay vacante pendiente, encolarla como hoy, de modo que la cola espere la sesión.

#### Scenario: Omitir con vacante pendiente
- **WHEN** el usuario toca «Omitir por ahora» con una vacante pendiente
- **THEN** el alta se cierra y la vacante se encola esperando la sesión

#### Scenario: Omitir sin vacante
- **WHEN** el usuario toca «Omitir por ahora» sin vacante pendiente
- **THEN** el alta se cierra con el mensaje que manda al grupo

### Requirement: El paso se salta cuando no hace falta
El asistente SHALL saltar el paso, cerrando el alta de inmediato, cuando la cuenta de la plataforma que se espera ya estaba confirmada con la sesión abierta en el navegador, o cuando la plataforma de la vacante pendiente no tiene postulación automática.

#### Scenario: Cuenta ya confirmada con sesión abierta
- **WHEN** el usuario vuelve a vincular un navegador y la plataforma esperada ya está confirmada con sesión abierta
- **THEN** el alta se cierra sin esperar otro aviso

#### Scenario: Plataforma sin postulación automática
- **WHEN** la vacante pendiente es de una plataforma sin postulación automática
- **THEN** el paso se salta y la vacante sigue su camino de respaldo

### Requirement: Retomar el paso con /start
Si el usuario envía `/start` mientras el paso está abierto, el asistente MUST enviar la tarjeta del paso como mensaje nuevo al final del chat, con un aviso de que la vacante (si la hay) sigue guardada, y retirar la tarjeta anterior sin fallar si no se puede borrar.

#### Scenario: /start durante el paso
- **WHEN** el usuario con el paso abierto envía `/start v_<id>`
- **THEN** recibe un aviso y la tarjeta nueva, y `vacante_pendiente` vale `<id>`
