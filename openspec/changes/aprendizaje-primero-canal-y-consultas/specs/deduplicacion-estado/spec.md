# Spec Delta

## ADDED Requirements

### Requirement: Área y nivel de las vacantes publicadas
Para cada vacante enviada, el estado MUST guardar, además de lo que ya guarda, el área de TI detectada y su nivel (`practica`, `sin_experiencia`, `junior` u `otro`). Así el resumen puede medir el porcentaje de lo publicado por nivel y las fases siguientes pueden filtrar por área.

#### Scenario: Aprendiz de soporte enviado
- **WHEN** se envía «Aprendiz de soporte técnico»
- **THEN** su registro en vistas tiene área «soporte» y nivel `practica`

### Requirement: Republicación de una vacante repetida
Una vacante con la misma huella que una ya enviada MUST tratarse como nueva si cumple dos condiciones:
- su clave en la fuente es distinta;
- la vacante enviada se publicó hace más de `estado.republicar_tras_dias` días (30 por defecto).

La misma clave nunca se publica dos veces.

#### Scenario: Nueva cohorte de aprendices
- **WHEN** una empresa publica de nuevo «Aprendiz SENA Sistemas» con otra clave, 45 días después de la anterior
- **THEN** la vacante se evalúa y puede publicarse

#### Scenario: Copia en otra fuente
- **WHEN** la misma vacante aparece en otra fuente 2 días después
- **THEN** se trata como duplicada, como antes
