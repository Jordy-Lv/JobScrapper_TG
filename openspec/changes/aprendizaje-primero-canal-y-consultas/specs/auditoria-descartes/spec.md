# Spec Delta

## Purpose

Deja rastro de cada vacante que el buscador vio y no publicó, y permite al administrador averiguar por qué una vacante concreta no llegó al canal.

## ADDED Requirements

### Requirement: Registro de cada descarte
Cada vacante que una corrida real rechaza MUST quedar registrada con su clave, fuente, palabra clave, título, empresa, enlace, ubicación, modalidad, la etapa que la rechazó (reglas, IA, guardarraíl, nivel pausado o vencida sin clasificar), el motivo y el detalle. Una vacante vista otra vez MUST actualizar su registro en lugar de duplicarlo.

#### Scenario: Rechazo por reglas
- **WHEN** las reglas rechazan «Aprendiz SENA Contable» por no ser TI
- **THEN** queda un registro con etapa «reglas», motivo «no_ti» y la palabra clave que la trajo

#### Scenario: Rechazo de la IA
- **WHEN** la IA rechaza una dudosa
- **THEN** queda un registro con etapa «ia» y el motivo que dio la IA

#### Scenario: Vista dos veces
- **WHEN** la misma vacante se rechaza en dos corridas
- **THEN** existe un solo registro, con la fecha de la última vez y el número de veces que se vio

### Requirement: Retención de los descartes
Los registros de descartes MUST borrarse al superar `estado.dias_descartes` (14 por defecto), y las corridas en modo prueba o dry-run MUST NOT escribirlos.

#### Scenario: Limpieza
- **WHEN** una corrida empieza y hay descartes de hace 15 días
- **THEN** esos descartes se borran

### Requirement: Diagnóstico de una vacante
El comando `buscador.py diagnosticar` MUST aceptar un enlace o un texto de título y explicar qué pasó con la vacante. Si hay coincidencias, MUST informar si se publicó, si está en una cola (dudosas, detalle o envío) o si se descartó, con su etapa, motivo, detalle y fechas. MUST NOT escribir en la base.

#### Scenario: Vacante descartada
- **WHEN** el administrador ejecuta `buscador.py diagnosticar https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-aprendiz-sena-...`
- **THEN** el comando muestra que se descartó por reglas, con el motivo, el detalle de la regla y la palabra clave que la trajo

#### Scenario: Vacante nunca vista
- **WHEN** el enlace no aparece en vistas, colas ni descartes
- **THEN** el comando dice que el buscador nunca la recibió y lista las palabras clave buscadas en esa fuente durante los últimos 3 días, con cuántos resultados trajo cada una

### Requirement: Evaluación en seco de una vacante
`buscador.py diagnosticar --evaluar` MUST evaluar con las reglas vigentes una vacante descrita por título, empresa, ubicación, modalidad y descripción, y mostrar el veredicto, el motivo, la categoría y la decisión del guardarraíl. Con `--con-ia`, MUST además mostrar la respuesta del clasificador sin guardarla en la caché.

#### Scenario: Probar una regla
- **WHEN** el administrador evalúa «Aprendiz SENA Tecnólogo ADSO» en Cartagena, presencial
- **THEN** el comando muestra «aceptar», categoría «Prácticas y Aprendizaje» y que el guardarraíl no la cambia
