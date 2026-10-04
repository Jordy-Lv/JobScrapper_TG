# Spec Delta

## Purpose

Decidir qué vacantes crudas son prácticas, aprendizaje o junior de TI dentro del alcance geográfico. Reglas deterministas resuelven los casos claros y la IA desempata solo los dudosos, para igualar o superar el criterio de Hermes.

## ADDED Requirements

### Requirement: Normalización de texto para filtrar
El sistema SHALL comparar términos sobre texto en minúsculas, sin tildes y con límites de palabra, para que términos cortos como `sr` o `ti` no coincidan dentro de otras palabras.

#### Scenario: Límite de palabra
- **WHEN** el título es "Practicante de Sistemas en Srta. Group"
- **THEN** no se considera que contenga el término de seniority `sr`

#### Scenario: Tildes
- **WHEN** el título es "Práctica profesional Tecnología"
- **THEN** coincide con los términos `practica` y `tecnologia`

### Requirement: Veredicto aceptar, rechazar o dudosa
El sistema SHALL asignar a cada vacante exactamente un veredicto, aplicando las reglas en este orden sobre el título y, si existe, el fragmento de descripción (salvo los términos de seniority, los disparadores de dudosa y las áreas no TI, que se evalúan solo en el título):
1. **rechazar** si el **título** contiene un término de seniority excluido (`senior`, `sr`, `semi senior`, `ssr`, `lead`, `líder`, `gerente`, `manager`, `director`, `jefe`, `arquitecto`, `architect`, `head`, `coordinador`, `especialista`), o si el título o la descripción piden experiencia de 3 o más años. Los términos de seniority no se buscan en la descripción porque frases como "reportarás al líder técnico" descartarían vacantes junior válidas; si en operación se cuelan vacantes senior, se endurece la regla para ese caso.
2. **rechazar** si tiene más de 15 días de publicada, cuando la fecha es conocida.
3. **rechazar** si está fuera del alcance geográfico.
4. **aceptar** si el **título** contiene al menos un término técnico de TI, hay al menos un término de nivel práctica/aprendiz/junior/entrada (en el título o la descripción) y el título no menciona un área que no es de TI. Si lo técnico solo aparece en la descripción, o el título menciona un área no TI (como en "Programador de mantenimiento"), la vacante pasa a dudosa.
5. **rechazar** si no contiene ningún término técnico de TI ni ningún término de los que hacen dudosa una vacante.
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

#### Scenario: Fuera de TI
- **WHEN** el título es "Practicante Contable"
- **THEN** el veredicto es rechazar por no ser TI

#### Scenario: TI solo en la descripción
- **WHEN** el título es "Auxiliar logístico" y la descripción menciona "manejo de sistemas"
- **THEN** el veredicto es dudosa y lo decide la IA

#### Scenario: Término de TI junto a un área no TI
- **WHEN** el título es "Programador de Mantenimiento Junior"
- **THEN** el veredicto es dudosa y lo decide la IA

#### Scenario: Caso ambiguo
- **WHEN** el título es "Practicante" sin área, o "Analista de Procesos" sin nivel
- **THEN** el veredicto es dudosa

#### Scenario: Vacante antigua
- **WHEN** la vacante tiene fecha de publicación de hace 20 días
- **THEN** el veredicto es rechazar por antigüedad

### Requirement: Alcance geográfico Colombia más remoto LATAM
El sistema SHALL aceptar vacantes ubicadas en cualquier ciudad de Colombia y vacantes remotas abiertas a Colombia o a LATAM publicadas en español. Las vacantes presenciales o híbridas fuera de Colombia, y las remotas restringidas a otros países, MUST rechazarse. Una vacante remota sin indicación de país MUST quedar como dudosa en lugar de aceptarse directamente.

#### Scenario: Ciudad colombiana
- **WHEN** la ubicación es "Cartagena, Bolívar"
- **THEN** pasa el filtro geográfico

#### Scenario: Remoto restringido a otro país
- **WHEN** la vacante es "Remoto - solo residentes en México"
- **THEN** se rechaza por ubicación

#### Scenario: Presencial en el exterior
- **WHEN** la ubicación es "Lima, Perú (Presencial)"
- **THEN** se rechaza por ubicación

### Requirement: Clasificación IA de vacantes dudosas
El sistema SHALL enviar a la IA todas las vacantes dudosas de una corrida en una sola llamada por lote, hasta el máximo de vacantes por llamada configurado. Por cada vacante envía título, empresa, ubicación, modalidad, salario, palabra clave, fragmento de descripción si existe e indicación de si la fuente ya filtró por nivel de experiencia (como LinkedIn con prácticas y nivel de entrada). Si el título no indica el nivel, la IA MUST aceptarla solo cuando haya evidencia de que es práctica o junior (filtro de nivel de la fuente, descripción o salario). Una vacante de aprendiz SENA genérica, cuyo título no nombra un área ("Aprendiz SENA", "Aprendiz SENA Cali", "Contrato de aprendizaje"), MUST aceptarse con categoría prácticas aunque no mencione TI, salvo que el título o la descripción indiquen un área o tareas que no son de TI (salud, farmacia, mecánica, retail, ventas, atención al cliente, tareas administrativas u operativas, etc.). La excepción aplica solo a aprendices SENA o de contrato de aprendizaje: un practicante sin área sigue la regla general. La IA MUST responder por cada vacante si se acepta, su categoría y un motivo breve. La IA MUST NOT recibir tokens, claves, cookies, ids de chat ni otros datos sensibles. La IA solo clasifica: no scrapea, no envía mensajes ni modifica configuración.

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

