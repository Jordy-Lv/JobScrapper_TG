## Why

La card de postulación muestra el título, la empresa, la afinidad, la barra y los pasos, pero no dice en qué plataforma (Computrabajo, Magneto, elempleo) está la vacante. El usuario solo la deduce por el botón «Postular» que tocó o, al final, por la línea «Magneto confirmó tu postulación». Con varias postulaciones en curso en portales distintos, la card no se explica sola: falta saber a qué portal va cada una desde que se crea hasta que termina.

## What Changes

- La cabecera de la card muestra la plataforma de la vacante junto a la empresa («Maaji · Magneto»), o sola si no hay empresa.
- La cabecera es la misma en todas las fases de principio a fin: cuenta regresiva, en cola, esperando navegador, pregunta rápida, revisión de respuestas, progreso, sesión, verificación, bloqueo, respaldo manual, cancelada, cerrada, confirmada e incierta.
- En la confirmación e incierta (`resumen_postulacion.tarjeta`) la plataforma también aparece en la cabecera, además de la cita de estado que ya la nombra.
- Si la postulación no tiene plataforma conocida, la cabecera queda como hoy (sin línea vacía ni «None»).
- Sin cambios en la extensión, en la base ni en los botones.

## Capabilities

### New Capabilities
<!-- ninguna -->

### Modified Capabilities
- `tarjeta-postulacion-asistente`: la cabecera de la card incluye la plataforma de la vacante en todas sus fases y vistas principales.

## Impact

- `buscador_vacantes/asistente/tarjeta_postulacion.py` (`_cabecera`) y `buscador_vacantes/asistente/resumen_postulacion.py` (`tarjeta`).
- Pruebas en `tests/asistente/test_tarjeta_postulacion.py` y `tests/asistente/test_resumen_postulacion.py` (o donde hoy se prueba la cabecera); las que comparan el texto exacto de la cabecera se actualizan.
- Sin migración ni cambios de API. Convive con `explicar-espera-en-cola`, que también toca esta capacidad: aquí el requisito es aparte.
