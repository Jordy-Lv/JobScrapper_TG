# resumen-diario Specification

## Purpose
Dar al administrador una vista diaria de la salud y los resultados del buscador, con recomendaciones accionables, para ajustar filtros, fuentes y palabras clave con datos.

## Requirements

### Requirement: Resumen diario programado
Si el resumen está activado en la configuración, el sistema SHALL enviar al canal un resumen una vez al día a la hora configurada (08:00 de Colombia por defecto) que cubre las 24 h anteriores. Si está desactivado, MUST NOT enviar nada.

#### Scenario: Resumen activado
- **WHEN** son las 08:00 y el resumen está activado
- **THEN** llega al canal un único resumen de las últimas 24 h

#### Scenario: Resumen ya enviado
- **WHEN** el resumen del día ya se envió y el proceso se ejecuta de nuevo ese día
- **THEN** no se envía un segundo resumen

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

### Requirement: Una sola llamada y datos sanitizados
Cada resumen SHALL generarse con una sola llamada a la IA, enviándole solo métricas agregadas. Las llamadas del resumen MUST limitarse a un máximo diario configurable (3 por defecto). Así un reintento o una prueba no deja al resumen programado sin recomendaciones, y un error no puede repetir llamadas sin límite. La llamada MUST NOT incluir tokens, claves, cookies ni ids de chat.

#### Scenario: Llamada única
- **WHEN** se genera el resumen del día
- **THEN** se hace exactamente una llamada a la IA

#### Scenario: Prueba previa el mismo día
- **WHEN** ese día ya se hizo una llamada de resumen en una prueba y llega el resumen programado de las 08:00
- **THEN** el resumen programado se genera con recomendaciones de la IA, porque no se alcanzó el tope diario

### Requirement: Resumen de respaldo sin IA
Si la IA no está disponible (falla, saldo bajo o respuesta inválida), el sistema SHALL enviar igualmente el resumen con las métricas en texto plano, sin recomendaciones, e indicar el motivo.

#### Scenario: IA no disponible a las 08:00
- **WHEN** la API de DeepSeek responde 5xx al generar el resumen
- **THEN** se envía el resumen con las métricas y la nota "recomendaciones IA no disponibles"
