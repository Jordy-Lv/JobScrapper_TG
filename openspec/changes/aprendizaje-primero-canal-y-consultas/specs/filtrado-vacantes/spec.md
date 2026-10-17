# Spec Delta

## ADDED Requirements

### Requirement: Nivel junior configurable y pausado por defecto
El alcance por nivel MUST configurarse en `alcance.junior.activo`, con valor `false` por defecto. Con el nivel pausado, una vacante aceptada por reglas o por la IA con una categoría distinta de «Prácticas y Aprendizaje» MUST descartarse con el motivo `nivel_pausado`. Con el nivel activo, MUST publicarse en su categoría por área, como antes.

#### Scenario: Junior pausado
- **WHEN** las reglas aceptan «Desarrollador Junior Python», remoto, con el nivel junior pausado
- **THEN** la vacante se descarta con el motivo `nivel_pausado` y no se publica

#### Scenario: Junior activo
- **WHEN** la misma vacante llega con `alcance.junior.activo: true`
- **THEN** se publica en «Desarrollo Junior»

#### Scenario: Práctica con el nivel pausado
- **WHEN** llega «Practicante de desarrollo de software» en Cartagena con el nivel junior pausado
- **THEN** se publica en «Prácticas y Aprendizaje»

### Requirement: El guardarraíl respeta el nivel pausado
Cuando el guardarraíl de prácticas saca una vacante de «Prácticas y Aprendizaje» y el nivel junior está pausado, la vacante MUST descartarse con el motivo `nivel_pausado` en lugar de publicarse en su área.

#### Scenario: Puesto profesional marcado como práctica
- **WHEN** la IA acepta «Ingeniero IBM Sterling B2B» como práctica, sin evidencia de práctica, con el nivel junior pausado
- **THEN** la vacante se descarta con el motivo `nivel_pausado`

### Requirement: Prompt del clasificador según el alcance
El prompt que recibe la IA MUST describir solo los niveles activos. Con el nivel junior pausado, MUST pedir que se acepten solo prácticas, pasantías, aprendizaje, contrato de aprendizaje y etapa productiva de TI. Un cambio de alcance MUST cambiar la versión del prompt, para que no se reutilicen clasificaciones hechas con otro alcance.

#### Scenario: Cambio de alcance
- **WHEN** el administrador enciende el nivel junior
- **THEN** las dudosas se clasifican de nuevo con el prompt que incluye junior, sin usar la caché del prompt anterior

### Requirement: Más evidencia de práctica
El guardarraíl de prácticas MUST aceptar como evidencia en el título, además de los términos actuales: «SENA», «semillero», «programa de talento», «práctica universitaria», «estudiante en práctica» y «en formación». Los términos MUST ser configurables.

#### Scenario: Título con SENA sin «aprendiz»
- **WHEN** la IA acepta como práctica «Tecnólogo SENA en Análisis y Desarrollo de Software»
- **THEN** el guardarraíl la deja en «Prácticas y Aprendizaje»

### Requirement: Los años de la empresa no cuentan como experiencia exigida
La regla de años de experiencia MUST ignorar las frases que hablan de la trayectoria de la empresa o de la duración del contrato o del programa. Por ejemplo: «empresa con más de 20 años de experiencia», «trayectoria de 15 años en el sector», «contrato de aprendizaje por 2 años».

#### Scenario: Trayectoria de la empresa
- **WHEN** la descripción de «Aprendiz SENA sistemas» dice «somos una empresa con más de 20 años de experiencia en el sector»
- **THEN** la vacante no se rechaza por seniority

#### Scenario: Experiencia exigida
- **WHEN** la descripción de «Practicante de soporte» dice «experiencia mínima de 2 años en soporte»
- **THEN** la vacante se rechaza por seniority

### Requirement: Un término de seniority en una práctica no rechaza sin la IA
Si el título tiene evidencia de práctica y también un término de seniority, la vacante MUST NOT rechazarse por reglas: MUST quedar dudosa para que decida la IA. Los años de experiencia exigidos siguen rechazando.

#### Scenario: Práctica en un área de coordinación
- **WHEN** llega «Practicante Coordinador de Proyectos TI»
- **THEN** la vacante queda dudosa y decide la IA

### Requirement: «Práctica sin TI» solo con la descripción completa
Una práctica sin nada de TI en el título ni en la descripción MUST rechazarse sin la IA solo si la descripción es completa: viene del detalle de la oferta o tiene al menos `filtros.min_caracteres_descripcion_completa` caracteres (400 por defecto). Con un fragmento más corto, MUST quedar dudosa.

#### Scenario: Fragmento corto de elempleo
- **WHEN** llega de elempleo «Aprendiz SENA» con un fragmento de 120 caracteres sin términos de TI
- **THEN** la vacante queda dudosa y decide la IA

#### Scenario: Descripción completa sin TI
- **WHEN** llega de Magneto «Aprendiz SENA» con 1.200 caracteres de descripción sobre bodega y despachos
- **THEN** la vacante se rechaza por no ser TI, sin la IA

### Requirement: Las prácticas dudosas esperan más a la IA
Una dudosa con evidencia de práctica en el título MUST esperar a la IA hasta `clasificador.horas_vencimiento_practicas` (72 por defecto) antes de vencer, en lugar de las 24 h de las demás. Al vencer, MUST quedar registrada como descarte de la etapa «vencida».

#### Scenario: DeepSeek caído un día
- **WHEN** DeepSeek falla durante 30 h seguidas y hay una dudosa «Aprendiz SENA» pendiente
- **THEN** la dudosa sigue pendiente y se clasifica cuando DeepSeek vuelve

#### Scenario: Vencimiento
- **WHEN** una práctica dudosa lleva 73 h sin clasificarse
- **THEN** sale de la cola y queda en los descartes con etapa «vencida»
