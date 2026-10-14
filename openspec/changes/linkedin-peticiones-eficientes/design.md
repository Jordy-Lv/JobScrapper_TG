## Context

Ver `proposal.md` (Why). Estado actual del código:

- `Fuente.ejecutar()` (`fuentes/base.py`) recorre el lote con pausas globales (`red.pausa_min_s/max_s`, 4–10 s), se detiene ante un 429/403/999 y aplica `aplicar_cooldown()` (2 h, 6 h, 24 h). `filtrar_cabeceras()` ya guarda `retry-after` en el `Intento`, pero nadie lo usa.
- `rotacion.calcular_lote()` toma `reservado_nucleo` palabras del núcleo (con `paginas_nucleo` páginas) y el resto del presupuesto de la cola larga. Trabaja con listas de `str`: no le importa si cada «palabra» es en realidad una consulta combinada.
- `LinkedIn.construir_peticion()` manda `keywords`, `location`, `f_E`, `f_TPR=r86400` y `start=0` fijo. No ordena, no pagina y no declara `tamano_pagina` (el valor por defecto de la base es 20, pero LinkedIn entrega 10).
- La corrida alterna las variantes (`opciones.variantes`) con la rotación de grupo `variante`, y `Corrida._consultar` ya conoce el índice de la variante.
- La tabla `kv (clave, valor)` y `Estado.kv_obtener/kv_guardar` existen: sirven para guardar estado nuevo sin migrar el esquema.
- `config.yaml`: LinkedIn tiene `presupuesto: 3`, `reservado_nucleo: 2`; el núcleo tiene 14 palabras y la cola larga está agrupada por área (9 áreas, 69 términos).
- Datos del servidor (2026-10-13): 36 requests en el día, 9 con 429, siempre en la 2.ª o 3.ª petición de una corrida; todas las respuestas 200 traen exactamente 10 items.

## Goals / Non-Goals

**Goals:**
- Pasar de ~144 a ~50 peticiones diarias a LinkedIn sin que ninguna publicación nueva tarde más de ~1 h en detectarse (hoy una palabra clave del núcleo se revisa cada ~3,5 h).
- Que la petición traiga lo último publicado aunque haya más de 10 coincidencias.
- Que el sistema baje solo el ritmo ante bloqueos y lo recupere, sin intervención ni edición de `config.yaml`.
- Poder volver al comportamiento actual con un cambio de configuración.

**Non-Goals:**
- Proxies, rotación de IP, cambio de huella u otra forma de esquivar el bloqueo.
- Pedir el detalle de cada vacante (más peticiones).
- Cambiar las otras fuentes (solo reciben las capacidades genéricas de `Retry-After`, pausa propia y ritmo, sin activarlas).
- Cambiar el filtrado ni la clasificación.

## Decisions

### 1. Una consulta combinada es un `str` más en las listas de rotación
`PalabrasClave` gana `grupos_nucleo(max_terminos)` y `grupos_cola(max_terminos)`: cada grupo es un único `str` con los términos entre comillas y unidos por ` OR ` (`"practicante sistemas" OR "aprendiz SENA" …`). La cola larga se agrupa por área, partida en trozos de `max_terminos`. Como `Consulta.keyword` ya es un `str`, `Fuente`, `intentos.keyword` y `Vacante.keyword` no cambian de forma. El log recorta la consulta a ~80 caracteres.

*Alternativa descartada*: una petición por término con `sortBy=DD` solamente. Sin combinar, cubrir 14 términos cada hora cuesta 14 peticiones por hora, justo lo que dispara el 429.

*Consecuencia aceptada*: la métrica «palabras clave sin resultados en 7 días» del resumen pasa a hablar de grupos, no de términos.

### 2. Turnos: una petición por corrida, con la cola larga cada N corridas
Con `opciones.consulta.modo: or`, el lote de la corrida lo calcula una función nueva de `rotacion` (no `calcular_lote`):
- Un contador de grupo `turno` cuenta las corridas ejecutadas. Si `turno % cola_cada == cola_cada - 1`, el lote es un grupo de la cola larga (página 1); si no, es un grupo del núcleo (con `paginas_nucleo: 2`, la página 2 solo se lee si la 1 vino completa).
- Dentro del núcleo y de la cola, la posición recorre el producto *(grupo × variante)*: `variante = n % V`, `grupo = (n // V) % G`. Así ninguna variante queda atada a un solo grupo (si ambos alternaran con período 2, siempre coincidirían).
- El núcleo y la cola llevan contadores propios, y avanzan solo si la consulta se ejecutó.

