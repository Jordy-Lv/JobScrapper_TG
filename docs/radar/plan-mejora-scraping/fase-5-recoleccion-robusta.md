# Fase 5: recolección robusta y eficiente

| | |
|---|---|
| **Dificultad** | 🔴 pesada: toca todas las fuentes y la rotación, depende de fixtures y de pruebas contra los portales reales |
| **Change de OpenSpec** | `recoleccion-robusta` (nuevo). Se recomienda partirlo en tres changes: `recoleccion-huella-y-ritmo` (5a), `recoleccion-frescura` (5b) y `recoleccion-calidad-y-cobertura` (5c). |
| **Atiende** | punto 4 del diagnóstico (recomendaciones de un experto en scraping) |
| **Depende de** | [fase 4](fase-4-observabilidad.md): sin el embudo por fuente no se puede medir si los cambios mejoran algo |

## Objetivo

Traer **más vacantes nuevas con menos peticiones**, sin bloqueos, y detectar el mismo día cuándo un portal cambia su HTML.

Hoy son unas 1.100 peticiones al día desde una sola IP, con cadencia fija, y gran parte devuelve lo mismo que la corrida anterior. En RPA el robot no debe parecer un robot ni trabajar de más: tiene que leer lo justo, cuando hay algo nuevo, y fallar de forma ruidosa.

## 5a. Huella y ritmo (🔴)

| # | Mejora | Por qué | Dónde |
|---|---|---|---|
| 1 | **Encabezados coherentes de navegador:** `Accept`, `Accept-Encoding`, `sec-ch-ua*`, `Sec-Fetch-*`, `Referer` de la propia fuente, con el mismo orden y la misma versión que el User-Agent. | Un User-Agent de Chrome sin sus encabezados es la firma más obvia de un bot. | `fuentes/base.py:175-183` |
| 2 | **Cookies persistentes por fuente:** el *cookie jar* se guarda en `kv` o en un archivo y se reutiliza entre corridas, con caducidad. | Un visitante sin cookies cada 30 minutos no es humano. | `fuentes/base.py` |
| 3 | **HTTP/2** donde el portal lo use (`httpx[http2]`). | Coherencia con el navegador declarado. | `fuentes/base.py` |
| 4 | **Cadencia irregular:** cada fuente decide en cada corrida si le toca, con un intervalo base y una fluctuación del ±30 %. | La cadencia exacta de :00 y :30 es un patrón detectable. | `corrida._fuentes_a_consultar` |
| 5 | **Frecuencia según el rendimiento:** el intervalo de cada fuente se ajusta a sus vacantes nuevas por petición, medidas en el embudo de la fase 4. Fuente que rinde, más seguido; fuente que repite, menos. Con piso y techo configurables. | Se ahorra presupuesto en fuentes saturadas y se refuerzan las productivas. | `radar/rotacion.py`, `config.yaml fuentes.*` |
| 6 | **Horario de actividad:** menos frecuencia de noche (de 22:00 a 05:00) y los domingos. | Los portales publican en horario laboral, y de noche el tráfico de bot destaca más. | `config.yaml operacion` |
| 7 | **Evaluar una salida alternativa** (proxy residencial o una segunda IP) solo si la fase 4 muestra bloqueos recurrentes. | No se agrega costo si no hace falta. | decisión del dueño 👤 |

**Meta:** al menos un 30 % menos de peticiones al día, con las mismas o más vacantes nuevas por día y cero cooldowns de 24 h en 2 semanas.

## 5b. Frescura (🔴)

