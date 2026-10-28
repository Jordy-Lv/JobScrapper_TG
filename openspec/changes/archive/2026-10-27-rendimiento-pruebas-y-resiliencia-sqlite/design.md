## Context

Ver `proposal.md` para la motivación.

El proyecto cuenta con dos bases de datos SQLite principales:
1. `data/vacantes.db`: administrada por el radar (`Estado`), leída en modo de solo lectura por el asistente (`abrir_vacantes_ro`).
2. `data/asistente.db`: administrada por el asistente (`BaseAsistente`), con múltiples escrituras y lecturas concurrentes (latidos de navegadores, bot de Telegram, cola de postulaciones).

Actualmente ambas bases usan `journal_mode=WAL` y `synchronous=NORMAL`. Sin embargo, la asignación de memoria para caché es la mínima por defecto (~2 MB), el almacenamiento temporal usa archivos de disco y el `busy_timeout` depende exclusivamente del argumento de conexión de Python sin asegurar el pragma del motor.

En cuanto a las pruebas, existen 1.904 pruebas automatizadas que se ejecutan de manera secuencial por defecto, demorando varios minutos.

## Goals / Non-Goals

**Goals:**
- Proveer soporte oficial para ejecución de pruebas en paralelo mediante `pytest-xdist`.
- Asegurar que todas las aperturas de SQLite configuren de forma uniforme y determinista los pragmas de resiliencia y desempeño (`busy_timeout`, `temp_store`, `cache_size`, `mmap_size`).
- Proteger las lecturas del asistente a `vacantes.db` activando `query_only = ON`.
- Mantener compatibilidad 100% con bases `:memory:` utilizadas en pruebas unitarias.

**Non-Goals:**
- Migrar el motor de base de datos fuera de SQLite (PostgreSQL, MySQL, etc.).
- Modificar el esquema de tablas o la lógica de negocio de las consultas SQL.
- Forzar `-n auto` de manera rígida e incondicional en `pyproject.toml` (se deja a discreción del comando CLI para no interferir con depuradores paso a paso).

## Decisions

### 1. Inclusión de `pytest-xdist>=3.5` en el grupo `dev`
- **Decisión:** Agregar `pytest-xdist>=3.5` a `pyproject.toml` bajo `[dependency-groups.dev]`.
- **Alternativas consideradas:**
  - Instalarlo solo localmente sin declarar: rompe la reproducibilidad en CI o en el servidor Fedora con `uv sync`.
  - Forzar `addopts = "-n auto"` en `[tool.pytest.ini_options]`: causaría problemas al correr pruebas con breakpoints (`--pdb`), depuración en IDEs o pruebas puntuales. La opción recomendada es invocar `pytest -n auto` cuando se desee paralelismo.

### 2. Pragmas de conexión uniformes para bases con escritura (`asistente.db` y `vacantes.db`)
- **Decisión:** Al abrir la base en `BaseAsistente.abrir` y `Estado.abrir`, ejecutar:
  ```sql
  PRAGMA busy_timeout = 30000;
  PRAGMA temp_store = MEMORY;
  PRAGMA mmap_size = 268435456;
  PRAGMA cache_size = -64000;
  ```
- **Razón:**
  - `busy_timeout = 30000`: 30 segundos de espera activa ante cerrojos WAL concurrentes.
  - `temp_store = MEMORY`: ordenamientos y tablas temporales se procesan en RAM en vez de archivos `.tmp` en disco.
  - `mmap_size = 268435456` (256 MB): mapeo en memoria para acceso directo a páginas sin llamadas repetidas a `read()`.
  - `cache_size = -64000` (64 MB): caché de páginas sustancialmente más amplia que los 2 MB por defecto.

### 3. Pragmas en conexiones de solo lectura
- **Decisión:** En `abrir_vacantes_ro` (`datos.py`) y `abrir_solo_lectura` (`diagnostico.py`), ejecutar:
  ```sql
  PRAGMA busy_timeout = 30000;
  PRAGMA query_only = ON;
  PRAGMA mmap_size = 268435456;
  ```
- **Razón:** `query_only = ON` optimiza la ruta del planificador de SQLite e impide de forma estricta cualquier intento accidental de mutación.

## Risks / Trade-offs

- **[Riesgo]** Consumo adicional de memoria RAM por conexión con `cache_size = -64000` (64 MB).
  - *Mitigación:* APOLO TI utiliza un número bajo de conexiones simultáneas de larga duración por proceso (servidor FastAPI y servicio del radar). 64 MB es un valor seguro y ligero para la infraestructura destino.
- **[Riesgo]** Incompatibilidad de `mmap_size` o WAL en bases en memoria `:memory:` en tests.
  - *Mitigación:* SQLite ignora silenciosamente `mmap_size` para bases `:memory:` sin lanzar error.
