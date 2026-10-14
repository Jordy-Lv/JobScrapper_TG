# Spec Delta

## ADDED Requirements

### Requirement: Botón ⚡ Postularme en cada vacante del canal
Cuando el asistente está activo y `asistente.enlace_canal` está habilitado, cada mensaje del canal SHALL llevar debajo un botón "⚡ <título de la vacante>" por cada vacante que contiene, en el mismo orden de las fichas. El botón identifica la vacante con un id corto derivado de su clave (callback de hasta 64 bytes) y MUST NOT llevar datos personales.

Para que el toque llegue al asistente, esos mensajes SHALL publicarse con el bot asistente (`ASISTENTE_BOT_TOKEN`), que es administrador del canal: Telegram solo informa los toques de un botón al bot que envió el mensaje.

Al tocar el botón, el bot asistente recibe quién lo tocó y:
- si el usuario ya completó su registro, encola la postulación de inmediato, sin abrir ningún chat, y le muestra un aviso corto sobre el canal ("⚡ Postulando a …"). El resultado le llega después por el chat privado;
- si aún no se registró o no terminó el alta, le abre el chat del bot con esa vacante, para que el alta continúe y la postule al terminar;
- si ya tenía esa postulación, sus postulaciones están en pausa o la vacante no se puede enviar sola, se lo dice en una ventana breve sin duplicar nada.

Las vacantes nunca se envían al chat privado: solo se publican en el canal.

Si el asistente o el botón están deshabilitados, los mensajes MUST quedar idénticos a los de antes y publicarse con el bot del buscador, para poder probar el bot sin mostrarlo en el canal.

#### Scenario: Botón habilitado
- **WHEN** se publica un mensaje con 3 vacantes y el botón está habilitado
- **THEN** el mensaje lleva 3 botones ⚡, uno por vacante, y lo publica el bot asistente

#### Scenario: Toque de un usuario registrado
- **WHEN** Ana, ya registrada, toca "⚡ Practicante QA Tester" en el canal
- **THEN** la postulación queda en cola para Ana al instante, ve "⚡ Postulando a Practicante QA Tester…" sobre el canal y el resultado le llega por el bot

#### Scenario: Toque de alguien sin registro
- **WHEN** un miembro que nunca habló con el bot toca un botón ⚡
- **THEN** se le abre el chat del bot con esa vacante para registrarse, y al terminar el alta se postula

#### Scenario: Botón deshabilitado
- **WHEN** `asistente.enlace_canal` es falso
- **THEN** los mensajes no llevan botones y los publica el bot del buscador

#### Scenario: Id estable
- **WHEN** la misma vacante se reenvía al canal tras un error de envío
- **THEN** su botón lleva el mismo id
