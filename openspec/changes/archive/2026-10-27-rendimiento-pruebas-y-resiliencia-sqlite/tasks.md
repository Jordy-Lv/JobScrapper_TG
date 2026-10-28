## 1. Dependencias y configuración de pruebas

- [x] 1.1 Declarar `pytest-xdist>=3.5` en `pyproject.toml` en el grupo `dev` y verificar con `uv run ruff check pyproject.toml`

## 2. Pragmas de resiliencia y desempeño en SQLite

- [x] 2.1 Configurar pragmas (`busy_timeout`, `temp_store`, `mmap_size`, `cache_size`) en `buscador_vacantes/comun/estado.py`
- [x] 2.2 Configurar pragmas en `buscador_vacantes/asistente/datos.py` (`BaseAsistente.abrir` y `abrir_vacantes_ro`) y en `buscador_vacantes/radar/diagnostico.py` (`abrir_solo_lectura`)

## 3. Pruebas y verificación

- [x] 3.1 Agregar pruebas en `tests/comun/test_estado.py` y `tests/asistente/test_datos.py` que verifiquen los pragmas activos
- [x] 3.2 Ejecutar las pruebas con `pytest -n auto` y verificar que todo pase en verde
