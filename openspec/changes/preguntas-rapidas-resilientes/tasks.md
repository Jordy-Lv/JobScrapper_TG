## 1. Aval de la institución como dato recordado

- [x] 1.1 Agregar `aval_institucion` a `CAMPOS` en `campos.py` y 6 a 8 formulaciones al banco (`assets/asistente/banco_preguntas.yaml`), incluida «¿Cuentas con el aval por parte de tu institución educativa para iniciar proceso de prácticas de inmediato?»; verificar en `test_campos.py` que el campo es válido y guardable y que `valor("aval_institucion")` devuelve lo guardado en el cuestionario y `None` si es `RESERVADO`
- [x] 1.2 Probar en `test_respuestas.py` que la pregunta del aval, con el dato guardado, se resuelve sin IA (con texto libre y con opciones «Sí»/«No» del portal) y que sin dato queda `falta=True` con `campo = "aval_institucion"`; verificar que `sembrar_banco` agrega las preguntas nuevas en una base existente

## 2. Botones Sí/No en preguntas de texto

- [x] 2.1 Agregar `es_pregunta_si_no(texto)` en `respuestas.py` (inicio de verbo de sí/no, sin interrogativos de dato abierto) y verificar con una tabla de pruebas: casos de sí/no («¿Cuentas con el aval…?», «¿Tienes moto?», «¿Puedes viajar?», «¿Aceptas trabajo híbrido?») y casos que no lo son («¿Por qué te interesa…?», «¿Cuántos años de experiencia tienes?», «¿Cuál es tu aspiración salarial?», «Describe tu experiencia»)
- [x] 2.2 En `_crear_pendientes` (`nucleo.py`) guardar `["Sí", "No"]` y tipo `si_no` para un pendiente de formulario sin opciones y de sí/no, y solo las opciones en un pendiente de `dato` sin sugerencias; verificar en `test_nucleo.py` que una pregunta con opciones del portal no cambia
- [x] 2.3 En `tarjeta_postulacion.py` tratar `si_no` como `dato` en `_pregunta` («Elige una opción o escríbela tú.») y en `_botones_pregunta` (Sí, No, «✍️ Escribir yo», sin «Prefiero no decirlo»); verificar en `test_tarjeta_postulacion.py` el texto y los botones, y que la pregunta abierta sigue mostrando «Escribe tu respuesta.» sin botones
- [x] 2.4 En `conversacion.py` aceptar el texto escrito tras «Escribir yo» en un pendiente `si_no` (`_texto_pendiente`), y usar las mismas opciones en la pregunta sin card (`_preguntar_pendiente`); verificar en `test_bot.py` los tres caminos: tocar «Sí», escribir tras «Escribir yo» (el mensaje se borra) y texto fuera de turno ignorado, y que la respuesta queda en `respuestas_aprendidas` y, con campo guardable, en el cuestionario
- [x] 2.5 Verificar en una prueba de integración que el motor genérico (`/pantalla`) y el formulario clásico (`/formulario`) devuelven `esperar_usuario` con el pendiente `si_no` para una pregunta de texto de sí/no, en dos plataformas distintas

## 3. Reintento cuando la IA falla de forma temporal

- [x] 3.1 Agregar `asistente.formulario_ia.esperas_s` (por defecto `[30, 60, 120]`, lista vacía desactiva) en `comun/config.py` y `config.yaml`; verificar en `tests/comun/test_config.py` el valor por defecto, el valor del `config.yaml` y el rechazo de valores negativos
- [x] 3.2 Agregar `ia_fallo` al `Contexto` y encenderlo en `resolver` (clasificación) y en `_redactar` solo ante `Saturado` o `ErrorIA` sin contacto, nunca ante `ClaveInvalida`, `CuotaAgotada`, `TopeAlcanzado`, `ModeloNoDisponible` ni sin clave; verificar en `test_respuestas.py` cada caso
- [x] 3.3 En `resolver_formulario` repetir solo lo que falló por la IA tras cada espera de la lista (conservando lo ya resuelto) y salir en cuanto no haya falla temporal; verificar en `test_nucleo.py` con un cliente falso: saturado y luego bien (sin pendientes, esperas usadas), saturado siempre (pendientes tras agotar las esperas), sin clave (sin esperas), cuota agotada (sin esperas)
- [x] 3.4 Verificar con `con_latido` en `test_api.py` que una espera larga del formulario no deja la postulación como navegador caído y que `/pantalla` también reintenta

## 4. Aviso de IA en la card

- [x] 4.1 Registrar el paso `ia_no_respondio` al agotar los reintentos y mostrar en la card la línea «La IA no respondió esta vez» mientras haya preguntas de ese motivo; verificar en `test_tarjeta_postulacion.py` que aparece con el paso y no aparece sin él ni sin clave de IA

## 5. Cierre

- [x] 5.1 Documentar en `docs/asistente/` el reintento de IA, los botones Sí/No y el campo del aval, y correr la suite completa en segundo plano (`.venv/Scripts/python -m pytest`) y `.venv/Scripts/ruff check` sin fallas nuevas
- [ ] 5.2 👤 Del dueño: tras el despliegue en Fedora, repetir una postulación de Computrabajo con una pregunta de sí/no y confirmar que la card muestra «Sí» y «No»; si la IA vuelve a saturarse, confirmar que el asistente espera antes de preguntar
