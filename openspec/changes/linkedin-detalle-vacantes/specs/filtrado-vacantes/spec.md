# Spec Delta

## ADDED Requirements

### Requirement: Ofertas pendientes de detalle
Para una fuente que puede pedir detalle, una oferta cuya modalidad es desconocida y que no trae descripción NO MUST rechazarse por «presencial fuera de la ciudad base» ni por «call center no remoto» mientras su detalle no se haya pedido. Se trata como **pendiente de detalle** cuando, por lo demás, pasa los filtros del título: lista negra, seniority, antigüedad, términos de TI y áreas no TI. Una oferta que esas reglas rechazan igual (por ejemplo, un título sin nada de TI) se rechaza de inmediato, sin pedir detalle.

Cuando el detalle llega, la oferta se evalúa de nuevo con todas las reglas y con su descripción. Si la modalidad sigue sin saberse tras leer la descripción, el veredicto es dudosa con la condición «remoto o híbrido» (o «solo remoto» para call center) y decide la IA.

#### Scenario: Oferta remota de otra ciudad
- **WHEN** llega de LinkedIn "Software Engineer Intern" en "Colombia", sin modalidad ni descripción
- **THEN** queda pendiente de detalle y no se rechaza

#### Scenario: Título sin TI
- **WHEN** llega de LinkedIn "Cajera Sur de Bogotá" en "Bogotá", sin modalidad ni descripción
- **THEN** se rechaza por no ser TI, sin pedir detalle

#### Scenario: Detalle que confirma lo presencial
- **WHEN** el detalle de una oferta de Bogotá dice que el trabajo es presencial en las oficinas
- **THEN** el veredicto final es rechazar por presencial fuera de la ciudad base

#### Scenario: Detalle sin pistas de modalidad
- **WHEN** el detalle de una oferta de Medellín describe las funciones pero no dice nada de la modalidad
- **THEN** el veredicto es dudosa con la condición «remoto o híbrido» y la IA la rechaza si el texto no da indicio

#### Scenario: Call center pendiente
- **WHEN** llega de LinkedIn "Agente de soporte técnico" en Cartagena sin modalidad ni descripción
- **THEN** queda pendiente de detalle, y el detalle decide si es remoto

### Requirement: La modalidad que solo sale del detalle la confirma la IA
Cuando la oferta es de una fuente que obtiene su descripción del detalle y la única señal de remoto o híbrido está en esa descripción, la oferta MUST ir a la IA con la condición de modalidad correspondiente en lugar de aceptarse por reglas, porque una mención suelta («oficinas remotas», «trabajo remoto ocasional») no prueba que el puesto lo sea. La IA MUST aceptarla solo si el texto indica que la modalidad del propio puesto es la exigida, y MUST rechazarla si el texto indica trabajo presencial o si la mención remota se refiere a la empresa u otra cosa.

#### Scenario: Mención remota genérica
- **WHEN** el detalle de una oferta de Bogotá dice "somos una empresa con equipos remotos en varios países" y "asistirás a nuestra sede"
- **THEN** la oferta va a la IA con la condición «remoto o híbrido» y la IA la rechaza

#### Scenario: Remoto del puesto
- **WHEN** el detalle de una oferta de Bogotá dice "esta posición es 100% remota"
- **THEN** la oferta va a la IA con la condición «remoto o híbrido» y la IA puede aceptarla

### Requirement: Nada se rechaza por falta de detalle
Una oferta pendiente de detalle MUST permanecer en una cola persistente hasta que ocurra una de estas cosas: se resuelve su detalle, la oferta está cerrada (el detalle responde 404 o 410) o vence la espera máxima configurable (48 horas por defecto). Un fallo del detalle (429, tiempo agotado, error de servidor, página sin descripción reconocible) o el agotarse el presupuesto de la corrida MUST dejar la oferta en la cola, sin rechazarla ni publicarla. La cola se atiende de la más antigua a la más reciente. Cada salida de la cola por cierre o vencimiento MUST registrarse en el log con el título y la fuente.

#### Scenario: Fallo temporal
- **WHEN** el detalle de una oferta responde error de servidor
- **THEN** la oferta sigue en la cola y se reintenta en una corrida posterior

#### Scenario: Orden de la cola
- **WHEN** hay ofertas en cola de distintas corridas y el presupuesto alcanza para algunas
- **THEN** se piden primero las más antiguas

#### Scenario: Oferta cerrada
- **WHEN** el detalle de una oferta responde 404
- **THEN** sale de la cola como cerrada y queda contada y registrada

#### Scenario: Espera vencida
- **WHEN** una oferta lleva más de 48 horas en la cola sin poder resolverse
- **THEN** sale de la cola como vencida y queda contada y registrada

#### Scenario: Oferta repetida
- **WHEN** una oferta que ya está en la cola vuelve a aparecer en una búsqueda
- **THEN** no se agrega otra vez ni se cuenta como nueva
