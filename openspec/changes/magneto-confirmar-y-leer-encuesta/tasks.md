## 1. Fixtures y pruebas que fallan primero

- [x] 1.1 🟡 Crear `tests/fixtures/extension/mg_cuestionario.html` con la estructura medida en el portal (pantalla «Para continuar responde las siguientes preguntas:», dos preguntas `jobOfferQuestionnaire_job-offer-questionnaire__question` con `question-title` y botones `question-possible-answer-button` «Si»/«No» que llevan un `input.ant-radio-input` sin `name`, y «Cancelar» / «Enviar respuestas»), con un script mínimo que marca la opción al hacer clic y, al pulsar «Enviar respuestas», muestra tras ~2 s el modal `mg_application_summary_summary-modal` con «Se ha enviado tu aplicación» y su botón «Cerrar». Un segundo fixture `mg_aplicada_sin_encuesta.html` muestra el modal justo tras «Aplicar», y `mg_ya_aplicaste.html` el banner «Ya aplicaste a este empleo». Verificar abriendo cada archivo en el navegador de pruebas y leyendo sus clases y textos con una prueba corta.
- [x] 1.2 🟡 Agregar en `tests/asistente/test_extension.py` las pruebas del flujo de Magneto (siguiendo el patrón de `test_preguntas_de_seleccion_reales_se_leen_llenan_y_confirman`): (a) con encuesta, el servidor recibe 2 preguntas obligatorias con opciones «si»/«no» y el texto del título, se pulsan los botones elegidos, se pulsa «Enviar respuestas» y la postulación termina `enviada` con «Se ha enviado tu aplicación»; (b) sin encuesta, termina `enviada` sin llamar a `/formulario`; (c) «Ya aplicaste» termina `ya_postulada` sin ningún paso de envío; (d) pregunta sin respuesta del servidor → `esperar_usuario` y nada enviado; (e) si el modal no aparece y las preguntas siguen, `formulario_desconocido` con «no aceptó el envío». Verificar que fallan con el `magneto.json` actual (rojo) antes de arreglar.

## 2. Motor de la extensión (`extension/motor.js`)

- [x] 2.1 🟡 Agregar al paso `formulario` el modo `preguntas` (pregunta / título / respuesta como selectores): una función que arma los campos `{texto, tipo: "opciones", opciones, obligatoria: true}` y los guarda como `{tipo: "boton", elementos}`, ignorando «Cancelar» y «Enviar respuestas». Verificar con la prueba 1.2(a) en la parte de lectura de campos.
- [x] 2.2 🟡 Agregar a `llenar` la rama `boton`: clic en el botón elegido, comprobar que su `input` quedó `checked` y, si no, intentar también el clic en el `input`; si sigue sin marcar, devolver el error de formulario desconocido con la evidencia. Verificar con 1.2(a) y con una prueba donde el fixture no marca la opción.
- [x] 2.3 🟢 Confirmar que `motor.js` sin la clave `preguntas` se comporta igual que antes: correr las pruebas de Computrabajo y elempleo de `test_extension.py` y verificar que siguen verdes.

## 3. Selectores de Magneto (`assets/asistente/selectores/magneto.json`)

- [x] 3.1 🟢 Agregar «se ha enviado tu aplicacion» a `textos.confirmacion` y mover la detección de `ya_postulado` a `revisar_vacante`. Verificar con 1.2(c).
- [x] 3.2 🟡 Reescribir el paso `preguntas` (contenedor de la pantalla de preguntas, bloque `preguntas`, espera ~8 s, opcional), el paso `enviar` (solo «Enviar respuestas» dentro del contenedor, opcional, sin los textos «enviar» / «postularme» / «aplicar»), quitar `revisar_postulacion` y dar a `confirmar` el selector del modal y `no_enviado` apuntando a la pantalla de preguntas. Verificar con 1.2(a)–(e) en verde.
- [x] 3.3 🟢 Subir `version` a `2026.10.17-1` y actualizar `notas` con lo verificado el 2026-10-17 (flujo en página, modal con retraso de ~5 s, `/profile/processes`); dejar `verificado.postulacion` en `false` hasta la tarea 6.3. Verificar con la prueba que compara la versión de los selectores y con `python -c "import json; json.load(open(...))"`.

