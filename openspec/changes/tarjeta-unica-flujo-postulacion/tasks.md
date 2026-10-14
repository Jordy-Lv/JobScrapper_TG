## 1. Estado y vista de la card

- [x] 1.1 🟡 Leer `pendientes` (¿guarda `postulacion_id`?), `nucleo.tocar` y `cola.reintentar` y anotar en `design.md` cómo se liga una pendiente a su card; verificar con una consulta o prueba que el `pid` se resuelve
- [x] 1.2 🟡 Crear `tarjeta_postulacion.py` con funciones puras de texto y botones para cada fase de la tabla del diseño (incluye el bloque de conexión de `tarjeta.py`) y pruebas unitarias del texto, las filas de botones, el escape y el límite de 4096 caracteres
- [x] 1.3 🟢 Guardar y leer `card:{pid}` en `kv` (`mensaje_id`, `fase`, `vista`, `pregunta`, `motivo`) y probar la ida y vuelta

## 2. Nacimiento, progreso y conexión

- [x] 2.1 🔴 En `procesar_toque`, crear la card al tocar (también fuera del alta), reutilizar la tarjeta del alta y reusar la card en el reintento; probar que cada toque produce un solo mensaje y que el reintento no envía otro
- [x] 2.2 🟡 Llevar `_pintar_progreso`, `_iniciar_progreso`, `_animar_progreso` y `_editar_progreso` a la card y quitar el camino de mensaje propio; probar etapas y que no se envía ningún mensaje extra
- [x] 2.3 🟡 Pintar en la card las fases de conexión (por vincular, por confirmar, distinta, revisando, completando) desde `_avisar_dict` y el callback `cuenta`; probar cada estado y sus botones

## 3. Preguntas y errores dentro de la card

- [x] 3.1 🟡 Mover `_preguntar_pendiente`/`_responder_pendiente`/`pend` a la fase `pregunta` con borrado del texto del usuario y avance entre pendientes; probar opciones, texto libre, varias pendientes y texto fuera de turno
- [x] 3.2 🟡 Pintar sesión pendiente, verificación, bloqueo del portal con «Reintentar», esperando navegador y cierre en `_avisar_evento`, sin mensajes sueltos; probar cada `E.*` y el reintento
- [x] 3.3 🟡 Respaldo manual: fase `respaldo` con acciones, quitar los avisos sueltos de `procesar_toque` y `_avisar_evento` y fundir el cierre del paquete con la card; probar que el paquete sigue llegando y que no hay aviso duplicado

## 4. Confirmación, vistas y seguimiento

- [x] 4.1 🟡 Reescribir `_enviar_resumen` para editar la card en `confirmada`/`incierta` (cuerpo en `<blockquote>`, filas de botones, CV como documento aparte); probar ambos estados y los datos faltantes
- [x] 4.2 🟡 Vistas «Respuestas» y «De qué trata» con «Volver» en `_ver_resumen` y `resumen_postulacion.py`, conservando el camino efímero para tarjetas anteriores; probar vista, vuelta, recorte por longitud y tarjeta anterior
- [x] 4.3 🟢 `seg` marca ✓ la opción en la card y permite cambiarla; probar el repintado y que un toque sobre estado superado no reencola
- [x] 4.4 🟢 Mensajes efímeros de tarjetas anteriores: botón «Cerrar» que los borra de inmediato además del borrado automático; probado

## 5. Cierre

- [x] 5.1 🟡 Ajustar las pruebas existentes que esperaban varios mensajes (`tests/test_asistente_tarjeta.py`, `test_asistente_resumen_postulacion.py` y las de conversación) y ejecutar `uv run pytest` y `uv run ruff check` en verde
- [ ] 5.2 👤 Probar en Telegram real con el servidor Fedora: toque, preguntas, sesión pendiente, bloqueo, confirmada, incierta, respaldo y seguimiento (lo hace el dueño)
