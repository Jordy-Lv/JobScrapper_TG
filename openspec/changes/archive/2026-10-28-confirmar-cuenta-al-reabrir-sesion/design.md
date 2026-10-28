## Context

Ver `proposal.md` para el motivo. Estado actual, observado en el código:

- `latido` (`api.py`) guarda por portal el último estado reportado en `navegadores.portales_json` (`estado`, `cuenta`, `aviso`). Avisa de una cuenta por confirmar o distinta solo si `verificacion.nuevo` o si `previo["cuenta"]` difiere del estado nuevo. Cuando el portal reporta `sin_sesion`, conserva el campo `cuenta` previo; por eso al volver, la cuenta sigue «igual» y no se avisa.
- `cuentas.verificar` devuelve `por_confirmar` con `nuevo=True` solo la primera vez (o al cambiar de correo estando pendiente).
- `conversacion._avisar_dict` convierte `cuenta_por_confirmar` y `cuenta_distinta` en `_actualizar_tarjeta`, que edita la tarjeta de conexión del usuario (`tarjeta:<id>` en `kv`, con su `mensaje_id`) o la crea. Con una postulación en curso la conexión va dentro de su card; si el aviso es de otro portal, va a un mensaje aparte (`tarjeta_otros:<id>`).
- `bot.editar` ya ignora «message is not modified», así que repetir una edición idéntica no genera mensajes duplicados.
- El botón «Confirmar» (`cb("cuenta", plataforma, "si")`) hoy confirma en `cuentas_portal` y edita la tarjeta a «✓ portal · correo»; el mensaje queda en el chat. Tras un `ALTA` completa, la tarjeta se «suelta» (`tarjeta:<id>` vacío) al cerrar la card de una postulación.

## Goals / Non-Goals

**Goals:**
- Que un usuario con una cuenta por confirmar o distinta la vea de nuevo cada vez que reabre la sesión del portal.
- Que el mensaje de confirmación suelto desaparezca al confirmar.

**Non-Goals:**
- Reenviar el aviso con un temporizador o mientras la sesión siga abierta: solo al reabrir.
- Cambiar el flujo del alta, la card de la postulación, «Cancelar», «Es mi cuenta nueva» o «No es mía».
- Cambiar la extensión (ya reporta `sin_sesion` y luego `listo`) ni el esquema de la base.

## Decisions

**1. El latido detecta la reapertura con el estado previo guardado.** `previo["estado"] == "sin_sesion"` (el valor que el propio latido escribe al ver el portal sin sesión) y verificación `por_confirmar` o `distinta` → se emite el mismo evento que hoy (`cuenta_por_confirmar` / `cuenta_distinta`), además de las condiciones actuales. Alternativa descartada: reenviar cada N minutos mientras esté por confirmar; es más ruidoso y el dueño pidió explícitamente atarlo a cerrar y abrir la sesión. No se reavisa `sin_correo` (solo registra en el log).

**2. Reutilizar `_actualizar_tarjeta` para pintar.** Ya edita el mensaje existente y crea uno nuevo si no hay o no se puede editar, que es justo lo pedido. Una tarjeta nueva se marca `navegador=True` (el latido prueba que hay navegador), para que no falte «✓ Navegador vinculado».

**3. Retirar el mensaje tras confirmar, solo si es de confirmación.** Un ayudante en `conversacion.py`, llamado después de confirmar la cuenta, decide con la tarjeta ya actualizada:
- Si el usuario está en `ALTA` o la tarjeta tiene `paso`: no hace nada (la tarjeta es el alta).
- Si la tarjeta no tiene postulación (`pid` vacío): si no queda ninguna cuenta `por_confirmar`, `distinta` o `revisando`, borra `tarjeta.mensaje_id` y suelta la tarjeta (`_guardar_tarjeta(None)`).
- Si tiene postulación y el portal confirmado no es el de la card: el mensaje de conexión aparte (`tarjeta_otros:<id>`) se borra si, entre los portales que muestra (todos menos el de la card), no queda ninguno por resolver; se vacía esa clave.
- Si el portal es el de la card: nada; el bloque «Conexión» es parte de la card.
Borrar es mejor esfuerzo: un fallo de Telegram se registra y no afecta a la confirmación (mismo patrón que el borrado de la tarjeta anterior en el paso de plataformas).

**4. Sin migración ni configuración.** El estado vive en `kv` y `portales_json`, que ya existen.

## Risks / Trade-offs

- [Latidos con `sin_sesion` intermitente (portal que parpadea) repiten el aviso] → es una edición del mismo mensaje, que Telegram ignora si el texto no cambió; no se acumulan mensajes.
- [Borrar un mensaje que otro flujo siga editando] → solo se borra cuando la tarjeta no tiene postulación ni paso de alta, y se suelta del `kv` a la vez; si otro aviso llega después, `_actualizar_tarjeta` crea una nueva.
- [El usuario con el portal confirmado ya no ve rastro de la confirmación] → es lo pedido; el estado queda en `cuentas_portal` y en el popup de la extensión.
- [El caso ya atascado (elempleo del dueño) no se arregla solo al desplegar] → se resuelve la primera vez que cierre y abra esa sesión.

## Migration Plan

Despliegue normal (`git pull --ff-only` y reinicio del servicio); sin migración. Reversión: volver al commit anterior.
