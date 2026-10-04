# Spec Delta

## Purpose

Dar al administrador una vista diaria de la salud y los resultados del buscador, con recomendaciones accionables, para ajustar filtros, fuentes y palabras clave con datos.

## ADDED Requirements

### Requirement: Resumen diario programado
Si el resumen está activado en la configuración, el sistema SHALL enviar al canal un resumen una vez al día a la hora configurada (08:00 de Colombia por defecto) que cubre las 24 h anteriores. Si está desactivado, MUST NOT enviar nada.

#### Scenario: Resumen activado
- **WHEN** son las 08:00 y el resumen está activado
- **THEN** llega al canal un único resumen de las últimas 24 h

#### Scenario: Resumen ya enviado
- **WHEN** el resumen del día ya se envió y el proceso se ejecuta de nuevo ese día
- **THEN** no se envía un segundo resumen

### Requirement: Contenido del resumen
El resumen SHALL incluir las vacantes enviadas por fuente y por categoría, los descartes por cada regla de filtrado, las dudosas aceptadas, rechazadas y pendientes por la IA, los incidentes abiertos y cerrados en el periodo, el consumo de IA del día (llamadas y tokens) y entre 1 y 3 recomendaciones redactadas por la IA a partir solo de esas métricas. Ejemplos de recomendación: una palabra clave sin resultados en 7 días, o un filtro que descarta una proporción inusual.

#### Scenario: Recomendación basada en datos
- **WHEN** la palabra clave "semillero" no trajo resultados en ninguna fuente durante 7 días
- **THEN** el resumen puede recomendar revisarla, citando ese dato

### Requirement: Una sola llamada y datos sanitizados
El resumen SHALL generarse con una sola llamada a la IA por día, enviándole solo métricas agregadas. La llamada MUST NOT incluir tokens, claves, cookies ni ids de chat.

#### Scenario: Llamada única
- **WHEN** se genera el resumen del día
- **THEN** se hace exactamente una llamada a la IA

### Requirement: Resumen de respaldo sin IA
Si la IA no está disponible (falla, saldo bajo o respuesta inválida), el sistema SHALL enviar igualmente el resumen con las métricas en texto plano, sin recomendaciones, e indicar el motivo.

#### Scenario: IA no disponible a las 08:00
- **WHEN** la API de DeepSeek responde 5xx al generar el resumen
- **THEN** se envía el resumen con las métricas y la nota "recomendaciones IA no disponibles"
