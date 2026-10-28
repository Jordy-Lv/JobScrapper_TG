# filtrado-vacantes Specification

## Purpose
Decidir qué vacantes crudas son prácticas, aprendizaje o junior de TI dentro del alcance geográfico. Reglas deterministas resuelven los casos claros y la IA desempata solo los dudosos, para igualar o superar el criterio de Hermes.

## Requirements

### Requirement: Normalización de texto para filtrar
El sistema SHALL comparar términos sobre texto en minúsculas, sin tildes y con límites de palabra, para que términos cortos como `sr` o `ti` no coincidan dentro de otras palabras.

#### Scenario: Límite de palabra
- **WHEN** el título es "Practicante de Sistemas en Srta. Group"
- **THEN** no se considera que contenga el término de seniority `sr`

#### Scenario: Tildes
- **WHEN** el título es "Práctica profesional Tecnología"
- **THEN** coincide con los términos `practica` y `tecnologia`

### Requirement: Veredicto aceptar, rechazar o dudosa
El sistema SHALL asignar a cada vacante exactamente un veredicto. Las reglas se aplican en este orden sobre el título y, si existe, el fragmento de descripción. Los términos de seniority, los disparadores de dudosa, las áreas no TI, los términos de call center y las palabras de la lista negra se evalúan solo en el título:
0. **rechazar** por lista negra si la empresa coincide con una empresa de la lista negra o el título contiene una palabra de la lista negra.
1. **rechazar** por seniority si el **título** contiene un término de seniority excluido (`senior`, `sr`, `semi senior`, `ssr`, `lead`, `líder`, `gerente`, `manager`, `director`, `jefe`, `arquitecto`, `architect`, `head`, `coordinador`, `especialista`, `middle`). También si el título o la descripción piden **2 o más años** de experiencia. Los términos de seniority no se buscan en la descripción porque frases como «reportarás al líder técnico» descartarían vacantes junior válidas.
2. **rechazar** si tiene más de 15 días de publicada, cuando la fecha es conocida.
3. **rechazar** si está fuera del alcance geográfico o si es soporte de call center que no es remoto (ver los requisitos «Alcance geográfico con ciudad base» y «Soporte de call center solo remoto»).
4. **rechazar** por no TI si el título contiene un término de nivel práctica, la vacante **trae descripción** y ni el título ni la descripción tienen ningún término técnico de TI. Sin descripción no hay con qué afirmarlo: la vacante sigue su curso y, si no cae en otra regla, queda dudosa para la IA.
5. **aceptar** si se cumplen las tres condiciones:
   - el **título** contiene al menos un término técnico de TI;
   - hay al menos un término de nivel práctica/aprendiz/junior/entrada, en el título o en la descripción;
   - el título no menciona un área que no es de TI.

   Si se cumplen pero la modalidad debe confirmarse (ver «Alcance geográfico con ciudad base»), la vacante pasa a dudosa. Si lo técnico solo aparece en la descripción, o el título menciona un área no TI (como en «Programador de mantenimiento»), la vacante también pasa a dudosa.
6. **rechazar** si no contiene ningún término técnico de TI ni ningún término de los que hacen dudosa una vacante.
7. **dudosa** en cualquier otro caso.

Las listas de términos, la lista negra y el umbral de años MUST ser configurables.

#### Scenario: Senior descartado
- **WHEN** el título es "Desarrollador Java Senior"
- **THEN** el veredicto es rechazar por seniority

#### Scenario: Seniority solo en la descripción
- **WHEN** el título es "Desarrollador Junior" y la descripción dice "trabajarás con el líder técnico y el manager del equipo"
- **THEN** la regla de seniority no lo rechaza

#### Scenario: Experiencia alta en la descripción
- **WHEN** el título es "Profesional QA" y la descripción pide "2 años de experiencia en pruebas"
- **THEN** el veredicto es rechazar por seniority

#### Scenario: Un año de experiencia
- **WHEN** el título es "Técnico soporte TI Nivel 1 Junior" en Cartagena y la descripción pide "1 año de experiencia"
- **THEN** la regla de seniority no lo rechaza

#### Scenario: Empresa en la lista negra
- **WHEN** la lista negra incluye la empresa "Magneto empleos" y llega "Promotor(a) Junior de Tecnología" de "Magneto empleos"
- **THEN** el veredicto es rechazar por lista negra

#### Scenario: Caso claro aceptado
- **WHEN** el título es "Aprendiz SENA Desarrollo de Software" y la ubicación es "Cartagena, Bolívar"
- **THEN** el veredicto es aceptar

