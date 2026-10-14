# Spec Delta

## ADDED Requirements

### Requirement: Métricas de detalle en el resumen
El resumen diario SHALL incluir, para las últimas 24 horas, los detalles de ofertas pedidos, los que fallaron, las ofertas recuperadas (las que sin el detalle se habrían rechazado y tras leerlo siguieron adelante), las ofertas que siguen en la cola y las que salieron de ella por cierre o vencimiento. Las mismas cifras MUST pasar a los datos que recibe la IA para las recomendaciones, de modo que pueda señalar, por ejemplo, una cola que crece o muchos fallos.

#### Scenario: Línea de detalle
- **WHEN** en las últimas 24 h se pidieron 60 detalles, fallaron 4, se recuperaron 9 ofertas, 3 siguen en cola y 1 venció
- **THEN** el resumen muestra esas cifras en una línea de detalle de LinkedIn

#### Scenario: Cola que no se vacía
- **WHEN** la cola de detalle tiene más de 30 ofertas
- **THEN** el resumen puede recomendar subir el presupuesto de detalle o revisar los bloqueos, citando ese dato
