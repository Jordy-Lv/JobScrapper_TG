## Context

Hoy una postulación se reparte entre: la tarjeta de conexión (`tarjeta.py`, un `Tarjeta` por usuario en `kv` `tarjeta:{id}`, con `pid` solo si la vacante vino del alta), `procesar_toque` (que fuera del alta envía un «En cola» suelto y guarda su id en `postulaciones.mensaje_id`), `_iniciar_progreso`/`_pintar_progreso`/`_editar_progreso` (edita ese mensaje y lo deja como «título + estado»), `_avisar_evento` (envía mensajes nuevos para bloqueo, respaldo y resumen), `_preguntar_pendiente` (mensaje suelto), y `_enviar_resumen` + `_ver_resumen` (tarjeta nueva más mensajes efímeros). `_editar_progreso` descarta la tarjeta de conexión al terminar. El cambio previo `tarjeta-unica-preguntas-rapidas` ya resolvió el cuestionario del alta con su propia tarjeta (`preguntas_tarjeta.py`); este cambio no lo toca. Ver proposal.md para la motivación.

Decisiones tomadas con el dueño: la card nace siempre al tocar; las preguntas pendientes van dentro de la card; las vistas de respuestas y de qué trata van dentro de la card; en el respaldo manual el paquete va aparte y la card lo resume.

## Goals / Non-Goals

**Goals:**
- Un único mensaje por postulación, editado en el lugar, desde el toque hasta el seguimiento.
- Texto y botones como funciones puras en un módulo nuevo (mismo patrón que `tarjeta.py` y `preguntas_tarjeta.py`); la conversación solo guarda estado y edita.
- Todos los casos de error visibles en la misma card, con su botón.

**Non-Goals:**
- No cambia la cola, la extensión, la API ni los eventos que emite `cola.py`.
- No cambia el cuestionario del alta ni el paquete de respaldo (CV, carta, respuestas, datos), solo cómo se anuncia.
- No cambia los avisos de recordatorio (`recordatorios`) ni el aviso al dueño.

## Decisions

1. **Estado de la card por postulación en `kv` (`card:{pid}`), con `postulaciones.mensaje_id` como ancla.** Guarda `mensaje_id`, `fase`, `vista` (`principal` | `respuestas` | `de_que_trata`), `pregunta` (id pendiente y avance) y `motivo` (respaldo o bloqueo). La fuente de verdad del contenido sigue en la base (`postulaciones`, `respuestas`, `postulacion_pasos`); la card se **recalcula** al pintar, así una card borrada o un reinicio no pierden nada. *Alternativa*: guardar el texto ya armado; se descarta porque se desincroniza.

2. **La tarjeta de conexión se vuelve un bloque de la card.** `Tarjeta` se conserva (cuentas, navegador, `listo`); la card de postulación la usa para pintar su bloque «Conexión» solo mientras haya algo que decir (cuenta por confirmar, distinta, revisando, completando, sin sesión). Si todo está en orden, el bloque desaparece o queda en una línea (`Computrabajo · correo`). Al terminar el alta con vacante pendiente, `procesar_toque(en_tarjeta=True)` ya reutiliza el mensaje: se mantiene ese camino y se le agrega la fase. Fuera del alta se crea la card sin bloque de conexión.

3. **Estados de la card** (fase → texto del `<blockquote>` → botones):

   | Fase | Cuerpo | Botones |
   |---|---|---|
   | `en_cola` | «En cola. Te aviso el resultado.» | — |
   | `esperando_navegador` | «Se enviará cuando abras tu navegador.» | — |
   | `cuenta` (por confirmar / distinta / revisando / completando) | línea por portal con correo | Confirmar·Cancelar / Es mi cuenta nueva·No es mía |
   | `por_vincular` | «Falta vincular tu navegador.» | Vincular navegador |
   | `pregunta` | «Pregunta rápida (n de N)» + enunciado | opciones o «Escribe tu respuesta» + Omitir |
   | `progreso` | etapas ✓ / spinner / · | — |
   | `sesion` | «Inicia sesión en {portal} en tu navegador y sigo solo» + enlace de registro | Crear cuenta (url) |
   | `verificacion` | «El portal pide una verificación; complétala en la pestaña abierta» | — |
   | `bloqueo` | causa de `BLOQUEOS_PORTAL`; «No envié nada todavía» | Reintentar |
   | `confirmada` | «{portal} confirmó tu postulación» + fecha · encuesta · CV | Respuestas·De qué trata·Ver vacante / Entrevista·Rechazada·Oferta |
   | `incierta` | «{portal} no mostró la confirmación: revisa «Mis postulaciones»» + lo mismo que confirmada | igual que confirmada |
   | `respaldo` | motivo de `MOTIVOS_RESPALDO`; «Te envío el paquete abajo» | Ver vacante / Ya me postulé·No me interesa |
   | `cerrada` | «Vacante cerrada» / «El portal rechazó el envío» | Ver vacante (si aplica) |
   | vistas | `respuestas` o `de_que_trata` | Volver |

   Las fases se derivan del `estado` de la cola (`E.*`) y del `Evento`; la conversación las traduce en `_avisar_evento` y `procesar_toque`. «Cuenta por vincular» cubre el motivo `sin_navegador`; «sesión pendiente», `E.ESPERANDO_SESION`; «bloqueo del portal», `E.BLOQUEADA` con detalle en `BLOQUEOS_PORTAL`; «incierta», `E.INCIERTA`; «respaldo manual», `CON_RESPALDO`.

