# Spec Delta

## MODIFIED Requirements

### Requirement: Estado persistente
El sistema SHALL guardar en almacenamiento local persistente:
- las vacantes vistas y enviadas, con su ubicación y modalidad;
- el estado de cada fuente: cooldown, fallos consecutivos y último éxito;
- la posición de rotación, incluida la variante de búsqueda de cada fuente que las tenga;
- los intentos, las corridas (con las correcciones del guardarraíl de prácticas) y los incidentes;
- las clasificaciones de IA, con la versión del prompt que las produjo.

El estado MUST sobrevivir a reinicios del PC y quedar consistente aunque una corrida se interrumpa. Un cambio de esquema MUST migrar la base existente al arrancar, sin perder datos.

#### Scenario: Reinicio del PC
- **WHEN** el PC se reinicia entre dos corridas
- **THEN** la siguiente corrida conoce todas las vacantes ya enviadas, los cooldowns vigentes y la posición de rotación

#### Scenario: Corrida interrumpida
- **WHEN** una corrida se corta a mitad del envío
- **THEN** solo quedan marcadas como enviadas las vacantes que Telegram confirmó

#### Scenario: Migración de esquema
- **WHEN** la primera corrida con la versión nueva abre una base del esquema anterior
- **THEN** la base se migra al esquema nuevo, las vacantes vistas y las corridas anteriores se conservan, y las clasificaciones anteriores quedan sin versión de prompt, así que no se reutilizan
