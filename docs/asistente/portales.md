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

LinkedIn quedó fuera de alcance por sus términos hasta el 2026-10-21, cuando el dueño revirtió esa
decisión: ver la sección «LinkedIn» al final.

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

**Activación (2026-10-18).** El dueño decidió activar elempleo con el piloto en 1 de 3 (postulación 44,
variante normal, `enviada` y visible en «Mis procesos»), para que quede encendida como Computrabajo y
Magneto y no dependa de `/plataformas elempleo on`, que se pierde en cada reinicio del servicio. Se hizo la
7.1 completa: `automatica: true`, `elempleo.json` `2026.10.18-1` con `verificado.postulacion: true` y la
autorización de datos en la versión 2. La variante rápida y el cuestionario adicional siguen sin verse en
una postulación real: revisar las primeras de cada tipo con los puntos de «Qué comprobar al repetir el
piloto».

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
el banco ni la IA: se le preguntan al usuario por la card y se recuerda su respuesta.

**Preguntas abiertas (2026-10-18, postulación 51).** La encuesta puede mezclar botones con preguntas de
texto libre: un `textarea name="text"` («Tu respuesta») sin `maxlength`, con el contador «0 de 140». Se
leen como preguntas `texto` obligatorias con `maximo` tomado del contador (`preguntas.abierta` y
`preguntas.limite`), se redactan o se piden al usuario como en Computrabajo, y el motor comprueba que el
texto quedó escrito. «Enviar respuestas» está `disabled` hasta que todo tiene respuesta: el paso `enviar`
(`esperar_habilitado`) lo espera y, si no se habilita, termina `formulario_desconocido` sin pulsarlo. Una
pregunta sin botones ni campo abierto también termina `formulario_desconocido` con la evidencia.

**Estado.** Verificada con una postulación real (2026-10-17, postulación 43, «Auxiliar de Infraestructura TIC para Apartadó», Servicio de Empleo Comfama): terminó `enviada` por el modal «Se ha enviado tu aplicación», con 2 preguntas respondidas y guardadas (el tratamiento de datos lo había decidido el usuario; la otra, de confirmar la participación, la redactó la IA). `verificado.postulacion` pasó a `true` en la versión `2026.10.17-2`. El perfil (`verificado.perfil`) sigue sin verificar.

## LinkedIn

Sección del change `medir-destinos-linkedin` (tareas 6.1 y 6.2, e insumo de la 6.3).

### Decisión del dueño y riesgo (2026-10-21)

- El dueño revirtió el *non-goal* de LinkedIn. Se automatizan la **Solicitud sencilla** y las
  **solicitudes externas** (página de la empresa o ATS), para el dueño y para los invitados, con
  **envío final automático también en páginas que el bot no conoce**.
- **Riesgo aceptado:** la sección 8.2 de las condiciones de uso de LinkedIn prohíbe bots y extensiones
  que automaticen acciones. LinkedIn puede restringir la cuenta del dueño y la de los invitados. Por eso
  cada invitado debe aceptar ese riesgo de forma expresa (nueva versión de la autorización) y poder
  apagar LinkedIn para sí mismo.
- **Reglas que no cambian:** no se evaden captchas ni protecciones anti-bot, no se crean cuentas y no se
  escriben credenciales en ningún ATS. Tampoco se envían mensajes en nombre del usuario (WhatsApp,
  correo). Todo eso termina en el paquete de respaldo.

### Medición (tarea 5.1, con la sesión del dueño)

30 vacantes enviadas al canal del 12 al 15 de octubre: **11 externas, 4 sencillas, 9 cerradas y 6
pausadas** (detalle en `openspec/changes/medir-destinos-linkedin/design.md`). La mitad ya no recibía
solicitudes a los 6-9 días: conviene postular pronto y no gastar el turno en vacantes cerradas
(`jobPosting/{id}` ya las distingue sin sesión).

### Reconocimiento de los destinos (2026-10-21)

Sin sesión: 20 GET públicos, uno cada ~8 s y ninguno bloqueado. En el navegador integrado, solo se leyó
el DOM de Workday, Ashby y Typeform, sin escribir ni enviar nada. En Workday se pulsó «Solicitar
manualmente» y en Typeform «start», dos botones que solo cambian de pantalla. No se guardan nombres de
empresas: solo familias y dominios.

