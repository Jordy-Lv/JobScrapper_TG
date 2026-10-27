## Why

Con la fase 0 el código del asistente ya está en `main` y en `~/buscador-vacantes` (Fedora), pero el servicio `buscador-asistente` sigue corriendo desde la copia de desarrollo `~/buscador-asistente` (rama `asistente-postulacion-telegram`) por un archivo `prueba.conf` que el propio archivo dice que se borra «al pasar a producción». Mientras tanto hay dos copias del código, dos bases con datos distintos y una rama que ya no se debe mantener. Hay que traspasar el piloto para tener un solo lugar de producción, y es requisito previo de la fase 1 de la reestructura.

## What Changes

- Parar `buscador-asistente`, copiar sus datos (`data/asistente.db` y `data/asistente/`) a `~/buscador-vacantes/data/` y verificarlos.
- Copiar al `.env` de producción las variables del asistente que faltan, sobre todo `ASISTENTE_CLAVE_CIFRADO`, sin mostrar ni registrar valores.
- Completar `config.local.yaml` de producción con lo que hoy solo tiene la copia del piloto: `asistente.api.url_publica` y la ruta de `vacantes_db`, conservando `enlace_canal: true`.
- Instalar las dependencias del grupo `asistente` en `~/buscador-vacantes` (`uv sync --group asistente`).
- Borrar `~/.config/systemd/user/buscador-asistente.service.d/prueba.conf` para que el servicio arranque desde `~/buscador-vacantes`, recargar y arrancar.
- Comprobar que el bot responde, que la API pública (Tailscale Funnel) responde y que la información de los usuarios sigue legible.
- Dejar `~/buscador-asistente` intacta como vuelta atrás hasta pasados unos días; retirarla después con confirmación aparte.
- **No** cambia el código del repositorio ni el comportamiento del asistente.

## Capabilities

### New Capabilities
- `traspaso-piloto-asistente`: condiciones para pasar el asistente de la copia de desarrollo a producción sin perder datos, con vuelta atrás.

### Modified Capabilities

## Impact

- Servidor (Fedora): `data/` y `.env` de `~/buscador-vacantes`, `config.local.yaml`, la unidad systemd del asistente (se quita `prueba.conf`).
- Usuarios del piloto: el bot queda parado unos minutos durante el traspaso.
- Datos sensibles: la clave de cifrado y los datos cifrados de los usuarios; si la clave no coincide, quedan ilegibles.
- Respaldo ya hecho en `~/respaldos/2026-10-14-pre-unificacion/` (bases, `.env`, evidencia); se repite uno justo antes de empezar.
- Todos los pasos modifican producción: cada fase pide confirmación explícita al dueño y los comandos por SSH requieren permiso.
