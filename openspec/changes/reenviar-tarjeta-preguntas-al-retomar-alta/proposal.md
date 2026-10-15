## Why

Un usuario con el alta a medias (paso `faltantes:N` o `cuestionario:N`) que toca el botón de una oferta del grupo llega al bot con `/start v_<id>` y **no ve ninguna respuesta**: `_reanudar_preguntas` repinta la tarjeta de preguntas editando el mensaje antiguo, que queda arriba en el chat. Parece que el bot no responde, y el usuario no sabe que debe terminar el registro ni que la vacante quedó guardada.

## What Changes

- Al retomar el alta por `/start`, la tarjeta de preguntas se envía como **mensaje nuevo al final del chat**, y la tarjeta antigua se borra (si no se puede borrar, se deja).
- Antes de la tarjeta, un aviso corto: tiene el registro a medias y, si el enlace traía una vacante, quedó guardada para cuando termine.
- El resto de los caminos del cuestionario (responder, editar, navegar dentro de la tarjeta) sigue editando la tarjeta en su sitio.

## Capabilities

### New Capabilities
- `retomar-alta-asistente`: qué ve el usuario con el alta a medias cuando vuelve al bot por `/start` (con o sin vacante pendiente).

### Modified Capabilities

(ninguna: `preguntas-rapidas-asistente` aún vive en el change `tarjeta-unica-preguntas-rapidas`, sin archivar)

## Impact

- Código: `buscador_vacantes/asistente/conversacion.py` (`al_iniciar`, `_continuar_alta`, `_reanudar_preguntas`, `_pintar_preguntas`) y textos en `buscador_vacantes/asistente/textos.py`.
- Pruebas: `tests/` del asistente (flujo de alta por `/start`).
- Despliegue: reiniciar `buscador-asistente` en el servidor Fedora.