| Familia (de 11) | Cómo se arma | Campos y marcado | CV | Preguntas propias | ¿Cuenta? | Captcha / iframes | API pública de lectura |
|---|---|---|---|---|---|---|---|
| **Greenhouse** (4: 3 por `grnh.se` → 301 a `job-boards.greenhouse.io/{tablero}/jobs/{id}`, 1 directa) | HTML completo desde el servidor (Remix). El esquema también viene en `window.__remixContext` (`questions`). `form#application-form` | `input#first_name`/`#last_name`/`#email` con `autocomplete` `given-name`/`family-name`/`email`; `#phone` `type=tel`; `label[for]` con «*», `aria-label` y `aria-required="true"`. Las listas son react-select: `input[role=combobox]` con `aria-labelledby`, más un `<input required>` oculto; las opciones **no están en el DOM** hasta abrir la lista. País y «Location (City)» son combobox con búsqueda | `input#resume[type=file]` oculto tras «Attach» (también Dropbox, Google Drive o «Enter manually»), `accept=.pdf,.doc,.docx,.txt,.rtf`. Carta opcional (`#cover_letter`) | `question_{id}`: 5 en un tablero y 11-13 en el otro. Sí/No (autorización para trabajar en Colombia, ubicación, carrera), texto (universidad, salario en COP o «con moneda», LinkedIn), rangos de promedio, nivel de inglés A1–C1, «¿cómo te enteraste?» y **un archivo obligatorio extra (certificado de notas)** | **No**. «Autofill my application» (MyGreenhouse) es opcional | reCAPTCHA Enterprise **invisible** al enviar (`GOOGLE_RECAPTCHA_INVISIBLE_KEY`). Sin iframes en el tablero alojado; muchas empresas lo **incrustan en su sitio** con un iframe `boards.greenhouse.io/embed/job_app` | **Sí**: `boards-api.greenhouse.io/v1/boards/{tablero}/jobs/{id}?questions=true` (200): `questions` con `name`, `type` (`input_text`, `input_file`, `textarea`, `multi_value_single_select`, `multi_value_multi_select`), `values` y `required`, más `location_questions`, `demographic_questions` y `compliance` (EEOC) |
| **Workday** (2: `wd12`, `wd501`) | SPA pura. Sin navegador, la URL responde `{"widget":"redirect","externalSpa":true}` | Todo con `data-automation-id`. Paso 1 de 6, «Create Account/Sign In»: `email`, `password` y `verifyPassword` (`autocomplete=new-password`), `createAccountCheckbox` y un **campo trampa** `beecatcher` | «Rellenar automáticamente con currículo» o «Solicitar manualmente» (después de la cuenta) | `questionnaireId` en el JSON; pasos My Information, My Experience, Application Questions, Voluntary Disclosures y Review | **Sí, por empresa** (verificado) | No se vieron | **Sí**: `/wday/cxs/{tenant}/{sitio}/job/{ruta}` (`canApply`, `questionnaireId`, `includeResumeParsing`, `endDate`) |
| **Pandapé** de Computrabajo (1: `*.pandape.computrabajo.com`) | HTML desde el servidor (ASP.NET y jQuery Validate unobtrusive, como Computrabajo) | El detalle lleva a `/ApplyCT/{id}`: un formulario `POST /Apply` que pide solo el correo (`input#Email type=email`, `actionFrom=SetEmail`, `requireLoginCt=false` y token antifalsificación) | No se vio | No se vio | **Sin confirmar**: identifica la candidatura por el correo y lo siguiente solo aparece al enviarlo | No se vieron | No |
| **Ashby** (1: `jobs.ashbyhq.com/{org}/{id}/application`) | SPA (React). `window.__appData` no trae el formulario | **Sin `<form>`**; `name` e `id` = ruta del campo (`_systemfield_name`, `_systemfield_email`, UUID), `label[for]` y `required`. Botón `type=submit` «Submit Application» | Dos `input[type=file]`: **el primero, sin etiqueta, es «Autofill from resume»**; el CV es `#_systemfield_resume` | Esta vacante: nombre, correo, teléfono (opcional) y CV. El esquema admite `String`, `Email`, `Phone`, `File`, `Boolean`, `ValueSelect`, `MultiValueSelect`, `LongText`, `Number`, `Date` y `Location` | **No** | reCAPTCHA Enterprise **invisible**: los iframes `anchor` y `bframe` están en la página desde que carga, ocultos | **Sí**: `api.ashbyhq.com/posting-api/job-board/{org}` (vacantes con `applyUrl`, sin formulario) y `POST jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting` (lo que llama la propia página, sin autenticación): `applicationForm.sections[].fieldEntries[]` con `path`, `type`, `isRequired` y `selectableValues` |
| **Typeform** (1: `{cuenta}.typeform.com/to/{id}`) | SPA. **La definición completa** está en `window.rendererData.form` | **Una pregunta por pantalla**: `input` con `aria-labelledby="{id}-title"` y «*» en el título; botones `[data-qa=ok-button]` («start») y `[data-qa^=ok-button-visible]` («Continue»); pantalla de bienvenida y de gracias | `file_upload` obligatorio (PDF, 10 MB) | 17 preguntas: `short_text`, `email`, `phone_number`, 6 `long_text` de experiencia y motivación (redacción), `multiple_choice` (años de experiencia, herramientas) | **No** | No se vieron | Lectura de la propia página (`rendererData`); la API oficial pide token |
| **SuccessFactors** (1: `careers.{empresa}.com`, SAP RMK «j2w») | HTML desde el servidor | Detalle con `a.dialogApplyBtn` → `/talentcommunity/apply/{id}/`, que sin sesión hace 301 a la portada, con un formulario a `career2.successfactors.eu/career?…login_ns=register` (`ucc_email`). Banner de cookies | — | — | **Sí** (registro con contraseña) | No se vieron | No |
| **Acortador** (1: `ai-job.link`) | — | 302 → `wa.me/{número}?text=…` → `api.whatsapp.com`: **un chat de WhatsApp** con el mensaje ya escrito y el código de la vacante | — | — | — (no es un formulario) | — | — |

**Pide cuenta:** de las 11 externas, **6 no** (Greenhouse 4, Ashby y Typeform), **3 sí** (Workday 2 y
SuccessFactors), Pandapé está **sin confirmar** y 1 **no es un formulario** (WhatsApp).

**Lo que se aprende para el diseño:**
1. **El marcado accesible es la regla.** Greenhouse, Ashby y Typeform etiquetan cada campo (`label[for]`,
   `aria-labelledby`, `aria-label`) y marcan los obligatorios (`required`, `aria-required`, «*»). El motor
   actual ya lee casi todo eso; le faltan los widgets ARIA (`role=combobox` con opciones que se cargan al
   abrir, `aria-haspopup=listbox`, `role=radio`).
2. **No siempre hay `<form>`** (Ashby). El contenedor se deduce de los campos visibles.
3. **El captcha invisible está casi siempre.** Greenhouse y Ashby cargan reCAPTCHA Enterprise desde el
   inicio, con sus iframes ocultos. El motor actual ya solo cuenta un captcha **visible** (`buscar` filtra
   por `visible`), y el modo genérico debe mantener esa regla: «**desafío visible**» (un iframe del
   desafío con tamaño y a la vista, o el texto de verificación), nunca «hay un script de captcha», porque
   eso mandaría casi todo al respaldo. Hay que sumar `recaptcha/enterprise/bframe` a los selectores.
4. **Hay trampas y señuelos:** un campo trampa oculto (`beecatcher` en Workday) y un `input[type=file]` de
   «autofill» antes del CV (Ashby). El motor nunca llena campos ocultos ni fuera de pantalla, y elige el
   archivo por su etiqueta.
5. **Hay archivos obligatorios distintos del CV** (certificado de notas) y datos que el perfil no tiene
   (promedio). No se inventan: se le preguntan al usuario o la vacante va al respaldo.
6. **Tres familias publican su esquema** (API o JSON en la página): el formulario se puede conocer
   **antes** de abrirlo, para resolver todas las respuestas en una sola llamada al redactor.
7. **Formularios en inglés.** Hay que responder en el idioma del formulario y entender etiquetas en
   inglés y portugués.
