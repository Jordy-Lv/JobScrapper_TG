## Context

El flujo de Magneto está en `assets/asistente/selectores/magneto.json` (versión `2026.10.15-2`, `verificado.postulacion: false`) y lo ejecuta `extension/motor.js` paso a paso; `servicio.js` coordina las páginas y, cuando un paso `formulario` devuelve `campos`, llama a `POST /postulaciones/{id}/formulario` y luego a `llenar`. El servidor (`api.py` → `nucleo.resolver_formulario`) responde cada pregunta y **ya guarda** las respuestas en la tabla `respuestas`; de ahí salen el botón «Respuestas» y «Encuesta de N» (`conversacion._datos_resumen`, `tarjeta_postulacion._botones_confirmacion`). Por eso la lectura de la encuesta es lo único que falta del lado del navegador.

Lo que se observó en el portal real (2026-10-17, memoria `reconocimiento-magneto`):

- Tras «Aplicar» y con la **misma URL**, aparece «Para continuar responde las siguientes preguntas:» sin `<form>` ni `[role=dialog]`.
- Cada pregunta es `div[class*='jobOfferQuestionnaire_job-offer-questionnaire__question']`, con título `[class*='question-title']` y respuestas `button[class*='question-possible-answer-button']` (un `input.ant-radio-input` dentro de cada botón, sin `name`). Al final, «Cancelar» y «Enviar respuestas».
- ~5 s después de enviar, un modal en el documento normal (`mg_application_summary_summary-modal`, botón «Cerrar» `mg_application_button_button-summary`) dice «Se ha enviado tu aplicación». Luego la vacante muestra «Ya aplicaste a este empleo».

Por qué hoy falla (leído en `motor.js` y `magneto.json`): el paso `preguntas` busca `[role='dialog'] form` / `form` y no encuentra nada (es opcional, así que sigue); `leerCampos` agruparía los radios por `name || id`, y como no tienen ninguno los juntaría todos en un solo grupo cuya etiqueta saldría de un `<p>` cualquiera; `enviar` prueba «enviar postulacion», «enviar» y por último «aplicar», y cae en un botón equivocado; `revisar_postulacion` espera 3000 ms y el modal tarda ~5 s; y `textos.confirmacion` no contiene «se ha enviado tu aplicacion» (la palabra «aplicaste» solo calza con el banner posterior).

## Goals / Non-Goals

**Goals:**
- Que una postulación de Magneto con encuesta termine `enviada` y deje las respuestas guardadas para la tarjeta.
- Que una sin encuesta termine `enviada` por el modal.
- Resolver con datos en `magneto.json` todo lo que se pueda; tocar `motor.js` solo en lo que no se expresa como datos y de forma reutilizable por otros portales.

**Non-Goals:**
- No se leen las respuestas desde Magneto después del envío: el portal no las muestra (la pestaña «Detalle» solo repite la vacante). Se guarda lo que el asistente envió, como en Computrabajo.
- No se cambia el servidor, el esquema de la base ni la tarjeta, salvo que las pruebas demuestren lo contrario.
- No se verifica el CV, el perfil ni la cuenta de Magneto (`verificado.perfil` sigue en `false`).
- No se resuelven preguntas con texto libre ni de otros tipos que aún no se hayan visto: si aparece una pregunta sin botones de respuesta, el paso falla como `formulario_desconocido` con la evidencia.

## Decisions

1. **Datos en `magneto.json` más un modo «preguntas con botones» en `motor.js`; sin adaptador nuevo.** El paso `preguntas` pasa a declarar, además del contenedor, cómo se ve una pregunta: `{"contenedor": [<la pantalla de preguntas>], "preguntas": {"pregunta": "div[class*='…__question']", "titulo": "[class*='question-title']", "respuesta": "button[class*='question-possible-answer-button']"}}`. En `motor.js`, el caso `formulario` ve esa clave y arma los campos con una función nueva (por ejemplo `leerPreguntas`) en lugar de `leerCampos`: cada pregunta es un campo `{texto: título, tipo: "opciones", opciones: textos de los botones, obligatoria: true, nombre: null}` y se guarda internamente como `{tipo: "boton", elementos: [botones]}`; `llenar` suma una rama que hace `click()` en el botón elegido y verifica que quedó marcado (el `input.ant-radio-input` de dentro, `checked`).
   - Alternativa descartada: un adaptador `magneto.js` con su propia `formulario`/`llenar`. `campos` es estado privado del motor, así que habría que exponerlo en `api` para que el adaptador lo llene; es más superficie que una rama de 20 líneas en el motor, y otros portales con botones de respuesta (elempleo tiene cuestionarios) la reutilizarían.
   - Alternativa descartada: tratar los `input.ant-radio-input` como radios normales con `leerCampos`. Sin `name` ni `id` se mezclan en un grupo; y el clic que cuenta es el del botón contenedor, no el del input oculto.

