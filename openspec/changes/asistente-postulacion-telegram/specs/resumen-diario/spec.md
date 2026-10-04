# Spec Delta

## ADDED Requirements

### Requirement: Métricas del asistente en el resumen
Cuando el asistente de postulación está activo, el resumen diario SHALL incluir de las últimas 24 h:
- usuarios activos y altas nuevas;
- paquetes generados;
- vacantes marcadas como postuladas;
- porcentaje de respuestas resueltas sin IA;
- preguntas nuevas agregadas al banco.

A la IA del resumen (DeepSeek) MUST pasarse solo esos conteos agregados, nunca nombres, ids de Telegram, perfiles ni vacantes por usuario. Con el asistente desactivado, el resumen MUST quedar igual que antes.

#### Scenario: Día con actividad
- **WHEN** en 24 h hubo 6 usuarios activos, 14 paquetes y 9 postuladas
- **THEN** el resumen muestra esos conteos y el porcentaje de respuestas sin IA

#### Scenario: Asistente desactivado
- **WHEN** `asistente.activo` es falso
- **THEN** el resumen no muestra la sección del asistente
