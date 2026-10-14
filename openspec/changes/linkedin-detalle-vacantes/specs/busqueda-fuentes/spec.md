# Spec Delta

## ADDED Requirements

### Requirement: Detalle de ofertas de LinkedIn
La fuente LinkedIn SHALL poder pedir el detalle público de una oferta para obtener su descripción, que las tarjetas de búsqueda no traen. El detalle se pide con un presupuesto de peticiones por corrida y una pausa entre peticiones, ambos configurables y propios del detalle. El texto se recorta a un máximo de caracteres configurable, conservando además las frases que hablan de la modalidad (remoto, híbrido, presencial) aunque caigan fuera del recorte.

#### Scenario: Detalle obtenido
- **WHEN** se pide el detalle de una oferta de LinkedIn y la respuesta es correcta
- **THEN** la oferta recibe su descripción recortada y la petición queda registrada como un intento de la fuente

#### Scenario: Presupuesto de la corrida
- **WHEN** hay 20 ofertas esperando detalle y el presupuesto es de 6 peticiones por corrida
- **THEN** se piden como máximo 6 detalles y las otras 14 siguen esperando

#### Scenario: Pausa entre detalles
- **WHEN** se piden dos detalles seguidos en la misma corrida
- **THEN** entre una petición y la siguiente transcurre la pausa configurada para el detalle

### Requirement: Un bloqueo en el detalle frena a LinkedIn
Una respuesta 403, 429 o 999, o un desafío anti-bot, al pedir un detalle MUST aplicar el mismo cooldown de LinkedIn que un bloqueo en la búsqueda (respetando `Retry-After` si viene) y MUST cortar los detalles de esa corrida. Mientras LinkedIn esté en cooldown no se piden detalles. El sistema MUST NOT evadir captchas ni usar proxies.

#### Scenario: 429 en un detalle
- **WHEN** el tercer detalle de la corrida responde 429
- **THEN** LinkedIn entra en cooldown, no se piden más detalles en la corrida y las ofertas sin resolver siguen en la cola

#### Scenario: LinkedIn en cooldown
- **WHEN** LinkedIn tiene un cooldown vigente al empezar la corrida
- **THEN** no se pide ningún detalle y las ofertas en cola esperan

### Requirement: Caché del detalle
El sistema SHALL guardar la descripción obtenida de cada oferta y reutilizarla mientras la oferta pueda seguir apareciendo, de modo que el detalle de una misma oferta no se pida dos veces. Un fallo al pedirlo no se guarda como si fuera una descripción.

#### Scenario: Oferta que reaparece
- **WHEN** una oferta cuyo detalle ya se pidió vuelve a aparecer en una búsqueda posterior
- **THEN** se evalúa con la descripción guardada y no se hace otra petición de detalle
