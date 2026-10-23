# Tasks

## 1. Categoría Prácticas

- [ ] 1.1 Agregar `nivel.practica_en_descripcion` (lista configurable, obligatoria) a `config.Nivel` y a `config.yaml` con los términos fuertes del design. En `categoria_por_terminos`, usar esa lista para la descripción. Verificar con `tests/test_filtros.py`: "Analista de datos" + "tecnólogo graduado o estudiante de últimos semestres" → DATOS; "Auxiliar de sistemas" + "contrato de aprendizaje SENA" → PRACTICAS; los casos existentes siguen pasando.

## 2. Salario de entrada

- [ ] 2.1 Agregar `filtros.salario_max_entrada` (entero, por defecto 4500000) a `config.Filtros` y a `config.yaml`, y una función que extrae el menor monto COP del salario. En el paso 4 de `evaluar`, si el título no tiene `nivel.practica` y el salario supera el tope, devolver dudosa (`detalle="salario alto"`). Verificar con pruebas: el caso real "CEID Analista de analítica" ($4.700.000) → dudosa; "Practicante de Desarrollo de Software" con $5.000.000 → aceptar; rango "$1.000.001 - $1.500.000" → aceptar; "USD 1500" → sin efecto.

## 3. Pista y prompt para la IA

- [ ] 3.1 Agregar `Filtros.area_no_ti_en_titulo` (reutilizando la limpieza del paso 4) y enviar `area_no_ti_en_titulo` en el payload de `Clasificador._clasificar_lote`. Verificar con `tests/test_clasificador.py` que el payload de "aprendiz administrativa" trae "administrativa" y el de "Aprendiz SENA Cali" trae null.
- [ ] 3.2 Actualizar `clasificador.prompt_sistema` en `config.yaml`: excepción del aprendiz genérico solo sin área en el título, con ejemplos ("Aprendiz administrativa", "Aprendiz contable", "Aprendiz de logística" → no genéricos) y uso de `area_no_ti_en_titulo`. Verificar con una prueba en `tests/test_config.py` y con `uv run pytest`, `uv run ruff check` y `uv run ruff format --check`.

## 4. Despliegue

- [ ] 4.1 Commit y push (sin atribución a IA), `git pull` en el servidor, y en el servidor reevaluar los dos casos reales con el código nuevo (CEID → dudosa por salario; "aprendiz administrativa" → payload con área). Verificar en la siguiente corrida que no hay errores y que las vacantes de Prácticas enviadas tienen nivel práctica en el título o un término fuerte en la descripción.
