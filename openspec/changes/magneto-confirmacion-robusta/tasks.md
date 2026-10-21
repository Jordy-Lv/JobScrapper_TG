## 1. Pruebas que fallan primero

- [x] 1.1 🟡 `tests/asistente/test_api.py`: una llamada a `/postulaciones/{id}/formulario` cuya resolución tarda más que `navegador_caido_min` (resolver simulado con espera) no deja pasar a `navegador_cerrado` cuando `cola.vigilar` corre a mitad; al terminar queda el paso `formulario_resuelto` con los segundos. Verificar que falla con el código actual.
- [x] 1.2 🟡 `tests/asistente/test_extension.py` (fixture de Magneto): (a) «Aplicar» que no hace nada (sin encuesta ni modal, botón presente) → resultado `formulario_desconocido` con motivo `aplicar_sin_efecto`, no `incierta`; (b) «Aplicar» que sí envía y no muestra el modal, sin botón → sigue `incierta`; (c) una encuesta de varias preguntas deja un paso `llenado_N` por cada una, sin el texto, y uno que se corta deja el último N. Verificar que fallan.
- [x] 1.2b 🟡 `tests/asistente/test_extension.py`: un `llenar` que no termina (fixture con un campo que nunca acepta el valor y bloquea) → a los 30 s (plazo reducido en la prueba) la postulación termina `formulario_desconocido` con motivo `llenado_sin_respuesta` y sin pulsar «Enviar respuestas». Verificar que falla.
- [x] 1.3 🟢 `tests/asistente/test_tarjeta_postulacion.py`: motivo `aplicar_sin_efecto` → la card dice que el portal no cargó la postulación, que no se envió nada y trae «Reintentar»; no contiene «no mostró la confirmación».

## 2. Servidor

- [x] 2.1 🟡 `buscador_vacantes/asistente/api.py`: en `formulario`, correr `resolver_formulario` como tarea y refrescar `navegadores.ultimo_latido` cada 30 s mientras dure; registrar el paso `formulario_resuelto` con los segundos. Verificar con 1.1 en verde y `test_cola.py` intacto.
- [x] 2.2 🟢 `buscador_vacantes/asistente/textos.py` y `tarjeta_postulacion.py`: texto del motivo `aplicar_sin_efecto` y su card con «Reintentar». Verificar con 1.3. Además `conversacion.py` enruta `formulario_desconocido` con estos motivos a la card de bloqueo (prueba en `test_bot.py`), sin avisar al dueño.

## 3. Extensión y selectores

- [x] 3.1 🟡 `extension/motor.js` y `extension/servicio.js`: `confirmar` usa `sin_efecto` y devuelve el error con el motivo `aplicar_sin_efecto`; `llenar` devuelve cada respuesta escrita y `servicio.js` reporta `llenado_N`; en `formulario()` el `llenar` corre con un tope de 30 s (opción de prueba para acortarlo) y, al vencer, termina con el motivo `llenado_sin_respuesta` (tratado como `aplicar_sin_efecto` en `textos.py` y la card). Verificar con 1.2 y 1.2b en verde y las pruebas de Computrabajo y elempleo de `test_extension.py`.
- [x] 3.2 🟢 `assets/asistente/selectores/magneto.json`: `confirmar.sin_efecto`, versión `2026.10.18-2` y notas con los hallazgos de las postulaciones 54 y 55. Verificar con `test_plataformas.py`.

## 4. Verificación y despliegue

- [x] 4.1 🟡 Suite completa en segundo plano (`.venv/Scripts/python -m pytest`, ~11 min) y `.venv/Scripts/ruff check`.
- [ ] 4.2 👤 Desplegar en el Fedora (PR hacia `main`, `git pull --ff-only`, reinicio del servicio), recargar la extensión en el Chrome del dueño y repetir una postulación de Magneto con encuesta larga; leer en `postulacion_pasos` el `formulario_resuelto` y los `llenado_N`.
- [ ] 4.3 👤 Reproducir «Aplicar» sobre una vacante retirada (la CEID, con permiso del dueño) para ver el aviso de «el portal no cargó la postulación».