Con `cola_cada: 4` y un solo grupo de núcleo, son 36 consultas de núcleo y 12 de cola al día: cada variante del núcleo se revisa cada hora; la cola larga recorre sus ~10 grupos cada ~20 h.

*Alternativa descartada*: `presupuesto: 2` con una consulta de núcleo y otra de cola en cada corrida. Son ~96 peticiones al día y vuelve a rozar el umbral observado.

### 3. Ventana de publicación (`f_TPR`) según el último sondeo
La petición pide `f_TPR=r<segundos>` con `segundos = ahora − último_sondeo_ok + margen`, acotado entre `ventana_min_h` (2 h) y 24 h. Si no hay sondeo, 24 h. El sondeo se guarda en `kv` con la clave `sondeo:<fuente>:<variante>:<hash corto de la consulta>`.

Esto cumple tres cosas:
- En régimen normal la ventana es de ~1,5–2 h: una página completa de 10 significa de verdad «hay más nuevas de las que caben», y la segunda página se pide solo entonces.
- Tras un cooldown o un apagado la ventana crece sola y cubre el hueco: no se pierde lo publicado mientras LinkedIn estuvo en pausa.
- La cola larga, que se revisa cada ~20 h, pide ~20 h.

Detalles que importan:
- La ventana se calcula una vez por consulta y corrida y se reutiliza en la página 2: el sondeo se escribe al final, nunca entre páginas.
- El sondeo se escribe solo si **todas** las páginas pedidas de esa consulta respondieron bien. Si la página 2 recibe un 429, se conserva el sondeo anterior y la ventana siguiente cubre ese hueco.
- La hora que se guarda es la del inicio de la petición, no la del fin.
- Con `--dry-run` no se escribe ningún sondeo.

*Alternativa descartada*: ventana fija de 2 h. Si el servidor se apaga o hay un cooldown de 6 h, se pierde lo publicado en ese tiempo.

*Riesgo de la verificación*: LinkedIn podría no aceptar segundos arbitrarios en `f_TPR`. En ese caso (tarea 1.2) se vuelve a `r86400` con orden por fecha y paginación por saturación, que sigue cumpliendo los escenarios con menos precisión.

### 4. Ritmo adaptativo genérico en la base, activado solo en LinkedIn
Se agrega a `config.Fuente` un bloque opcional `ritmo: {intervalos_min: [30, 60, 120], limpias_para_bajar: 12, tolerancia_min: 5}`. El estado va en `kv`: `ritmo:<fuente>:nivel`, `ritmo:<fuente>:limpias` y `ritmo:<fuente>:ultima`.
- Antes de consultar (junto al chequeo de cooldown en `Corrida._consultar`), si `ahora − ultima < intervalos_min[nivel] − tolerancia_min`, la fuente se omite con el motivo «ritmo adaptado a N min». La tolerancia absorbe el `RandomizedDelaySec=120` del timer, que de otro modo haría que una corrida a los 29:40 min saltara.
- Un bloqueo sube `nivel` (tope: el último) y pone `limpias` en 0. Cada petición exitosa suma `limpias`; al llegar a `limpias_para_bajar` baja un nivel y vuelve a 0.
- `ultima` se escribe al hacer una petición, no al omitir.
- Con `--dry-run` no se tocan `nivel`, `limpias` ni `ultima`.

Esto sustituye al «presupuesto adaptativo» planteado al inicio: con una petición base por corrida no hay presupuesto que bajar, y el parámetro que sí controla la presión sobre LinkedIn es cada cuánto se la consulta. Se suma al cooldown, no lo reemplaza: el cooldown corta de golpe; el ritmo evita que, al volver, se repita el patrón que provocó el bloqueo.

### 5. `Retry-After` en `aplicar_cooldown`
`aplicar_cooldown(ahora, minimo_s=None)` toma el mayor entre el escalón y `minimo_s`, con tope `red.retry_after_max_h` (24 por defecto). `ejecutar()` lee `retry-after` del `Intento` que bloqueó y lo interpreta como segundos o como fecha HTTP; un valor ilegible se ignora. No cambia el cálculo del escalón ni de `fallos_consecutivos`.

