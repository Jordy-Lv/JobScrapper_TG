## Why

El 2026-10-17 el dueño reportó que las postulaciones de Magneto terminan «incierta» (la 41 no se registró en el portal) y que Telegram no muestra las «Respuestas» de la encuesta, como sí hace Computrabajo. Un reconocimiento con el Chrome del dueño (ver la memoria `reconocimiento-magneto`) mostró la causa: los selectores de `magneto.json` se escribieron antes de ver el flujo real, y el flujo real no tiene `<form>` ni `[role=dialog]`. El asistente no encuentra las preguntas, pulsa un botón equivocado y no reconoce el aviso «Se ha enviado tu aplicación».

## What Changes

- **Confirmación**: `magneto.json` reconoce el modal `mg_application_summary_summary-modal` («Se ha enviado tu aplicación», aparece unos 5 s después de enviar) como confirmación, y el paso `confirmar` espera lo suficiente. «Ya aplicaste a este empleo» se revisa antes de pulsar «Aplicar» y no después.
- **Lectura y llenado de la encuesta**: el motor de la extensión aprende a leer una encuesta hecha de preguntas con botones de respuesta (sin `<form>`, sin `name`, con un `input.ant-radio-input` dentro de cada botón), a pasarla al servidor por `/formulario` y a responderla pulsando el botón elegido. Se declara en `magneto.json` (contenedor de la pregunta, título, botón de respuesta, botón «Enviar respuestas»), con un cambio pequeño y genérico en `motor.js`; no hace falta un adaptador nuevo.
- **Envío correcto**: el paso `enviar` pulsa «Enviar respuestas» y deja de caer en el botón «Aplicar»; si el portal no trae encuesta, el flujo sigue a `confirmar`.
- **Respuestas en Telegram**: las respuestas que el servidor ya guarda en la tabla `respuestas` al resolver el formulario llegan a la tarjeta («Respuestas» y «Encuesta de N»), igual que en Computrabajo. Se verifica con pruebas; no se espera cambio en Python.
- Se sube la versión de `magneto.json` y se marca `verificado.postulacion` cuando la prueba real lo confirme.
- Se agregan fixtures HTML del cuestionario y del modal, pruebas en `tests/asistente/test_extension.py`, el despliegue en el Fedora y una prueba real en Telegram.

No cambia: el CV de Magneto (`modo: adjunto`), la sesión, la cuenta ni el perfil.

## Capabilities

### New Capabilities
- `postulacion-magneto`: cómo el asistente postula en Magneto: detecta y responde la encuesta de botones, reconoce la confirmación por el modal de resumen y deja las respuestas disponibles para la tarjeta de Telegram.

### Modified Capabilities
<!-- Ninguna: `postulacion-automatica` y `extension-navegador` viven solo en el change `conectar-plataformas-extension` (aún sin archivar), así que no existen en `openspec/specs/` y se complementan con una capacidad nueva. -->

## Impact

- `assets/asistente/selectores/magneto.json` (pasos `revisar_vacante`, `aplicar`, `preguntas`, `enviar`, `confirmar`; `textos.confirmacion`; versión; `verificado.postulacion`).
- `extension/motor.js` (lectura y llenado de preguntas con botones; sin ejecutar código remoto, solo datos que el motor interpreta). `extension/adaptadores/magneto.js` queda igual.
- `tests/fixtures/extension/` (cuestionario y modal de Magneto) y `tests/asistente/test_extension.py`.
- `docs/asistente/portales.md` (sección de Magneto).
- Despliegue: el motor viaja en la extensión, no en el servidor. El Fedora recibe los selectores con `git pull --ff-only` y reinicio del servicio; el Chrome del dueño necesita recargar la extensión (y subir la versión de `manifest.json` si el servidor exige `version_minima`).
- Depende de `conectar-plataformas-extension` (misma rama, `motor.js` y selectores) y se archiva después de ese change.
