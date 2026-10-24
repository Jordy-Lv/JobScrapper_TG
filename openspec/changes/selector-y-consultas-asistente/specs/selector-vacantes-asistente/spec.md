# Spec Delta

## Purpose

Permite elegir, desde el chat privado con el bot asistente, a cuál de las vacantes de un mensaje del canal postularse, sin llenar el canal de botones.

## ADDED Requirements

### Requirement: Un solo botón de postulación por mensaje del canal
Con el asistente activo y el enlace del canal habilitado, cada mensaje de ofertas del canal MUST llevar un único botón «⚡ Postularme a una de estas (N)», donde N es la cantidad de vacantes del mensaje. El mensaje MUST NOT llevar un botón por vacante.

#### Scenario: Mensaje con cinco vacantes
- **WHEN** se publica un mensaje con cinco vacantes y el asistente está activo
- **THEN** el mensaje lleva un solo botón «⚡ Postularme a una de estas (5)»

#### Scenario: Asistente apagado
- **WHEN** se publica un mensaje con el asistente apagado
- **THEN** el mensaje no lleva botones

#### Scenario: Mensaje de una sola vacante
- **WHEN** se publica un mensaje con una sola vacante
- **THEN** el mensaje lleva un solo botón «⚡ Postularme» que abre el selector con esa vacante

### Requirement: El botón abre el bot en privado con el lote del mensaje
El botón MUST abrir el chat privado del bot asistente con un identificador opaco del lote de vacantes de ese mensaje, y el bot MUST resolver ese identificador a las mismas vacantes, en el mismo orden en que aparecen en el mensaje.

#### Scenario: Usuario registrado
- **WHEN** un usuario con el registro terminado toca el botón de un mensaje con cuatro vacantes
- **THEN** el bot le muestra en privado el selector con esas cuatro vacantes, en el orden del mensaje

#### Scenario: Lote vencido
- **WHEN** el lote tiene más días que la retención del índice del asistente
- **THEN** el bot responde que esas vacantes ya no están disponibles y ofrece «🔎 Buscar vacantes»

### Requirement: Selector en una sola tarjeta paginada
El selector MUST ser un único mensaje editable que lista las vacantes numeradas (título, empresa y lugar) y ofrece un botón por vacante, con un máximo de 6 por página y botones «⬅️ Anterior» y «Siguiente ➡️» cuando hay más. Cambiar de página MUST editar la misma tarjeta en lugar de enviar mensajes nuevos.

#### Scenario: Lote de nueve vacantes
- **WHEN** el selector abre un lote de nueve vacantes
- **THEN** muestra las vacantes 1 a 6 con «Siguiente ➡️», y al tocarlo la misma tarjeta muestra la 7 a la 9 con «⬅️ Anterior»

#### Scenario: Destacadas en el selector
- **WHEN** el lote incluye vacantes destacadas
- **THEN** las destacadas aparecen primero y marcadas con ⭐

### Requirement: Elegir una vacante sigue el flujo de postulación existente
Al tocar una vacante del selector, el bot MUST iniciar la postulación a esa vacante con el mismo comportamiento que tenía el botón ⚡ individual: automática, paquete de respaldo, «ya la tienes» o «no disponible». El selector MUST marcar con ✅ las vacantes a las que el usuario ya se postuló.

#### Scenario: Vacante automática
- **WHEN** el usuario elige en el selector una vacante de Computrabajo con postulación automática activa
- **THEN** se encola la postulación y el bot muestra su tarjeta de postulación, como antes

#### Scenario: Vacante ya postulada
- **WHEN** el usuario abre de nuevo el selector de un lote en el que ya se postuló a la vacante 2
- **THEN** la vacante 2 aparece con ✅ y tocarla muestra el estado de esa postulación

### Requirement: El lote sobrevive al registro
Si quien toca el botón no está registrado, no aceptó la política vigente o no terminó el alta, el bot MUST guardar el lote como pendiente y, al terminar el alta, MUST mostrar el selector de ese lote.

#### Scenario: Usuario nuevo
- **WHEN** un miembro del grupo sin registro toca el botón y termina el alta
- **THEN** al terminar el alta el bot le muestra el selector del lote que tocó

#### Scenario: No miembro
- **WHEN** alguien que no pertenece al grupo abre el enlace del lote
- **THEN** el bot responde que el asistente es exclusivo del grupo y no guarda datos suyos

### Requirement: Compatibilidad con los botones ya publicados
El bot MUST seguir atendiendo los botones ⚡ individuales y los enlaces `v_` de los mensajes publicados antes de este cambio, mientras sus vacantes estén dentro de la retención del índice.

#### Scenario: Botón viejo
- **WHEN** un usuario toca el botón ⚡ individual de un mensaje publicado la semana anterior
- **THEN** la postulación a esa vacante se inicia como antes
