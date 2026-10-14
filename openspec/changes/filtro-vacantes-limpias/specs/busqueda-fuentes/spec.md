# Spec Delta

## ADDED Requirements

### Requirement: Búsqueda de LinkedIn por ciudad base
La fuente LinkedIn SHALL alternar sus peticiones entre variantes de búsqueda configurables, sin aumentar el presupuesto de peticiones por corrida. Por defecto hay dos variantes:
- **Colombia**: ubicación Colombia.
- **Ciudad base**: ubicación Cartagena.

La variante se elige en orden circular entre corridas y su posición MUST persistir entre corridas. La fuente MUST NOT asignar una modalidad que no conoce: la API pública de LinkedIn ignora el filtro de modalidad (`f_WT`) y sus tarjetas no indican la modalidad, así que las vacantes de LinkedIn quedan con la modalidad vacía salvo que el título o la ubicación la digan.

#### Scenario: Variantes alternadas
- **WHEN** la corrida N usa la variante «Colombia»
- **THEN** la corrida N+1 usa la variante «Ciudad base»

#### Scenario: Sin modalidad inventada
- **WHEN** una vacante llega de LinkedIn con ubicación "Bogotá, Distrito Capital, Colombia" y sin «remoto» en el título
- **THEN** su modalidad queda vacía y, sin descripción, se rechaza por presencial fuera de la ciudad base

#### Scenario: Remoto dicho en el título
- **WHEN** una vacante de LinkedIn se titula "Junior QA Engineer - Remote Work" y su ubicación es "Colombia"
- **THEN** se trata como remota y pasa el filtro geográfico

#### Scenario: Presupuesto sin cambios
- **WHEN** LinkedIn tiene un presupuesto de 3 peticiones por corrida
- **THEN** la corrida hace como máximo 3 peticiones a LinkedIn, sea cual sea la variante
