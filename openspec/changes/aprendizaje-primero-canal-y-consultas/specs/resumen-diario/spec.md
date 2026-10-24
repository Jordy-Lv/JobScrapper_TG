# Spec Delta

## ADDED Requirements

### Requirement: Métricas del clasificador IA en el resumen
El resumen diario MUST incluir, de las últimas 24 h:
- las llamadas al clasificador y las que fallaron, por motivo;
- las dudosas aceptadas y rechazadas por la IA;
- las que la IA rechazó teniendo evidencia de práctica en el título;
- las pendientes y las vencidas;
- el último saldo conocido de DeepSeek.

#### Scenario: Día normal
- **WHEN** se genera el resumen tras un día con 40 llamadas, 1 fallo por timeout y 6 prácticas rechazadas por la IA
- **THEN** el resumen muestra esas cifras y el saldo de DeepSeek

### Requirement: Descartes por etapa y porcentaje por nivel en el resumen
El resumen diario MUST incluir:
- los descartes de las últimas 24 h agrupados por etapa (reglas, IA, guardarraíl, nivel pausado y vencidas), con los tres motivos más frecuentes de cada una;
- el porcentaje de las vacantes enviadas en las últimas 24 h por nivel: prácticas, sin experiencia y otro, con el total.

#### Scenario: Nivel junior pausado
- **WHEN** el nivel junior está pausado y en el día se descartaron 18 vacantes por ese motivo
- **THEN** el resumen muestra «nivel pausado: 18» entre los descartes

#### Scenario: Porcentaje por nivel
- **WHEN** en el día se enviaron 20 vacantes: 14 prácticas, 5 sin experiencia y 1 de otro nivel
- **THEN** el resumen muestra 70 % prácticas, 25 % sin experiencia y 5 % otro, e indica si se cumple la meta de al menos 95 % entre prácticas y sin experiencia

### Requirement: Recomendaciones sobre prácticas perdidas
Los datos que recibe la IA para redactar el resumen MUST incluir las palabras clave del núcleo sin resultados en 7 días y los motivos de descarte que más afectan a las vacantes con evidencia de práctica. Así sus recomendaciones pueden apuntar a reglas o búsquedas que pierden aprendizaje.

#### Scenario: Regla que descarta prácticas
- **WHEN** en el día se descartaron 9 vacantes con «aprendiz» en el título por «presencial fuera»
- **THEN** ese dato llega a la IA del resumen y puede aparecer en una recomendación
