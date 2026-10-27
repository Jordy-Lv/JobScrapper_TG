## 1. Comprobaciones previas (solo lectura)

- [x] 1.1 Confirmar que la corrida del radar de las 02:30 terminó bien con el código unificado y que el aviso de administración llega al grupo (hecho 2026-10-14: corrida 497 ok; el dueño confirmó el aviso)
- [x] 1.2 Comparar por huella (sin mostrar valores) `ASISTENTE_BOT_TOKEN` entre ambos `.env` (iguales por huella)
- [x] 1.3 Anotar recuentos de usuarios, postulaciones y respuestas de `asistente.db` del piloto (usuarios 2, postulaciones 0, respuestas 0, navegadores 0, banco_preguntas 96)
- [x] 1.4 Decidir con el dueño si `GEMINI_PRUEBA` pasa a producción (decisión del dueño: no pasa; si un usuario la usa, pone la suya desde el bot)
- [x] 1.5 Confirmar que `uv` y las dependencias del grupo `asistente` se pueden instalar en `~/buscador-vacantes` (uv 0.12.23; `uv sync --frozen --group asistente --dry-run` ok)

## 2. Preparación (aún sin parar el servicio)

- [x] 2.1 Repetir el respaldo (bases con la API de SQLite, `.env` y `config.local.yaml` de ambas carpetas) y verificar su integridad (`~/respaldos/2026-10-14-traspaso-piloto/`, integridad ok)
- [x] 2.2 `uv sync --group asistente` en `~/buscador-vacantes` y probar `buscador.py asistente --help`
- [x] 2.3 Preparar el `config.local.yaml` de producción con `api.url_publica`, conservando `enlace_canal: true` (`vacantes_db` no hace falta: `null` usa la base propia; copia previa en el respaldo)

## 3. Traspaso (👤 confirmación del dueño antes de parar)

- [x] 3.1 Avisar al dueño y pedir confirmación; parar `buscador-asistente`
- [x] 3.2 Copiar `asistente.db` con la API de respaldo de SQLite y `data/asistente/` con `cp -a` a `~/buscador-vacantes/data/`
- [x] 3.3 Verificar integridad y mismos recuentos que en 1.3
- [x] 3.4 Copiar `ASISTENTE_CLAVE_CIFRADO` (y las variables acordadas en 1.4) al `.env` de producción sin imprimir; comprobar por huella que coinciden
- [x] 3.5 Retirar `prueba.conf`, `systemctl --user daemon-reload` y arrancar `buscador-asistente` (arrancó 02:39:44; `prueba.conf` guardado en el respaldo)

## 4. Verificación

- [x] 4.1 Revisar el registro de arranque sin errores y que el servicio corre desde `~/buscador-vacantes`
- [x] 4.2 Comprobar que el servicio descifra un dato existente de un usuario (sin imprimirlo)
- [x] 4.3 Comprobar que el bot responde a un comando del dueño y que la URL pública de Tailscale responde (URL pública `/api/v1/ping` ok; el dueño confirmó que el bot responde)
- [x] 4.4 Comprobar que el enlace ⚡ de una vacante funciona sin tocar el canal (`asistente enlace`)

## 5. Vuelta atrás (solo si falla algo)

- [x] 5.1 Parar el servicio, restaurar `prueba.conf` desde `deploy/prueba/buscador-asistente.service.d.conf`, `daemon-reload` y arrancar (no necesaria: el traspaso salió bien)
- [x] 5.2 Confirmar que el piloto vuelve a responder con sus datos originales (no necesaria: el traspaso salió bien)

## 6. Cierre

- [x] 6.1 Dejar `~/buscador-asistente` intacta unos días como respaldo y anotar la fecha de revisión (revisar el 2026-10-21)
- [x] 6.2 Actualizar `deploy/INSTALAR.md` (asistente ya corre desde producción) y la memoria del servidor del piloto (commit b6d8a56)
- [x] 6.3 Con confirmación aparte, retirar la copia de desarrollo (borrada por el dueño; respaldo comprimido y parche del stash en `~/respaldos/2026-10-14-traspaso-piloto/`)
