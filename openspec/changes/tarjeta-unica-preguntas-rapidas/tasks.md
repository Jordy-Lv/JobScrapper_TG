## 1. Estado y vista de la tarjeta

- [x] 1.1 Crear `preguntas_tarjeta.py` con funciones puras de texto y botones (pregunta, «Otro valor», resumen, lista de edición, línea de cierre) y pruebas unitarias del texto, el progreso («Faltan N»/«Última») y los límites de longitud
- [x] 1.2 Guardar y leer el estado de la tarjeta en `kv` (`mensaje_id`, `fase`, `indices`, `actual`, `editando`) y verificar con una prueba de ida y vuelta

## 2. Flujo en la conversación

- [x] 2.1 Reemplazar el envío por pregunta por la tarjeta única en `_preguntar_cuestionario`/`_preguntar_faltante` (editar en el lugar, reenvío si el mensaje no existe) y probar que N preguntas producen un solo mensaje enviado
- [x] 2.2 «Otro valor» dentro de la tarjeta con botón «Volver» y validación del número sin mensajes extra; probar que no se envía ningún mensaje adicional
- [x] 2.3 Borrar el texto del usuario tras guardar (mejor esfuerzo) en `al_texto` y probar el borrado, el fallo de borrado y el texto fuera de turno
- [x] 2.4 Resumen final con Confirmar/Editar y callbacks `cuest ok|editar|campo|volver`; probar el resumen, la confirmación que sigue a `navegador` y los toques viejos ignorados

## 3. Edición y reanudación

- [x] 3.1 Lista de edición, pregunta puntual y regreso al resumen (por botón y por texto); probar que el valor nuevo reemplaza al anterior
- [x] 3.2 Reanudar la tarjeta según su fase desde `_continuar_alta` y adaptar `/cuestionario` al mismo flujo; probar la reanudación tras reinicio y que `/cuestionario` usa la tarjeta

## 4. Cierre

- [x] 4.1 Ajustar las pruebas existentes del cuestionario que esperaban un mensaje por pregunta y ejecutar `uv run pytest` y `uv run ruff check` en verde
- [ ] 4.2 👤 Probar en Telegram real con el bot: flujo completo, borrado de respuestas escritas, editar una respuesta y confirmar (lo hace el dueño)
