## 1. Latido: volver a avisar al reabrir la sesión

- [x] 1.1 En `latido` (`buscador_vacantes/asistente/api.py`), emitir `cuenta_por_confirmar` / `cuenta_distinta` también cuando el estado previo del portal era `sin_sesion` y la verificación sigue siendo `por_confirmar` o `distinta`; no reavisar si la sesión no se cerró ni si la cuenta es `ok` o `sin_correo`. Verificar con pruebas nuevas en `tests/asistente/test_api.py`: reabrir con cuenta por confirmar avisa; latidos seguidos con la sesión abierta no repiten; reabrir con cuenta confirmada no avisa; reabrir con cuenta distinta avisa `cuenta_distinta`.

## 2. Conversación: pintar y retirar el mensaje

- [x] 2.1 En `conversacion.py`, al tratar `cuenta_por_confirmar` y `cuenta_distinta`, marcar `navegador=True` en la tarjeta (nueva o existente). Verificar con una prueba en `tests/asistente/test_bot.py`: sin tarjeta previa se envía un mensaje con «✓ Navegador vinculado» y los botones; con tarjeta previa se edita el mismo mensaje y no se envía otro.
- [x] 2.2 Agregar el ayudante que retira la confirmación y llamarlo tras confirmar con «Confirmar» (`case "cuenta"` / `"si"`): borra el mensaje y suelta la tarjeta si no hay postulación, paso de alta ni usuario en `ALTA` y no quedan cuentas por confirmar, distintas o revisando; borra el mensaje aparte (`tarjeta_otros`) si la confirmada no es la de la card abierta y no queda nada por resolver en él; un fallo de Telegram al borrar no interrumpe. Verificar con pruebas en `tests/asistente/test_bot.py` para cada escenario de `specs/confirmacion-cuenta-portal/spec.md` (suelto, dos pendientes, alta, bloque de la card, mensaje aparte, borrado fallido).

## 3. Cierre

- [x] 3.1 Correr `.venv/Scripts/ruff check` y `.venv/Scripts/python -m pytest tests/asistente/test_api.py tests/asistente/test_bot.py tests/asistente/test_tarjeta.py tests/asistente/test_tarjeta_postulacion.py -q` y verificar que todo pase.
- [x] 3.2 👤 Desplegar en el Fedora (`git pull --ff-only` y reinicio) y, con una cuenta por confirmar, cerrar y abrir la sesión del portal en Chrome; verificar que llega la confirmación en el mismo mensaje y que desaparece al tocar «Confirmar».

> 2026-10-28: el dueño dio por probadas las verificaciones suyas al archivar el change.