| # | Mejora | Por qué | Dónde |
|---|---|---|---|
| 1 | **Ordenar por fecha** donde el portal lo permita: Computrabajo (parámetro de orden por fecha en lugar de relevancia en la página 1) y GetOnBoard (orden por `published_at` o filtro de fecha). | Hoy la página 1 de Computrabajo es por relevancia y GetOnBoard no tiene orden: se pierde lo nuevo. | `fuentes/computrabajo.py`, `fuentes/getonboard.py` |
| 2 | **Paginación incremental:** seguir a la página siguiente solo si la actual trajo vacantes nuevas, y parar en cuanto todo lo leído ya esté visto o sea más viejo que la última corrida buena. | Lee más hondo cuando hay novedades y se ahorra peticiones cuando no. | `fuentes/base.py` |
| 3 | **Magneto: página 2** cuando la página 1 trae solo vacantes nuevas. | Hoy solo lee la página 1. | `fuentes/magneto.py` |
| 4 | **Detalle de LinkedIn desacoplado** del intervalo del listado: presupuesto propio por hora, y que no se corte del todo con el ritmo adaptado; baja a la mitad. | Hoy salen como máximo unos 24 detalles al día, y cero después de un 429. | `corrida._resolver_detalles_de` |
| 5 | **Cohortes nuevas no son duplicados** (H5 de la fase 1, `republicar_tras_dias: 30`). | Una empresa que repite «Aprendiz SENA» cada mes quedaba bloqueada 90 días. | `comun/estado.py:ya_vista` |
| 6 | **Huella con ciudad:** la misma vacante de la misma empresa en otra ciudad no es duplicada. | Las convocatorias de aprendices se abren por ciudad. | `comun/normalizar.py` |

**Meta:** más vacantes nuevas por petición, y la mitad del tiempo entre la publicación en el portal y la llegada al grupo; ambas cosas se miden con `vistas.publicada` (fase 2).

## 5c. Calidad y cobertura (🟡)

| # | Mejora | Por qué |
|---|---|---|
| 1 | **Pruebas de contrato por fuente:** un fixture HTML o JSON actual de cada fuente (listado y detalle) con lo que se espera extraer: título, empresa, fecha y su precisión, URL y modalidad. | Hoy un cambio de HTML se detecta tarde y como «sin resultados». |
| 2 | **Canario diario:** una corrida `--dry-run` por fuente a las 07:00 con una consulta fija («aprendiz»). Verifica que el parser extrae al menos N vacantes con todos sus campos; si no, abre el incidente `cambio_html` con la muestra de la fase 4. | Detecta el mismo día que un portal cambió. |
| 3 | **Fuentes nuevas de aprendizaje:** evaluar la **Agencia Pública de Empleo del SENA** (el portal oficial de contratos de aprendizaje), las bolsas de empleo universitarias de la región (Universidad de Cartagena, UTB) y las convocatorias de etapa productiva. Para cada candidata, una ficha de viabilidad: términos de uso, API o HTML, volumen y bloqueos. Se implementan en changes aparte, como `agregar-fuente-spe`. | La prioridad es aprendizaje, y hoy ninguna fuente es especializada en eso, salvo SPE. |
| 4 | **Selectores en configuración:** pasar a `config.yaml` (o a `assets/radar/selectores/<fuente>.json`, como el asistente) los selectores CSS que hoy están en el código de cada fuente. | Un cambio de HTML se arregla sin tocar Python y se prueba con el fixture. |

## Criterios de aceptación

- [ ] **5a:** el embudo de la fase 4 muestra al menos un 30 % menos de peticiones al día, sin bajar las vacantes nuevas por día, durante 2 semanas, y cero cooldowns de 24 h.
- [ ] **5b:** las pruebas cubren la paginación incremental y el orden por fecha; las vacantes nuevas por petición suben frente a las 2 semanas anteriores.
- [ ] **5c:** cada fuente tiene su prueba de contrato, el canario corre a diario y hay una ficha de viabilidad por fuente candidata.
- [ ] `uv run pytest` y ruff en verde después de cada sub-change.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Cambiar encabezados o cookies provoca bloqueos nuevos. | Una fuente a la vez, primero con `--dry-run`, mirando el embudo durante 48 h antes de pasar a la siguiente. |
| Con la frecuencia adaptativa, una fuente lenta se olvida. | Piso de frecuencia por fuente, y el canario la sigue leyendo a diario. |
| Las fuentes nuevas tienen términos de uso restrictivos. | Ficha de viabilidad antes de escribir código; si no se puede, no se implementa. |

## Sesión recomendada

**Una sesión nueva por sub-fase** (🔴). Mensaje listo para pegar, para la 5a:

> Ejecuta la fase 5a de `docs/radar/plan-mejora-scraping/fase-5-recoleccion-robusta.md`: crea con `/opsx:propose` el change `recoleccion-huella-y-ritmo` (encabezados coherentes, cookies persistentes, HTTP/2, cadencia irregular, frecuencia según el rendimiento y horario de actividad) y aplícalo fuente por fuente.