4. **Pregunta pendiente en la card.** `_preguntar_pendiente` deja de enviar mensajes: guarda la fase `pregunta` y edita la card del `pid` de la pendiente (`pendientes.postulacion_id`; si la tabla no lo tiene, se resuelve por la postulación en curso del usuario, verificado en la tarea 1.1). `_responder_pendiente` guarda, borra el texto del usuario (mejor esfuerzo, como en `_borrar_texto_usuario`), avanza a la siguiente pendiente o vuelve a `en_cola`/`progreso`, y elimina «✅ Gracias, lo recordaré».

   *Verificado (1.1)*: `pendientes_usuario.postulacion_id` existe y lo llena `nucleo._crear_pendientes`; `nucleo.pendientes(usuario_id)` devuelve cada fila con ese campo, así que la card se resuelve con `pendiente["postulacion_id"]` y no hace falta inferirla. `nucleo.tocar` reencola con `cola.reintentar` conservando el `pid` (solo desde `REINTENTABLES`); cualquier otro estado devuelve `YA_EXISTE`. `responder_pendiente` marca respondidas todas las pendientes del usuario con la misma pregunta (aunque sean de otra postulación) y reanuda la postulación cuando no le quedan.

5. **Vistas internas y compatibilidad de callbacks.** `res <pid> r|d` pasa a editar la card (`vista`), y se agrega `res <pid> v` para «Volver». Si no existe `card:{pid}` (tarjeta enviada antes del cambio), `_ver_resumen` conserva el camino efímero actual: así los botones viejos siguen funcionando sin migración. `seg <pid> <valor>` guarda el seguimiento, devuelve «Anotado» y repinta la card marcando ✓ la opción; `rei <pid>` reutiliza la card existente en vez de enviar «En cola» (el reintento ya conserva el `pid`, ver `nucleo.tocar`).

6. **Respaldo.** `_avisar_evento` pone la fase `respaldo` en la card y lanza `_enviar_paquete` como hoy; los mensajes del paquete son nuevos pero independientes, y el aviso suelto «Te preparo el paquete…» y el «No puedo postularla sola» de `procesar_toque` desaparecen (lo dice la card). El último mensaje del paquete («Cuando termines, cuéntame») se funde con los botones de la card para no repetir «Ya me postulé».

7. **Estilo.** `<blockquote>` para el cuerpo de estado (el título y la empresa quedan fuera, en negrita), `<blockquote expandable>` para descripciones largas. Botones en filas de hasta tres: acciones del estado, luego vistas, luego seguimiento. Texto de botones sin emoji; ✅/❔/🔒/⚠️ solo en el cuerpo, como estado. Sustituye los emojis de botones actuales (🗣 ❌ 🎉 📝 📋 🔗 🔁).

8. **Animación.** Se conserva el ciclo de `_animar_progreso`, que ya edita la card; deja de caer a su camino alterno de mensaje propio, porque ahora siempre hay card.

9. **Límites de Telegram.** La card se recorta a 4000 caracteres como `partir()` lo hace hoy; las vistas largas (respuestas) se acortan con «…» y ya no se parten en varios mensajes. Si una descripción excede, `descripcion_corta` sigue aplicando.

## Risks / Trade-offs

- [Card borrada o de más de 48 h] → reenvío con el estado recalculado y `mensaje_id` actualizado (patrón ya usado).
- [Edición con texto idéntico: Telegram rechaza] → se trata como éxito.
- [Varias postulaciones simultáneas] → una card por `pid`; las preguntas pendientes se atienden en orden y cada una pinta la card de su postulación.
- [El texto del usuario no se puede borrar] → mejor esfuerzo; la respuesta ya quedó guardada.
- [Toques viejos] → cada callback valida fase y `pid` contra el estado; si no corresponde, repinta la card actual y no envía mensajes.
- [Tarjetas anteriores al cambio] → siguen respondiendo por el camino heredado (decisión 5); se retira ese camino en un cambio posterior.
- [Pérdida de historial en el chat al unificar] → se asume: lo que importa queda en la card final, en `/historial` y en `/detalle`.

## Migration Plan

Sin cambios de esquema. Desplegar el servicio; las postulaciones en curso sin `card:{pid}` terminan con el flujo anterior y las nuevas usan la card. Reversión: volver al commit anterior; las claves `card:*` huérfanas son inofensivas.

## Open Questions

- ¿Se retira ya la limitación de toques por minuto de «Ver respuestas» (`_toque_resumen_permitido`) o se mantiene como protección contra ráfagas de ediciones? Se mantiene por defecto y se revisa tras probar con el servidor.
