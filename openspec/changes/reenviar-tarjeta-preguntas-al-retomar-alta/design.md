## Context

`al_iniciar` → `_continuar_alta` → `_reanudar_preguntas` → `_pintar_preguntas`. Esta última edita `estado.mensaje_id` y solo envía uno nuevo si la edición falla. Telegram no avisa al usuario de una edición, así que un `/start` con la tarjeta ya enviada no produce nada visible. Los demás pasos del alta (`clave`, `cv`, …) envían mensajes nuevos, por eso el síntoma solo aparece en el cuestionario.

## Goals / Non-Goals

**Goals:**
- Que `/start` con el cuestionario a medias siempre deje algo visible al final del chat.
- Avisar de la vacante guardada.

**Non-Goals:**
- Cambiar el resto de pasos del alta (resumen, revisión, enfoque, navegador); si alguno repite el síntoma se trata en otro change.
- Cambiar cómo se guardan las preguntas o la vacante pendiente.

## Decisions

- **`_reanudar_preguntas` recibe `nuevo: bool = False`.** `_continuar_alta` sigue llamándolo igual desde las demás rutas (`_ir_a`, avance del alta); solo `al_iniciar` pide `nuevo=True`. Alternativa descartada: reenviar siempre, porque las transiciones normales del alta deben seguir editando.
- **Cómo llega `nuevo` desde `al_iniciar`:** `_continuar_alta(usuario, reenviar=False)`, que lo pasa a `_reanudar_preguntas`. `al_iniciar` lo activa en la rama `EstadoUsuario.ALTA`.
- **`_pintar_preguntas(..., nuevo=False)`:** con `nuevo=True` omite la edición, envía el mensaje, borra el antiguo (mejor esfuerzo, como `_borrar_texto_usuario`) y guarda el nuevo `mensaje_id`. Primero se envía y después se borra, para no dejar al usuario sin tarjeta si el envío falla.
- **Aviso:** texto nuevo en `textos.py` (una constante con y otra sin vacante), enviado antes de la tarjeta con `_enviar`. Si no hay estado de preguntas guardado, `_iniciar_preguntas` ya envía mensaje nuevo, y el aviso se manda igual.

## Risks / Trade-offs

- [Dos `/start` seguidos duplican avisos] → el límite de mensajes por minuto (`_permitir`) ya lo acota, y cada reenvío borra la tarjeta anterior.
- [Borrar un mensaje con más de 48 h falla en Telegram] → es mejor esfuerzo: se registra en log y se sigue, quedaría una tarjeta antigua inerte.
