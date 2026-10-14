## Why

El grupo «JOBS - PRACTICAS/APRENDIZ» recibe muchas vacantes que no sirven (unas 55 al día). Entre el 2026-10-10 y el 2026-10-13 llegaron, entre otras:

- Prácticas sin relación con sistemas: «Aprendiz etapa productiva», «Aprendiz SENA» genérico, «Aprendiz Universitario de Planeación de Importados» y «Auxiliar farmacia (manejo base de datos)».
- Puestos profesionales marcados como prácticas: «Ingeniero IBM Sterling B2B» y «Programador Staff CELLS».
- Soporte de call center presencial: los «Asesor/a de soporte técnico» de KONECTA.
- Sobre todo, vacantes **presenciales en otras ciudades**: Bogotá, Cali, Valledupar, Cúcuta y Boyacá.

El dueño vive en Cartagena: una vacante presencial solo le sirve si es en Cartagena, y las de otras ciudades tienen que ser remotas o híbridas. El diagnóstico de `docs/radar/diagnostico-practicas-falsos-positivos.md` ya mostraba entre 19 % y 67 % de error en «prácticas». La causa es que el prompt toma el filtro de nivel de LinkedIn y el salario como evidencia, y nada en el código corrige a la IA.

## What Changes

- **Ubicación con ciudad base (Cartagena):**
  - Las presenciales solo se aceptan en Cartagena y su área cercana (lista configurable).
  - Las de otra ciudad de Colombia solo pasan si son remotas o híbridas.
  - Si no se sabe la modalidad, decide la IA, que solo acepta si hay un indicio de remoto o híbrido. Sin descripción no hay con qué decidir y se rechaza sin llamar a la IA.
  - Lo remoto en Colombia o LATAM sigue igual. **BREAKING** para el alcance «cualquier ciudad de Colombia».
- **LinkedIn por ciudad base:** con el mismo presupuesto de peticiones, LinkedIn alterna entre buscar en toda Colombia y buscar solo en Cartagena. No filtra por modalidad: la API pública de LinkedIn ignora `f_WT` y sus tarjetas no dicen la modalidad.
- **Soporte de call center solo si es remoto:**
  - Un título de atención o soporte al cliente («asesor/a de soporte», «agente de soporte», «call center»…) se rechaza si no es remoto, aunque sea en Cartagena.
  - Si no se sabe la modalidad, decide la IA exigiendo un indicio de remoto.
- **Guardarraíl de «prácticas» en el código:**
  - Para publicarse como «Prácticas y Aprendizaje» hace falta evidencia textual: practicante, aprendiz, pasante, pasantía, etapa productiva, etapa práctica, contrato de aprendizaje, becario, estudiante, trainee o intern.
  - Sin esa evidencia, la vacante pasa a su categoría real o se rechaza.
  - Aplica a lo que aceptan las reglas y a lo que acepta la IA.
- **Prácticas sin TI se rechazan:**
  - Si la vacante trae descripción y ni el título ni la descripción tienen nada de TI, se rechaza en lugar de ir a la IA. Sin descripción no se rechaza: decide la IA.
  - Se elimina del prompt la excepción que aceptaba el «Aprendiz SENA» genérico. **BREAKING** para la regla «Aprendiz SENA genérico».
- **Experiencia máxima de 1 año:** `anios_experiencia_excluidos_desde` pasa de 3 a 2 y el prompt dice «hasta 1 año».
- **Prompt del clasificador corregido:**
  - Se quita `nivel_filtrado_por_fuente` del JSON que recibe la IA.
  - Manda la experiencia que pide el anuncio. El salario solo sirve como apoyo cuando el anuncio no dice nada de nivel, y nunca basta por sí solo para aceptar.
- **Caché atada a la versión del prompt:** las clasificaciones guardadas solo se reutilizan si se hicieron con el mismo prompt. Así, lo que se aceptó con el prompt viejo no vuelve a pasar.
- **Lista negra configurable** de empresas y de palabras del título. Se edita en `config.yaml` hasta que exista el panel de Telegram.
- **Métrica en el resumen diario:**
  - Descartes por ubicación presencial, call center y lista negra.
  - Cuántas prácticas corrigió el guardarraíl (recategorizadas o rechazadas).
- **Auditoría:** la tabla `vistas` guarda la ubicación y la modalidad de cada vacante publicada.

Fuera de alcance: el comando `/noera` y la edición desde Telegram (van en `panel-control-telegram`), los perfiles en SQLite (`perfiles-busqueda-y-arquitectura`) y los cambios al asistente Apolo TI.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `filtrado-vacantes`: cambian el veredicto (lista negra, call center, prácticas sin TI y máximo 1 año), el alcance geográfico (ciudad base), la clasificación IA (prompt y datos enviados), la caché (versión del prompt), las categorías (guardarraíl de prácticas) y las métricas de descarte.
- `busqueda-fuentes`: LinkedIn alterna sus búsquedas por modalidad y por ciudad base.
- `resumen-diario`: el contenido suma los descartes nuevos y las correcciones del guardarraíl.
- `deduplicacion-estado`: el estado guarda la ubicación y la modalidad de cada vacante vista y la versión del prompt en cada clasificación.

## Impact

- **Código:**
  - `buscador_vacantes/radar/filtros.py`: ciudad base, modalidad, call center, lista negra, prácticas sin TI y guardarraíl.
  - `clasificador.py`: datos que recibe la IA, versión del prompt y guardarraíl tras la IA.
  - `corrida.py`: nuevos descartes y el conteo de correcciones.
  - `config.py`: nuevos campos validados con pydantic.
  - `estado.py`: el esquema pasa de la versión 1 a la 2.
  - `resumen.py` y `fuentes/linkedin.py`.
- **Configuración:**
  - `config.yaml`: `filtros.ubicacion.ciudad_base`, términos de modalidad, `filtros.call_center`, `filtros.lista_negra`, `filtros.nivel.evidencia_practica`, `anios_experiencia_excluidos_desde: 2`, variantes de LinkedIn y el prompt del clasificador.
- **Datos:**
  - `data/vacantes.db` migra sola al esquema 2 en la primera corrida: columnas nuevas, sin perder datos.
  - Las clasificaciones viejas dejan de reutilizarse.
- **Operación:**
  - Se publicarán bastante menos vacantes, sobre todo de LinkedIn y de ciudades distintas a Cartagena.
  - Puede subir un poco el uso de IA por las dudosas de modalidad. Sigue limitado por `ia.presupuesto_dia`.
- **Ramas:**
  - Se trabaja desde `main`, que es lo que corre producción (`~/buscador-vacantes`).
  - Al unir con `asistente-postulacion-telegram` habrá que resolver `config.yaml`, `corrida.py` y `resumen.py`, que esa rama también modifica.
