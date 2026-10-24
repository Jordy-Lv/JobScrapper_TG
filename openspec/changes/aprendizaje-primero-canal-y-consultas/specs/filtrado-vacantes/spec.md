# Spec Delta

## ADDED Requirements

### Requirement: Alcance de prácticas y sin experiencia, con junior pausado por defecto
El alcance por nivel MUST configurarse en `alcance.junior.activo`, con valor `false` por defecto. Cada vacante MUST tener un nivel: `practica`, `sin_experiencia`, `junior` u `otro`. Con el nivel junior pausado, una vacante aceptada por reglas o por la IA cuyo nivel no sea `practica` ni `sin_experiencia` MUST descartarse con el motivo `nivel_pausado`. Con el nivel activo, MUST publicarse en su categoría por área, como antes.

#### Scenario: Junior pausado
- **WHEN** las reglas aceptan «Desarrollador Junior Python», remoto, con el nivel junior pausado
- **THEN** la vacante se descarta con el motivo `nivel_pausado` y no se publica

#### Scenario: Junior activo
- **WHEN** la misma vacante llega con `alcance.junior.activo: true`
- **THEN** se publica en «Desarrollo Junior»

#### Scenario: Práctica con el nivel pausado
- **WHEN** llega «Practicante de desarrollo de software» en Cartagena con el nivel junior pausado
- **THEN** se publica en «Prácticas y Aprendizaje»

#### Scenario: Sin experiencia dentro del alcance
- **WHEN** llega «Soporte técnico sin experiencia», remoto, sin años de experiencia exigidos, con el nivel junior pausado
- **THEN** su nivel es `sin_experiencia` y se publica en «Prácticas y Aprendizaje»

#### Scenario: Sin experiencia y junior en el mismo título
- **WHEN** llega «Desarrollador Junior (sin experiencia)» sin años exigidos
- **THEN** su nivel es `sin_experiencia`, no `junior`

### Requirement: «Sin experiencia» es un nivel propio
Los términos de «sin experiencia» («sin experiencia», «no requiere experiencia», «primer empleo», «recién egresado», «recién graduado», «nivel de entrada») MUST vivir en un grupo propio, `filtros.nivel.sin_experiencia`, separado de `filtros.nivel.junior`. Apagar el nivel junior MUST NOT apagarlos. Una vacante cuenta como `sin_experiencia` solo si no exige años de experiencia.

#### Scenario: Sin experiencia que exige años
- **WHEN** llega «Auxiliar de sistemas, sin experiencia en la herramienta» con «mínimo 2 años de experiencia en soporte» en la descripción
- **THEN** la vacante no es `sin_experiencia` y se rechaza por los años exigidos

### Requirement: El guardarraíl respeta el nivel pausado
Cuando el guardarraíl de prácticas saca una vacante de «Prácticas y Aprendizaje» y el nivel junior está pausado, la vacante MUST descartarse con el motivo `nivel_pausado` en lugar de publicarse en su área. El guardarraíl MUST tratar la evidencia de «sin experiencia» en el título como evidencia válida y no sacar la vacante de la categoría.

#### Scenario: Puesto profesional marcado como práctica
- **WHEN** la IA acepta «Ingeniero IBM Sterling B2B» como práctica, sin evidencia de práctica, con el nivel junior pausado
- **THEN** la vacante se descarta con el motivo `nivel_pausado`

### Requirement: Prompt del clasificador según el alcance
El prompt que recibe la IA MUST describir solo los niveles activos. Con el nivel junior pausado, MUST pedir que se acepten solo prácticas, pasantías, aprendizaje, contrato de aprendizaje, etapa productiva y vacantes sin experiencia (0 años) de TI. Un cambio de alcance MUST cambiar la versión del prompt, para que no se reutilicen clasificaciones hechas con otro alcance.

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

### Requirement: Nivel de la regla 5 solo en el título o con evidencia fuerte
La regla de aceptación sin IA MUST aceptar una vacante únicamente si el término de nivel está en el título, o si la descripción trae evidencia fuerte (`filtros.nivel.evidencia_practica_descripcion` o un término de «sin experiencia»). En cualquier otro caso MUST quedar dudosa.

#### Scenario: «Mejores prácticas» en la descripción
- **WHEN** llega «Desarrollador Java» con «mejores prácticas de desarrollo» en la descripción
- **THEN** la vacante queda dudosa y no se acepta por reglas

### Requirement: Frases que no indican nivel
`filtros.frases_ignoradas` MUST incluir «mejores prácticas», «prácticas de desarrollo», «prácticas ágiles» y «equipo junior»: esas frases solas MUST NOT dar nivel. «Auxiliar» MUST dejar de contar como nivel junior y MUST quedar solo como disparador de vacante dudosa.

#### Scenario: Auxiliar con años exigidos
- **WHEN** llega «Auxiliar de sistemas» con «2 años de experiencia» en la descripción
- **THEN** la vacante se rechaza por los años exigidos

### Requirement: Detección de años de experiencia en más formas
La regla de años de experiencia MUST reconocer los años escritos en letra («dos años»), la experiencia en meses (12 o más cuenta como un año o más) y el patrón «Experiencia:» seguido de un salto de línea con el número en la línea siguiente.

#### Scenario: Años en letra
- **WHEN** la descripción dice «experiencia mínima de dos años en soporte»
- **THEN** la vacante se rechaza por los años exigidos

#### Scenario: Meses
- **WHEN** la descripción dice «24 meses de experiencia»
- **THEN** la vacante se rechaza; con «18 meses» también, y con «6 meses» no

#### Scenario: Número en la línea siguiente
- **WHEN** la descripción dice «Experiencia:» y el número «2 años» en la línea siguiente
- **THEN** la vacante se rechaza por los años exigidos

### Requirement: Umbral de experiencia con el nivel junior pausado
Con el nivel junior pausado, la regla de años MUST rechazar a partir de 1 año de experiencia exigida, en lugar del umbral anterior. MUST aceptar hasta 6 meses y la experiencia descrita como «deseable» u «opcional». En un rango MUST contar el mínimo: «1 a 3 años» se rechaza. Con el nivel activo, MUST regir el umbral anterior.

#### Scenario: Experiencia deseable
- **WHEN** llega «Aprendiz de soporte» con «6 meses de experiencia deseable» en la descripción
- **THEN** la vacante no se rechaza por experiencia

#### Scenario: Un año exigido
- **WHEN** llega «Practicante de sistemas» con «1 año de experiencia» exigido
- **THEN** la vacante se rechaza por los años exigidos

#### Scenario: Rango
- **WHEN** la descripción pide «de 1 a 3 años de experiencia»
- **THEN** la vacante se rechaza

### Requirement: Área y nivel de cada vacante aceptada
Una vacante aceptada MUST conservar, además de su categoría, el área de TI detectada y su nivel (`practica`, `sin_experiencia`, `junior` u `otro`). Para una práctica, el área MUST detectarse igual que para las demás: «Aprendiz de desarrollo» tiene categoría «Prácticas y Aprendizaje» y área «desarrollo».

#### Scenario: Aprendiz de desarrollo
- **WHEN** se acepta «Aprendiz de desarrollo de software»
- **THEN** su categoría es «Prácticas y Aprendizaje», su área es «desarrollo» y su nivel es `practica`
