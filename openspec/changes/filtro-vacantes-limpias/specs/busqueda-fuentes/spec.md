# Spec Delta

## ADDED Requirements

### Requirement: Búsqueda de LinkedIn por modalidad y ciudad base
La fuente LinkedIn SHALL alternar sus peticiones entre variantes de búsqueda configurables, sin aumentar el presupuesto de peticiones por corrida. Por defecto hay dos variantes:
- **Colombia remoto o híbrido**: ubicación Colombia, filtrada a remoto o híbrido.
- **Ciudad base**: ubicación Cartagena, con cualquier modalidad.

La variante se elige en orden circular entre corridas y su posición MUST persistir entre corridas. Las vacantes de la variante «Colombia remoto o híbrido» MUST normalizarse con modalidad «Remoto o híbrido», porque el filtro de la propia fuente la garantiza. Las de la variante «Ciudad base» MUST quedar con la modalidad vacía si la tarjeta no la indica.

#### Scenario: Variantes alternadas
- **WHEN** la corrida N usa la variante «Colombia remoto o híbrido»
- **THEN** la corrida N+1 usa la variante «Ciudad base»

#### Scenario: Modalidad desde el filtro
- **WHEN** una vacante llega por la variante «Colombia remoto o híbrido» con ubicación "Bogotá, Distrito Capital"
- **THEN** su modalidad normalizada es «Remoto o híbrido» y pasa el filtro geográfico

#### Scenario: Presupuesto sin cambios
- **WHEN** LinkedIn tiene un presupuesto de 3 peticiones por corrida
- **THEN** la corrida hace como máximo 3 peticiones a LinkedIn, sea cual sea la variante
