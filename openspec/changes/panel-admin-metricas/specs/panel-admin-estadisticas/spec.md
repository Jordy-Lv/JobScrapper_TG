## Purpose

Da a los administradores vistas de solo lectura del radar y del asistente: cuántas vacantes salen por plataforma y por tipo, cómo se filtran y cuánto se usa la IA, en el día, semana, mes o rango que elijan, con comparación y bajada de detalle.

## ADDED Requirements

### Requirement: Selector de periodo
Todas las vistas de estadísticas SHALL ofrecer los periodos **día**, **semana** (de lunes a domingo), **mes** y **rango libre** (de 1 a 366 días). Las fechas se interpretan en America/Bogota. El selector MUST:
- traer el día de hoy por defecto;
- tener flechas para el periodo anterior y el siguiente, sin pasar de hoy;
- tener un calendario para elegir el día, la semana o el mes;
- guardar el periodo en la URL (`?periodo=dia&fecha=2026-10-14`, `?periodo=rango&desde=…&hasta=…`), para que recargar o compartir el enlace muestre lo mismo.

#### Scenario: Día concreto
- **WHEN** el admin elige el día 2026-10-14
- **THEN** todas las cifras cuentan solo lo ocurrido entre las 00:00 y las 23:59 de ese día, hora de Colombia

#### Scenario: Semana
- **WHEN** el admin elige la semana del 2026-10-12
- **THEN** el periodo va del lunes 12 al domingo 18 de octubre

#### Scenario: Rango inválido
- **WHEN** el rango pedido tiene más de 366 días, o el fin es anterior al inicio
- **THEN** el panel muestra el error junto al selector y no consulta

#### Scenario: Enlace compartido
- **WHEN** otro admin abre la URL con `?periodo=mes&fecha=2026-09`
- **THEN** ve la misma vista de septiembre de 2026

### Requirement: Comparación con el periodo anterior
Cada cifra del resumen SHALL mostrar su variación frente al periodo anterior del mismo largo (el día, la semana, el mes o el rango inmediatamente anterior), en valor absoluto y en porcentaje. Si el periodo anterior no tiene datos, MUST mostrar «sin datos para comparar» en lugar de un porcentaje.

#### Scenario: Variación del mes
- **WHEN** en septiembre se publicaron 400 vacantes y en octubre 500
- **THEN** octubre muestra 500 con «+100 (+25 %)»

#### Scenario: Periodo anterior vacío
- **WHEN** el periodo anterior es previo al primer dato guardado
- **THEN** la cifra muestra «sin datos para comparar»

### Requirement: Bajada de detalle
Los gráficos de tendencia SHALL agrupar por hora cuando el periodo es un día y por día cuando es una semana, un mes o un rango. Al pulsar un punto o una barra:
- en una semana, un mes o un rango, el panel pasa a ese día;
- en un día, pasa a la lista de vacantes de esa hora, o de esa fuente, categoría o tipo.

El detalle por hora y las listas de vacantes solo existen mientras se conserva el detalle (90 días para vacantes y 30 para corridas e IA). Fuera de ese plazo, el panel MUST mostrar «El detalle de este periodo ya se borró; quedan los totales diarios» y seguir mostrando los totales.

#### Scenario: Del mes al día
- **WHEN** el admin pulsa la barra del 14 en la vista de octubre
- **THEN** el panel pasa a la vista del día 2026-10-14

#### Scenario: Del día a la lista
- **WHEN** en la vista de un día el admin pulsa la barra de Computrabajo
- **THEN** ve la lista de las vacantes de Computrabajo de ese día, con título, empresa, categoría, tipo, modalidad, hora y enlace a la oferta

#### Scenario: Detalle ya borrado
- **WHEN** el admin pide las horas de un día de hace 120 días
- **THEN** ve los totales del día y el aviso de que el detalle ya se borró

### Requirement: Vista Resumen
La vista Resumen SHALL mostrar, para el periodo:
- vacantes publicadas en el canal;
- vacantes vistas (crudas);
- tasa de aceptación (publicadas sobre vistas);
- corridas con error;
- postulaciones creadas y terminadas con éxito;
- llamadas a la IA.

Cada cifra lleva su comparación con el periodo anterior y un minigráfico de su tendencia.

#### Scenario: Resumen del día
- **WHEN** el admin abre `/panel/` sin parámetros
- **THEN** ve las cifras de hoy, cada una con su variación frente a ayer

### Requirement: Vista Vacantes
La vista Vacantes SHALL mostrar las vacantes publicadas del periodo:
- por plataforma (LinkedIn, Computrabajo, elempleo, Magneto, GetOnBoard, SPE y las que se agreguen);
- por categoría (prácticas, desarrollo, infraestructura, bases de datos, soporte, datos, QA, ciberseguridad, otros TI);
- por tipo (practicante, aprendiz SENA, pasantía, trainee, intern, junior, otro);
- por modalidad (presencial, híbrida, remota, sin dato).

Incluye una tendencia apilada por plataforma y una tabla filtrable por plataforma, categoría, tipo y texto del título. Cada fila enlaza a la oferta. Los filtros de la tabla MUST combinarse con el periodo.

#### Scenario: Gráfico por plataforma y tipo
- **WHEN** el admin abre Vacantes para la semana actual
- **THEN** ve, por cada plataforma, cuántas publicadas fueron de cada tipo

#### Scenario: Filtrar la tabla
- **WHEN** el admin filtra la tabla por plataforma «magneto» y tipo «aprendiz SENA»
- **THEN** la tabla muestra solo esas vacantes del periodo, y el total coincide con el del gráfico

### Requirement: Vista Embudo del radar
La vista Embudo SHALL mostrar, sumado sobre las corridas del periodo:
- crudas;
- descartes por cada regla;
- duplicadas;
- dudosas;
- aceptadas y rechazadas por la IA;
- pendientes;
- enviadas.

También muestra el número de corridas y las que tuvieron error. Además lista cada fuente con su último éxito, sus fallos consecutivos y su cooldown vigente, si lo tiene.

#### Scenario: Descartes por regla
- **WHEN** en el periodo la regla de seniority descartó 120 vacantes
- **THEN** el embudo muestra «seniority: 120» entre los descartes

#### Scenario: Fuente en cooldown
- **WHEN** LinkedIn tiene cooldown hasta las 15:00
- **THEN** la lista de fuentes la marca «en pausa hasta 15:00»

### Requirement: Vista IA y costos
La vista IA SHALL mostrar, para el periodo, las llamadas, sus errores y los tokens de entrada y de salida de dos grupos: las tareas del radar (clasificador, reportero, resumen) y las tareas del asistente (leer CV, requisitos, adaptar CV, carta, responder, clasificar pregunta). Debe incluir el presupuesto diario configurado de cada tarea del radar. Los datos del asistente MUST mostrarse solo como totales por tarea, sin desglose por usuario.

#### Scenario: Uso del clasificador
- **WHEN** el clasificador hizo 80 llamadas el día elegido, con un tope de 300
- **THEN** la vista muestra «80 / 300» para el clasificador ese día

### Requirement: Solo lectura
Ninguna vista de este change SHALL cambiar datos ni configuración. Las rutas de datos de las estadísticas MUST aceptar solo GET.

#### Scenario: Método no permitido
- **WHEN** llega un POST a una ruta de estadísticas
- **THEN** responde 405