8. Lo que no es formulario (WhatsApp) y lo que exige cuenta (Workday, SuccessFactors) se puede saber
   **por el dominio**, antes de abrir nada.

Pendiente de ver con sesión (👤, en el change de postulación): la **Solicitud sencilla** dentro de
LinkedIn (un modal de varios pasos), el paso siguiente de Pandapé después del correo y la verificación
por código que Greenhouse puede pedir al enviar (conocida, no vista aquí).

#### Lever (reconocimiento sin sesión, 2026-10-25, tarea 3.3 de `postular-linkedin`)

Ninguna vacante de la medición era de Lever, así que se leyó, solo con GET y con 8 s entre peticiones,
la página pública `/apply` de una vacante abierta de otra empresa (`jobs.lever.co/spotify/{id}/apply`,
la primera que devolvió `api.lever.co/v0/postings/spotify`). No se escribió ni se envió nada, y el recorte
de `tests/fixtures/ats/lever_apply.html` no tiene datos personales (el nombre de la empresa se cambió).

- **Esquema en el HTML**: `form#application-form` con una `li.application-question` por pregunta. La
  etiqueta es `.application-label` y la marca de obligatorio un `<span class="required">✱</span>`.
  Las preguntas de la empresa son `li.custom-question` con `name="cards[{uuid}][field{n}]"`.
- **Campos fijos**: `resume` (archivo, tras «ATTACH RESUME/CV»), `name`, `email`, `phone`, `location`
  (con lista de sugerencias; el valor elegido va en `selectedLocation`, oculto), `org` y
  `urls[LinkedIn|GitHub|Portfolio|Other]`.
- **Listas**: radios o casillas con `.application-answer-alternative` (las opciones sí están en el DOM)
  y `<select>`. Las **encuestas voluntarias** (`surveysResponses[…]`: género, raza, veterano) y los
  `pronouns` no se responden, y el lector los ignora.
- **Captcha**: el formulario trae **hCaptcha** (`.h-captcha`, `hcaptcha.com/1/secure-api.js`). «Submit
  application» (`#btn-submit`) lanza `hcaptcha.execute` y recién entonces envía. El motor no resuelve
  captchas: si aparece el desafío, la postulación se detiene como barrera (`captcha`) y va al respaldo.
  Hay que ver en el ensayo qué fracción de los envíos de Lever lo muestra.
- **Sin cuenta**: no pide contraseña ni correo de verificación en esta página.
- **Sin ver todavía**: la página de gracias de Lever (se supone `…/thanks`) y el tipo de campo de las
  preguntas de salario o fecha, porque la muestra no los tenía. `assets/asistente/familias_ats.json`
  los declara como datos para corregirlos sin publicar otra extensión.

#### Vacante y Solicitud sencilla de LinkedIn (reconocimiento con sesión, 2026-10-25, tarea 5.1)

Con la sesión del dueño en Claude in Chrome, solo lectura. Se abrieron 6 vacantes de la medición
(1 sencilla de un paso, 1 sencilla de varios pasos, 1 externa, 1 cerrada, 1 pausada) y los dos modales
se cerraron con **«Descartar»**, sin guardar nada ni pulsar «Enviar solicitud». Recortes sin datos
personales en `tests/fixtures/linkedin/`.

- **Las clases CSS están ofuscadas** (`l4jlhg`, `l4jhc3`…) y cambian: los selectores van por
  `aria-label`, `role`, `type` y texto, nunca por clase ni por `id` generado (`_r_1c_`).
- **Vacante sencilla**: `button[aria-label="Solicitud sencilla"]` (texto «Solicitud sencilla») junto a
  `button[aria-label="Guardar empleo"]`.
