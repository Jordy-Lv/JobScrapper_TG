## Why

La card de una postulación en curso solo muestra cuatro etapas con un indicador que gira: el usuario no ve cuánto falta ni cuándo termina, y al confirmarse el envío el momento más importante del flujo pasa casi desapercibido. Queremos una card que se sienta viva mientras trabaja y un cierre que celebre la postulación enviada.

## What Changes

- La card de progreso agrega, bajo la cabecera, una **barra suave** (bloques `█▉▊▌▍▎▏░`) con el **porcentaje** y el **tiempo restante estimado**, que avanza por etapa y por subpaso dentro de la etapa; las etapas con ✓ / indicador giratorio / atenuadas se conservan.
- El porcentaje nunca llega a 100 % mientras la postulación siga en curso; el 100 % solo se muestra en la confirmación.
- Al confirmarse la postulación, la card muestra un **mensaje de confirmación pulido**: título «Postulación enviada», barra al 100 %, portal, hora, duración del proceso, folio, si hubo encuesta y qué hoja de vida recibió el portal. Las vistas «Respuestas» / «De qué trata», «Ver vacante» y el seguimiento se conservan.
- La card de confirmación se entrega con **confeti** (efecto de mensaje nativo de Telegram, `message_effect_id`, solo chats privados): como los efectos solo existen al **enviar** un mensaje, la card de progreso se reemplaza por una card nueva enviada con el efecto y la anterior se borra, de modo que sigue habiendo una sola card por postulación.
- Si Telegram rechaza el efecto o el mensaje, la confirmación se envía igual sin confeti; nunca se pierde el aviso.
- Solo la confirmada (`CONFIRMADA`) lleva confeti; la incierta (`INCIERTA`) no.
- La interfaz de salida del asistente (`Salida`, `SalidaTelegram` y la `SalidaFalsa` de las pruebas) gana el parámetro opcional `efecto` en `enviar`.
- Se respeta el límite de ~1 edición por segundo por chat: se mantiene el intervalo de animación actual (2,5 s).

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `tarjeta-postulacion-asistente`: la card de progreso suma barra, porcentaje y tiempo restante; la confirmación pasa a un mensaje más completo entregado con confeti, sin dejar de ser una sola card por postulación.

## Impact

- Código: `buscador_vacantes/asistente/progreso.py`, `tarjeta_postulacion.py`, `resumen_postulacion.py`, `conversacion.py` (`Salida`, `_pintar_card`, `_enviar_resumen`, `_datos_resumen`), `bot.py` (`SalidaTelegram.enviar`).
- Pruebas: `tests/asistente/test_progreso.py`, `test_tarjeta_postulacion.py`, `test_resumen_postulacion.py`, `test_bot.py`.
- Sin cambios de base de datos ni de la extensión. Sin dependencias nuevas (se usa `message_effect_id` de `python-telegram-bot>=21.6`, a verificar al aplicar).
- Especificación principal afectada: `openspec/specs/tarjeta-postulacion-asistente/spec.md`.
