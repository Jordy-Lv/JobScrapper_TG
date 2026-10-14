## Why

El grupo «JOBS - PRÁCTICAS/APRENDIZ» recibe, además de las ofertas, el resumen diario y los avisos de incidentes del buscador. Mezclan operación con ofertas y ensucian el grupo de los usuarios, que solo quieren ver las vacantes con sus botones ⚡.

## What Changes

- Nueva variable de entorno `TELEGRAM_CHAT_ADMIN`: id del grupo de administración, creado aparte.
- El grupo de ofertas (`TELEGRAM_CHAT_ID`) recibe solo el banner y los mensajes de vacantes con sus botones.
- El resumen diario y los avisos de incidentes (reportero) pasan a `TELEGRAM_CHAT_ADMIN`.
- Sin `TELEGRAM_CHAT_ADMIN` se conserva el comportamiento actual (todo al grupo de ofertas) y se deja una advertencia en el log, para no perder avisos.
- En modo prueba todo sigue yendo a `TELEGRAM_CHAT_PRUEBA`.
- Se verifica que el asistente no envíe nada operativo al grupo de ofertas (hoy solo comprueba membresía y avisa al dueño por privado).

## Capabilities

### New Capabilities
- `destino-mensajes-telegram`: a qué chat de Telegram va cada tipo de mensaje del buscador (ofertas vs. operación).

### Modified Capabilities

## Impact

- Código: `buscador_vacantes/config.py` (secretos), `buscador_vacantes/corrida.py` (`_chat_destino`, `_incidentes`, `_resumen`), `buscador_vacantes/simulacion.py` si aplica.
- Configuración: `.env.example`, `deploy/INSTALAR.md`, README.
- Pruebas: `tests/test_config.py`, `tests/test_buscador.py` (o la que cubra la corrida y el resumen).
- Despliegue: el dueño crea el grupo, añade el bot como administrador y pone el id en el `.env` del servidor.
