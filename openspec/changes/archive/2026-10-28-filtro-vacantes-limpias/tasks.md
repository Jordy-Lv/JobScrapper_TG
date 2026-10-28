## 1. Configuración y esquema (🟡)

- [x] 1.1 Agregar a `config.py` (pydantic) los campos nuevos:
  - `filtros.ubicacion.ciudad_base`, `.hibrido` y `.presencial`;
  - `filtros.call_center` y `filtros.lista_negra.{empresas, palabras}`;
  - `filtros.nivel.evidencia_practica` y `.evidencia_practica_descripcion`;
  - `fuentes.*.opciones.variantes`, que sigue siendo opcional.

  Todos con valores por defecto. Llenarlos en `config.yaml` con los valores del spec, cambiar `anios_experiencia_excluidos_desde` a 2 y agregar `middle` a `exclusion_seniority`. Verificar con `test_config.py`: la configuración real carga y una configuración sin los campos nuevos también.
- [x] 1.2 Agregar a `modelo.py` el campo `Vacante.exige_modalidad` y a `filtros.Motivo` los valores `LISTA_NEGRA`, `PRESENCIAL_FUERA` y `CALL_CENTER`. Verificar que `vacante_a_json`/`vacante_de_json` conservan `exige_modalidad`, con una prueba en `test_estado.py`.
- [x] 1.3 Migrar el esquema de `estado.py` a la versión 2 (`ALTER TABLE` según design §10). `registrar_vista` debe guardar la ubicación y la modalidad, y `_guardar_corrida` las dos columnas de correcciones. Verificar en `test_estado.py`: una base de esquema 1 con datos migra a 2 sin perder filas, y una base nueva nace en 2.

## 2. Reglas deterministas en `filtros.py` (🟡)

- [x] 2.1 Implementar la lista negra como primer paso de `evaluar()`, con la empresa normalizada igual que en la huella. Verificar con pruebas de empresa y palabra en `test_filtros.py`.
- [x] 2.2 Implementar la detección de modalidad (portal → título y ubicación → descripción, esta última solo para remoto o híbrido) y la nueva `_geografia()`: ciudad base, híbrido en Colombia, `PRESENCIAL_FUERA` y `CONFIRMAR_MODALIDAD`, con rechazo si no hay descripción. Verificar con los escenarios de «Alcance geográfico con ciudad base» y «Alcance geográfico Colombia más remoto LATAM» como pruebas.
- [x] 2.3 Implementar la regla de call center antes de la ciudad base (design §3). Verificar con los escenarios de «Soporte de call center solo remoto», incluido el caso en Cartagena.
- [x] 2.4 Quitar la excepción de prácticas del paso 5 y rechazar como `NO_TI` («práctica sin TI») cuando hay descripción y ni ella ni el título tienen TI (sin descripción decide la IA). Una aceptación por reglas que exige confirmar la modalidad pasa a dudosa con `exige_modalidad`. Verificar con los escenarios de «Veredicto aceptar, rechazar o dudosa». Actualizar las pruebas existentes que esperaban dudosa para «Practicante Contable» y «Practicante» sin área.
- [x] 2.5 Implementar `Filtros.guardarrail_practicas()` (design §6). Verificar con los cuatro escenarios de «Guardarraíl de la categoría prácticas» como pruebas unitarias.

## 3. Clasificador IA (🟡)

- [x] 3.1 Quitar `nivel_filtrado_por_fuente` y `fuentes_con_filtro_nivel`, agregar `ciudad_base` y `exige_modalidad` al payload, y quitar el cálculo de `con_filtro` en `Corrida._clasificar`. Verificar en `test_clasificador.py` que el JSON enviado no contiene `nivel_filtrado_por_fuente` y sí trae la condición de modalidad.
- [x] 3.2 Agregar `version_prompt` (hash del prompt) a `_cache()` y `_guardar_clasificacion()`. Verificar con una prueba: una clasificación guardada con otra versión, o con `NULL`, provoca una nueva llamada a la IA, y una con la misma versión se reutiliza.
- [x] 3.3 Reescribir `clasificador.prompt_sistema` en `config.yaml`:
  - hasta 1 año de experiencia;
  - experiencia sobre salario, que solo sirve de apoyo y nunca basta para aceptar;
  - regla de `exige_modalidad` con ejemplos de indicios presenciales («en sitio», «técnico de campo», «con moto»);
  - ciudad base;
  - sin excepción para el SENA genérico.

  Verificar que se quitaron «nivel_filtrado_por_fuente» y «ACÉPTALA con categoría "practicas", aunque no se mencione TI», con una prueba que lea el prompt cargado.

## 4. LinkedIn por variantes (🟡)

