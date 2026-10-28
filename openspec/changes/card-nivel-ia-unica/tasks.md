## 1. Card única, Cerrar y borrado

- [x] 1.1 🟡 `tests/asistente/test_bot.py`: reescribir las pruebas de `/ia` para exigir: elegir un nivel edita el mismo mensaje y no envía otro; la card trae «Cerrar» (`cb("cerrar", "ia")`); un segundo `/ia` borra la primera; la card queda registrada en `mensajes_efimeros`; elegir reinicia el plazo a `lectura_min_s`; «Cerrar» la borra. Verificar que fallan primero.
- [x] 1.2 🟡 `asistente/conversacion.py`: `_c_ia` borra la card anterior, envía la nueva con la fila de `mensajes_efimeros` (clave `ia`, `lectura_max_s`) y guarda el id en `kv`; la rama `ia` de `al_boton` guarda el nivel, edita la card (o envía una nueva si ya no existe) y reemplaza la fila efímera con plazo `lectura_min_s`. Verificar con 1.1 en verde y `tests/asistente/test_bot.py` completo.
- [x] 1.3 🟢 `.venv/Scripts/ruff check` y la suite `tests/asistente` (sin las de navegador) en verde. Verificar con ambas salidas.
- [ ] 1.4 👤 Probar en Telegram: `/ia`, elegir un nivel (edita y se borra), `/ia` dos veces (queda una) y «Cerrar». Verificar a ojo.
