## 1. Pruebas que fallan primero

- [x] 1.1 🟡 Ampliar `tests/fixtures/extension/mg_cuestionario.html` con preguntas abiertas como las de la postulación 51 (`textarea name="text"` con contador «0 de 140», sin `maxlength`) y con «Enviar respuestas» `disabled` hasta que todas las preguntas tengan respuesta. Agregar en `tests/asistente/test_extension.py`: (a) encuesta mixta → el servidor recibe opciones y textos con `maximo` 140, se escriben los textos y termina `enviada`; (b) un bloque sin botones ni campo → `formulario_desconocido`; (c) «Enviar respuestas» que no se habilita → `formulario_desconocido` sin pulsarlo. Verificar que fallan con el motor actual.

## 2. Motor y selectores

- [x] 2.1 🟡 `extension/motor.js`: `leerPreguntas` lee el campo abierto (`def.abierta`) y su límite (`maxlength` o `def.limite`); `llenar` escribe y comprueba la rama `abierta`; el paso `enviar` con `esperar_habilitado` espera el botón habilitado. Verificar con 1.1 en verde y las pruebas de Magneto, Computrabajo y elempleo de `test_extension.py`.
- [x] 2.2 🟢 `assets/asistente/selectores/magneto.json`: `preguntas.abierta`, `preguntas.limite`, `enviar.esperar_habilitado`, versión `2026.10.18-1` y notas. Verificar con `test_plataformas.py`.

## 3. Despliegue y prueba real

- [x] 3.1 👤 Desplegar los selectores en el Fedora, recargar la extensión en el Chrome del dueño y repetir una postulación de Magneto con preguntas abiertas (la 51 u otra que nombre el dueño).

> 2026-10-28: el dueño dio por probadas las verificaciones suyas al archivar el change.
