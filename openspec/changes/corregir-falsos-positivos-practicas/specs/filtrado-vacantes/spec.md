# Spec Delta

## MODIFIED Requirements

### Requirement: Veredicto aceptar, rechazar o dudosa
El sistema SHALL asignar a cada vacante exactamente un veredicto, aplicando las reglas en este orden sobre el título y, si existe, el fragmento de descripción (salvo los términos de seniority, los disparadores de dudosa y las áreas no TI, que se evalúan solo en el título):
1. **rechazar** si el **título** contiene un término de seniority excluido (`senior`, `sr`, `semi senior`, `ssr`, `lead`, `líder`, `gerente`, `manager`, `director`, `jefe`, `arquitecto`, `architect`, `head`, `coordinador`, `especialista`), o si el título o la descripción piden experiencia de 3 o más años. Los términos de seniority no se buscan en la descripción porque frases como "reportarás al líder técnico" descartarían vacantes junior válidas; si en operación se cuelan vacantes senior, se endurece la regla para ese caso.
2. **rechazar** si tiene más de 15 días de publicada, cuando la fecha es conocida.
3. **rechazar** si está fuera del alcance geográfico.
4. **aceptar** si el **título** contiene al menos un término técnico de TI, hay al menos un término de nivel práctica/aprendiz/junior/entrada (en el título o la descripción) y el título no menciona un área que no es de TI. Si lo técnico solo aparece en la descripción, o el título menciona un área no TI (como en "Programador de mantenimiento"), la vacante pasa a dudosa. También pasa a dudosa, en lugar de aceptarse, si el título no tiene un término de nivel práctica y el menor valor del salario publicado supera el salario máximo de entrada configurado (4.500.000 COP por defecto): un sueldo así suele indicar un cargo que no es de entrada, y lo decide la IA.
5. **rechazar** si no contiene ningún término técnico de TI ni ningún término de los que hacen dudosa una vacante. Excepción: si el **título** contiene un término de nivel práctica (practicante, aprendiz, pasante, pasantía, práctica, trainee, intern, becario, estudiante…), la vacante MUST pasar a dudosa en lugar de rechazarse, aunque el título nombre un área no TI, para que la IA decida según sus funciones.
6. **dudosa** en cualquier otro caso.

Las listas de términos MUST ser configurables.

#### Scenario: Senior descartado
- **WHEN** el título es "Desarrollador Java Senior"
- **THEN** el veredicto es rechazar por seniority

#### Scenario: Seniority solo en la descripción
- **WHEN** el título es "Desarrollador Junior" y la descripción dice "trabajarás con el líder técnico y el manager del equipo"
- **THEN** la regla de seniority no lo rechaza

#### Scenario: Experiencia alta en la descripción
- **WHEN** el título es "Desarrollador Junior" y la descripción pide "4 años de experiencia"
- **THEN** el veredicto es rechazar por seniority

#### Scenario: Caso claro aceptado
- **WHEN** el título es "Aprendiz SENA Desarrollo de Software"
- **THEN** el veredicto es aceptar

#### Scenario: Fuera de TI sin nivel de práctica
- **WHEN** el título es "Auxiliar Contable"
- **THEN** el veredicto es rechazar por no ser TI

#### Scenario: Práctica de un área no TI la decide la IA
- **WHEN** el título es "Practicante Contable"
- **THEN** el veredicto es dudosa y lo decide la IA (que la rechaza si sus funciones no son de TI)

#### Scenario: Práctica de otra área con funciones de TI
- **WHEN** el título es "Practicante administrativo" y la descripción pide construir tableros en Power BI y consultas SQL
- **THEN** el veredicto de las reglas es dudosa y la IA puede aceptarla en prácticas

#### Scenario: TI solo en la descripción
- **WHEN** el título es "Auxiliar logístico" y la descripción menciona "manejo de sistemas"
- **THEN** el veredicto es dudosa y lo decide la IA

#### Scenario: Término de TI junto a un área no TI
- **WHEN** el título es "Programador de Mantenimiento Junior"
- **THEN** el veredicto es dudosa y lo decide la IA

#### Scenario: Caso ambiguo
- **WHEN** el título es "Practicante" sin área, o "Analista de Procesos" sin nivel
- **THEN** el veredicto es dudosa

#### Scenario: Salario por encima del de entrada
- **WHEN** el título es "Analista de analítica", la descripción dice "tecnólogo graduado o estudiante de últimos semestres" y el salario es "$4.700.000"
- **THEN** el veredicto es dudosa y lo decide la IA

#### Scenario: Práctica con salario alto
- **WHEN** el título es "Practicante de Desarrollo de Software" y el salario es "$5.000.000"
- **THEN** el veredicto es aceptar, porque el título ya indica nivel práctica

#### Scenario: Vacante antigua
- **WHEN** la vacante tiene fecha de publicación de hace 20 días
- **THEN** el veredicto es rechazar por antigüedad

