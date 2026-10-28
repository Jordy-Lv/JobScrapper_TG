## Why

En Telegram, `/ia` manda una card nueva por cada toque: al elegir «Máximo» llegó una segunda card igual
debajo de la primera (2026-10-25). Quedan dos cards con botones, una desactualizada, y ninguna se borra ni
tiene «Cerrar», a diferencia de los demás mensajes de consulta del asistente.

## What Changes

- La card de `/ia` es **un solo mensaje**: al elegir un nivel se edita en su lugar (marca ✅, texto del
  consumo) en vez de enviar otra.
- Lleva un botón **Cerrar** que la borra de una vez.
- **Se borra sola**: unos segundos después de elegir un nivel, o tras un tiempo de lectura si nadie la toca.
- Un `/ia` nuevo borra la card anterior que siga en pantalla, para que nunca haya dos.

## Capabilities

### New Capabilities
- `card-nivel-ia`: comportamiento de la card de `/ia` en Telegram (mensaje único, Cerrar, borrado automático).

### Modified Capabilities

## Impact

- `buscador_vacantes/asistente/conversacion.py` (`_c_ia`, rama `ia` de `al_boton`, registro en `mensajes_efimeros`).
- Pruebas en `tests/asistente/test_bot.py` (las de `/ia` hoy esperan una card nueva por toque).
- Sin cambios de esquema, de configuración ni de la extensión. El nivel guardado y su efecto sobre las
  postulaciones no cambian.
