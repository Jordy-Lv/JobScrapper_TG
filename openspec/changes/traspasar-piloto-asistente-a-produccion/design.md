## Context

Ver proposal.md. Estado medido el 2026-10-14 en el Fedora (solo lectura):
- `~/buscador-vacantes` está en `main` (`9da02c9`, incluye la fase 0) y su `.env` tiene `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_CHAT_PRUEBA`, `DEEPSEEK_API_KEY`, `HEALTHCHECK_URL`, `ASISTENTE_BOT_TOKEN` y `TELEGRAM_CHAT_ADMIN`; **no** tiene `ASISTENTE_CLAVE_CIFRADO`.
- `~/buscador-asistente` está en la rama del asistente (`c94b579`); su `.env` tiene `TELEGRAM_CHAT_ID`, `ASISTENTE_BOT_TOKEN`, `ASISTENTE_CLAVE_CIFRADO` y `GEMINI_PRUEBA`. Datos: `data/asistente.db` (~704 KB), `data/asistente/` (~112 KB: `postulaciones/` y `usuarios/`) y un `vacantes.db` propio que no se traspasa (el piloto ya apunta a la de producción).
- La unidad `buscador-asistente.service` apunta a `~/buscador-vacantes`, pero `prueba.conf` (en `buscador-asistente.service.d/`) fuerza `WorkingDirectory=~/buscador-asistente`.
- `config.local.yaml` del piloto tiene `asistente.vacantes_db: /home/ByLOGAN/buscador-vacantes/data/vacantes.db`, `asistente.api.url_publica: https://postulador.tailf6cdf1.ts.net` y `enlace_canal: false`; el de producción tiene `enlace_canal: true` y no tiene esas dos claves.
- Tailscale Funnel expone `https://postulador.tailf6cdf1.ts.net` hacia el puerto 8787 local; no depende de la carpeta.
- El instalador (`deploy/INSTALAR.md`, §11) describe la unidad y el `prueba.conf` solo para el piloto.

## Goals / Non-Goals

**Goals:**
- Asistente corriendo desde `~/buscador-vacantes` con sus datos y clave, sin pérdida.
- Vuelta atrás probada en minutos.

**Non-Goals:**
- Cambiar código, mover carpetas del repositorio (fase 1) o migrar `asistente.db` a `control.db` (fase 4).
- Retirar `~/buscador-asistente` (tarea posterior con confirmación aparte).
- Tocar el buscador (radar) ni sus temporizadores.

## Decisions

- **Parar antes de copiar:** con la base en modo WAL, se detiene el servicio y se copia con la API de respaldo de SQLite (no con `cp` en caliente), y luego se copia la carpeta de evidencia con `cp -a`.
- **Clave sin pantalla:** se copia del `.env` del piloto al de producción con `grep`/`>>` en el propio servidor, sin imprimir; la comprobación compara huellas (hash) de ambos valores, no los valores.
- **Token del bot:** si `ASISTENTE_BOT_TOKEN` difiere entre carpetas (comparación por huella), se usa el del piloto, que es el que tiene usuarios vinculados; no se pierden sus vínculos.
- **`config.local.yaml`:** se añaden a la copia de producción solo `vacantes_db` y `api.url_publica`, manteniendo `enlace_canal: true` (decisión del dueño ya vigente en producción).
- **`GEMINI_PRUEBA`:** no se copia (es una clave de prueba del piloto); se consulta al dueño si debe pasar.
- **Dependencias:** `uv sync --group asistente` en `~/buscador-vacantes` antes de quitar `prueba.conf`; la unidad usa `uv run --frozen --group asistente`.
- **Vuelta atrás:** reinstalar `prueba.conf` y `daemon-reload`; la copia de desarrollo no se toca. Alternativa descartada: mover (no copiar) los datos, que impediría volver atrás.
- **Ventana:** hacerlo con poca actividad; el bot queda parado entre la parada y el arranque. Se avisa al dueño antes.

## Risks / Trade-offs

- Clave distinta o corrupta deja ilegibles los datos cifrados → comprobación de descifrado previa al cierre y vuelta atrás.
- Los usuarios escriben al bot mientras está parado → el bot de Telegram reentrega las actualizaciones pendientes al arrancar, pero se avisa de la ventana.
- Dos servicios con el mismo token de bot a la vez provocan conflicto de `getUpdates` → nunca se arranca el nuevo sin parar el viejo.
- Falta de dependencias del grupo `asistente` en producción → `uv sync` previo y prueba con `--help`.
- Los permisos de SSH de Claude Code pueden bloquear los comandos de modificación → el dueño da la regla o ejecuta los pasos.
