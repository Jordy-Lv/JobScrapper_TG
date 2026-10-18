# Portales del asistente: términos, volumen y reconocimiento

Documento del change `conectar-plataformas-extension`. Registra, por portal, si conviene
conectarlo a la extensión, y más adelante el reconocimiento con sesión real (selectores,
indicadores y fixtures).

## Términos de uso (tarea 1.1, revisada el 2026-10-14)

Lectura hecha sobre las páginas públicas. **No es asesoría legal**: ninguna cláusula aparece
con el texto «postulación automatizada» y la decisión final es del dueño (tarea 1.2).

| Portal | Documento | Qué dicen sobre automatización | Conclusión |
|---|---|---|---|
| elempleo | [Términos y Condiciones](https://www.elempleo.com/co/sitio-empresarial/tcc/terminos-y-condiciones), v1.1.0 del 10-02-2026 | Sin cláusula explícita sobre robots, scrapers ni acceso automatizado. Lo más cercano: prohíbe «usar cualquier elemento, diseño, software o rutina para interferir» con el sitio, y limita el acceso a «uso personal y no comercial». | **Dudosa**: no prohíbe expresamente, pero la postulación asistida corre dentro de la sesión del propio usuario y a su ritmo (sin interferir ni uso comercial). Riesgo bajo si se respeta el ritmo y no se evaden captchas. |
| GetOnBoard | [Terms and Conditions Agreement](https://www.getonbrd.com/about/tos), v1.1 del 2026-09-17 | Es el contrato de las **empresas clientes**. Prohíbe «copying or permitting automatic downloading» de su propiedad intelectual y entrenar modelos con la plataforma; puede limitar el uso excesivo de su API. No habla de postular en nombre de alguien ni de bots de candidato. | **Dudosa, poca información**: el texto vigente para candidatos no apareció. Hay que leer las «Platform Policies» antes de cualquier piloto. |
| Servicio Público de Empleo | — | No se revisó: ver la medición de abajo. | Sin objeto por ahora. |

LinkedIn sigue fuera de alcance por sus términos.

## Volumen real de vacantes (tarea 1.3, `vacantes.db` del Fedora, 2026-10-14)

Consulta de solo lectura sobre la tabla `vistas`, agrupada por fuente y dominio del enlace.

**Últimos 30 días** (desde 2026-09-14):

| Fuente | Dominio del enlace | Vacantes | Enviadas al canal |
|---|---|---|---|
| computrabajo | co.computrabajo.com / www.computrabajo.com.co | 301 / 15 | 295 / 15 |
| **elempleo** | www.elempleo.com | **164** | 148 |
| **getonboard** | www.getonbrd.com | **1** | 1 |
| linkedin | co.linkedin.com / www.linkedin.com | 474 / 37 | 463 / 37 |
| magneto | www.magneto365.com | 92 | 86 |
| **spe** | — | **0** | 0 |

**Toda la historia** (desde 2026-07-28): computrabajo 423, linkedin 667, elempleo 181, magneto 92,
**getonboard 3**, remoteok 6 y **spe 0**. Ninguna vacante tiene enlace a `buscadordeempleo.gov.co`.

### Conclusiones

1. **elempleo vale la pena**: 164 vacantes en 30 días, comparable con Magneto y por encima de él.
2. **GetOnBoard casi no aporta**: 1 vacante en 30 días y 3 en toda la historia. El filtro del radar
   (junior y sin experiencia, remoto en español) deja pasar muy pocas.
3. **El SPE no aporta nada hoy**: no hay una sola vacante con esa fuente ni con ese dominio. Las plazas
   con enlace a elempleo o Magneto ya se atribuyen a esos portales.

Según la decisión 4 del `design.md`, el SPE queda en **respaldo** (no se hace su reconocimiento) y el
grupo 6 se omite. Para GetOnBoard se propone lo mismo, y retomarlo solo si el volumen crece.

## Decisión del dueño (tarea 1.2)

**2026-10-14: solo elempleo.** GetOnBoard y el SPE quedan en paquete de respaldo; se retoman únicamente
si su volumen de vacantes crece. Se omiten los grupos 5 y 6 del change.

## Reconocimiento con sesión

### elempleo

Reconocimiento del 2026-10-15, hecho con la sesión del dueño (Chrome) y sin guardar datos personales en el
repositorio. La primera parte (dos postulaciones reales) la hizo el dueño; la segunda leyó el marcado y el
JavaScript del portal (`JobOfferDetail.min.js`) sin pulsar ningún envío. Los fixtures recortados están en
`tests/fixtures/extension/ee_*.html` (tarea 2.4).

**Vacantes recorridas:** «Analista de soporte it - cartagena» (1886757326, con video V-Prez) y «Auxiliar de
surtido 636565» (JOBANDTALENT), postuladas por el dueño; «Auxiliar de mercadeo» (1886780205, postulación
rápida), «Mercaderista Funza» (1886780017, postulación normal) y «Analista de pruebas funcionales junior»
(1886742826, cerrada), solo leídas. Se revisó además el marcado de 20 ofertas del listado.

| Punto | Hallazgo |
|---|---|
| Sesión iniciada | Enlace `a[href*='/Account/LogOff']` («Cerrar sesión», en el menú «Cuenta»). |
| Sin sesión | Enlace `a[href='/co/iniciar-sesion']` («Iniciar sesión») y el botón de postular lleva la clase `js-login-extra-params`. Registro: `/co/registro-hoja-de-vida`. |
| Correo de la cuenta | `/co/hoja-de-vida/mi-cuenta` («Ajustes» o «Configuración»): `span.ee-account-email strong` y el campo oculto `input#EmailAddress`. El pie de todas las páginas trae un correo `@elempleo.com`, que el motor descarta por ser del portal. |
| Perfil incompleto | Banner «Hoja de vida incompleta… para postularte»; el portal responde al envío con `Response 3` y muestra `.js-alert-offer-cv-incomplete`. En el menú «Cuenta», `span.myresume-indicator.js-status-indicator` lleva la clase `full` cuando está completa. En `/co/hoja-de-vida` aparece «Completa» o «Incompleta», un porcentaje y un botón «Completar» por sección. |
| Ya postulado | Banner `div.alert.js-alert-already-applied` («Postulación realizada · Ya te postulaste a esta oferta»), visto al recargar justo después de postular; el campo `offerapplied` de `.js-hdnvars` dice lo mismo. Es fiable, pero tarda unos minutos en reflejar una postulación nueva. (El 2026-10-15 las dos vacantes postuladas dejaron de mostrarlo porque el dueño retiró esas postulaciones.) Si se repite el envío, el portal responde `Response 4` (`UserAlreadyAppliedForThisJobOffer`); la cola del servidor tampoco toma dos veces la misma vacante. |
| Vacante cerrada | Banner `div.alert.new-alert-warning` «Oferta no disponible · Esta oferta de empleo ya no está disponible» y los botones de postular ocultos. |
| Lista de postulaciones | `/co/estadisticas/mis-procesos/`. Tarda unos minutos en mostrar una postulación nueva: no sirve como confirmación inmediata. |
| Dos variantes de postulación | La oferta trae `.js-config[data-is-quick-offer-application]`. **Normal** (`False`, la mayoría: 15 de 20): `button.js-apply-offer` envía la postulación con un solo clic (POST por AJAX a `JobOfferDetail/Save`). **Rápida** (`True`): `button.js-apply-modal-quick-offer` abre el modal `#QuickApplicationApplyOffer` y su botón `button.js-apply-quick-offer` hace el envío (formulario `.js-quick-application-form`). |
| Aviso de datos | `#habeasModal`, con «Entendido» (`a.close-habeas`). Sale al pulsar postular en las dos variantes y se cierra solo a los 6 s; no bloquea el envío. |
| Confirmación | Sin recargar: `div.alert.js-alert-offer` («Postulación exitosa · Gracias por haberte postulado…») pasa a visible y aparece `.id-ShowApplied` («Postulado»). Otras respuestas del portal: `Response 1` y `5` redirigen a otra página, `2` abre un sitio externo del empleador, `3` hoja de vida incompleta y `4` ya postulado. |
| Video (V-Prez) | `#jobOfferApplicationVprez`, solo si `#vprezInputHidden[data-vprez-url]` tiene valor (6 de 20). Sale **después** de guardar la postulación: «Omitir» (`#btnSkipVprez`) o «Continuar proceso» (`#btnRedirectVprez`, cuestionario en video en v-prez.com con la imagen del candidato). Es opcional y la postulación ya quedó hecha. |
| Nota de presentación | `#ApplicationNoteLightBox` (formulario `form.js-offer-apply`, `textarea[name=ApplicationNote]`, hasta 2.000 caracteres), con «Enviar» (`button.js-apply-with-note`) y «Omitir este paso» (`a.js-apply-offer-lightbox`). Solo en ofertas VIP (`data-is-vip`, 0 de 20) y **antes** del envío: en la variante normal «Enviar» postula; en la rápida pasa al modal del CV. |
| Preguntas del empleador | No hay un cuestionario propio en el detalle de la oferta (ni una marca pública que lo anuncie): lo que el empleador pide aparte es el video de V-Prez (externo), la nota o el cuestionario adicional de la fila siguiente. |
| Cuestionario adicional | Visto en el piloto del 2026-10-17 (postulación 39, evidencia en `tests/fixtures/extension/ee_cuestionario.html`). Al guardar la postulación, el portal responde `1` o `5` y lleva a `/co/JobOffers/Questionnaires/…`, «Cuestionario adicional · Para finalizar la postulación a la oferta de empleo es obligatorio completar el cuestionario»: preguntas numeradas (`textarea[name='[n].OpenAnswer']`, obligatorias, hasta 2.000 caracteres; `[n].IsCloseAnswer` hace pensar que también hay preguntas cerradas) y «Postularme a oferta» (`form.js-questionnaire-form`). `Questionnaires.js` (público) valida con jQuery Validate y envía por AJAX a `EndQuestionnaire`: `2` muestra `#confirmationSuccessModal` («¡Postulación exitosa!»), `1` lleva a otro cuestionario y `4` muestra `#confirmationSuccessModalAts` («Cuestionario guardado», el empleador sigue en su propio sistema). Los dos modales vienen ocultos en el HTML desde que carga la página. Si `.js-timer-elapsed` trae un número, el cuestionario tiene tiempo límite y al vencer redirige a `DoRedirect`. |
| Modo del CV | **`perfil_multiple`** (corrige la nota anterior que decía `perfil_unico`): el modal rápido muestra «La hoja de vida que recibirá la empresa es:» con una lista (`select.js-select-file`, `Attachments.SelectedIds`) de los documentos guardados en la hoja de vida, uno ya elegido. Un archivo nuevo (`input#attachment-input[name=File]`, PDF/DOC, máx. 3 MB) se envía con la postulación **y queda guardado en la hoja de vida**; con el máximo de documentos (`data-max-files-allowed`, 5) el campo se desactiva. La variante normal no deja elegir: el empleador recibe la hoja de vida del perfil. |
| Captcha | Ninguno al postular (la página carga reCAPTCHA solo para «Compartir oferta»). |
| Páginas que no se tocan | `/co/Account/LogOff`, el cambio de contraseña y de correo de «Mi cuenta», «Compartir oferta» y las alertas de empleo. |

**Regla para los pasos extra (decisión del dueño, 2026-10-15):** el bot debe poder leer todo lo que le salga
y lograr una postulación exitosa.
- Paso opcional que no exige contenido del candidato (por ejemplo el video) → se omite.
- Paso que pide contenido (nota de presentación, preguntas del empleador, encuesta) → el motor lee el texto,
  la IA redacta con los datos reales del perfil y, si hay duda o el paso es obligatorio, se le pregunta al
  usuario por Telegram con botones antes de enviar.
- Lo que implica la imagen o la voz del usuario (video) nunca se hace sin su respuesta expresa.
- Paso desconocido → `formulario_desconocido` y paquete de respaldo, sin enviar.

#### Piloto de elempleo (tareas 4.5 y 7.1)

Listo para el dueño desde el 2026-10-15. Los selectores (`assets/asistente/selectores/elempleo.json`) no
exigen una versión nueva de la extensión: `motor.js` y los adaptadores no cambiaron.

1. **Desplegar con `automatica: false`.** Unir la rama `conectar-plataformas-extension` a `main` y, en el
   Fedora, `git pull --ff-only` en `~/buscador-vacantes` y `systemctl --user restart buscador-asistente`
   (los selectores se cargan al arrancar). Desde ese momento el popup ofrece elempleo, pero un ⚡ sigue
   yendo al paquete de respaldo.
2. **Permiso y cuenta.** En el popup, activar elempleo (permiso de `elempleo.com`), iniciar sesión en el
   portal y confirmar en Telegram el correo que lee la extensión (`/co/hoja-de-vida/mi-cuenta`).
3. **Activar solo para el piloto.** Por Telegram, `/plataformas elempleo on` (comando del dueño; vale
   hasta el próximo reinicio y para todos los usuarios, así que mejor hacerlo sin invitados activos).
4. **Tres vacantes nuevas**, ninguna de las ya postuladas (1886757326 y «Auxiliar de surtido 636565»):
   - una **normal** (`button.js-apply-offer`, la mayoría);
   - una **rápida** (`data-is-quick-offer-application="True"`, con el modal del CV), por ejemplo una de
     las que muestran «Si deseas, a continuación puedes adjuntar nuevos documentos»;
   - una **con video V-Prez**, para comprobar que se omite.
   Si aparece una oferta VIP (nota de presentación), sirve para probar la pregunta por la card. Ninguna
   marca pública avisa del cuestionario adicional: se ve solo al postular.
5. **Revisar cada una:** estado `enviada` en Telegram, el banner «Postulación exitosa» en la pestaña (o la
   evidencia en `data/asistente/postulaciones/<id>/`), y en el portal la postulación y el documento
   enviado. «Mis procesos» y el banner «ya postulado» tardan unos minutos en reflejarla.
6. **Al terminar**, `/plataformas elempleo off` si algo falló, y anotar aquí el resultado.

**Primer intento (2026-10-17): falló en el cuestionario adicional.** La postulación 39 («Consultor ti
sector corporativo - bogotá», variante normal, sin nota) pasó `aplicar`, `omitir_video`,
`revisar_postulacion` y `aviso_datos`. El portal respondió al envío con la página «Cuestionario adicional»
(tres preguntas abiertas obligatorias) y el flujo terminó en `formulario_desconocido` en `cv_subir` («no
apareció el campo del archivo»), sin responder ni enviar el cuestionario. La postulación no quedó
finalizada en el portal.

Arreglo (tarea 4.4c, `elempleo.json` versión `2026.10.17-1`, sin versión nueva de la extensión). En la
variante normal, el cuestionario se lee después de `aviso_datos` (pasos `cuestionario`,
`cuestionario_enviar` y `revisar_cuestionario`, antes de `cv_subir`). En la rápida se lee después de
`enviar` (`cuestionario_tras_enviar` y `cuestionario_enviar_tras_enviar`, antes de `confirmar`). Sus
preguntas pasan por el banco de respuestas como cualquier formulario. Si falta una obligatoria, el bot la
pregunta por la card y la pestaña se cierra sin pulsar «Postularme a oferta». `#confirmationSuccessModal`
da `enviada`, y el modal del ATS da `incierta`.

**Qué comprobar al repetir el piloto** (con los selectores nuevos desplegados):
- Si sale el cuestionario: las respuestas enviadas (pasos `llenado` y la evidencia) y el modal «¡Postulación
  exitosa!».
- Si el bot pregunta por la card: al responder, la postulación vuelve a la cola y empieza otra vez desde
  la oferta. **No se ha visto** qué muestra entonces el portal para una postulación con el cuestionario a
  medias: puede volver a llevar al cuestionario (lo esperado), responder `4` o mostrar el banner «ya
  postulado». En ese caso terminaría como `ya_postulada` sin haber completado el cuestionario. Anotar aquí
  lo que pase y revisar «Mis procesos».
- Un segundo cuestionario encadenado (respuesta `1` de `EndQuestionnaire`) no está soportado: en la
  variante normal termina en `formulario_desconocido` en `cv_subir` y en la rápida en `incierta`, los dos
  con el HTML de la evidencia.

**7.1, si las tres salen bien:** poner `elempleo: {automatica: true}` en `config.yaml`, cambiar
`verificado.postulacion` a `true` en `elempleo.json` (subir `version`) y actualizar la autorización de datos
(ver abajo), commit, `git pull --ff-only` en el Fedora, reinicio del servicio y un ⚡ de prueba que termine
en `enviada`. Si alguna falla, se deja en `false` y se anota el motivo aquí con el HTML de la evidencia,
y la autorización no se toca.

**Autorización de datos (cierra la tarea 7.3).** En el mismo commit de la 7.1, en `config.yaml` →
`asistente.politica.texto`, punto 1, cambiar «el correo de tus cuentas de Computrabajo y Magneto» por
«el correo de tus cuentas de Computrabajo, Magneto y elempleo», y subir `asistente.politica.version`
de `1` a `2`. Al reiniciar, cada usuario debe aceptar la autorización de nuevo antes de seguir usando
el bot; conviene avisar a los invitados. Se hace solo cuando elempleo queda activa, para pedir esa
aceptación nueva una sola vez.

**Qué mirar si algo falla:**
- `incierta` con «no apareció la confirmación»: el portal respondió con una redirección (respuestas 1 o 5)
  a una página que no se vio; el HTML de la evidencia dice cuál es.
- `formulario_desconocido` en `aplicar`: cambió la clase del botón de postular.
- `formulario_desconocido` en `cuestionario_enviar` («el portal marcó campos sin responder»): una
  pregunta del cuestionario quedó vacía (por ejemplo, una cerrada que el motor no supo marcar); no se envió.
- `bloqueada` con `portal_perfil_incompleto`: la hoja de vida del portal está incompleta.
- Con autorización para actualizar el CV y 5 documentos ya guardados, el portal desactiva el campo del
  archivo: la postulación sale con el documento elegido aunque el resumen diga que se subió el nuevo.

### Magneto

Reconocimiento con la sesión del dueño (2026-10-17). La postulación 41 había terminado «incierta» y no
quedó registrada en el portal: los selectores se habían escrito antes de ver el flujo real.

**Flujo real** (change `magneto-confirmar-y-leer-encuesta`, `magneto.json` versión `2026.10.17-1`):

- Todo ocurre en la misma página, con la misma URL, y sin `<form>` ni `[role=dialog]`.
- Si la vacante muestra «Ya aplicaste a este empleo», la postulación termina `ya_postulada` antes de
  pulsar nada (paso `revisar_vacante`).
- «Aplicar» (`button[class*='applyButton_apply-btn']`) puede mostrar «Para continuar responde las
  siguientes preguntas:». Cada pregunta es un bloque `[class*='job-offer-questionnaire__question']` con
  título `[class*='question-title']` y botones `button[class*='question-possible-answer-button']`
  («Si» / «No»), cada uno con un `input.ant-radio-input` sin `name`. Al final van «Cancelar» y
  «Enviar respuestas». El portal no deja enviar con preguntas sin responder.
- El motor lee esas preguntas con la clave `preguntas` del paso `formulario` (todas obligatorias), las
  manda al servidor por `/formulario` y responde pulsando el botón elegido; si su `input` no queda marcado
  no envía nada y termina `formulario_desconocido`. El paso `enviar` pulsa solo «Enviar respuestas».
- Unos 5 s después de enviar aparece el modal `mg_application_summary_summary-modal` con «Se ha enviado tu
  aplicación» (botón «Cerrar»). Ese modal confirma la postulación. Si pasan 25 s con las preguntas aún en
  pantalla y sin modal, el resultado es `formulario_desconocido` («el portal no aceptó el envío»).
- Una vacante sin encuesta se envía al pulsar «Aplicar» y solo muestra el modal; `preguntas` y `enviar`
  son opcionales y se omiten tras unos segundos de espera.
- El indicador fiable es `https://web.magneto365.com/profile/processes` («Procesos activos», cada uno
  «Aplicación enviada» con fecha).

**Respuestas en Telegram.** Las respuestas que el asistente envía se guardan en la tabla `respuestas` y la
card muestra «Encuesta de N» y el botón «Respuestas», como en Computrabajo. Magneto no las vuelve a
mostrar después (la pestaña «Detalle» solo repite la vacante).

**Lo que no se hace.** Las autorizaciones y aceptaciones (tratamiento de datos, términos) no las contesta
el banco ni la IA: se le preguntan al usuario por la card y se recuerda su respuesta. No se resuelven
preguntas sin botones de respuesta (texto libre): terminan `formulario_desconocido` con la evidencia.

**Estado.** Verificada con una postulación real (2026-10-17, postulación 43, «Auxiliar de Infraestructura TIC para Apartadó», Servicio de Empleo Comfama): terminó `enviada` por el modal «Se ha enviado tu aplicación», con 2 preguntas respondidas y guardadas (el tratamiento de datos lo había decidido el usuario; la otra, de confirmar la participación, la redactó la IA). `verificado.postulacion` pasó a `true` en la versión `2026.10.17-2`. El perfil (`verificado.perfil`) sigue sin verificar.
