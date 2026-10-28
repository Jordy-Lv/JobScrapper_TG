## Why

Hoy, al tocar «Postular» (⚡), la vacante se encola al instante y la extensión puede empezar a postular en segundos. Un toque sin querer en el canal o en el bot ya no se puede deshacer: la única salida es llegar a tiempo a la pestaña del portal. Una pausa corta y visible antes de encolar da margen para arrepentirse sin costo.

## What Changes

- Al tocar «Postular», la card de la postulación muestra una **cuenta regresiva animada de 5 segundos** (barra que se va llenando y los segundos restantes) con un botón **«Cancelar»**. Se edita el mismo mensaje; no se envían mensajes sueltos.
- La vacante **solo se encola cuando la cuenta termina** sin cancelar. Mientras cuenta, la cola, la extensión y el servidor no saben de la postulación.
- Si el usuario cancela, **no se encola nada**: la card pasa a «Cancelaste la postulación. No envié nada.» con un botón «Postular» para volver a empezar.
- Un segundo toque sobre la misma vacante mientras cuenta no abre otra cuenta ni otra card; el aviso corto dice que ya está contando.
- Si el bot se reinicia durante la cuenta, la cuenta se descarta (no se postula) y la card avisa que se interrumpió y ofrece «Postular».
- La duración es configurable (`asistente.cuenta_regresiva_segundos`, 5 por defecto; 0 la desactiva).
- **Sin cambios en**: «Reintentar» tras un bloqueo (es una acción explícita sobre algo que ya existe), el paquete de respaldo, la cola, la extensión y el contrato del servidor.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `tarjeta-postulacion-asistente`: la card gana la fase de cuenta regresiva y la de cancelación, y el toque ya no encola de inmediato. Esta spec hoy solo existe dentro del change `tarjeta-unica-flujo-postulacion` (aún sin archivar), así que el delta usa `ADDED` y se aplica después de archivarlo, como ya hacen otros changes del repositorio.

## Impact

- **Código**: `buscador_vacantes/asistente/conversacion.py` (`procesar_toque`, `al_toque_canal`, `al_boton`, arranque), `buscador_vacantes/asistente/tarjeta_postulacion.py` (fases y botones nuevos), `buscador_vacantes/asistente/textos.py`, configuración (`config.yaml` y su modelo).
- **Pruebas**: `tests/asistente/test_tarjeta_postulacion.py` y `tests/asistente/test_bot.py`; varios tests actuales esperan «En cola» justo tras el toque y deberán usar una cuenta de 0 s.
- **Riesgos**: el límite de ediciones de Telegram (una edición por segundo, cinco por toque); la respuesta del botón del canal debe seguir siendo inmediata. Mitigación: la cuenta corre en segundo plano, fuera del candado del usuario.
- **Dependencias**: se apoya en `tarjeta-unica-flujo-postulacion`.