### Requirement: Categorías de publicación
El sistema SHALL asignar cada vacante aceptada a una categoría:
- "Prácticas y Aprendizaje": cualquier rol de TI con nivel práctica, pasantía, aprendiz, trainee o etapa productiva.
- Para el nivel junior/entrada, una categoría por área: "Desarrollo", "Infraestructura / DevOps / Cloud", "Bases de datos", "Soporte IT", "Datos y Analítica", "QA / Testing", "Ciberseguridad" y "Otros TI".

Si una vacante tiene a la vez nivel aprendiz y área, va a "Prácticas y Aprendizaje". El nivel aprendiz se reconoce por un término de nivel práctica en el **título**, o por un término **fuerte** de aprendizaje en la descripción (contrato de aprendizaje, etapa productiva, etapa práctica, aprendiz, practicante, pasante, pasantía, cuota SENA), configurable. Los términos débiles en la descripción ("estudiante", "semillero", "prácticas", "programa de talento") MUST NOT bastar para la categoría Prácticas, porque aparecen en empleos normales que aceptan estudiantes. Para las aceptadas por reglas, la categoría se decide por los términos que coinciden; si coinciden varias áreas, gana la primera según el orden configurado. Para las aceptadas por la IA, se usa la categoría que propone la IA si es válida y, si no, la que corresponde por términos.

#### Scenario: DevOps junior
- **WHEN** el título es "Analista Jr CloudOps (SysOps AWS)"
- **THEN** la categoría es Infraestructura / DevOps / Cloud

#### Scenario: Aprendiz de datos
- **WHEN** el título es "Aprendiz Análisis de Datos"
- **THEN** la categoría es Prácticas y Aprendizaje

#### Scenario: Soporte junior
- **WHEN** el título es "Técnico de Soporte IT Junior"
- **THEN** la categoría es Soporte IT

#### Scenario: Aprendiz reconocido por la descripción
- **WHEN** el título es "Auxiliar de sistemas" y la descripción dice "contrato de aprendizaje SENA, etapa productiva"
- **THEN** la categoría es Prácticas y Aprendizaje

#### Scenario: "Estudiante" en la descripción no es práctica
- **WHEN** el título es "Analista de datos" y la descripción dice "tecnólogo graduado o estudiante de últimos semestres"
- **THEN** la categoría es Datos y Analítica, no Prácticas

### Requirement: Clasificación IA de vacantes dudosas
El sistema SHALL enviar a la IA todas las vacantes dudosas de una corrida en una sola llamada por lote, hasta el máximo de vacantes por llamada configurado. Por cada vacante envía título, empresa, ubicación, modalidad, salario, palabra clave, fragmento de descripción si existe, indicación de si la fuente ya filtró por nivel de experiencia (como LinkedIn con prácticas y nivel de entrada) y el área no TI detectada en el título, si la hay (`area_no_ti_en_titulo`). Si el título no indica el nivel, la IA MUST aceptarla solo cuando haya evidencia de que es práctica o junior (filtro de nivel de la fuente, descripción o salario). Una vacante de aprendiz SENA genérica, cuyo título no nombra un área ("Aprendiz SENA", "Aprendiz SENA Cali", "Contrato de aprendizaje"), MUST aceptarse con categoría prácticas aunque no mencione TI, salvo que el título o la descripción indiquen un área o tareas que no son de TI (salud, farmacia, mecánica, retail, ventas, atención al cliente, tareas administrativas u operativas, etc.). La excepción aplica solo a aprendices SENA o de contrato de aprendizaje cuyo título no nombra ningún área: si `area_no_ti_en_titulo` trae un valor ("Aprendiz administrativa"), la excepción MUST NOT aplicarse y la vacante se acepta solo si sus funciones principales son de TI. Un practicante sin área sigue la regla general. La IA MUST responder por cada vacante si se acepta, su categoría y un motivo breve. La IA MUST NOT recibir tokens, claves, cookies, ids de chat ni otros datos sensibles. La IA solo clasifica: no scrapea, no envía mensajes ni modifica configuración.

#### Scenario: Dudosas clasificadas
- **WHEN** una corrida produce 5 vacantes dudosas
- **THEN** se hace una sola llamada a la IA con las 5 y se envían las que la IA acepta

#### Scenario: Sin dudosas
- **WHEN** una corrida no produce vacantes dudosas
- **THEN** no se llama a la IA para clasificar

#### Scenario: Aprendiz SENA genérico
- **WHEN** el título es "Aprendiz SENA Candelaria Cali" y ni el título ni la descripción nombran un área
- **THEN** la IA la acepta en la categoría prácticas

#### Scenario: Aprendiz SENA de otra área
- **WHEN** el título es "Aprendiz SENA - Villavicencio" y la descripción es de un cargo de salud
- **THEN** la IA la rechaza

#### Scenario: Aprendiz con área no TI en el título
- **WHEN** el título es "aprendiz administrativa" y la descripción no muestra funciones de TI
- **THEN** la vacante llega a la IA con `area_no_ti_en_titulo` = "administrativa" y la IA la rechaza