#### Scenario: Fuera de TI
- **WHEN** el título es "Auxiliar Contable"
- **THEN** el veredicto es rechazar por no ser TI

#### Scenario: Práctica sin nada de TI, con descripción
- **WHEN** el título es "Aprendiz etapa productiva" o "Practicante Contable", la vacante trae descripción y ni el título ni la descripción tienen un término técnico de TI
- **THEN** el veredicto es rechazar por no ser TI, sin llamar a la IA

#### Scenario: Práctica de un área no TI la decide la IA
- **WHEN** el título es "Aprendiz etapa productiva" o "Practicante Contable" y la vacante no trae descripción
- **THEN** no se rechaza por no ser TI: el veredicto es dudosa y la decide la IA

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
- **WHEN** el título es "Analista de Procesos" sin nivel
- **THEN** el veredicto es dudosa

#### Scenario: Vacante antigua
- **WHEN** la vacante tiene fecha de publicación de hace 20 días
- **THEN** el veredicto es rechazar por antigüedad

### Requirement: Alcance geográfico Colombia más remoto LATAM
El sistema SHALL aceptar vacantes remotas abiertas a Colombia o a LATAM publicadas en español, vacantes híbridas en cualquier ciudad de Colombia y vacantes presenciales en la ciudad base (ver «Alcance geográfico con ciudad base»). Las vacantes presenciales o híbridas fuera de Colombia, y las remotas restringidas a otros países, MUST rechazarse. Una vacante remota sin indicación de país MUST quedar como dudosa en lugar de aceptarse directamente.

#### Scenario: Ciudad colombiana
- **WHEN** la ubicación es "Cartagena, Bolívar" y la modalidad es presencial
- **THEN** pasa el filtro geográfico

#### Scenario: Remoto restringido a otro país
- **WHEN** la vacante es "Remoto - solo residentes en México"
- **THEN** se rechaza por ubicación

#### Scenario: Presencial en el exterior
- **WHEN** la ubicación es "Lima, Perú (Presencial)"
- **THEN** se rechaza por ubicación

### Requirement: Clasificación IA de vacantes dudosas
El sistema SHALL enviar a la IA todas las vacantes dudosas de una corrida, agrupadas en lotes de hasta el máximo de vacantes por llamada configurado. Por cada vacante envía:
- título, empresa, ubicación, modalidad, salario y palabra clave;
- el fragmento de descripción, si existe;
- la ciudad base;
- la condición de modalidad que debe confirmar, si la hay: «remoto o híbrido» o «solo remoto».

La IA MUST NOT recibir ninguna indicación de que la fuente filtró por nivel, porque un filtro de seniority de la fuente («Entry level») no prueba que la vacante sea práctica ni junior.

**Nivel.** Si el título no indica el nivel, la IA MUST aceptarla solo cuando el anuncio dé evidencia de práctica, junior o hasta 1 año de experiencia. La experiencia que pide el anuncio manda sobre el salario. El salario solo sirve de apoyo cuando el anuncio no dice nada de experiencia ni de nivel: un salario alto es indicio de que no es junior, y un salario bajo nunca basta por sí solo para aceptar. Una vacante que pide 2 o más años MUST rechazarse.

**Modalidad.** Si la vacante trae una condición de modalidad, la IA MUST aceptarla solo con un indicio de esa modalidad en el texto. La MUST rechazar si el texto indica trabajo presencial o en sitio, o si no dice nada de la modalidad.

**Áreas.** Las prácticas, pasantías y aprendices sin área, o de un área no TI, MUST aceptarse solo si sus funciones principales son de TI. No hay excepción para el «Aprendiz SENA» genérico.

La IA MUST responder por cada vacante si se acepta, su categoría y un motivo breve. La IA MUST NOT recibir tokens, claves, cookies, ids de chat ni otros datos sensibles. La IA solo clasifica: no scrapea, no envía mensajes ni modifica configuración.

#### Scenario: Dudosas clasificadas
- **WHEN** una corrida produce 5 vacantes dudosas
- **THEN** se hace una sola llamada a la IA con las 5 y se envían las que la IA acepta

#### Scenario: Sin dudosas
- **WHEN** una corrida no produce vacantes dudosas
- **THEN** no se llama a la IA para clasificar

#### Scenario: Título sin nivel
- **WHEN** el título es "Software Engineer - Cloud Images", la descripción no habla de nivel ni de experiencia y la fuente filtró por "Entry level"
- **THEN** la IA la rechaza por falta de evidencia de nivel