- **Vacante externa**: `a[aria-label="Solicitar en el sitio web de la empresa"]` (texto «Solicitar ↗»,
  `target=_blank`), con href `linkedin.com/safety/go/?url=…&urlhash&mt&isSdui` y el destino en `url`.
  Hay **otros** enlaces `/safety/go` en la página (por ejemplo, el aviso de privacidad de la empresa,
  con aria-label «Abrir https://…»): el destino solo se toma del enlace con ese aria-label. Texto de la
  página: «Respuestas gestionadas fuera de LinkedIn».
- **Cerrada** («Ya no se aceptan solicitudes») y **pausada** («No se aceptan solicitudes en estos
  momentos»): sin botón de solicitar; se distinguen solo por el texto.
- **El modal es un `<dialog open aria-labelledby="dialog-header">`**, con la X `button[aria-label="Descartar"]`.
  Hay **dos formas**:
  - *Un paso* (visto en Holcim ADC): contacto (correo y código de país en `<select required>`,
    teléfono `input[type=tel]`), CV y casilla «Sigue a {empresa}…» **marcada por defecto**
    (`input[type=checkbox][aria-label^="Sigue a "]`), y directo «Enviar solicitud». No hay «Siguiente»
    ni «Revisar».
  - *Varios pasos* (visto en 4 páginas): barra de progreso («25 porcentaje completado», «1/4 páginas»)
    y botones «Siguiente» / «Volver». La página 1 es el contacto, ya rellenado; la 2 pide el CV.
- **CV**: el modal pide «Resume*» y lista los guardados en `fieldset[role=radiogroup]`. La cuenta del
  reconocimiento **no tenía ninguno guardado**, así que solo salió «Cargar currículum» y el
  `<input type=file>` **no existe hasta pulsar ese botón**. Por eso el reconocimiento se detuvo en la
  página 2/4: subir un archivo habría entregado datos del usuario. El texto del modal dice que las
  respuestas y el CV se guardan para la próxima vez.
- **Cerrar con la X** abre un segundo `<dialog open>` encima, «¿Quieres guardar esta solicitud?», con
  «Descartar» y «Guardar» (guardar deja un borrador en la cuenta; el motor debe usar «Descartar»).
- **Sin ver todavía**: la pantalla de revisión de un modal de varios pasos (y si ahí está «Seguir a la
  empresa»), las preguntas adicionales, el mensaje de «Se envió tu solicitud» y el aviso de seguridad
  de LinkedIn (no se provocó). La 5.2 deja esos selectores como supuestos hasta verlos en el ensayo.

#### Modal de varios pasos hasta la revisión (reconocimiento con CV del dueño, 2026-10-27, tarea 5.1)

Se recorrieron dos sencillas de 4 pasos (Resolv Global y RappiPay) y la de RappiPay llegó hasta la
pantalla de revisión **sin pulsar «Enviar solicitud»**; se cerró con «Descartar». Los datos escritos
eran de prueba, dictados por el dueño.

- **Pasos**: 1 contacto (ya relleno), 2 «Currículum*» (en Resolv Global el rótulo es «Resume*» y hay una
  «Cover letter» opcional), 3 «Preguntas adicionales», 4 revisión. Los textos del modal salen en el idioma
  de la empresa, no en el de la cuenta (Resolv Global en inglés, RappiPay en español).
- **Preguntas adicionales** (paso 3): `input[type=text]` con `aria-label` igual a la pregunta, todas
  obligatorias en estos dos casos: años con TensorFlow, Python y PyTorch y aspiración salarial (RappiPay);
  ubicación, salario, velocidad de internet y WhatsApp (Resolv Global), además de radios Sí/No de
  residencia y de zona horaria. Sin respuesta el paso no avanza.
- **El botón del paso 3 se llama «Revisar»**, no «Siguiente»; con él se llega a «Revisa tu solicitud»
  (`h2`), con secciones «Información de contacto», «Currículum» y «Preguntas adicionales», cada una con
  `button[aria-label="Editar …"]`.
- **Revisión**: la casilla «Sigue a {empresa} para enterarte de las novedades de su página» sale
  **marcada por defecto** y debajo está «Enviar solicitud». El texto avisa de que «tus respuestas y tu CV
  se guardarán» para solicitudes futuras (enlace `/help/linkedin/answer/a507694/`) y trae el «Aviso de
  derechos laborales», un enlace `/safety/go` que **no** es un destino externo.
- **El CV no persiste si se descarta**: el `fieldset[role=radiogroup]` («CV selection») está **vacío** en
  la solicitud siguiente aunque se haya subido el archivo en la anterior; el aviso del diálogo de cierre
  lo dice («No se guardarán los archivos importados»). Hay que subir el CV en cada solicitud o enviar
  una vez para que LinkedIn lo guarde.
- **Subida**: el `<input type=file>` se crea al pulsar «Cargar currículum» y esa pulsación abre el
  selector nativo. En el reconocimiento se evitó parcheando `HTMLInputElement.prototype.click` para que no
  abriera el selector y subiendo con `file_upload` al input capturado. Tras subir, el modal muestra la
  tarjeta del PDF con el radio marcado y el aviso «Se ha cargado el currículum». Acepta DOC, DOCX o PDF de
  menos de 2 MB.
- **Sigue sin verse**: el mensaje de «Se envió tu solicitud» (no se envió ninguna) y el aviso de seguridad.

#### Cómo lo recorre la extensión 1.3.0 (tarea 5.3, 2026-10-27)

- **Vacante**: abre `linkedin.com/jobs/view/{id}` y la clasifica con `linkedin.json`, en este orden:
  sin sesión (URL de ingreso o `/authwall`), aviso de seguridad (`/checkpoint/` o sus textos),
  externa, sencilla, pausada y cerrada. El orden importa: **`/authwall` también muestra un diálogo
  «Verificación de seguridad»** (visto el 2026-10-27 al abrir la ventana de contacto sin sesión), y
  confundirlo con el aviso de seguridad pausaría LinkedIn 24 h sin motivo.
- **Externa**: nunca pulsa «Solicitar». Lee el parámetro `url` del enlace con aria-label «Solicitar en
  el sitio web de la empresa» (no el de otros `/safety/go`), lo manda a `POST /destino` y, con
  `abrir`, navega **la misma pestaña** al destino y sigue con el bucle genérico como plataforma
  `externa`. Un destino ya guardado se abre directo, sin pasar por LinkedIn.
- **Plataforma `externa`**: el motor solo opera si la URL es https, no es de ingreso, registro, OAuth
  ni pago, no está en `hosts_prohibidos` y su host es el del destino, comparte su dominio
  registrable o es de una familia de ATS conocida (`medicion_linkedin.familias`, que el servidor
  entrega como `familias_hosts`). Si no, se detiene con `salto_de_dominio`, `oauth` o
  `pagina_prohibida`. Los datos de `familias_ats.json` (CV, botón de enviar y éxito) van antes que
  las reglas genéricas.
- **Sencilla**: avisa con `POST /destino {"tipo": "sencilla"}`, pulsa «Solicitud sencilla» y el bucle
  lee solo dentro del `<dialog>` del modal (también su `<footer>`, donde están los botones). Antes de
  cada pantalla desmarca «Sigue a …» y resuelve el CV: con la autorización de actualizar el CV pulsa
  «Cargar currículum» y adjunta el adaptado; si no, elige el primer CV guardado; sin ninguno, va al
  respaldo con `linkedin_sin_cv`. La casilla y el grupo de CV nunca se mandan al servidor. Sin envío
  (ensayo, respaldo o error) cierra con la X y «Descartar».
- **Cuenta (supuesto)**: las páginas de empleo no muestran el correo. `linkedin.json` lo lee del
  enlace `mailto:` de la ventana «Información de contacto» del propio perfil
  (`/in/me/overlay/contact-info/`). **No se pudo verificar**: el 2026-10-27 la sesión de LinkedIn del
  Chrome del dueño había caducado. Se verifica en el ensayo (6.2); sin correo, la cuenta no se
  confirma y la cola no asigna trabajos de LinkedIn.
- **Permiso `https://*/*`**: el popup lo pide con un toque y su explicación (bloque «Páginas de las
  empresas», visible cuando el servidor habilita LinkedIn). La extensión lo reporta en el latido
  como `portales.externa` y el servidor lo borra en cuanto deja de llegar.

### Qué se reutiliza del asistente

| Pieza | Hoy | Para LinkedIn |
|---|---|---|
| `extension/motor.js` | Pasos declarativos por portal (`detectar`, `clic`, `enviar`, `formulario`, `llenar`, `confirmar`). `leerCampos` ya resuelve `label[for]`, la etiqueta envolvente, `aria-label`, `aria-labelledby`, el título del bloque y `placeholder`, y detecta lo obligatorio por `required`, `aria-required`, `data-val-*` y «*». `asignarValor` usa el *setter* nativo (sirve para React). `adjuntar` sube el PDF con `DataTransfer` | Base del modo genérico: se añaden widgets ARIA, la deducción del contenedor, la clasificación de botones, la detección de resultado y las barreras |
| `extension/servicio.js` | Abre la pestaña, inyecta el motor, coordina los pasos, `correrSeguro` ante una navegación, `formulario()` → `/formulario`, `envio` antes del clic, verificación con la pestaña visible, evidencia sin valores | El bucle genérico es otro `ejecutar` con los mismos ladrillos. Se añade la inyección en iframes (`allFrames`) |
| `extension/portales.js` | `DOMINIOS` por plataforma, `paginaPermitida` y `PROHIBIDAS` | La plataforma «externa» admite cualquier `https` salvo la lista de prohibidas, ampliada con inicio de sesión, cuenta, pagos y OAuth |
| `assets/asistente/selectores/*.json` | Datos versionados que entrega el servidor (sin código remoto) | El mismo formato sirve para las **recetas por dominio** que aprende el bot |
| `asistente/respuestas.py` | Orden: tipo y `name` → aprendidas → consentimiento al usuario → banco → clasificación con IA → redactor por formulario (`redactar_formulario`, una llamada) → «falta dato» por la card | Se mantiene el orden y se añaden `autocomplete`, los sinónimos en inglés y portugués y el idioma de respuesta |
| `asistente/campos.py` | Catálogo cerrado de 19 campos + `conoce`/`idioma` | Hacen falta `nombre_pila`, `apellido`, `pais`, `enlace_linkedin`, `autorizacion_trabajo` (con parámetro: país), `promedio` y `fuente_vacante` (la respuesta a «¿cómo te enteraste?» es «LinkedIn» sin preguntar) |
| Card de Telegram y `esperando_usuario` | Preguntas pendientes con botones, respuesta recordada | Igual, más los archivos extra que el usuario quiera dar una vez |

### Diseño del modo genérico

**Idea central:** no se escribe un flujo por ATS. Un solo bucle **lee la pantalla, decide, llena,
avanza y vuelve a leer**. Lo específico de cada sitio son datos (recetas) que el bot aprende solo.

#### 1. Clasificar el destino antes de abrirlo

En la pestaña de LinkedIn, con la sesión del usuario, el motor lee el tipo de solicitud: el botón
«Solicitud sencilla» o `a[href*="/safety/go"]` con el parámetro `url`. Luego limpia la URL y llama a
`familia_de` (del change de medición). Con eso decide:

| Resultado | Qué pasa |
|---|---|
| Cerrada o pausada (`jobPosting` o la propia página) | `vacante_cerrada`, sin abrir nada más |
| `wa.me`, `api.whatsapp.com`, `mailto:`, `t.me` | Respaldo («la empresa recibe por WhatsApp o correo»), con el enlace |
| Familia con cuenta conocida (Workday, SuccessFactors, Taleo, iCIMS, Gupy…) o dominio aprendido como barrera | Respaldo inmediato, motivo `ats_con_cuenta` |
| Solicitud sencilla | Bucle genérico dentro del modal de LinkedIn |
| Cualquier otra (Greenhouse, Ashby, Lever, Typeform, Pandapé, sitio propio, acortador…) | Bucle genérico, con el adaptador de la familia si existe |

Los acortadores se resuelven solos, porque la pestaña sigue las redirecciones; la clasificación se
repite sobre la URL final.

#### 2. El bucle

Cada vuelta es una «pantalla». Tope de 12 pantallas (40 en los formularios de una pregunta por pantalla,
como Typeform) y de 10 minutos.

1. **Leer la pantalla** (`leerPantalla`). El resultado es uno de estos:
   - **barrera**: `input[type=password]` visible; `autocomplete` `current-password`/`new-password`;
     textos como «crear cuenta», «create account», «inicia sesión para postular», «sign in to apply» o
     «criar conta» junto al formulario; solo botones de OAuth («Apply with LinkedIn/Google») como
     camino; desafío de captcha **visible**; código de verificación. → para.
   - **intermedia**: descripción de la vacante con un botón o enlace de postular («Apply», «Aplicar»,
     «Postular», «Solicitar», «Candidatar-se», «I'm interested») y sin formulario → se pulsa, sin
     contarlo como envío.
   - **formulario**: hay campos visibles → esquema.
   - **éxito**: textos («thank you for applying», «application received», «gracias por postularte»,
     «hemos recibido tu postulación», «candidatura enviada»…), URL (`/confirmation`, `/thank`,
     `/success`, `submitted`) o el formulario desaparece y aparece un encabezado nuevo.
   - **error**: campos con `aria-invalid="true"`, `[role=alert]` o mensajes de validación junto a los
     campos.
   - **desconocida**: nada de lo anterior.

   Antes de leer, si un banner de cookies tapa la página, se pulsa la opción que rechaza las no
   esenciales («Rechazar», «Declinar», «Reject all»), como en Workday y SuccessFactors. Pandapé solo
   ofrece «Aceptar y cerrar», que es un consentimiento: no se pulsa mientras el banner no tape los campos.
2. **Extraer el esquema** (amplía `leerCampos`):
   - *Contenedor*: el `form` con más campos visibles o, si no hay ninguno (Ashby), el ancestro común
     más cercano de los campos visibles. Se excluyen el banner de cookies, el buscador y la cabecera.
   - *Controles*: los nativos más `role=combobox`/`listbox`/`radiogroup`/`radio`/`checkbox`/`switch`,
     `button[aria-haspopup=listbox]` y `contenteditable`. Si las opciones de un combobox no están en el
     DOM, se abre (foco y flecha abajo), se leen los `[role=option]` y se cierra con Escape. En las
     listas enormes o con búsqueda (país, ciudad) se manda solo la marca `busqueda: true`.
   - *Por campo*: `texto` (etiqueta), `ayuda` (`aria-describedby`), `tipo`, `opciones`, `obligatoria`,
     `nombre`, `autocomplete`, `maximo`, `accept` (archivos) e `idioma` (el `lang` de la página o el
     detectado).
   - *Fuera siempre*: ocultos, fuera de pantalla, `tabindex=-1` con `aria-hidden`, trampas (`beecatcher`,
     `honeypot`, `website` oculto), contraseñas, `g-recaptcha-response` y el `input[type=file]` sin
     etiqueta si hay otro etiquetado como CV.
   - Si un **adaptador** dio el esquema antes de abrir (punto 4), la pantalla solo se empareja con él.
3. **Resolver en el servidor** (el `resolver` actual, ampliado), en este orden:
   1. `autocomplete` → campo: `given-name`, `family-name`, `name`, `email`, `tel`/`tel-national`,
      `address-level2`, `country`/`country-name`, `url`, `organization`.
   2. `type` y tokens de `name`/`id`: `first_name`, `last_name`, `email`, `phone`, `resume`, `cv`,
      `cover_letter`, `linkedin`, `website`, `location`, `_systemfield_*`.
   3. Respuestas aprendidas del usuario y banco compartido, **sembrado también en inglés y portugués**
      («First Name», «Sobrenome», «LinkedIn Profile», «How did you hear about…», «Are you legally
      authorized to work in…», «desired salary», «pretensão salarial», «English level»…).
   4. Clasificación con IA (ya existe) → se guarda en el banco.
   5. Redactor por formulario (ya existe): una llamada por pantalla, o una por formulario si el esquema
      vino antes. **Responde en el idioma del formulario** y respeta `maximo` y la moneda que pida la
      pregunta.
   6. Lo que falta, los consentimientos y los **archivos obligatorios distintos del CV** → card de
      Telegram (`esperando_usuario`). En la primera versión, un archivo extra obligatorio lleva al
      respaldo. Los opcionales se dejan vacíos.
   7. Preguntas voluntarias de diversidad (EEOC): la opción «prefiero no responder» si existe; si no, se
      dejan vacías cuando no son obligatorias.
4. **Llenar y comprobar** (amplía `llenar`): texto con el *setter* nativo; combobox (escribir, esperar
   las opciones, pulsar la que coincide y **leer lo que quedó mostrado**); radios y casillas ARIA (clic y
   `aria-checked`); fechas en el formato del `placeholder`; teléfono con selector de país (+57 y número);
   archivo con `DataTransfer` en el `input[type=file]` etiquetado como CV. Si un campo no quedó como se
   quería, no se avanza: `formulario_desconocido` con la evidencia, como hoy.
5. **Avanzar o enviar.** Se clasifican los botones del contenedor y los de justo debajo:
   - *avanzar*: siguiente, continuar, next, continue, próximo, revisar, review, «OK»;
   - *enviar*: enviar, submit, apply, postular, aplicar, «submit application», «enviar solicitud»,
     «enviar candidatura»;
   - *nunca*: cancelar, volver, guardar borrador, subir o adjuntar, autofill, «locate me», iniciar
     sesión, «apply with…», compartir.

   Con `type=submit` y un solo candidato, ese gana. Si hay ambigüedad, decide el árbitro (punto 6).
   Antes de **enviar** se reporta `envio` al servidor (la regla de no reenviar se mantiene) y se espera
   a que el botón se habilite.
6. **Árbitro con IA (solo cuando las reglas dudan).** Para una página que no se entiende (no se sabe si
   hay barrera, cuál es el botón o si se envió), se manda a la IA un **resumen de la página sin valores**:
   la lista numerada de elementos visibles e interactivos con su rol y texto, los encabezados y los
   avisos. La IA responde un índice y una etiqueta (`avanzar`, `enviar`, `exito`, `barrera`, `error`).
   Es una llamada corta y solo en los casos dudosos. Es lo que permite operar en un ATS que nunca se vio
   sin que nadie escriba selectores.
7. **Detectar el resultado** (hasta 25 s, también después de navegar): con éxito → `enviada`; con error
   de validación → **una** sola vuelta de corrección (releer los campos marcados y resolverlos de
   nuevo) y, si sigue igual, `formulario_desconocido`; con campos nuevos → otra vuelta del bucle; con
   barrera → respaldo; si nada cambió tras «avanzar» → `formulario_desconocido`; si nada claro tras
   «enviar» → `incierta`. Un código de verificación por correo después de enviar se le pide al usuario
   por la card (tiene el correo a mano) o, si no responde en 10 minutos, queda `incierta`.

#### 3. Aprender de cada página (recetas por dominio)

- Tras cada `enviada`, la extensión reporta la **receta** de ese sitio, **sin valores**: host y patrón de
  ruta, familia, y por pantalla una firma (las claves de los campos en orden), el mapeo campo → dato del
  catálogo (o «redactar»), el selector del botón usado (avanzar o enviar) y la señal de éxito vista
  (texto, URL o selector). Tiene la misma política que el banco de preguntas: no guarda datos
  personales y se comparte entre usuarios.
- El servidor la guarda (`recetas_dominio`: host, familia, firma, receta en JSON, éxitos, fallos,
  versión) y la entrega con el trabajo, como hoy los selectores. En la siguiente vacante de ese dominio,
  o de esa familia si el dominio es nuevo, el motor **prueba primero la receta**. Si la firma no
  coincide, vuelve a las heurísticas.
- También se aprende lo negativo: si el dominio pide cuenta o no es un formulario, las vacantes
  siguientes de ese dominio van al respaldo **sin abrir la página**.
- **Autocorrección:** cuando una página falla con evidencia, el servidor le pide a la IA, sobre el HTML
  sin valores, una **receta candidata** (otro botón, otra señal de éxito, otro contenedor). Se prueba en
  la siguiente vacante de ese dominio y solo pasa a firme con un éxito. Una receta con 2 fallos
  seguidos se apaga (vuelven las heurísticas) y se avisa al dueño.
- Las recetas son datos interpretados por `motor.js`, nunca código remoto, igual que
  `assets/asistente/selectores/`. Una receta con 3 éxitos puede pasarse a mano a un archivo revisado.

#### 4. Adaptadores que valen la pena

Un adaptador es corto. Da el esquema antes de abrir la página (para resolver todo en una sola llamada)
y declara el botón y la señal de éxito de la familia. No reemplaza al bucle.

| Adaptador | Por qué | Qué aporta |
|---|---|---|
| **Greenhouse** | La familia más frecuente de la muestra (4 de 11) y muy común en vacantes remotas | Esquema desde `boards-api` o `__remixContext` (con las opciones de los combobox), `#resume`, «Submit application», detección del iframe `embed/job_app` en sitios propios |
| **Solicitud sencilla de LinkedIn** | 4 de las 15 abiertas, y se queda dentro de LinkedIn | Modal de varios pasos (`[role=dialog]`): elegir el CV, preguntas de selección, «Siguiente», «Revisar», «Enviar solicitud». Pide reconocimiento con sesión (👤) |
| **Ashby** | Frecuente en startups; sin `<form>` | Esquema por la consulta GraphQL; evita el campo de «autofill» |
| **Typeform** | Una pregunta por pantalla y muchas preguntas largas | Esquema desde `rendererData`: el redactor responde todo en una llamada y el bucle solo pulsa «Continue» |
| **Lever** (no apareció en la muestra) | Muy común; `jobs.lever.co/{empresa}/{id}/apply`, sin cuenta, API pública `api.lever.co/v0/postings/{empresa}/{id}` | Esquema y botón |
| Workday, SuccessFactors, Taleo, iCIMS | Piden cuenta | **Ninguno**: solo la regla del clasificador (respaldo) |

#### 5. Cobertura estimada

Sobre la muestra, con las 15 abiertas (11 externas y 4 sencillas):

| Capa | Externas que completaría (de 11) | Comentario |
|---|---|---|
| Clasificador y barreras | 0 automáticas, pero **4 al respaldo sin perder tiempo** (Workday 2, SuccessFactors 1, WhatsApp 1) | Es correcto que esas cuatro vayan al respaldo |
| Bucle genérico solo | **2-3** (Ashby, el Greenhouse sin archivo extra y, con suerte, Typeform) | Los combobox de react-select y las 17 pantallas de Typeform son los puntos frágiles |
| + adaptadores (Greenhouse, Ashby, Typeform) | **3 seguras** | Las 3 de un tablero de Greenhouse piden un certificado de notas obligatorio |
| + preguntas y archivos extra por la card | **6** | El usuario da el promedio y sube el certificado una vez |
| + Pandapé, si después del correo no pide contraseña | **7** | Por confirmar |
| Solicitud sencilla | **+4 de 4** si el modal se comporta como se espera | Por confirmar con sesión |

Con todas las capas: **10-11 de las 15 abiertas (67-73 %)** sin intervención, y las demás al respaldo con
motivo claro. Sin la Solicitud sencilla ni los archivos extra, el mínimo es **3 de 15 (20 %)**.

Para páginas nunca vistas, en general (estimación por el comportamiento conocido de cada familia, sin
medir): el bucle genérico con el árbitro debería completar **más o menos la mitad** de los formularios
públicos de una sola página en el primer intento. Los fallos terminan en `formulario_desconocido` sin
enviar nada. Con las recetas, un dominio que funcionó una vez sigue funcionando **sobre el 90 %** de las
veces. **Cuidado:** la muestra es pequeña (11 externas, 3 del mismo tablero), así que estas cifras son
orientativas. La medición de 100 vacantes (tarea 4.1) da la distribución real de familias.

#### 6. Permisos, seguridad y ritmo

- **Permiso opcional amplio** (`https://*/*`), pedido desde el popup con una explicación clara y solo a
  quien activó LinkedIn. Sin él, las externas van al respaldo. Inyección con `allFrames` para los
  formularios incrustados.
- **Páginas prohibidas ampliadas:** inicio de sesión, registro, recuperar contraseña, pagos, OAuth
  (`accounts.google.com`, `login.microsoftonline.com`, `linkedin.com/oauth`) y cualquier dominio de banca.
  Si el flujo salta a un dominio no relacionado con la vacante y no es un ATS conocido, se detiene.
- **Nunca:** crear cuentas, escribir contraseñas, resolver captchas, aceptar OAuth, enviar mensajes,
  pagar, ni subir documentos que el usuario no autorizó. Los consentimientos los decide el usuario, como
  hoy.
- **Ritmo en LinkedIn:** una postulación a la vez, pausas humanas y un tope diario por usuario (por
  ejemplo, 15), para no llamar la atención sobre la cuenta.
- **Por usuario:** aceptación expresa del riesgo de LinkedIn (sube la versión de la autorización) e
  interruptores separados para «Solicitud sencilla» y «páginas externas».

### IA del usuario y autorreparación (decisión del dueño, 2026-10-21)

El dueño aprobó que el bot entienda los formularios con la IA que cada usuario configuró en Telegram
(Gemini, Groq, OpenRouter, OpenAI, Anthropic o DeepSeek, por `ClienteIA`), que llene solo, que use la
IA únicamente cuando la necesite y que, si algo falla, se repare y siga. Además pidió que esto valga
**para todas las plataformas**, no solo para LinkedIn.

**Meta realista:** «sin fallos» no se puede garantizar, porque las páginas cambian, se caen o piden cosas
que el usuario no tiene. La meta es **nunca fallar mal** (no inventar, no enviar dos veces, no escribir
donde no se debe) y **repararse solo** en la mayoría de los casos, aprendiendo para que no se repita.

#### Capas, de la más barata a la más cara

1. **Reglas**: `autocomplete`, etiquetas, botones y textos conocidos. Sin costo.
2. **Flujo declarado o receta**: los pasos de `assets/asistente/selectores/*.json` en Computrabajo,
   Magneto y elempleo, y las recetas aprendidas en los demás sitios. Sin costo.
3. **Árbitro** (tarea de IA nueva, `entender_pagina`): solo cuando las reglas dudan. Recibe la lista
   numerada de elementos visibles sin valores y responde un índice y una acción.
4. **Reparación** (tarea de IA nueva, `reparar_flujo`): cuando un paso falla **antes de enviar**.
   Recibe la evidencia (HTML sin valores, el paso que falló y el motivo) y propone una corrección.

Cuenta aproximada por postulación: una llamada al redactor y de 0 a 3 al árbitro. En un dominio con
receta, casi siempre 0.

#### Autorreparación dentro de la misma postulación

- **Antes de pulsar «enviar»** reintentar es seguro. La reparación propone una acción: otro botón, un
  campo que faltó, cerrar un modal o esperar más. Se aplica y se reintenta, como máximo 2 veces por
  postulación. Si funciona, la corrección queda como receta o como **parche candidato** de los
  selectores.
- **Después de pulsar «enviar»** nunca se reintenta solo, porque podría postular dos veces. Si el
  resultado no es claro, queda `incierta`, como hoy.
- **En las plataformas declaradas** (Computrabajo, Magneto, elempleo), un paso que falla antes del envío
  ya no termina directamente en `formulario_desconocido`: primero entra el bucle genérico con la
  reparación. El fallo del cuestionario de elempleo del 2026-10-17 es el caso de prueba: el bucle lo
  habría leído como un formulario más.
- Los parches de los selectores declarados se aplican como **candidatos** (solo para la siguiente
  postulación de esa plataforma) y pasan a firmes con un éxito. Al dueño le llega el parche con la
  evidencia para pasarlo al JSON revisado cuando quiera.

#### Límites duros de la IA

- Solo responde con **índices de la lista** que le pasó el motor y con una acción de una lista cerrada
  (`llenar`, `pulsar`, `elegir`, `esperar`, `cerrar_modal`, `avanzar`, `enviar`, `exito`, `barrera`,
  `respaldo`). Nunca escribe selectores, URL ni contraseñas, y nunca navega por su cuenta.
- Su salida se valida con pydantic, como la del redactor. Un índice que no existe se descarta.
- El texto de la página va delimitado como datos (`INSTRUCCION_DATOS`): si una página intenta darle
  órdenes a la IA, no logra nada fuera de esa lista.
- Nunca recibe valores del usuario en el resumen de la página. Las respuestas personales siguen saliendo
  del redactor, con la clave del propio usuario.

#### Qué clave paga cada cosa

- **Respuestas y árbitro**: la clave del usuario, como hoy, porque son su postulación y sus datos.
- **Reparación**: la clave del usuario cuya postulación falló. Como la receta que sale de ahí no tiene
  datos personales y sirve a todos, el dueño puede activar `asistente.autorreparacion.clave_duenio`
  para que, sin cuota del usuario, repare la clave del dueño. Viene apagado: hoy ninguna tarea usa la
  clave de otro usuario.
- Sin IA o sin cuota: reglas y recetas compartidas. Si hace falta IA y no hay, respaldo con el motivo
  `sin_ia`.

#### Niveles de IA por usuario (decisión del dueño, 2026-10-22)

El bot no depende de la IA: la usa solo cuando hace falta, y cada usuario elige cuánta con `/ia nivel` o en
el popup.

- **Ahorro**: IA solo para redactar las preguntas abiertas. Sin árbitro ni reparación; lo dudoso va a la card
  o al respaldo.
- **Normal** (por defecto): además, clasifica preguntas nuevas, árbitro hasta 3 y 1 reparación.
- **Máximo**, «lo mejor de lo mejor»: modelo completo con más razonamiento, respuestas alineadas a los
  requisitos de la vacante, el estilo del usuario, doble redacción de las respuestas largas, un revisor final
  que corrige idioma, límites e incoherencias antes de enviar, carta opcional en PDF, árbitro hasta 6 y 2
  reparaciones.

La seguridad es igual en los tres niveles. Si se acaba la cuota, el nivel baja en vez de fallar, y cada nivel
muestra su costo. Sin IA, el bot sigue con reglas, recetas y los datos del usuario. Detalle en el change
`motor-generico-autorreparable` (capacidad `nivel-ia-postulacion`).

#### Mejoras propuestas además de lo pedido

1. **Preparación anticipada.** Al tocar ⚡, el servidor lee el esquema del formulario **antes de
   abrirlo**, cuando la familia lo publica (API de Greenhouse, Ashby y Lever, o el JSON de Typeform), y resuelve todas las respuestas. Lo que falte se pregunta en la **misma card**, antes de
   encolar. La postulación ya no se detiene a la mitad para preguntar.
2. **Perfil de postulación ampliado y documentos.** Por Telegram, una sola vez: autorización para
   trabajar, salario en COP y en USD, nivel de inglés, promedio, LinkedIn y portafolio. Además, los
   documentos extra (certificado de notas o carta en PDF), que se guardan cifrados y se adjuntan solo
   cuando un formulario los pide por etiqueta.
3. **Modo ensayo.** Llena todo y **no pulsa enviar**: reporta qué habría enviado y dónde se trabó.
   Sirve por plataforma y por usuario, y es el primer paso de cada piloto. Una o dos semanas de ensayo
   en LinkedIn miden la cobertura real y acumulan recetas sin arriesgar postulaciones ni la cuenta.
4. **Vigía diario de portales.** Una vez al día, en modo ensayo, el navegador del dueño abre una
   vacante abierta de cada plataforma y recorre el flujo hasta antes de enviar. Si algo cambió, se
   repara o avisa **antes** de que le falle a un usuario.
5. **Banco de pruebas con páginas reales.** Copias recortadas de formularios de cada familia y portal
   como fixtures, con el motor corriendo en Playwright contra un envío falso. Cada versión de la
   extensión debe mantener o subir el porcentaje de éxito.
6. **Métricas por familia y plataforma**: éxito, `formulario_desconocido`, reparaciones, uso de IA y
   motivos de respaldo. Aparecen en el resumen semanal del dueño y en el panel de administración.

### Propuesta de changes (insumo de la tarea 6.3)

Para que valga en todas las plataformas, el trabajo se divide en **dos changes**:

1. **`motor-generico-autorreparable`** (todas las plataformas): el bucle genérico en `motor.js` y
   `servicio.js` (widgets ARIA, contenedor deducido, botones, resultado, barreras, iframes), el
   resolvedor ampliado (`autocomplete`, sinónimos en inglés y portugués, campos nuevos, idioma), las
   tareas de IA `entender_pagina` y `reparar_flujo`, la autorreparación, las recetas por dominio y los
   parches candidatos, la preparación anticipada, el perfil ampliado con documentos, el modo ensayo,
   el vigía, el banco de pruebas y las métricas. Se prueba primero sobre Computrabajo, Magneto y elempleo.
2. **`postular-linkedin`**: el clasificador de destino, la plataforma «externa» con el permiso amplio,
   los adaptadores de Greenhouse, Ashby, Typeform y Lever, la Solicitud sencilla (con reconocimiento 👤),
   la aceptación del riesgo, los interruptores por usuario, el tope diario y los pilotos en modo ensayo y
   luego reales. Depende del primero.
