## Why

El 2026-10-13 LinkedIn bloqueó al buscador con HTTP 429 nueve veces (incidente «LinkedIn · bloqueo», severidad alta). Cada bloqueo dejó la fuente 2 h en cooldown, y el efecto es peor que el ahorro que buscan: LinkedIn pasó de publicar unas 74 vacantes al día (6–9 de octubre) a 17 hoy (22 ayer, 25 el 11).

Los datos del servidor muestran dos problemas:

- **Demasiadas peticiones, mal aprovechadas.** Son 3 requests cada 30 min (unos 144 al día). El 8 y 9 de octubre no hubo bloqueos; desde entonces el umbral de LinkedIn bajó y el 429 llega casi siempre en el 2.º o 3.º request de una corrida, tras 4–7 peticiones en menos de una hora.
- **Cada request trae poco de lo nuevo.** Todas las respuestas 200 llegan llenas (10 items), así que hay más coincidencias en 24 h de las que caben en la página. Como la búsqueda no pide orden por fecha, lo recién publicado puede quedar fuera del top 10. Además, cada palabra clave del núcleo se consulta una sola vez cada ~3,5 h (14 palabras, 2 por corrida).

Se puede pedir menos y ver más: ordenar por fecha y cubrir varias palabras con una sola petición.

## What Changes

- **Orden por fecha:** la búsqueda de LinkedIn agrega `sortBy=DD` (configurable), de modo que la primera página trae lo más nuevo.
- **Consultas combinadas con OR:**
  - Una sola petición cubre varias palabras clave unidas con `OR`. El núcleo completo va en una consulta y la cola larga se agrupa por área, usando los grupos que ya existen en `config.yaml`.
  - Con 1 request por corrida, alternando las dos variantes (Colombia remoto o híbrido, y Cartagena), son unos 48 requests al día en lugar de ~144. Cada variante se revisa cada hora.
  - **Respaldo:** si LinkedIn no acepta el `OR`, la misma agrupación se hace con grupos pequeños de palabras en rotación, sin `OR`.
- **Ritmo adaptativo:** tras un bloqueo, LinkedIn pasa a una escala más lenta de intervalo mínimo entre peticiones (30 → 60 → 120 min) y la recupera tras N peticiones limpias seguidas. Sustituye al «presupuesto adaptativo»: con 1 petición base por corrida lo que se regula es cada cuánto se consulta.
- **Respetar `Retry-After`:** si el 429 trae esa cabecera, el cooldown dura al menos ese tiempo (con un tope).
- **Ritmo propio por fuente:** `pausa_min_s` y `pausa_max_s` pueden fijarse por fuente; LinkedIn usa pausas más largas que las globales (4–10 s).
- **Verificación previa:** antes de activar la forma combinada se comprueba con una sola petición real (`--dry-run --fuente linkedin`), pasado el cooldown, que LinkedIn acepta `sortBy=DD` y el `OR`.

Fuera de alcance: proxies, rotación de IP o cualquier forma de evadir el bloqueo; tocar las demás fuentes; el filtrado de vacantes.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `busqueda-fuentes`: LinkedIn ordena por fecha y combina palabras clave con `OR` (con respaldo por grupos); el ritmo de una fuente se adapta a los bloqueos; el cooldown respeta `Retry-After`; las pausas pueden ser por fuente.

## Impact

- **Código:**
  - `buscador_vacantes/fuentes/linkedin.py`: `sortBy` y construcción de la consulta combinada.
  - `buscador_vacantes/fuentes/base.py`: `Retry-After` y pausa propia de la fuente.
  - `buscador_vacantes/rotacion.py` y `corrida.py`: lote por turnos de grupos de palabras y chequeo del ritmo.
  - `buscador_vacantes/config.py`: campos nuevos con valores por defecto.
  - El estado nuevo (sondeos, ritmo) usa la tabla `kv` que ya existe: sin cambios en `estado.py`.
- **Configuración:** `config.yaml` (`fuentes.linkedin`: modo de consulta, tamaño de grupos, ritmo adaptativo, pausas propias; la cola larga ya está agrupada por área).
- **Datos:** sin migración de esquema; solo claves nuevas en `kv` y `rotacion`.
- **Operación:**
  - Bajan los requests a LinkedIn de ~144 a ~48 al día.
  - Se espera que desaparezcan los bloqueos y que LinkedIn vuelva a su nivel de ~70 vacantes al día.
  - La rotación de palabras clave de LinkedIn cambia: ya no avanza de 2 en 2 sino por grupos. El historial de rotación de esa fuente se reinicia.
  - Hay que desplegar en `~/buscador-vacantes` del Fedora, y la primera comprobación real se hace tras el cooldown de las 18:45 (Bogotá).
