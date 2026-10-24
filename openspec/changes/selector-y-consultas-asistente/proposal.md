# Proposal

> **Origen.** Estos bloques salieron de `aprendizaje-primero-canal-y-consultas` (antes bloques 6 y 7) el 2026-10-24, por la decisión del dueño de poner primero el aprendizaje y el «sin experiencia». Queda **propuesto para después** del [plan de mejora del scraping](../../../docs/radar/plan-mejora-scraping/README.md). No se aplica antes de las fases 1 y 2.

## Why

El canal «JOBS - PRÁCTICAS/APRENDIZ» tiene dos fricciones de uso, ajenas a qué vacantes se encuentran:

- **Ruido en el canal.** Cada mensaje del canal lleva un botón ⚡ por vacante.
- **El bot solo sirve para postularse.** No permite consultar las ofertas ya publicadas: el usuario tiene que desplazarse por el canal para encontrarlas.

## What Changes

**1. Elegir la vacante con menos ruido**
- Cada mensaje de ofertas del canal lleva **un solo botón**, «⚡ Postularme a una de estas», en lugar de un botón por vacante.
- El botón abre el bot asistente en privado con un **selector**: una sola tarjeta editable con las vacantes de ese mensaje, numeradas y paginadas. Al elegir una vacante sigue el flujo de postulación de siempre.
- Si el usuario aún no terminó el registro, el lote de vacantes queda pendiente y el selector aparece al terminar.

**2. Consultas de ofertas desde el bot asistente**
- Nuevo comando `/buscar` y botón «🔎 Buscar vacantes» en la ayuda del bot. Abren una tarjeta de filtros con botones: nivel, área, modalidad, antigüedad, fuente y solo destacadas.
- Los resultados se paginan y cada uno se puede elegir para postularse, con el mismo selector del punto 1.
- **Búsqueda con tus palabras:** `/buscar remotas de Python de esta semana`. DeepSeek solo traduce el texto a filtros de una lista cerrada, y el código hace la consulta. La IA nunca inventa ni elige vacantes.
  - Tiene un tope diario por usuario.
  - Sin IA, el texto se usa como búsqueda en el título.
- Mientras `alcance.junior` esté apagado, el filtro «Junior» aparece como pausado.

**Fuera de alcance:**
- alertas personalizadas («avísame cuando salga…»);
- filtros guardados;
- fuentes nuevas;
- cambios en la extensión del navegador.

## Dependencias

- **Fase 1** (`aprendizaje-primero-canal-y-consultas`): el interruptor `alcance.junior`, la tabla `descartes` y, ya migradas en la tarea 1.1 de ese change, la tabla `lotes_canal` y las columnas `publicada`, `destacada` y `area` de `vistas`.
- **Fase 2** (`visibilidad-area-y-fecha`): define qué es una vacante destacada (área foco) y la fecha exacta de publicación. El filtro «solo destacadas» y la marca ⭐ del selector se ajustan a esa definición **al aplicar este change**. Los specs de aquí conservan los criterios del diseño original (práctica en el título, área de TI, ciudad base o remoto, 3 días) y hay que revisarlos primero.
- `dividir-conversacion-asistente` (0/20): si se aplica antes, el selector y las consultas se registran con su `@boton`.

## Capabilities

### New Capabilities

- `selector-vacantes-asistente`: el botón único del canal, el enlace al bot con el lote de vacantes y la tarjeta de selección paginada.
- `consultas-vacantes-asistente`: el comando `/buscar`, la tarjeta de filtros, los resultados paginados y la traducción del texto libre a filtros con DeepSeek.

### Modified Capabilities

Estas capacidades todavía no están en `openspec/specs/`: nacen al archivar `crear-buscador-vacantes`. Por eso su delta solo usa `ADDED`.

- `deduplicacion-estado`: se guarda el lote de cada mensaje publicado y los datos de consulta de cada vacante enviada.

## Impact

- **Radar:** `publicacion.py` (botón único) y `comun/estado.py` (escritura de `lotes_canal`, tabla ya migrada por el change de la fase 1).
- **Notificador:** `NotificadorBotAPI.enviar_mensaje` acepta botones `url:`.
- **Asistente:**
  - `asistente/conversacion.py`, o el paquete que deje `dividir-conversacion-asistente`: selector y `/buscar`.
  - `asistente/selector.py` y `asistente/consultas.py` nuevos, con lógica pura.
  - `asistente/vacantes.py`: el índice gana ubicación, modalidad, publicada, destacada y área.
  - `asistente/datos.py`: migración del esquema 3.
  - `asistente/textos.py` y `docs/asistente/guia-usuario.md`.
- **Configuración:** `asistente.consultas` en `config.yaml`.
- **Pruebas:** `tests/radar/test_publicacion.py`, `tests/asistente/test_bot.py`, `test_datos.py` y archivos nuevos para el selector y las consultas.
- **Producción (Fedora):** `git pull` y reinicio de `buscador-asistente`. La migración de `asistente.db` es aditiva.
- **Costo de IA:** la traducción de consultas usa la clave DeepSeek del servidor, con tope diario.
