## Purpose
Fijar cómo se organiza el código en paquetes y qué dependencias entre ellos se permiten, para que el buscador y el asistente evolucionen por separado sin cambiar lo que hace el sistema.

## ADDED Requirements

### Requirement: Organización en tres paquetes
El código SHALL organizarse en `buscador_vacantes/comun/`, `buscador_vacantes/radar/` y `buscador_vacantes/asistente/`, y las pruebas en `tests/comun/`, `tests/radar/` y `tests/asistente/` con la misma correspondencia.

#### Scenario: Módulo del radar
- **WHEN** un módulo sirve solo a la búsqueda, el filtrado, la publicación o el resumen de vacantes
- **THEN** vive en `radar/` y su prueba en `tests/radar/`

#### Scenario: Módulo compartido
- **WHEN** un módulo lo usan el radar y el asistente
- **THEN** vive en `comun/`

### Requirement: Dirección de las dependencias
Las dependencias SHALL ir en un solo sentido: `comun` SHALL NOT importar de `radar` ni de `asistente`, y `asistente` SHALL NOT importar de `radar`. `radar` MAY importar de `asistente` y de `comun`, porque el radar publica los enlaces y botones del asistente y reporta sus métricas.

#### Scenario: Importación permitida
- **WHEN** un módulo de `radar/` importa un módulo de `asistente/` o de `comun/`
- **THEN** la prueba de arquitectura pasa

#### Scenario: Importación prohibida
- **WHEN** un módulo de `asistente/` importa un módulo de `radar/`, o un módulo de `comun/` importa de `radar/` o `asistente/`
- **THEN** una prueba de arquitectura falla

### Requirement: Comportamiento idéntico
Tras el reordenamiento, el sistema SHALL comportarse igual: mismas salidas del comando `buscador.py`, mismos mensajes, mismo `config.yaml` y mismo esquema de las bases SQLite.

#### Scenario: Suite y corrida de prueba
- **WHEN** se ejecuta la suite completa y una corrida en modo prueba tras el movimiento
- **THEN** la suite pasa sin modificar aserciones de comportamiento y la corrida produce el mismo resultado que antes

### Requirement: Punto de entrada estable
`buscador.py` y los comandos de las unidades systemd SHALL seguir funcionando sin cambios.

#### Scenario: Servicios existentes
- **WHEN** se arranca `buscador.py`, `buscador.py resumen` o `buscador.py asistente servicio`
- **THEN** responden igual que antes del movimiento

### Requirement: Historial conservado
Los archivos movidos SHALL moverse con `git mv` y sin reescribirse en el mismo commit que su movimiento.

#### Scenario: Revisión del historial
- **WHEN** se consulta `git log --follow` de un módulo movido
- **THEN** se ve su historial anterior al movimiento
