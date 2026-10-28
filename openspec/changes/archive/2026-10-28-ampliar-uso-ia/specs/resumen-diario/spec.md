# Spec Delta

## MODIFIED Requirements

### Requirement: Una sola llamada y datos sanitizados
Cada resumen SHALL generarse con una sola llamada a la IA, enviándole solo métricas agregadas. Las llamadas del resumen MUST limitarse a un máximo diario configurable (3 por defecto). Así un reintento o una prueba no deja al resumen programado sin recomendaciones, y un error no puede repetir llamadas sin límite. La llamada MUST NOT incluir tokens, claves, cookies ni ids de chat.

#### Scenario: Llamada única
- **WHEN** se genera el resumen del día
- **THEN** se hace exactamente una llamada a la IA

#### Scenario: Prueba previa el mismo día
- **WHEN** ese día ya se hizo una llamada de resumen en una prueba y llega el resumen programado de las 08:00
- **THEN** el resumen programado se genera con recomendaciones de la IA, porque no se alcanzó el tope diario
