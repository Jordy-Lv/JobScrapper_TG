## Context

La card de postulación (`tarjeta_postulacion.py`) es un único mensaje que `conversacion.py` edita en el lugar. En progreso, `progreso.etapas(etapa, cuadro)` pinta cuatro etapas (✓ / indicador giratorio / atenuadas) y una tarea (`_animar_progreso`) edita la card cada `intervalo_animacion` = 2,5 s con un `cuadro` creciente. Al confirmarse, `_enviar_resumen` llama a `_cerrar_card(CONFIRMADA)`, que detiene la animación y repinta la misma card con `resumen_postulacion.tarjeta`.

Telegram solo aplica `message_effect_id` al **enviar** un mensaje (`send_message`), no al editarlo, y solo en chats privados. La `Salida` del asistente (`enviar`, `editar`, `documento`, `borrar`) no tiene forma de pasar un efecto. `postulaciones` ya guarda `tomada_en` y `terminada_en`, de donde sale la duración.

## Goals / Non-Goals

**Goals:**
- Barra suave, porcentaje y tiempo restante estimado en la card de progreso, sin pasar de 99 % antes de confirmar.
- Mensaje de confirmación más completo (título, barra al 100 %, hora, duración, folio).
- Confeti nativo al confirmar, manteniendo una sola card por postulación.
- Que un efecto rechazado nunca pierda el aviso de confirmación.

**Non-Goals:**
- No hay otras animaciones (radar, afinidad, carta escribiéndose, resumen semanal): son changes aparte.
- No se cambia la extensión, la base de datos ni el intervalo de 2,5 s.
- No se mide la duración real de cada etapa ni se aprende un tiempo estimado por usuario.
- Sin confeti en la postulación incierta ni en los repintados posteriores.

## Decisions

1. **Barra con bloques de octavos.** `progreso.barra(porcentaje, ancho=14)` devuelve `█` completos, un bloque parcial `▉▊▋▌▍▎▏` y `░` de relleno. Es función pura y se prueba sin Telegram. Alternativa descartada: `▰▱` por casillas (ya usada en la cuenta regresiva), porque da saltos de 10 % y no se siente animada.

2. **Avance = etapa + fracción dentro de la etapa.** Cada etapa pesa lo mismo (25 %). Dentro de la etapa en curso se suma una fracción `min(0,9, segundos_en_etapa / DURACION_ETAPA_S)` con `segundos_en_etapa` medido con el reloj de la conversación desde que la etapa empezó (no con el contador de cuadros, que no se reinicia al cambiar de etapa). Así la barra sigue avanzando entre pasos de la extensión sin llegar a la etapa siguiente. El porcentaje se limita a 99 y nunca baja porque el tope dentro de una etapa (90 % de su tramo) queda por debajo del inicio de la siguiente.
   - `DURACION_ETAPA_S` y el tiempo restante usan una constante estimada (~10 s por etapa). Es una estimación declarada con «~», no una medición. Alternativa descartada: medir por etapa en la base; añade datos y consultas para un valor que solo es decorativo.

3. **El tiempo restante** es `max(1, round(etapas_restantes × DURACION_ETAPA_S − segundos_en_etapa))`. Los segundos de la etapa llegan como argumento (`Datos.segundos_etapa`) para mantener las funciones puras.

4. **Confeti: card nueva con efecto, no mensaje aparte.** En `_enviar_resumen`, para `CONFIRMADA`: se guarda la fase, se envía la card pintada con `efecto=CONFETI`, se actualiza `mensaje_id` / `_anclar`, y se borra el mensaje anterior (best-effort). Alternativa descartada: enviar un segundo mensaje corto «🎉» con el efecto; deja dos mensajes por postulación y rompe la spec «una sola card». Alternativa descartada: editar y no mandar efecto; no cumple lo pedido.

5. **`Salida.enviar(chat_id, texto, botones=None, efecto=None)`.** `SalidaTelegram` pasa `message_effect_id=efecto` a `send_message`; si Telegram responde `BadRequest` y había efecto, **reintenta sin efecto** dentro de la propia `SalidaTelegram`, así `conversacion.py` no se ocupa de los detalles. `SalidaFalsa` de las pruebas registra el efecto recibido. Id del confeti 🎉: `5046509860389126442` (constante `EFECTO_CONFETI` en `textos.py`, a verificar con una postulación real).

6. **Solo `CONFIRMADA`.** `_cerrar_card` sigue siendo el camino para los demás cierres; el reemplazo con efecto vive en `_enviar_resumen`. Los repintados posteriores usan `_pintar_card`, que edita y no pasa `efecto`. Si la edición falla y se reenvía una card nueva, tampoco lleva efecto.

7. **Confirmación.** `resumen_postulacion.tarjeta` suma la línea de título «✅ Postulación enviada» (confirmada) o «❔ …» (incierta, sin cambios de fondo), la barra al 100 % y, en la cita, hora · duración y folio. `DatosResumen` gana `duracion_s: int | None` y `folio: str | None`; `_datos_resumen` los calcula con `tomada_en` / `terminada_en` y el id de la postulación (`P-<id>`). Si falta un dato, la línea se omite.

## Risks / Trade-offs

- **El efecto no se aplica en el cliente del usuario** (versiones viejas de Telegram, chats con efectos desactivados) → solo se pierde el confeti; el mensaje llega igual.
- **El `message_effect_id` puede cambiar** o ser rechazado por Telegram → reintento sin efecto y constante única fácil de ajustar.
- **Reemplazar la card cambia la posición del mensaje** (queda al final del chat) → es lo esperado al celebrar; los botones de la card vieja se invalidan al borrarla y los toques sobre mensajes viejos ya se ignoran o repintan la vigente por spec.
- **Condición de carrera con la animación:** un cuadro de progreso puede editar el mensaje justo antes de borrarlo → `_detener_progreso` se espera antes de enviar la nueva card (como hoy en `_cerrar_card`); un error de edición del mensaje viejo se ignora.
- **Estimación imprecisa:** la barra puede quedarse en una etapa más de lo estimado → tope de 99 % y «~1 s» evitan prometer un fin falso.
- **Límite de ediciones:** no se acorta el intervalo de 2,5 s, lejos del tope de ~1 edición/s por chat.

## Open Questions

- Confirmar en Telegram real que el id de confeti sigue vigente (tarea del dueño, parte de las pruebas manuales).