## 4. Servidor y tarjeta de Telegram

- [x] 4.1 🟡 Escribir una prueba (sin navegador) de que las preguntas de Magneto (`tipo: opciones`, `nombre: null`, opciones «Si»/«No») pasan por `resolver_formulario`, quedan en la tabla `respuestas` y producen «Encuesta de 2» y el botón «Respuestas» en `resumen_postulacion` / `tarjeta_postulacion`; sin encuesta, «Sin encuesta». Verificar con `pytest tests/asistente/test_resumen_postulacion.py tests/asistente/test_tarjeta_postulacion.py` y la prueba nueva.
- [x] 4.2 🟡 Verificar con una prueba que una pregunta de tratamiento de datos / consentimiento sin respuesta guardada del usuario no recibe un «Si» inventado y pasa a `esperar_usuario` (decisión 4 del diseño). Si el banco o la IA la contestan solos, ajustarlo en `respuestas.py` y cubrirlo con la prueba. Verificar con la prueba en verde.

## 5. Documentación y cierre local

- [x] 5.1 🟢 Actualizar la sección de Magneto de `docs/asistente/portales.md` (flujo con encuesta en página, modal con retraso, indicador `/profile/processes`, qué no se hace) y la memoria `reconocimiento-magneto` con el estado. Verificar leyendo el texto y con `grep` de «revisar_postulacion» sin resultados en la doc de Magneto.
- [x] 5.2 🔴 Correr la suite completa y `ruff check` / `ruff format --check`: en segundo plano (~11 min), sin tocar archivos mientras corre; la prueba intermitente de `test_extension.py` por tiempos es la única excepción conocida. Verificar con todo en verde. Recomendar sesión nueva antes de empezarla si el contexto ya está cargado.
- [x] 5.3 🟢 Hacer commit de lo del change (solo los archivos propios; el working tree puede traer cambios de otros changes), en español y sin atribuciones a la IA. Verificar con `git show --stat` y `git log -1 --format=%B`.

## 6. Despliegue y prueba real

- [ ] 6.1 👤 Llevar la rama al Fedora: `git push origin <rama>:main` si corresponde, `git pull --ff-only` en `~/buscador-vacantes` y reiniciar `buscador-asistente`. Verificar que el servicio arranca y que `GET /selectores/magneto` (o el latido de la extensión) reporta la versión `2026.10.17-1`.
- [ ] 6.2 👤 Recargar la extensión en Chrome (`chrome://extensions`) para que cargue el `motor.js` nuevo y, si se subió `manifest.json`, confirmar que el latido no pide actualizar.
- [ ] 6.3 👤 Prueba real en Telegram: el dueño nombra una vacante de Magneto que no haya postulado (no repetir Comfama CEID 1626548986-1, Distracom, Aprendiz de sistemas ni la 41), toca ⚡ y decide las respuestas (incluidos los consentimientos). Verificar: la postulación termina `enviada`, la tarjeta muestra «Encuesta de N» y «Respuestas» con lo enviado, y la vacante aparece en «Procesos activos» de `https://web.magneto365.com/profile/processes`.
- [ ] 6.4 🟢 Con la prueba aprobada, poner `verificado.postulacion: true` y subir la versión de `magneto.json`, anotar el resultado en `docs/asistente/portales.md` y desplegar de nuevo (6.1). Si falla, guardar la evidencia (`data/asistente/postulaciones/<id>/`) y ajustar solo con datos antes de repetir.
- [ ] 6.5 🟢 Reconciliar con `conectar-plataformas-extension` (marcar lo que este change cierre de su tarea 7.1 para Magneto) y archivar este change con `/opsx:archive` después de ese. Verificar con `openspec validate` y `openspec list`.
