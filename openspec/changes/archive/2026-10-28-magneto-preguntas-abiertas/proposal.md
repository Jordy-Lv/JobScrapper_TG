## Why

El 2026-10-18 la postulación 51 de Magneto («Practicante De Ingeniería Sistemas - Mosquera») terminó `formulario_desconocido` con el motivo «la pregunta «¿Cómo se llama tu programa de formación actual?» no tiene botones de respuesta». La evidencia (`data/asistente/postulaciones/51/`) muestra que la encuesta de Magneto mezcla preguntas de botones «SI»/«NO» con **preguntas abiertas**: dentro del mismo bloque `job-offer-questionnaire__question` hay un `textarea name="text"` («Tu respuesta») con un contador «0 de 140» y sin atributo `maxlength`. El motor solo sabía leer preguntas de botones y se rendía ante la primera abierta. Además, «Enviar respuestas» queda `disabled` hasta que todas las preguntas tienen respuesta: hoy el motor lo pulsa igual y la falla se ve 25 s después como «no aceptó el envío».

## What Changes

- **Preguntas abiertas en la encuesta**: `leerPreguntas` acepta, en un bloque sin botones de respuesta, un campo abierto declarado en `magneto.json` (`preguntas.abierta`) y lo envía al servidor como pregunta `texto` obligatoria, con `maximo` tomado de `maxlength` o, si no lo hay, del contador del portal (`preguntas.limite`, «0 de 140» → 140). Un bloque sin botones ni campo abierto sigue siendo formulario desconocido.
- **Llenado comprobado**: el campo abierto se escribe con el setter nativo y los eventos `input`/`change` (Magneto es React) y se comprueba que el valor quedó; si no, no se envía.
- **Botón de envío deshabilitado**: el paso `enviar` con `esperar_habilitado` espera a que el botón se habilite y, si sigue deshabilitado, termina como formulario desconocido sin pulsarlo («el portal no dio por respondidas todas las preguntas»).
- Fixture del cuestionario con preguntas mixtas y contador, pruebas en `tests/asistente/test_extension.py`, versión `2026.10.18-1` de `magneto.json`.

No cambia: el servidor (las preguntas `texto` ya se redactan o se piden al usuario como en Computrabajo), la confirmación, la sesión ni el CV.

## Capabilities

### New Capabilities
<!-- Ninguna -->

### Modified Capabilities
- `postulacion-magneto`: la encuesta en página admite preguntas abiertas además de las de botones, y el envío espera a que el portal habilite «Enviar respuestas».

## Impact

- `extension/motor.js` (`leerPreguntas`, `llenar`, paso `enviar`).
- `assets/asistente/selectores/magneto.json` (`preguntas.abierta`, `preguntas.limite`, `enviar.esperar_habilitado`, versión, notas).
- `tests/fixtures/extension/mg_cuestionario.html` y `tests/asistente/test_extension.py`.
- Despliegue: `git pull` en el Fedora (selectores) y recargar la extensión en el Chrome del dueño (motor).
