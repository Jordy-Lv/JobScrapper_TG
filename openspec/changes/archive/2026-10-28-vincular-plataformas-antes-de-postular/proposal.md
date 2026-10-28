## Why

Hoy, apenas el usuario vincula el navegador en el alta, el asistente da el registro por terminado y, si había una vacante pendiente, arranca su postulación de inmediato. En ese momento el usuario normalmente aún no inició sesión en Computrabajo, Magneto o elempleo, así que la postulación queda en cola esperando una sesión que nadie le pidió abrir y termina en respaldo (`sin_sesion`) si no la abre a tiempo. Conviene mandarlo a iniciar sesión y confirmar la cuenta **antes** de postular.

## What Changes

- Nuevo paso del alta, **«Paso 6 · Inicia sesión en tus portales»**, entre vincular el navegador y el cierre. La tarjeta de conexión lista las plataformas con postulación automática y su estado (pendiente, por confirmar, confirmada).
- La postulación de la vacante pendiente **no arranca** hasta que la cuenta de la plataforma de esa vacante queda confirmada. Sin vacante pendiente, el paso termina cuando cualquier plataforma queda confirmada. Las demás plataformas se muestran como opcionales.
- Botón **«Omitir por ahora»**: cierra el alta con el comportamiento de hoy (la vacante se encola y la cola espera la sesión).
- El paso se salta solo si la cuenta de la plataforma ya estaba confirmada con sesión abierta, o si la plataforma de la vacante no es automática (va a respaldo y no necesita sesión).
- Si el usuario vuelve con `/start` durante el paso, el bot reenvía la tarjeta al final del chat y recuerda que la vacante sigue guardada.
- El texto del paso 5 deja de pedir el inicio de sesión: solo vincula el navegador.
- Sin cambios en la extensión, la cola ni la API.

## Capabilities

### New Capabilities

- `vinculacion-plataformas-alta`: el paso del alta que guía el inicio de sesión en los portales, cuándo se considera cumplido, cuándo se omite y qué pasa con la vacante pendiente.

### Modified Capabilities

- `cierre-alta-asistente`: el cierre del alta y el arranque de la vacante pendiente ocurren al cumplirse (o omitirse) el paso de plataformas, no al vincular el navegador.

## Impact

- `buscador_vacantes/asistente/conversacion.py` (`_continuar_alta`, `_avisar_dict` para `navegador_vinculado`, `portal_listo` y `portal_incompleto`, botón `cuenta` y un botón nuevo para omitir, `_terminar_alta`).
- `buscador_vacantes/asistente/tarjeta.py` y `textos.py` (texto del paso 5, texto del paso 6, líneas de plataformas opcionales).
- `tests/asistente/test_bot.py`.
- Despliegue: reiniciar `buscador-asistente` en el Fedora; la prueba real con una cuenta nueva es del dueño.
