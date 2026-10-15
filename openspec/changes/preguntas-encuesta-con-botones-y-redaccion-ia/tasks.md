## 1. Respuestas y redacción (respuestas.py)

- [ ] 1.1 Añadir `Sugerencias` y `sugerir(pregunta, ctx)` que devuelve 2–4 respuestas cortas, y `[]` si no hay IA o falla; verificar con pruebas en `tests/asistente/test_respuestas.py` (con IA, sin IA, error de IA, tope de 4 y longitud)
- [ ] 1.2 Hacer que `_redactar` acepte una semilla opcional con la instrucción de mantener su sentido sin inventar datos; verificar con pruebas de semilla «no»/«sí», sin semilla y con falla (devuelve la semilla)

## 2. Núcleo y estado

- [ ] 2.1 Guardar y leer las sugerencias de cada pendiente en `kv` y generarlas una sola vez; verificar con una prueba de que repintar no vuelve a llamar a la IA
- [ ] 2.2 Registrar el origen IA de la respuesta redactada en `responder_pendiente` (`nucleo.py`) y que `resumen_postulacion.py` la muestre con 🤖; verificar en `tests/asistente/test_resumen_postulacion.py`

## 3. Card y botones

- [ ] 3.1 En `tarjeta_postulacion.py` pintar para preguntas abiertas los botones de sugerencias, «✍️ Escribir yo» y «🤖 Que la IA decida» (y solo «escribe» sin IA); verificar en `tests/asistente/test_tarjeta_postulacion.py`
- [ ] 3.2 En `conversacion.py` manejar los callbacks `pend` (`sug`, `esc`, `ia`), activar la espera de texto solo tras «Escribir yo» y mostrar «Redactando…» mientras trabaja la IA; verificar en `tests/asistente/test_bot.py`
- [ ] 3.3 Redactar con la semilla (toque o texto escrito) antes de llamar a `responder_pendiente`, borrar el texto escrito del chat y usar la semilla tal cual si la IA falla; verificar con pruebas de los cuatro caminos (sugerencia, escribir, que la IA decida, falla de IA)
- [ ] 3.4 Confirmar que las preguntas con opciones siguen marcándose tal cual sin llamar a la IA; verificar con una prueba

## 4. Cierre

- [ ] 4.1 Ejecutar toda la suite de `tests/` y verificar que queda en verde
- [ ] 4.2 👤 Del dueño: reiniciar `buscador-asistente` en Fedora y probar una postulación con preguntas abiertas viendo botones, redacción y 🤖 en «Tus respuestas»
