# Design

## Context

- `Filtros.categoria_por_terminos` devuelve PRACTICAS si el título tiene un término de `nivel.practica`, o si el título no tiene término junior y la **descripción** tiene cualquier término de `nivel.practica`. Esa lista incluye términos débiles: "estudiante", "semillero", "programa de talento", "práctica", "prácticas" ("buenas prácticas"), "sena".
- `Filtros.evaluar`, paso 4, acepta por reglas si hay TI en el título y nivel (práctica o junior) en el título o la descripción, sin mirar el salario.
- `Clasificador._clasificar_lote` envía a la IA título, empresa, ubicación, modalidad, salario, palabra clave, `nivel_filtrado_por_fuente` y descripción. La IA no sabe qué palabra de `areas_no_ti` detectaron las reglas.
- El 2026-10-04 13:00 la IA aceptó "aprendiz administrativa" con el motivo "Aprendiz SENA genérico sin área específica".
- Orden de archivo: este change modifica "Veredicto aceptar, rechazar o dudosa" partiendo del texto de `ampliar-uso-ia`, así que `ampliar-uso-ia` se archiva antes.

## Goals / Non-Goals

**Goals:**
- Que en Prácticas solo haya prácticas y aprendices reales, sin perder los aprendices cuyo título no lo dice.
- Que la IA no aplique la excepción del aprendiz genérico cuando el título nombra un área.

**Non-Goals:**
- Rechazar por salario: el salario alto solo manda la vacante a la IA, no la descarta.
- Cambiar la lista `nivel.practica`, que se sigue usando para el nivel y para la excepción de dudosa de `ampliar-uso-ia`.
- Reclasificar lo que ya está en la caché de la IA.

## Decisions

**1. Lista nueva `filtros.nivel.practica_en_descripcion` (términos fuertes).**
- Términos: contrato de aprendizaje, etapa productiva, etapa práctica, etapa lectiva, aprendiz, aprendices, practicante, practicantes, pasante, pasantía, cuota sena, práctica profesional, prácticas profesionales.
- `categoria_por_terminos` usa esta lista para la descripción y `nivel.practica` para el título.
- Se descartó quitar del todo la descripción: un "Auxiliar de sistemas" con "contrato de aprendizaje SENA" en la descripción es un aprendiz real y debe ir a Prácticas.

**2. `filtros.salario_max_entrada: 4500000`.**
- Se extraen del texto del salario los montos en formato COP (`\d{1,3}(?:[.,]\d{3})+`, valores ≥ 100.000) y se toma el menor. Si es mayor que el tope y el título no tiene `nivel.practica`, el paso 4 devuelve dudosa con `detalle="salario alto"`.
- Se usa el menor valor porque, en un rango como "$4.000.000 - $5.500.000", el piso indica el nivel.
- Los textos sin montos COP (como "USD 1500") no activan la regla.
- El valor es el mismo umbral que ya usa el prompt ("más de unos 4,5 millones suele indicar un cargo no junior").

**3. `Filtros.area_no_ti_en_titulo(titulo) -> str | None`.**
- Reutiliza la lógica del paso 4: el título se limpia de las frases técnicas y se toma la primera coincidencia de `areas_no_ti`.
- `Clasificador` agrega `"area_no_ti_en_titulo"` al payload de cada vacante.
- Se descartó dejarlo solo en el prompt: la IA ya tenía la regla y la aplicó mal; un dato explícito es más robusto que pedirle que lo detecte.

**4. Prompt.**
- En la regla del aprendiz SENA genérico se aclara: "solo si el título no nombra ningún área; 'Aprendiz administrativa', 'Aprendiz contable' o 'Aprendiz de logística' NO son genéricos".
- Se agrega: "si `area_no_ti_en_titulo` trae un valor, aplica la regla de práctica de otra área".

## Risks / Trade-offs

- [Un aprendiz real con solo "estudiante" en la descripción va a su área (Soporte, Datos) en vez de a Prácticas] → Igual se publica; solo cambia la sección. Si pasa a menudo, se agrega el término a la lista fuerte.
- [Formatos de salario raros ("4.5 millones")] → No se reconocen como montos y la regla no se activa. Es el mismo comportamiento de hoy, sin regresión.
- [La IA ignora la pista] → Pruebas con el payload. En producción se revisan las líneas "IA acepta" de aprendices con área.

## Migration Plan

1. Desplegar con `git pull`. Aplica desde la siguiente corrida.
2. Rollback: `git revert`.
