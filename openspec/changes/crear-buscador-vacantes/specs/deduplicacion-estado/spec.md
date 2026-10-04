# Spec Delta

## Purpose

Garantizar que ninguna vacante se publique dos veces, ni siquiera cuando aparece en varias fuentes, conservando el estado del buscador entre corridas, reinicios y la migración desde Hermes.

## ADDED Requirements

### Requirement: Estado persistente
El sistema SHALL guardar en almacenamiento local persistente las vacantes vistas y enviadas, el estado de cada fuente (cooldown, fallos consecutivos, último éxito), la posición de rotación, los intentos, las corridas, los incidentes y las clasificaciones de IA. El estado MUST sobrevivir a reinicios del PC y quedar consistente aunque una corrida se interrumpa.

#### Scenario: Reinicio del PC
- **WHEN** el PC se reinicia entre dos corridas
- **THEN** la siguiente corrida conoce todas las vacantes ya enviadas, los cooldowns vigentes y la posición de rotación

#### Scenario: Corrida interrumpida
- **WHEN** una corrida se corta a mitad del envío
- **THEN** solo quedan marcadas como enviadas las vacantes que Telegram confirmó

### Requirement: Deduplicación por fuente y entre fuentes
El sistema SHALL identificar cada vacante por su clave `fuente:id_nativo` y por una huella de título y empresa normalizados. Al normalizar la empresa se quitan sufijos societarios como "S.A.S." o "S.A." y la palabra "Colombia". Una vacante MUST considerarse ya vista si coincide su clave o su huella con un registro existente.

#### Scenario: Misma vacante en dos fuentes
- **WHEN** "Practicante de Desarrollo – Redeban S.A.S." ya se envió desde LinkedIn y aparece en Computrabajo como "Practicante de desarrollo – Redeban"
- **THEN** no se vuelve a enviar

#### Scenario: Misma vacante en la misma fuente
- **WHEN** una vacante con clave `linkedin:4012345` reaparece en otra búsqueda
- **THEN** no se vuelve a enviar

### Requirement: Migración del historial de Hermes
El sistema SHALL importar las entradas de `historial_vacantes.json` como vacantes ya enviadas antes de la primera corrida real. La migración MUST ser idempotente: correrla dos veces no duplica registros.

#### Scenario: Migración
- **WHEN** se ejecuta la migración con un historial de 309 vacantes
- **THEN** quedan 309 registros marcados como enviados y ninguna de esas vacantes se publica después

#### Scenario: Migración repetida
- **WHEN** la migración se ejecuta por segunda vez
- **THEN** el número de registros no cambia

### Requirement: Modo seed
El sistema SHALL ofrecer un modo seed que hace una corrida completa y marca como vistas todas las vacantes encontradas que pasan los filtros, sin enviar nada a Telegram. Así la primera corrida real no inunda el canal.

#### Scenario: Corrida seed
- **WHEN** se ejecuta la corrida en modo seed y se encuentran 80 vacantes válidas
- **THEN** no se envía ningún mensaje y las 80 quedan registradas como vistas

### Requirement: Limpieza por antigüedad
El sistema SHALL borrar las vacantes vistas con más de 90 días, y los intentos y corridas con más de 30 días. Los incidentes abiertos MUST NOT borrarse.

#### Scenario: Registro antiguo
- **WHEN** una vacante fue vista por primera vez hace 91 días
- **THEN** se elimina en la siguiente limpieza