#### Scenario: Experiencia por encima del salario
- **WHEN** la vacante pide "2 años de experiencia" y ofrece un salario de entrada
- **THEN** la IA la rechaza

#### Scenario: Modalidad confirmada en la descripción
- **WHEN** la vacante es de Medellín, exige confirmar remoto o híbrido y la descripción dice "modalidad híbrida, 2 días en oficina"
- **THEN** la IA puede aceptarla

#### Scenario: Modalidad sin indicio
- **WHEN** la vacante es de Bogotá, exige confirmar remoto o híbrido y la descripción no dice nada de la modalidad
- **THEN** la IA la rechaza

#### Scenario: Aprendiz SENA genérico
- **WHEN** el título es "Aprendiz SENA Candelaria Cali" y ni el título ni la descripción nombran un área
- **THEN** la IA la acepta en la categoría prácticas

#### Scenario: Aprendiz SENA de otra área
- **WHEN** el título es "Aprendiz SENA - Villavicencio" y la descripción es de un cargo de salud
- **THEN** la IA la rechaza

### Requirement: Caché de clasificaciones
El sistema SHALL guardar el veredicto de la IA asociado a la huella de la vacante (título y empresa normalizados) y a la versión del prompt del clasificador, y reutilizarlo mientras el prompt no cambie. La misma vacante dudosa MUST NOT enviarse a la IA más de una vez con el mismo prompt, aunque aparezca en otra fuente o en otra corrida. Si el prompt cambia, las clasificaciones guardadas con otra versión MUST NOT reutilizarse.

#### Scenario: Vacante repetida en otra fuente
- **WHEN** una vacante dudosa ya clasificada con el prompt vigente aparece de nuevo en otra fuente
- **THEN** se usa el veredicto guardado sin llamar a la IA

#### Scenario: Prompt actualizado
- **WHEN** una vacante fue aceptada con el prompt anterior y reaparece después de cambiar el prompt
- **THEN** se vuelve a clasificar con el prompt vigente

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
- «Prácticas y Aprendizaje»: cualquier rol de TI con nivel práctica, pasantía, aprendiz, trainee o etapa productiva.
- Para el nivel junior o de entrada, una categoría por área: «Desarrollo», «Infraestructura / DevOps / Cloud», «Bases de datos», «Soporte IT», «Datos y Analítica», «QA / Testing», «Ciberseguridad» y «Otros TI».

Si una vacante tiene a la vez nivel aprendiz y área, va a «Prácticas y Aprendizaje». Para las aceptadas por reglas, la categoría se decide por los términos que coinciden; si coinciden varias áreas, gana la primera según el orden configurado. Para las aceptadas por la IA, se usa la categoría que propone la IA si es válida y, si no, la que corresponde por términos. En los dos casos, la categoría final MUST pasar por el guardarraíl de prácticas antes de publicarse.

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
El sistema SHALL registrar en cada corrida:
- cuántas vacantes descartó cada regla: lista negra, seniority, antigüedad, ubicación, presencial fuera de la ciudad base, call center no remoto y no TI;
- cuántas fueron dudosas y cuántas aceptó o rechazó la IA;
- cuántas quedaron pendientes;
- cuántas prácticas recategorizó o rechazó el guardarraíl.

#### Scenario: Conteo por filtro
- **WHEN** termina una corrida
- **THEN** el log incluye un conteo por cada regla de descarte, por cada resultado del clasificador y por cada corrección del guardarraíl

### Requirement: Alcance geográfico con ciudad base
El sistema SHALL tener una ciudad base configurable (Cartagena y su área cercana, por defecto `cartagena`, `turbaco` y `mamonal`). La modalidad se toma del dato del portal y, si falta, de los términos de remoto, híbrido o presencial del título, la ubicación o la descripción. Con eso, la vacante se trata así:
- **En la ciudad base**: pasa el filtro geográfico con cualquier modalidad.
- **Remota**: sigue las reglas de lo remoto (abierta a Colombia o LATAM).
- **Híbrida en otra ciudad de Colombia**: pasa el filtro geográfico.
- **Presencial en otra ciudad**: MUST rechazarse por «presencial fuera de la ciudad base».
- **Modalidad desconocida en otra ciudad, o sin ubicación**:
  - si tiene descripción, MUST quedar como dudosa con la condición «remoto o híbrido» para que la IA la confirme;
  - si no tiene descripción, MUST rechazarse por «presencial fuera de la ciudad base», porque la IA no tendría con qué decidir.

