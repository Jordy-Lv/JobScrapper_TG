## Why

El asistente solo pide confirmar la cuenta de un portal cuando esa cuenta es nueva o cambia de estado. Si el usuario deja el «¿Es tu cuenta?» sin atender (o borra el mensaje) y luego cierra y vuelve a abrir la sesión del portal en la extensión, el bot no vuelve a preguntar: la cuenta queda `pendiente` para siempre y las postulaciones a ese portal esperan sin explicación. Caso real: la cuenta de elempleo del dueño quedó por confirmar y el popup de la extensión decía «Confírmala» sin que llegara nada a Telegram.

## What Changes

- Cada vez que la sesión de un portal pasa de «sin sesión» a abierta y su cuenta sigue por confirmar (o es distinta de la registrada), el servidor vuelve a avisar al usuario con la tarjeta de conexión: se edita el mismo mensaje si existe y se envía uno nuevo si no.
- Al confirmar la cuenta, el mensaje de conexión que solo servía para confirmar se borra del chat. No se borra si es parte del alta (paso de plataformas) o el bloque «Conexión» de la card de una postulación, ni mientras quede otra cuenta por confirmar o distinta en ese mismo mensaje.
- Lo mismo para el mensaje de conexión aparte que acompaña a una card abierta: se borra al confirmar el último portal que mostraba.

## Capabilities

### New Capabilities
- `confirmacion-cuenta-portal`: cuándo el asistente pide (o vuelve a pedir) confirmar la cuenta de un portal y cuándo retira ese mensaje.

### Modified Capabilities

## Impact

- `buscador_vacantes/asistente/api.py`: el latido decide cuándo avisar de una cuenta por confirmar o distinta (hoy solo si es nueva o cambia de estado).
- `buscador_vacantes/asistente/conversacion.py`: el aviso `cuenta_por_confirmar` / `cuenta_distinta` y el botón «Confirmar» de la cuenta (borrado del mensaje).
- Pruebas en `tests/asistente/test_api.py` y `tests/asistente/test_bot.py`.
- Sin cambios de esquema, de configuración ni de la extensión.