2. **Reordenar los pasos para que el modal tarde lo que tarde.** `postular` queda así: `revisar_vacante` (detecta `cerrada` y ahora también `ya_postulado`, antes de tocar nada) → `aplicar` (sin cambios) → `preguntas` (opcional, espera ~8 s a que aparezcan las preguntas) → [`formulario` lo atiende `servicio.js`: `/formulario` + `llenar`] → `enviar` (opcional; solo «Enviar respuestas», buscado dentro del contenedor de preguntas; sin la lista de textos que caía en «Aplicar») → `confirmar` (25 s).
   - Se elimina `revisar_postulacion`: su espera de 3 s no sirve para un modal de ~5 s, y con una encuesta solo retrasaba el flujo. `confirmar` ya espera 25 s y es el único que decide `enviada` o `incierta`.
   - `confirmar` declara `selector` del modal de resumen además del texto nuevo en `textos.confirmacion` («se ha enviado tu aplicacion»), y `no_enviado` apuntando a la pantalla de preguntas: si pasan 25 s con las preguntas aún visibles y sin modal, el resultado es `formulario_desconocido` («el portal no aceptó el envío») y no `incierta`.
   - Vacante sin encuesta: `preguntas` (opcional) no encuentra nada tras su espera y `enviar` (opcional) tampoco; `confirmar` ve el modal. Costo: unos segundos de espera en ese caso, aceptable.
   - Alternativa descartada: dejar `revisar_postulacion` con más milisegundos. Un `detectar` no corta la espera cuando aparece la encuesta, así que la sumaría siempre.

3. **Todas las preguntas obligatorias.** El portal no deja pulsar «Enviar respuestas» sin responderlas y no marca `required`, así que el motor reporta `obligatoria: true`. Así `api.py` pasa una pregunta sin respuesta a `esperar_usuario` en vez de enviar a ciegas.

4. **Consentimientos: los decide el usuario.** La encuesta de Comfama pide aceptar el tratamiento de datos. El banco de respuestas / la IA no deben contestarlo solos: una pregunta de consentimiento sin respuesta guardada del usuario se le pregunta por Telegram (comportamiento normal de `esperar_usuario`). Las pruebas deben cubrir que el servidor no inventa un «Si» para ese texto; si hoy lo hace, se ajusta en `respuestas.py`/el banco dentro de este change.

5. **`enviar` sigue registrando `envio_pulsado`.** `servicio.js` llama a `/envio` antes de cualquier paso `enviar` o con `envia: true` (ya ocurre en `aplicar`). Se mantiene: si el navegador se cae entre el clic y el modal, la postulación queda `incierta` y nunca se reenvía.

6. **Despliegue en dos lugares.** Los selectores se cargan al arrancar el servicio en el Fedora (`git pull --ff-only` + reinicio). `motor.js` viaja en la extensión del Chrome del dueño: hay que recargarla en `chrome://extensions`. Si el change sube `manifest.json`, la `version_minima` del servidor puede obligar a actualizarla; se decide al aplicar según cómo `config.yaml` la define.

## Risks / Trade-offs

- [El clic en el botón no marca la opción (React/ant-design escucha el input, no el botón)] → la verificación posterior al clic lo detecta y falla con evidencia; en ese caso la rama de `llenar` pulsa también el `input` o despacha los eventos nativos. Solo se cierra con la prueba real (tarea 👤).
- [Magneto cambia los sufijos de las clases CSS (módulos CSS)] → los selectores usan `[class*='…']` sin el sufijo, como el resto del archivo; si cambian, el síntoma es `formulario_desconocido` con la evidencia HTML y se corrige solo con datos.
- [Otros tipos de pregunta (texto libre, selección múltiple) no vistos] → el paso falla como `formulario_desconocido` y guarda el HTML; no se envía nada a ciegas.
- [No hay HTML real guardado del cuestionario ni del modal] → el fixture se construye con la estructura medida en el reconocimiento (clases, textos, jerarquía). Una captura real y sin datos personales, si el dueño la autoriza, lo reemplaza. Las pruebas del navegador prueban el motor, no el portal.
- [Postular de verdad para probar] → solo con una vacante que el dueño nombre en el chat, que no esté entre las ya postuladas (Comfama CEID `1626548986-1`, Distracom, Aprendiz de sistemas, y la 41 `desarrollador-junior-erp-odoo-1100511` aún no registrada).
- [Esperas más largas en vacantes sin encuesta] → unos segundos extra; se aceptan por no dar un falso «incierta».

## Migration Plan

1. Implementar y probar en local (selectores + `motor.js` + fixtures + pruebas); suite completa en verde.
2. Commit (en español, sin atribuciones) y llevar la rama al Fedora: `git pull --ff-only` en `~/buscador-vacantes` y reinicio de `buscador-asistente` (lo hace el dueño o con su permiso por ssh).
3. El dueño recarga la extensión en Chrome.
4. Prueba real en Telegram con una vacante elegida por el dueño; si pasa, `verificado.postulacion: true` y nueva versión.
5. Vuelta atrás: restaurar `magneto.json` anterior y reiniciar el servicio; el motor nuevo es compatible con selectores viejos porque la clave `preguntas` es opcional.

## Open Questions

- ¿Hay que pulsar «Cerrar» en el modal de resumen antes de cerrar la pestaña? Probablemente no (la pestaña se cierra al terminar), pero conviene confirmarlo en la prueba real porque el modal fija el estado «Ya aplicaste».
