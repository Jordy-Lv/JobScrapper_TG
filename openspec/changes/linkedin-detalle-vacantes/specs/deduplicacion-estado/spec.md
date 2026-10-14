# Spec Delta

## ADDED Requirements

### Requirement: Estado de los detalles de ofertas
El sistema SHALL guardar en almacenamiento local persistente:
- la cola de ofertas pendientes de detalle, con su fecha de ingreso, el número de intentos fallidos y el último error;
- la descripción obtenida de cada oferta, con su fecha, durante el tiempo que la oferta pueda seguir apareciendo;
- por corrida, los detalles pedidos, los fallidos, las ofertas recuperadas y las vencidas o cerradas.

La cola y las descripciones MUST sobrevivir a reinicios del PC y quedar consistentes aunque la corrida se interrumpa: una oferta solo sale de la cola cuando su resultado ya quedó registrado. Los registros antiguos se limpian con el resto del estado. El cambio de esquema MUST migrar la base existente al arrancar, sin perder datos.

#### Scenario: Reinicio con ofertas en cola
- **WHEN** el PC se reinicia con 5 ofertas pendientes de detalle
- **THEN** la siguiente corrida las encuentra en la cola con su fecha de ingreso original

#### Scenario: Corrida interrumpida
- **WHEN** una corrida se corta tras pedir el detalle de una oferta pero antes de evaluarla
- **THEN** la oferta sigue en la cola y se vuelve a procesar en la siguiente corrida

#### Scenario: Migración del esquema 2 al 3
- **WHEN** la primera corrida con la versión nueva abre una base del esquema 2
- **THEN** la base se migra al esquema 3 y las vacantes vistas, las corridas y las clasificaciones anteriores se conservan
