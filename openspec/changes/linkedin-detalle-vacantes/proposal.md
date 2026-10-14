## Why

Las tarjetas de LinkedIn no dicen la modalidad ni traen descripción, y su API pública de búsqueda ignora el filtro de modalidad (`f_WT`, comprobado el 2026-10-14). Desde `filtro-vacantes-limpias`, toda oferta de LinkedIn fuera de Cartagena que no diga «remoto» en el título o la ubicación se rechaza como «presencial fuera de la ciudad base». Eso evita presenciales falsas, pero también tira remotas reales (por ejemplo las de Sezzle), y el dueño no quiere perder ninguna vacante.

La página de detalle sí sirve: `GET /jobs-guest/jobs/api/jobPosting/{id}` respondió 200 con la descripción completa en las 3 pruebas (40 a 66 KB) y no se bloqueó, mientras que la página `/jobs/view/{id}` dio 429 tras unas peticiones seguidas. No trae un campo estructurado de modalidad (no aparece «Presencial»), pero con la descripción las reglas y la IA ya pueden decidir.

## What Changes

- **Detalle de ofertas de LinkedIn:**
  - Cuando una oferta de LinkedIn solo se rechazaría por no saberse su modalidad (otra ciudad sin «remoto», o call center sin modalidad) y por lo demás pasa los filtros del título, no se rechaza: se pide su detalle una sola vez.
  - La descripción se guarda recortada y la oferta se vuelve a evaluar con las reglas de siempre. Si queda en duda, decide la IA con la condición de modalidad.
- **Que no se pierda ninguna vacante:**
  - Las ofertas que esperan detalle quedan en una cola persistente. Si el detalle falla (429, tiempo agotado, error de servidor) o se acaba el presupuesto de la corrida, siguen en la cola y se reintentan en las corridas siguientes.
  - Una oferta solo sale de la cola por una de estas razones, todas visibles en el log y en el resumen diario: se resolvió, la oferta ya está cerrada (404 o 410) o venció la espera (48 h por defecto, configurable).
- **Cuidado con LinkedIn:**
  - Presupuesto de peticiones de detalle por corrida y pausa entre ellas, configurables y más conservadores que los de la búsqueda.
  - Un 429 o desafío en el detalle aplica el cooldown de LinkedIn y corta los detalles de esa corrida. Mientras haya cooldown no se piden detalles.
  - El detalle de una oferta se guarda en una caché para no pedirlo dos veces.
- **Menos falsos remotos:** la modalidad que solo sale de la descripción de un detalle de LinkedIn no se acepta por reglas. La confirma la IA leyendo el texto, para no repetir el caso de una mención suelta de «remoto» en una oferta presencial. Se ajusta el prompt: el indicio tiene que ser la modalidad del puesto, no algo de la empresa.
- **Resumen diario:** muestra los detalles pedidos, los fallidos, las ofertas recuperadas, las que siguen en cola y las vencidas.
- **Esquema de la base 2 → 3:** tablas `pendientes_detalle` y `detalles`, y columnas de detalle en `corridas`.

Fuera de alcance: el detalle de otras fuentes (Computrabajo no trae modalidad en el listado, pero ya la deduce de su etiqueta), un lector de detalle compartido con el asistente de postulación (vive en otra rama) y el login de LinkedIn.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `busqueda-fuentes`: las fuentes pueden pedir el detalle de una oferta; LinkedIn lo hace con presupuesto, pausa, cooldown compartido y caché.
- `filtrado-vacantes`: una oferta sin modalidad ni descripción de una fuente con detalle queda pendiente de detalle en lugar de rechazarse; la modalidad que solo sale de ese detalle la confirma la IA; el prompt distingue la modalidad del puesto de menciones generales.
- `deduplicacion-estado`: el estado guarda la cola de pendientes de detalle y la caché de detalles, con migración del esquema 2 al 3.
- `resumen-diario`: el contenido suma las métricas de detalle.

## Impact

- **Código:**
  - `buscador_vacantes/radar/fuentes/base.py` y `fuentes/linkedin.py`: lectura del detalle.
  - `filtros.py`: nuevo resultado «pendiente de detalle» y confirmación por IA.
  - `corrida.py`: cola de detalle y reevaluación.
  - `estado.py`: esquema 3.
  - `config.py`, `resumen.py`.
- **Configuración:** `fuentes.linkedin.detalle` en `config.yaml` (presupuesto, pausa, caracteres, vencimiento) y un ajuste del prompt del clasificador.
- **Datos:** `data/vacantes.db` migra sola al esquema 3 en la primera corrida.
- **Operación:** más peticiones a LinkedIn (hasta el presupuesto de detalle por corrida) y algo más de uso de IA por las ofertas que confirma. Sigue limitado por `ia.presupuesto_dia`. Aparecen ofertas remotas de LinkedIn que hoy se pierden, con unos minutos de retraso si caen en la cola.
- **Ramas:** sale de `main` (producción corre `main`). Se apoya en `linkedin-peticiones-eficientes` (cooldown, ritmo y sondeos), ya en `main`.
