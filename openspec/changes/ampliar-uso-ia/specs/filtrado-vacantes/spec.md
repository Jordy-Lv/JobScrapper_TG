# Spec Delta

## MODIFIED Requirements

### Requirement: Veredicto aceptar, rechazar o dudosa
El sistema SHALL asignar a cada vacante exactamente un veredicto, aplicando las reglas en este orden sobre el título y, si existe, el fragmento de descripción (salvo los términos de seniority, los disparadores de dudosa y las áreas no TI, que se evalúan solo en el título):
1. **rechazar** si el **título** contiene un término de seniority excluido (`senior`, `sr`, `semi senior`, `ssr`, `lead`, `líder`, `gerente`, `manager`, `director`, `jefe`, `arquitecto`, `architect`, `head`, `coordinador`, `especialista`), o si el título o la descripción piden experiencia de 3 o más años. Los términos de seniority no se buscan en la descripción porque frases como "reportarás al líder técnico" descartarían vacantes junior válidas; si en operación se cuelan vacantes senior, se endurece la regla para ese caso.
2. **rechazar** si tiene más de 15 días de publicada, cuando la fecha es conocida.
3. **rechazar** si está fuera del alcance geográfico.
4. **aceptar** si el **título** contiene al menos un término técnico de TI, hay al menos un término de nivel práctica/aprendiz/junior/entrada (en el título o la descripción) y el título no menciona un área que no es de TI. Si lo técnico solo aparece en la descripción, o el título menciona un área no TI (como en "Programador de mantenimiento"), la vacante pasa a dudosa.
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

#### Scenario: Vacante antigua
- **WHEN** la vacante tiene fecha de publicación de hace 20 días
- **THEN** el veredicto es rechazar por antigüedad
