## Why

La suite de pruebas contiene más de 1.900 casos y su ejecución secuencial genera tiempos de espera elevados (varios minutos), dificultando la iteración rápida de desarrollo. Además, bajo concurrencia (latidos de navegadores, tareas en segundo plano del bot y corridas del radar), las conexiones a SQLite en `asistente.db` y `vacantes.db` se benefician de pragmas explícitos de resiliencia (`busy_timeout`, `temp_store`, `mmap_size` y `cache_size`) para prevenir contención de bloqueos y maximizar el rendimiento de lectura y escritura en modo WAL.

## What Changes

- Declarar `pytest-xdist>=3.5` en el grupo de dependencias `dev` de `pyproject.toml`, permitiendo la paralelización automática de la suite de pruebas con `-n auto`.
- Endurecer las conexiones SQLite en `buscador_vacantes/asistente/datos.py` (`BaseAsistente.abrir` y `abrir_vacantes_ro`):
  - Configurar explícitamente `PRAGMA busy_timeout = 30000;`.
  - Configurar `PRAGMA temp_store = MEMORY;` para procesar ordenamientos y tablas temporales en memoria RAM.
  - Configurar `PRAGMA mmap_size = 268435456;` (256 MB) y `PRAGMA cache_size = -64000;` (64 MB) para optimizar lecturas frecuentes.
  - Configurar `PRAGMA query_only = ON;` en conexiones de solo lectura (`abrir_vacantes_ro`).
- Aplicar la misma resiliencia y optimización en `buscador_vacantes/comun/estado.py` (`Estado.abrir`) y en `buscador_vacantes/radar/diagnostico.py` (`abrir_solo_lectura`).
- Agregar pruebas unitarias que verifiquen que los pragmas de resiliencia y timeout quedan activos al abrir las conexiones.

## Capabilities

### New Capabilities
<!-- Ninguna: mejora de infraestructura, rendimiento y resiliencia interna -->

### Modified Capabilities
<!-- Ninguna: el comportamiento funcional externo y los contratos de datos se mantienen idénticos -->

## Impact

- `pyproject.toml`: incorporación de `pytest-xdist` al grupo `dev`.
- `buscador_vacantes/asistente/datos.py`: pragmas de conexión en `abrir` y `abrir_vacantes_ro`.
- `buscador_vacantes/comun/estado.py`: pragmas de conexión en `abrir`.
- `buscador_vacantes/radar/diagnostico.py`: pragmas en `abrir_solo_lectura`.
- `tests/comun/test_estado.py` y `tests/asistente/test_datos.py`: validación de pragmas activos.
