# Proposal

## Why

El 2026-10-04 a las 13:00 llegaron a "Prácticas y Aprendizaje" dos vacantes que no lo son, y la prioridad del canal es justamente que esa categoría tenga aprendices y practicantes reales:

- **"CEID Analista de analítica"** (Magneto, $4.700.000, pide de 6 meses a 2 años de experiencia). La aceptaron las reglas y quedó en Prácticas porque la descripción dice "tecnólogo graduado o **estudiante** de últimos semestres". Hoy cualquier término de nivel práctica en la descripción, incluso uno débil como "estudiante", basta para la categoría Prácticas, y un salario de $4,7 M no frena la aceptación automática.
- **"aprendiz administrativa"** (elempleo). Desde `ampliar-uso-ia` llega a la IA, que la aceptó aplicando la excepción del "aprendiz SENA genérico". El título sí nombra un área ("administrativa").

## What Changes

- **Categoría Prácticas más estricta:** se asigna si el título tiene un término de nivel práctica, o si la descripción tiene un término **fuerte** de aprendizaje (contrato de aprendizaje, etapa productiva, etapa práctica, aprendiz, practicante, pasante, pasantía, cuota SENA). Los términos débiles en la descripción ("estudiante", "semillero", "prácticas", "programa de talento") ya no bastan. Así se conservan los aprendices reales cuyo título no lo dice.
- **Tope de salario de entrada (4.500.000 COP, configurable):** si el menor valor del salario publicado lo supera y el título no tiene nivel práctica, las reglas no la aceptan directo: pasa a dudosa y la decide la IA.
- **Pista para la IA:** cada vacante dudosa incluye `area_no_ti_en_titulo`, el área no TI detectada en el título o null.
- **Prompt aclarado:** la excepción del aprendiz SENA genérico solo aplica si el título no nombra ningún área, y si `area_no_ti_en_titulo` trae un valor se aplica la regla de "práctica de otra área". Se agregan ejemplos explícitos ("Aprendiz administrativa", "Aprendiz contable" → rechazar).

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `filtrado-vacantes`: cambian tres requisitos:
  - "Veredicto aceptar, rechazar o dudosa": tope de salario en la aceptación por reglas.
  - "Categorías de publicación": Prácticas por título o por términos fuertes de la descripción.
  - "Clasificación IA de vacantes dudosas": pista de área no TI y alcance de la excepción del aprendiz SENA.

## Impact

- **Código:** `buscador_vacantes/filtros.py` (`categoria_por_terminos`, paso 4 de `evaluar`, `area_no_ti_en_titulo`, lectura del salario), `buscador_vacantes/config.py` (`nivel.practica_en_descripcion` y `salario_max_entrada`) y `buscador_vacantes/clasificador.py` (campo nuevo en el payload).
- **Configuración:** `config.yaml` (listas nuevas, tope de salario y prompt).
- **Pruebas:** `tests/test_filtros.py`, `tests/test_clasificador.py` y `tests/test_config.py`, con los dos casos reales.
- **Producción:** sin migración. Las clasificaciones de la IA en caché siguen valiendo; "aprendiz administrativa" ya se envió y no se reenvía. Las vacantes de sueldo alto pasan a la IA, con algunas llamadas más.
