## Purpose

Conserva un resumen diario de las cifras del radar y del asistente después de que se borre el detalle, y define el tipo de cada vacante (practicante, aprendiz, trainee, junior…) a partir de su título, para poder consultar cualquier día o mes pasado.

## ADDED Requirements

### Requirement: Resumen diario del radar
Al terminar cada corrida, y siempre antes de la limpieza de registros antiguos, el radar SHALL recalcular el resumen de hoy y de ayer (America/Bogota) y guardarlo en `vacantes.db`. El resumen se agrupa por día, fuente, categoría, tipo y modalidad, y contiene:
- vistas y publicadas;
- y, por día: corridas, corridas con error, crudas, descartes por regla, duplicadas, dudosas, aceptadas y rechazadas por la IA, enviadas;
- llamadas y tokens de IA por tarea.

El recálculo MUST reemplazar las filas de esos días, de modo que repetirlo no duplique cifras. Las filas se conservan `asistente.panel.dias_metricas` días (730 por defecto), aunque el detalle se borre antes.

#### Scenario: Recalcular no duplica
- **WHEN** dos corridas seguidas del mismo día recalculan el resumen
- **THEN** las publicadas del día son las mismas que contar las vacantes enviadas ese día en `vistas`

#### Scenario: El detalle se borra y el resumen queda
- **WHEN** la limpieza borra las vistas de hace 91 días
- **THEN** el resumen de ese día sigue disponible con sus totales

#### Scenario: Día que cruza la medianoche
- **WHEN** una corrida empieza a las 23:55 y termina a las 00:05 hora de Colombia
- **THEN** al terminar recalcula el día anterior y el nuevo, y ninguna vacante cuenta dos veces

### Requirement: Resumen diario del asistente
El servicio del asistente SHALL guardar cada hora el resumen de hoy y de ayer en `asistente.db`. El resumen contiene:
- postulaciones creadas y terminadas por plataforma, estado final y origen (botón o automático);
- llamadas, errores y tokens de IA por tarea;
- usuarios por estado al cierre del día.

Se rige por las mismas reglas de reemplazo y conservación que el del radar, y MUST NOT contener ids de usuario.

#### Scenario: Resumen sin usuarios
- **WHEN** se guarda el resumen del asistente
- **THEN** sus filas tienen solo fechas, dimensiones y conteos, sin ningún id de usuario

### Requirement: Relleno inicial
La primera vez que corra con el esquema nuevo, el sistema SHALL calcular el resumen de todos los días que todavía tienen detalle (hasta 90 días de vacantes y 30 de corridas e IA). Así el panel muestra historial desde el primer día.

#### Scenario: Primer arranque
- **WHEN** el radar corre por primera vez con el esquema nuevo y `vistas` tiene 90 días de datos
- **THEN** el resumen queda con 90 días de vacantes, y con 30 de corridas e IA

### Requirement: Tipo de vacante
El sistema SHALL asignar a cada vacante un tipo según su título, recorriendo en orden la lista `asistente.panel.tipos` de `config.yaml`. Cada entrada tiene un `tipo` y sus `terminos`, y gana la primera que coincide. Se compara igual que los filtros: en minúsculas, sin tildes y con límites de palabra. Una vacante sin coincidencia MUST quedar como `otro`. El tipo MUST calcularse al consultar o resumir, sin cambiar la categoría ni la clasificación del radar, así que vale también para vacantes guardadas antes de este change.

#### Scenario: Aprendiz SENA
- **WHEN** el título es «Aprendiz SENA en análisis y desarrollo de software»
- **THEN** el tipo es «aprendiz_sena»

#### Scenario: Trainee
- **WHEN** el título es «Trainee de Tecnología»
- **THEN** el tipo es «trainee»

#### Scenario: Sin coincidencia
- **WHEN** el título es «Analista de Infraestructura»
- **THEN** el tipo es «otro»
