## Why

Producción (`~/buscador-vacantes` en el Fedora) corre `main`, pero el asistente de postulación vive en la rama `asistente-postulacion-telegram`, que lleva 77 commits que `main` no tiene, mientras `main` tiene 5 que la rama no tiene. Con las ramas divergentes, cualquier reestructura posterior de carpetas (fases 1-4 del plan de reestructura) generaría conflictos en cada archivo movido. Hay que unificar primero.

## What Changes

- Integrar `asistente-postulacion-telegram` en `main` con un merge (sin reescribir historia), resolviendo 4 conflictos de texto medidos en un merge de prueba: `README.md` (3 bloques), `tests/test_buscador.py` (2), `tests/test_config.py` (1) y `tests/test_resumen.py` (1). Todos son adiciones de ambos lados que se conservan juntas; `config.yaml`, `corrida.py` y `resumen.py` se fusionan sin conflicto.
- Dejar la suite de pruebas completa en verde sobre el resultado del merge antes de integrarlo a `main`.
- Verificar antes de desplegar que el `.env` del Fedora tenga `TELEGRAM_CHAT_ADMIN`. Estado medido hoy: **no lo tiene** (solo define `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_CHAT_PRUEBA`, `DEEPSEEK_API_KEY`, `HEALTHCHECK_URL` y `ASISTENTE_BOT_TOKEN`).
- Desplegar con `git pull` en el Fedora solo tras la confirmación explícita del dueño.
- No cambia el comportamiento del sistema más allá de lo que ya traen las ramas: los avisos de incidentes y el resumen pasan al grupo de administración.

## Capabilities

### New Capabilities
- `despliegue-produccion`: condiciones que deben cumplirse para integrar la rama del asistente en `main` y desplegarla en producción (suite en verde, variable de administración presente, confirmaciones del dueño).

### Modified Capabilities

## Impact

- Git: `main` recibe 77 commits; la rama `linkedin-detalle-vacantes` (con trabajo sin confirmar en el árbol de trabajo) se actualizará contra el `main` unificado después, no antes.
- Código: sin cambios de lógica propios; solo la resolución de conflictos en README y pruebas.
- Producción: el `.env` del Fedora necesita `TELEGRAM_CHAT_ADMIN`; sin ella, el aviso de incidentes y el resumen no tienen destino de administración.
- Pasos irreversibles o externos (merge a `main`, push, despliegue) quedan bloqueados hasta confirmación del dueño.