### Requirement: Caché de clasificaciones
El sistema SHALL guardar el veredicto de la IA asociado a la huella de la vacante (título y empresa normalizados) y reutilizarlo. La misma vacante dudosa MUST NOT enviarse a la IA más de una vez, aunque aparezca en otra fuente o en otra corrida.

#### Scenario: Vacante repetida en otra fuente
- **WHEN** una vacante dudosa ya clasificada aparece de nuevo en otra fuente
- **THEN** se usa el veredicto guardado sin llamar a la IA

### Requirement: Respaldo cuando la IA no clasifica
Si la IA falla, responde con datos inválidos o incompletos, o ya se alcanzó el máximo de llamadas diarias del clasificador, las vacantes dudosas afectadas MUST quedar pendientes y reintentarse en corridas siguientes. Una dudosa que siga sin clasificar después de 24 h MUST descartarse y registrarse en el log. En ningún caso la falla del clasificador MUST retrasar o impedir el envío de las vacantes aceptadas.

#### Scenario: IA caída
- **WHEN** la llamada de clasificación falla por timeout
- **THEN** las vacantes aceptadas por reglas se envían igual y las dudosas quedan pendientes para la próxima corrida

#### Scenario: Pendiente vencida
- **WHEN** una dudosa lleva más de 24 h pendiente
- **THEN** se descarta y queda registrada como no clasificada

#### Scenario: Clasificador desactivado
- **WHEN** el clasificador IA está desactivado en la configuración
- **THEN** las dudosas se tratan según la política configurada (descartar por defecto) sin llamar a la IA

### Requirement: Cobertura de todos los roles de TI en nivel aprendiz y junior
El sistema SHALL cubrir vacantes de nivel práctica, pasantía, aprendiz (incluido SENA), trainee, junior y entrada en **todos los roles de TI**, no solo desarrollo. Esto incluye como mínimo: desarrollo de software (backend, frontend, fullstack, móvil), infraestructura, DevOps, cloud y sysadmin, redes y telecomunicaciones, bases de datos (DBA), soporte IT y mesa de ayuda, análisis de datos, BI e ingeniería de datos, QA y testing, ciberseguridad, y análisis de sistemas y de TI. Las listas de términos técnicos y de nivel MUST incluir los términos de cada uno de estos roles, en español y en inglés (por ejemplo `dba`, `base de datos`, `sql`, `data analyst`, `power bi`, `soc`, `redes`, `helpdesk`).

#### Scenario: DBA junior
- **WHEN** el título es "DBA Junior SQL Server"
- **THEN** el veredicto es aceptar

#### Scenario: Análisis de datos junior
- **WHEN** el título es "Analista de Datos Jr - Power BI"
- **THEN** el veredicto es aceptar

#### Scenario: Aprendiz en rol no de desarrollo
- **WHEN** el título es "Aprendiz SENA Soporte de Redes"
- **THEN** el veredicto es aceptar

#### Scenario: Junior sin área
- **WHEN** el título es "Analista Junior" sin otro término técnico
- **THEN** el veredicto es dudosa y lo decide la IA

### Requirement: Categorías de publicación
El sistema SHALL asignar cada vacante aceptada a una categoría:
- "Prácticas y Aprendizaje": cualquier rol de TI con nivel práctica, pasantía, aprendiz, trainee o etapa productiva.
- Para el nivel junior/entrada, una categoría por área: "Desarrollo", "Infraestructura / DevOps / Cloud", "Bases de datos", "Soporte IT", "Datos y Analítica", "QA / Testing", "Ciberseguridad" y "Otros TI".

Si una vacante tiene a la vez nivel aprendiz y área, va a "Prácticas y Aprendizaje". Para las aceptadas por reglas, la categoría se decide por los términos que coinciden; si coinciden varias áreas, gana la primera según el orden configurado. Para las aceptadas por la IA, se usa la categoría que propone la IA si es válida y, si no, la que corresponde por términos.

#### Scenario: DevOps junior
- **WHEN** el título es "Analista Jr CloudOps (SysOps AWS)"
- **THEN** la categoría es Infraestructura / DevOps / Cloud

#### Scenario: Aprendiz de datos
- **WHEN** el título es "Aprendiz Análisis de Datos"
- **THEN** la categoría es Prácticas y Aprendizaje

#### Scenario: Soporte junior
- **WHEN** el título es "Técnico de Soporte IT Junior"
- **THEN** la categoría es Soporte IT

### Requirement: Métricas de descarte
El sistema SHALL registrar en cada corrida cuántas vacantes descartó cada regla (seniority, antigüedad, ubicación, no TI), cuántas fueron dudosas, cuántas aceptó o rechazó la IA y cuántas quedaron pendientes.

#### Scenario: Conteo por filtro
- **WHEN** termina una corrida
- **THEN** el log incluye un conteo por cada regla de descarte y por cada resultado del clasificador
