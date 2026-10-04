# Tasks

## 1. Prácticas a la IA

- [x] 1.1 En `filtros.Filtros.evaluar`, paso 5: si el título contiene un término de `nivel.practica`, devolver dudosa en lugar de rechazar por `NO_TI`. Actualizar `tests/test_filtros.py`: "Practicante Contable", "Aprendiz de Cocina", "Practicante Sistemas de Gestión de Calidad" y "Practicante Seguridad Salud en el trabajo" pasan a dudosa; agregar "Auxiliar Contable" → rechazo `NO_TI`; y verificar que seniority, antigüedad y ubicación siguen rechazando prácticas. Ajustar las cuentas de descartes en `tests/test_buscador.py`. Verificar que `uv run pytest` pasa.
- [x] 1.2 Agregar al `clasificador.prompt_sistema` de `config.yaml` la regla "práctica de otra área: aceptar solo si las funciones principales son de TI". Verificar con una prueba en `tests/test_config.py` que el prompt la contiene.

## 2. Topes de la IA

- [x] 2.1 En `config.yaml`, cambiar `ia.presupuesto_dia` a clasificador 300, reportero 20 y resumen 3. Actualizar las aserciones de `tests/test_config.py`. Verificar que `uv run pytest`, `uv run ruff check` y `uv run ruff format --check` pasan.
- [x] 2.2 Actualizar en `README.md` la frase "DeepSeek solo clasifica las vacantes dudosas", explicando que las prácticas de áreas no TI también pasan por la IA, y mencionar los topes. Verificar que coincide con `config.yaml`.

## 3. Despliegue

- [x] 3.1 Commit y push (sin atribución a IA) y `git pull` en el servidor. Verificar en el log de la siguiente corrida que suben las dudosas, que hay líneas "IA acepta/rechaza" de prácticas de otras áreas y que no aparece "tope diario alcanzado".
