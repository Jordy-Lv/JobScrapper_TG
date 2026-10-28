## 1. Fixtures y pruebas primero (TDD)

- [x] 1.1 🟡 Crear `tests/fixtures/extension/mg_chat_cuestionario.html` y `tests/fixtures/extension/mg_proceso_abandonado.html` reproduciendo fielmente el cajón conversacional de Magneto (`detailChatQuestionnaireChat_container`, `loading_dots`, `div[class*='mg_chat_questionnaire_question_question']` vs `article[role='bot']`, los 4 tipos de respuesta, el filtro de caracteres de `OpenShort` y el botón «Enviar respuestas» en `<footer>`) y la etiqueta «Proceso abandonado» (`renderApplyButton_status-label`).
- [x] 1.2 🟡 Escribir pruebas en `tests/asistente/test_respuestas.py`, `tests/asistente/test_cola.py` y `tests/asistente/test_tarjeta_postulacion.py` para selección múltiple (`multiple=True`, `opciones`), reinicio de `envio_pulsado` al abrir formulario o esperar al usuario, y tarjeta/ausencia de alerta en `proceso_abandonado` y `datos_adicionales_portal`.
- [x] 1.3 🔴 Escribir pruebas de navegador en `tests/asistente/test_extension.py`, `tests/asistente/test_motor_generico.py` y `tests/asistente/test_bucle_generico.py` para el flujo completo del chat de Magneto, espera al usuario en turno intermedio, `proceso_abandonado`, `alreadyAnsweredQuestionnaire` seguido de confirmación real vs `<magneto-spe>`/`<magneto-sign-up open="true">`/`appliedSummaryPending`, «Aplicación pendiente», preservación de `<footer>` de diálogos en `htmlSinValores`, alcance de `[aria-modal="true"]`, radios sin `name` y rescate por `respaldo_declarado` con `abre_sin_enviar`.

## 2. Servidor del asistente

- [x] 2.1 🟡 Añadir soporte de selección múltiple (`multiple: bool = False` en `Campo` y `Pregunta`, `opciones: list[int]` en `Respuesta`, `elegir_opciones`, `RespuestaRedactada`, `nucleo._redactar` / `_reutilizar` y `pantalla.respuestas_de`).
- [x] 2.2 🟢 Añadir `proceso_abandonado` y `datos_adicionales_portal` en `MOTIVOS_RESPALDO` / `MOTIVOS_SIN_ALERTA` (y `datos_adicionales_portal` en `MOTIVOS_REINTENTABLES`) en `buscador_vacantes/asistente/textos.py`, y restablecer `envio_pulsado = 0` en `cola.esperar_usuario` y al recibir campos en `POST /postulaciones/{id}/formulario` (`cola.py` y `api.py`).

## 3. Extensión y selectores de Magneto

- [x] 3.1 🔴 Implementar en `extension/motor.js` las acciones declarativas `chat_turno` y `chat_llenar` (con normalización `magneto_texto`, opción única, múltiple con «Guardar» y abierta con botón de envío), salida anticipada `cortar_si` en `esperar`/`enviar`, selectores con `ocultos: true` en `buscar` para componentes Shadow DOM (`magneto-spe`, `magneto-sign-up`), preservación de `<header>`/`<footer>` de diálogos y formularios en `htmlSinValores` y `enZonaExcluida`, alcance al modal activo (`[aria-modal="true"], dialog[open]`) y agrupación de radios sin `name`.
- [x] 3.2 🟡 Implementar en `extension/servicio.js` el bucle por turnos del cuestionario conversacional (`r.chat`), el restablecimiento de `contexto.envio = false` cuando un paso con `abre_sin_enviar` abre un contenedor sin enviar, y subir `extension/manifest.json` a `1.3.1`.
- [x] 3.3 🟡 Actualizar `assets/asistente/selectores/magneto.json` a la versión `2026.10.27-2` con `chat`, `abre_sin_enviar`, `cortar_si`, `proceso_abandonado`, `datos_adicionales_portal` (`magneto-spe`, `magneto-sign-up[open='true']`, `appliedSummaryPending_applied-modal`, «Aplicación pendiente») y exigencia estricta del modal de confirmación incluso tras `alreadyAnsweredQuestionnaire`.

## 4. Verificación y despliegue

- [x] 4.1 🟡 Ejecutar `ruff check`, `ruff format --check` y toda la suite de pruebas (`pytest` unitarias y suites Playwright secuenciales) verificando cero regresiones.
- [ ] 4.2 👤 Desplegar en Fedora (`git pull && systemctl --user restart buscador-asistente`), recargar la extensión desempaquetada (`1.3.1`) en el navegador vinculado y reintentar la vacante de Magneto para verificar el resultado real en vivo.