#### Scenario: Presencial en otra ciudad
- **WHEN** el título es "Técnico en Sistemas Valledupar" y la modalidad es presencial
- **THEN** se rechaza por presencial fuera de la ciudad base

#### Scenario: Híbrida en otra ciudad
- **WHEN** la vacante es "Desarrollador Junior" en Bogotá con modalidad "Presencial y remoto"
- **THEN** pasa el filtro geográfico y se acepta

#### Scenario: Presencial en Cartagena
- **WHEN** la vacante es "Auxiliar de sistemas" en "Cartagena, Bolívar" con modalidad presencial
- **THEN** pasa el filtro geográfico

#### Scenario: Modalidad desconocida con descripción
- **WHEN** la vacante es "Analista de datos Jr" en Medellín, el portal no dice la modalidad y trae descripción
- **THEN** el veredicto es dudosa con la condición «remoto o híbrido»

#### Scenario: Modalidad desconocida sin descripción
- **WHEN** la vacante es "Tecnólogo en sistemas" en Cali, el portal no dice la modalidad y no trae descripción
- **THEN** se rechaza por presencial fuera de la ciudad base

#### Scenario: En sitio en otra ciudad
- **WHEN** el título es "Soporte en sitio (Boyacá)"
- **THEN** se rechaza por presencial fuera de la ciudad base

### Requirement: Soporte de call center solo remoto
El sistema SHALL reconocer en el título los puestos de atención o soporte al cliente con una lista configurable de términos («asesor de soporte», «asesor/a», «agente de soporte», «soporte al cliente», «servicio al cliente», «atención al cliente», «customer experience», «customer support», «call center», «contact center», «teleoperador»). Uno de esos puestos se trata así, sin importar la ciudad, incluida la ciudad base:
- **Remoto**: sigue la evaluación normal.
- **Presencial o híbrido**: MUST rechazarse por «call center no remoto».
- **Modalidad desconocida**:
  - con descripción, MUST quedar como dudosa con la condición «solo remoto»;
  - sin descripción, MUST rechazarse por «call center no remoto».

#### Scenario: Call center presencial
- **WHEN** el título es "Asesor/a de Soporte técnico ¡Excelente Variable!" y la modalidad es presencial
- **THEN** se rechaza por call center no remoto

#### Scenario: Call center remoto
- **WHEN** el título es "Agente de soporte técnico" con modalidad "Remoto"
- **THEN** continúa la evaluación normal

#### Scenario: Call center en la ciudad base
- **WHEN** el título es "Asesor de soporte técnico" en Cartagena con modalidad presencial
- **THEN** se rechaza por call center no remoto

### Requirement: Guardarraíl de la categoría prácticas
El sistema SHALL verificar, antes de publicar cualquier vacante aceptada por reglas o por la IA en la categoría «Prácticas y Aprendizaje», que haya evidencia textual de práctica. La evidencia cuenta en estos casos:
- el **título** contiene un término de evidencia configurable (por defecto: practicante, práctica profesional, prácticas, aprendiz, aprendices, pasante, pasantía, etapa productiva, etapa práctica, contrato de aprendizaje, becario, estudiante, trainee, intern, internship);
- la **descripción** contiene un término fuerte (contrato de aprendizaje, etapa productiva, etapa práctica, pasantía, práctica profesional).

Que la fuente filtre por nivel MUST NOT contar como evidencia. Si no hay evidencia, la vacante MUST ir a la categoría que le corresponde por área. Si no coincide ningún área, va a «Otros TI» cuando el título o la descripción tienen un término de TI, y se rechaza en caso contrario. Cada recategorización y cada rechazo del guardarraíl MUST registrarse en el log con el título y la categoría original.

#### Scenario: Profesional marcado como práctica
- **WHEN** la IA acepta "Programador Staff CELLS" con categoría prácticas
- **THEN** se publica en Desarrollo y se registra como corrección del guardarraíl

#### Scenario: Ingeniero marcado como práctica
- **WHEN** la IA acepta "Ingeniero IBM STERLING B2B" con categoría prácticas y ningún área coincide
- **THEN** se publica en Otros TI y se registra como corrección

#### Scenario: Práctica con evidencia
- **WHEN** la IA acepta "Software Engineer Intern" con categoría prácticas
- **THEN** se publica en Prácticas y Aprendizaje sin corrección

#### Scenario: Estudiante solo en la descripción
- **WHEN** la IA acepta "Data Engineer Colombia" con categoría prácticas y la descripción solo dice "estudiantes de últimos semestres"
- **THEN** se publica en Datos y Analítica y se registra como corrección
