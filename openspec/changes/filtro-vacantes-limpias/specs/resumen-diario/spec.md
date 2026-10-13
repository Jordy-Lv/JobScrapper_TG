# Spec Delta

## MODIFIED Requirements

### Requirement: Contenido del resumen
El resumen SHALL incluir:
- las vacantes enviadas por fuente y por categoría;
- los descartes por cada regla de filtrado: lista negra, seniority, antigüedad, ubicación, presencial fuera de la ciudad base, call center no remoto y no TI;
- las correcciones del guardarraíl de prácticas (recategorizadas y rechazadas) como medida automática de falsos positivos evitados;
- las dudosas aceptadas, rechazadas y pendientes por la IA;
- los incidentes abiertos y cerrados en el periodo;
- el consumo de IA del día (llamadas y tokens);
- entre 1 y 3 recomendaciones redactadas por la IA a partir solo de esas métricas.

Ejemplos de recomendación: una palabra clave sin resultados en 7 días, un filtro que descarta una proporción inusual o muchas correcciones del guardarraíl.

#### Scenario: Recomendación basada en datos
- **WHEN** la palabra clave "semillero" no trajo resultados en ninguna fuente durante 7 días
- **THEN** el resumen puede recomendar revisarla, citando ese dato

#### Scenario: Correcciones del guardarraíl
- **WHEN** en las últimas 24 h el guardarraíl recategorizó 4 vacantes y rechazó 1
- **THEN** el resumen muestra «Guardarraíl de prácticas: 4 recategorizadas · 1 rechazada»

#### Scenario: Descartes por ciudad base
- **WHEN** en las últimas 24 h se rechazaron 30 vacantes presenciales fuera de la ciudad base
- **THEN** el resumen muestra ese conteo junto a los demás descartes