### 6. Pausa propia por fuente
`config.Fuente` gana `pausa_min_s` y `pausa_max_s` opcionales (validadas como las de `Red`). `Fuente.ejecutar()` usa los de la fuente si existen y, si no, los de `red`. LinkedIn: 20–45 s (solo se nota en la segunda página, porque el resto de corridas hace una sola petición).

### 7. Respaldo: `modo: simple`
`opciones.consulta.modo` admite `or` (por defecto, tras la verificación) y `simple`. En `simple`:
- se usa `rotacion.calcular_lote` con una palabra por petición, como hoy;
- se mantienen el orden por fecha, la ventana de publicación (por palabra), el ritmo adaptativo, `Retry-After` y las pausas propias;
- `presupuesto` y `reservado_nucleo` vuelven a mandar (se recomienda `presupuesto: 2`).

La cobertura baja (cada palabra tarda más en volver), pero el ritmo es sostenible y la primera página sigue trayendo lo último. Es el camino si la tarea 1.2 muestra que LinkedIn ignora o rechaza el `OR`.

### 8. `construir_peticion` y paginación de LinkedIn
- `sortBy` sale de `opciones.consulta.orden` (por defecto `DD`).
- `soporta_paginas = True`, `tamano_pagina = 10` y `start = (pagina − 1) × 10`. El resto de la lógica de saltar la página 2 si la 1 no vino completa ya está en `Fuente.ejecutar`.
- La corrida le pasa a la fuente el índice de su variante (`fuente.variante_id`), que forma parte de la clave del sondeo.

## Risks / Trade-offs

- **LinkedIn no acepta el `OR` o limita la longitud de la consulta** → tarea 1.2 lo comprueba con una petición real antes de activar; `max_terminos` baja si hace falta; `modo: simple` es el respaldo.
- **Una consulta muy amplia se llena de vacantes que no son de TI** y la página 1 sale saturada → la segunda página y la ventana corta lo absorben; las reglas y la IA siguen filtrando como hoy. Se mide en la primera semana con `intentos.items`.
- **Más de 20 publicaciones nuevas en una hora** (más que dos páginas) → pérdida posible, pero muy improbable con `f_E=1,2` en Colombia; la ventana de la siguiente consulta no la recupera, porque el sondeo avanza. Se vigila con la proporción de corridas que leen la página 2.
- **Frescura de la cola larga** (~20 h por grupo): es peor que el núcleo, pero hoy una palabra de la cola tarda ~69 corridas (~35 h) en volver. Mejora.
- **Corridas omitidas por el ritmo retrasan lo nuevo** tras un bloqueo → es el costo buscado; la ventana dinámica evita que se pierda y el intervalo vuelve a 30 min tras unas 12 peticiones limpias por nivel.
- **El mismo IP sigue sujeto a Cloudflare/LinkedIn** → si tras el cambio vuelven los 429 con ~50 peticiones diarias, el siguiente paso es bajar el ritmo base (60 min) en la configuración, no evadir.
- **El historial de rotación de LinkedIn se reinicia** → sin daño: solo cambia qué grupo toca primero.

## Migration Plan

1. Desarrollar y probar en local (`.venv/Scripts/python -m pytest`, 3 pruebas fallan siempre en Windows por motivos ajenos).
2. Desplegar en `~/buscador-vacantes` (`git pull --ff-only`) con `fuentes.linkedin.opciones.consulta.modo: simple` si LinkedIn sigue en cooldown.
3. Pasado el cooldown, ejecutar **una** petición de comprobación: `uv run buscador.py --dry-run --fuente linkedin` (tarea 1.2) y revisar `intentos` (status, items) y el listado impreso. Con el resultado, fijar `modo`, `max_terminos` y el formato de `f_TPR`.
4. Vigilar 48 h: peticiones por día, 429, vacantes de LinkedIn publicadas por día (meta: volver a ~70) y proporción de corridas con página 2.
5. **Vuelta atrás:** `modo: simple` y `ritmo` sin niveles extra, o revertir el commit. No hay migración de base de datos; las claves nuevas de `kv` y `rotacion` se ignoran si se revierte.
