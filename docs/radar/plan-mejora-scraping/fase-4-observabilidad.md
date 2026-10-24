# Fase 4: observabilidad, saber siempre por qué no llega nada

| | |
|---|---|
| **Dificultad** | 🟡 media: incidentes, healthcheck, resumen diario y fuentes |
| **Change de OpenSpec** | `observabilidad-scraping` (nuevo) |
| **Atiende** | punto 1 (que el silencio del 24/10 no vuelva a pasar a ciegas) y parte del 4 (recomendaciones de experto) |
| **Depende de** | [fase 0](fase-0-diagnostico-del-silencio.md). Si la fase 0 encuentra una falla operativa, la parte de esta fase que la cubre se adelanta. |

## Objetivo

Que ningún silencio del grupo dure más de **4 horas en horario laboral** sin una alerta en el chat de administración, y que esa alerta diga **en qué etapa** se cortó el flujo: fuentes, reglas, IA o Telegram.

## Principio

Hoy el radar mide lo que **entra** (ítems crudos por fuente), pero no lo que **sale** (vacantes publicadas). En RPA, la salud de un proceso se mide por su resultado de negocio, no por que el robot «corrió». Esta fase agrega la vigilancia del resultado y conserva evidencia para investigar.

## Tareas

### 1. Alerta de sequía (🟡)

- Incidente nuevo `radar:sequia`. Se abre si pasan `incidentes.horas_sequia` (4) horas sin publicar nada, dentro de `incidentes.horario_sequia` (de 07:00 a 20:00 de Bogotá, de lunes a sábado), **mientras** las fuentes devuelven ítems.
- El aviso incluye el embudo de las últimas N corridas (crudas → duplicadas → descartadas por etapa → dudosas → publicadas) y los tres motivos de descarte principales, sacados de `descartes`.
- Se cierra con la primera publicación.
- Agregar un ejemplo en `simulacion.py` y probarlo con `--simular-incidente radar:sequia --chat-prueba`.

### 2. El healthcheck dice la verdad (🟢)

- `salud.exito` **no** se envía cuando Telegram rechazó todos los mensajes de la corrida o cuando `por_enviar` lleva más de 2 h creciendo. En su lugar se envía `salud.fallo`, con el motivo.
- Las corridas que no publican porque no había nada nuevo siguen siendo un éxito.

### 3. Incidente desde el primer bloqueo (🟢)

- Hoy el incidente se abre a las 2 corridas bloqueadas seguidas (`incidentes.corridas_bloqueo: 2`). Pasar a **1** para las fuentes principales (Computrabajo, elempleo, Magneto), con un aviso corto: fuente, estado, hasta cuándo dura el cooldown y escalón.
- No repetir el aviso dentro del mismo cooldown.

### 4. Clasificación correcta de fallos (🟡)

| Caso | Hoy | Debe ser |
|---|---|---|
| LinkedIn responde 200 con el muro de login (*authwall*) | `cambio_html`, sin backoff | `bloqueo`: cooldown y ritmo adaptado |
| elempleo responde 404 | «sin resultados», cuenta como éxito | Como éxito solo si otras consultas de la misma corrida sí trajeron resultados; si todas dan 404, `cambio_html`. |
| Página de desafío | 5 subcadenas en `red.marcadores_desafio` | Agregar marcadores por fuente (títulos de Cloudflare, Akamai, «Just a moment», `cf_chl_opt`) y probarlos con fixtures. |

### 5. Evidencia para investigar (🟡)

- Guardar en `data/muestras/<fuente>/<fecha>/` el HTML (o JSON) de las respuestas que fallaron en el parseo, en un desafío o en un bloqueo, con sus encabezados, por **7 días**. Máximo 20 por fuente al día.
- `intentos` gana una columna `muestra` con la ruta del archivo.
- `diagnosticar` (de la fase 1) muestra la ruta de la muestra cuando la vacante o la fuente falló.

### 6. Embudo por fuente en el resumen diario (🟢)

Una tabla por fuente con:

- peticiones (y cuántas fueron ok);
- ítems crudos;
- nuevos;
- aceptados;
- publicados;
- tasa de duplicados;
- horas en cooldown.

Sirve para decidir en la [fase 5](fase-5-recoleccion-robusta.md) qué fuente merece más o menos presupuesto.

### 7. Runbook al día (🟢)

- `deploy/INSTALAR.md`:
  - ritmos de LinkedIn 120/180/240;
  - consultas de diagnóstico **en UTC** (las de [fase 0](fase-0-diagnostico-del-silencio.md));
  - cómo leer la alerta de sequía;
  - dónde quedan las muestras.
- Una sección «¿No llegan vacantes?» con el orden de revisión.

## Criterios de aceptación

- [ ] Con `--simular-incidente radar:sequia --chat-prueba` llega el aviso con el embudo.
- [ ] Una prueba demuestra que, si Telegram rechaza todo, el healthcheck recibe `fallo` y no `exito`.
- [ ] Un 403 de Computrabajo abre el incidente en la misma corrida.
- [ ] Un fixture del *authwall* de LinkedIn queda clasificado como `bloqueo`.
- [ ] Las muestras se guardan y se borran a los 7 días; se prueba con `Estado.limpiar` o con una limpieza de archivos.
- [ ] El resumen diario muestra el embudo por fuente.
- [ ] `uv run pytest` y ruff en verde.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Falsas alarmas de sequía los domingos y de noche. | Horario y días configurables; el umbral se mide primero en el chat de prueba. |
| Las muestras ocupan disco. | Tope por fuente y día, y retención de 7 días. |
| Abrir el incidente al primer bloqueo genera ruido. | Un solo aviso por cooldown y solo para las fuentes principales. |

## Sesión recomendada

**Sesión nueva**. Mensaje listo para pegar:

> Ejecuta la fase 4 de `docs/radar/plan-mejora-scraping/fase-4-observabilidad.md`: crea con `/opsx:propose` el change `observabilidad-scraping` (alerta de sequía, healthcheck veraz, incidente al primer bloqueo, clasificación de fallos, muestras de respuestas, embudo por fuente y runbook) y aplícalo.
