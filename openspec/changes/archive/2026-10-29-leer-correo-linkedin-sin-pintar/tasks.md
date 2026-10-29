## 1. Lectura del correo por HTML

- [x] 1.1 🟡 `motor.js`: función `correoPorHtml(sel)` que, con `cuenta.html`, toma el usuario de la ruta o del HTML de `inicio`, pide `url` con `fetch` (GET, mismo origen) y devuelve `{correo}` o `{motivo}` (`sin_perfil`, `sin_correo`, `varios_correos`, `sin_sesion`); se verifica con la prueba 2.1
- [x] 1.2 🟢 `linkedin.json`: bloque `cuenta.html` con los datos medidos en vivo y versión nueva; se verifica con la prueba 2.1 y con `python -m json.tool`
- [x] 1.3 🟡 `servicio.js`: llamar a `correoPorHtml` tras confirmar la sesión, usar el recorrido pintado como respaldo, informar `motivo` sin correo y reintentar a los 10 min un portal listo sin correo; se verifica con las pruebas 2.1–2.3. El servidor (`api.py`) guarda ese `motivo` en `portales_json` cuando hay sesión y no hay correo; prueba en `test_api.py`
- [x] 1.4 🟢 `manifest.json` a 1.3.3 y nota de la cuenta de LinkedIn corregida en `docs/asistente/portales.md`

## 2. Pruebas

- [x] 2.1 🟡 Prueba de la extensión: `/in/me/` se queda sin saltar y la página de contacto trae el correo solo en un `<script>` (sin pintar) → el latido trae el correo y `pagina_correo`
- [x] 2.2 🟢 Prueba: página de contacto sin `mailto:` → `listo`, sin correo y `motivo: sin_correo`
- [x] 2.3 🟢 Prueba: portal listo sin correo revisado hace más de 10 min se vuelve a revisar en el siguiente latido
- [x] 2.4 🟡 Correr `tests/asistente/test_extension.py` completo y `ruff` en verde (la prueba antigua de la 1.3.2 debe seguir pasando)

## 3. Despliegue y verificación en vivo

- [x] 3.1 👤 Unir el PR y desplegar en el Fedora (`git pull` y reiniciar el servicio) — Hecho el 2026-10-28: PR #24 unido (8da0e8e) y desplegado
- [x] 3.2 👤 Recargar la extensión sin empaquetar en el Chrome del dueño y comprobar que la tarjeta de LinkedIn pasa a «Confírmala» (o leer el motivo en `navegadores.portales_json`) — Verificado el 2026-10-28 a las 23:22: el servidor registró "Correo de linkedin leído en /in/carlosbechara/overlay/contact-info/" y la cuenta quedó por confirmar