- [x] 4.1 Soportar `opciones.variantes` en `fuentes/linkedin.py`: combinar los parámetros de la variante en `construir_peticion` y aplicar su `modalidad` en `parsear`. Sin variantes, el comportamiento es el actual. Verificar en `test_linkedin_computrabajo.py` que la petición lleva `f_WT=2,3` y la ubicación de la variante, y que las vacantes salen con «Remoto o híbrido».
- [x] 4.2 En `Corrida._consultar`, elegir la variante con `rotacion` (grupo `variante`) y avanzarla al terminar la corrida. Verificar en `test_buscador.py` que dos corridas seguidas usan variantes distintas y que el presupuesto de peticiones no cambia.

## 5. Corrida, métricas y resumen (🟡)

- [x] 5.1 Aplicar `guardarrail_practicas()` en `corrida.py` sobre las aceptadas por reglas y por la IA antes de armar `a_publicar`. Contar `practicas_recategorizadas` y `practicas_rechazadas` en `ResumenCorrida` y en `linea_log()`, y agregar los motivos nuevos a `DESCARTES`. Verificar en `test_buscador.py` con una corrida simulada (respx) en la que la IA acepta «Programador Staff CELLS» como prácticas y se publica en Desarrollo.
- [x] 5.2 Sumar los descartes nuevos y las correcciones en `resumen.py` (`NOMBRES_DESCARTE`, `calcular_metricas`, `componer_resumen` y `para_ia`). Verificar en `test_resumen.py` que aparecen la línea «🛡️ Guardarraíl de prácticas: N recategorizadas · M rechazadas» y los conteos de ciudad base y call center.

## 6. Regresión con casos reales (🟡)

- [x] 6.1 Crear `tests/fixtures/casos_reales_2026-10.yaml` con unas 30 vacantes publicadas en producción entre el 2026-10-10 y el 2026-10-13. Cada caso trae título, empresa, fuente, ubicación y modalidad supuestas, descripción si la había, y el resultado esperado según el spec. Ejemplos:
  - «Aprendiz etapa productiva» → rechazar;
  - «Técnico en Sistemas Valledupar» presencial → rechazar;
  - «238540 Asesor/a de Soporte técnico» de KONECTA → rechazar;
  - «Programador Staff CELLS» como prácticas → Desarrollo;
  - «Trainee de Sistemas» en Cartagena → aceptar en prácticas;
  - «Junior SDET - Remote Work» → aceptar.

  Escribir `tests/radar/test_casos_reales.py`, que evalúa cada caso con `Filtros` y el guardarraíl. Verificar que pasa.
- [x] 6.2 Correr la suite completa (`.venv/Scripts/python -m pytest`) y `ruff check`. Verificar que todo pasa, salvo las 3 pruebas propias de Windows que ya fallaban.

## 7. Documentación (🟢)

- [x] 7.1 Actualizar `README.md` y los comentarios de `config.yaml` (alcance con ciudad base, call center, lista negra, guardarraíl, variantes de LinkedIn). Agregar una nota en `docs/diagnostico-practicas-falsos-positivos.md` que remita a este change. Verificar que no queda ninguna mención a «cualquier ciudad de Colombia» como alcance vigente.

## 8. Verificación y despliegue (👤 con apoyo)

- [x] 8.1 Ejecutar `uv run buscador.py --dry-run` en una copia aparte del Fedora, con una copia de `data/vacantes.db` y sin tocar `~/buscador-vacantes`. Revisar con el dueño la lista de vacantes que se publicarían. Verificar que ninguna es presencial fuera de Cartagena ni práctica sin TI.
- [x] 8.2 👤 Con el visto bueno del dueño: unir `filtro-vacantes-limpias` a `main` y respaldar `data/vacantes.db` en el Fedora. Después, `git pull --ff-only` en `~/buscador-vacantes`. Verificar en el log de la siguiente corrida que la base quedó en el esquema 2 y que aparecen los descartes nuevos.
- [x] 8.3 👤 Revisar el grupo y el resumen diario durante 2 o 3 días. Verificar que el resumen muestra las correcciones del guardarraíl y que el dueño confirma que ya no llegan vacantes sin relación con sistemas ni presenciales fuera de Cartagena.
- [x] 8.4 Al integrar con `asistente-postulacion-telegram`, resolver los conflictos de `config.yaml`, `corrida.py` y `resumen.py`. Verificar que la suite de esa rama pasa.
- [x] 8.5 🟢 Archivar este change después de `crear-buscador-vacantes` y `ampliar-uso-ia`. Sus deltas usan `MODIFIED` sobre specs que solo existen al archivar `crear-buscador-vacantes`. Verificar que `openspec archive filtro-vacantes-limpias` termina sin rechazos.

> 2026-10-28: el dueño dio por probadas las verificaciones suyas al archivar el change.
