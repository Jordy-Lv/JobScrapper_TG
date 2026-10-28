## Context

`_c_ia` envía siempre un mensaje nuevo y la rama `ia` de `al_boton` la vuelve a llamar tras guardar el nivel
(`conversacion.py`), por eso aparece una card por toque. El asistente ya tiene mensajes que se borran solos
(tabla `mensajes_efimeros`, `borrar_vencidos` tras reinicios) y un botón «Cerrar» (`cb("cerrar", clave)`) que
borra todas las filas de la clave. `al_boton` no recibe el id del mensaje que se tocó.

## Goals / Non-Goals

**Goals:** una sola card, editable, con Cerrar y borrado automático, reutilizando `mensajes_efimeros`.
**Non-Goals:** cambiar la lógica del nivel, el popup de la extensión o los tiempos configurables nuevos.

## Decisions

1. **Guardar el id de la card en `kv` (`ia_msg:{usuario}`)**, igual que `prov_msg`, en vez de cambiar la
   firma de `al_boton`. Alternativa: pasar el `message_id` del callback desde `bot.py`; toca más capas y
   las pruebas, y un solo mensaje por usuario basta.
2. **La card se registra en `mensajes_efimeros` con clave `ia`** y plazo `lectura_max_s`. «Cerrar» reutiliza
   el manejador existente y el borrado tras reinicio también.
3. **Al elegir un nivel:** `editar` sobre el id guardado (si falla porque el mensaje ya no existe, se envía
   una card nueva) y se reemplaza la fila efímera por otra con plazo `lectura_min_s`. Se borra la fila vieja
   en lugar de actualizarla porque `_borrar_luego` ya programado leería la fila por id y no la encontraría.
4. **Al abrir `/ia`:** se borra la card anterior (fila efímera `ia` del usuario) antes de enviar la nueva.
5. Los botones son los tres niveles más «Cerrar» en una fila propia.

## Risks / Trade-offs

- Si el usuario borra el mensaje a mano, `editar` falla: se maneja enviando una card nueva.
- El plazo corto tras elegir puede cortar la lectura del consumo; usa `lectura_min_s` (25 s), suficiente.
