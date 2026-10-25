## Context

- Depende de `motor-generico-autorreparable`: bucle genérico, `/pantalla`, árbitro, reparación, recetas,
  dominios barrera, esquema anticipado, documentos extra y modo ensayo. Este change solo añade lo propio de
  LinkedIn y de las páginas externas.
- `medir-destinos-linkedin` deja `limpiar_destino`, `familia_de` y la configuración `familias` (tarea 2.2 y
  3.1). La muestra con sesión confirmó el marcado de LinkedIn: externa con `a[href*="/safety/go"]` y el
  parámetro `url`, sencilla con el botón «Solicitud sencilla», cerrada y pausada por su texto.
- El radar ya lee `jobs-guest/jobs/api/jobPosting/{id}` sin sesión, y ese recurso distingue cerrada,
  sencilla y externa (sin la URL). Respeta el cooldown de `fuentes_estado`.
- El reconocimiento de los ATS (`docs/asistente/portales.md`, sección «LinkedIn») da las fuentes de esquema:
  `boards-api.greenhouse.io/v1/boards/{t}/jobs/{id}?questions=true`, `POST
  jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting`, `window.rendererData.form` de Typeform. Para
  Lever, el formulario viene en el HTML de `jobs.lever.co/{empresa}/{id}/apply` (no se reconoció en la
  muestra: se verifica en la tarea 3.3).
- La extensión ya tiene `https://*.linkedin.com/*` como permiso opcional y `INGRESO.linkedin`.

## Goals / Non-Goals

**Goals:**
- Que una vacante de LinkedIn abra **una sola vez** LinkedIn por usuario y vacante, y ninguna vez si otro
  usuario ya resolvió el destino.
- Que lo que el bot no puede o no debe hacer (cuenta, mensajería, OAuth) vaya al respaldo **sin abrir** la
  página cuando se puede saber por el dominio.

**Non-Goals:**
- Workday, SuccessFactors y los demás ATS con cuenta: solo respaldo. Un modo «el usuario inicia sesión y el
  bot sigue» queda para otro change, si la medición muestra que vale la pena.
- Escribir mensajes en LinkedIn (InMail, conexiones) o seguir empresas.
- Leer LinkedIn con la sesión del dueño en nombre de los invitados: cada usuario usa la suya.

## Decisions

### 1. Los requisitos que excluyen LinkedIn
`asistente-postulacion-telegram` y `conectar-plataformas-extension` (sin archivar) dicen que LinkedIn MUST NOT
habilitarse. Como esos requisitos todavía no están en `openspec/specs/`, este change no puede modificarlos
con un delta. La tarea 1.1 los reconcilia: si al aplicar ya están archivados, se añade aquí un delta
`MODIFIED` de `postulacion-automatica` («Plataformas con postulación automática ampliables por
habilitación») que quita la exclusión. Si no, se edita la exclusión en esos changes antes de archivarlos, con
una nota que remite a este change.

### 2. Flujo de una vacante de LinkedIn
1. Al tocar ⚡: aceptación del riesgo e interruptores (`nucleo.camino_automatico`). Si hay destino guardado en
   `destinos_linkedin` (por id de vacante, con menos de 7 días), el servidor confirma por `jobPosting/{id}`
   que sigue abierta (respetando el cooldown), clasifica el destino y, si su familia tiene lector, lee el
   esquema y pregunta lo que falte en la card **antes de encolar**.
2. Sin destino guardado, el trabajo empieza en `linkedin.com/jobs/view/{id}` con los pasos de
   `assets/asistente/selectores/linkedin.json`: sesión, sencilla/externa/cerrada/pausada y el enlace
   `/safety/go`.
3. Externa: `POST /postulaciones/{id}/destino` con la URL. El servidor limpia, guarda, clasifica y responde
   `respaldo` (motivo), `esperar_usuario` (esquema leído con datos faltantes) o `abrir` (URL, familia,
   esquema, receta y datos de la familia). La extensión navega la **misma pestaña** a la URL y entra a
   `bucleGenerico` con la plataforma `externa`.
4. Sencilla: pulsa «Solicitud sencilla» y entra a `bucleGenerico` con el contenedor fijado en el modal
   (`[role=dialog]` de la Solicitud sencilla, declarado en `linkedin.json`).

*Alternativa descartada:* resolver el destino en el servidor con la sesión del dueño. Mezcla cuentas, carga
todo el riesgo en la cuenta del dueño y LinkedIn ve un patrón de bot.

### 3. Plataforma «externa» en la extensión
`portales.js` suma `externa`: cualquier `https` con el permiso `https://*/*` concedido, salvo `PROHIBIDAS`,
ampliada con `/login`, `/signin`, `/sign-in`, `/register`, `/signup`, `/oauth`, `/authorize`, `/checkout`,
`/payment`, y una lista de hosts prohibidos (`accounts.google.com`, `login.microsoftonline.com`,
`appleid.apple.com`, `www.linkedin.com/oauth`, dominios de banca y pagos en `linkedin.json`). La regla de
salto: el host final debe ser el del destino, compartir su dominio registrable, o pertenecer a una familia de
ATS de `familias` (por ejemplo, el sitio propio que incrusta Greenhouse).

El permiso `https://*/*` va en `optional_host_permissions` y se pide con `chrome.permissions.request` desde el
popup, porque necesita un gesto del usuario. No se puede pedir desde el service worker.

### 4. Lectores de esquema (`asistente/esquemas_ats.py`)
Funciones puras de traducción (JSON o HTML → `list[Pregunta]` con `nombre`) separadas del cliente `httpx`
con `Ritmo` por dominio. Greenhouse: `input_text` → texto, `textarea` → texto largo, `input_file` → archivo,
`multi_value_single_select` → opciones, `multi_value_multi_select` → casillas; claves `first_name`,
`question_{id}`, etc. Ashby: `String`/`Email`/`Phone`/`LongText`/`File`/`Boolean`/`ValueSelect`/
`MultiValueSelect`/`Number`/`Date`/`Location`, clave = `path`. Typeform: `short_text`, `long_text`, `email`,
`phone_number`, `multiple_choice`, `file_upload`, `number`, `date`, `yes_no`; se ignoran `statement` y las
pantallas de bienvenida y de gracias; clave = id del campo. Si Typeform tiene `logic` (saltos), solo se
resuelven las preguntas y el bucle sigue el orden real. Los datos de familia (CV, enviar, éxito) van en
`assets/asistente/familias_ats.json`, versionado como los selectores.

### 5. Solicitud sencilla
`linkedin.json` declara el botón, el modal, los botones del modal y la confirmación, y se completa en el
reconocimiento con sesión (tarea 5.1, 👤). El CV sigue `cv.modo: perfil_multiple`: con autorización se sube
el adaptado, y si no, se elige el primero de la lista de LinkedIn. «Seguir a la empresa» se desmarca por
selector declarado.

### 6. Ritmo
`asistente.linkedin.tope_diario` (15) y `pausa_min_s` (240, con variación) se cuentan sobre las aperturas de
LinkedIn por usuario. Un destino guardado no cuenta, porque no abre LinkedIn. El aviso de seguridad de
LinkedIn (`/checkpoint/`, textos de verificación) se trata como barrera de LinkedIn: pausa de 24 h por usuario
(`linkedin_pausado_hasta`) y aviso.

### 7. Destinos compartidos
Tabla `destinos_linkedin(id_vacante, destino, familia, resuelto, ultima_vez)`. Solo guarda la URL limpia del
destino, que es pública (la misma para todos), nunca datos del usuario que la resolvió.

## Risks / Trade-offs

- [LinkedIn restringe cuentas] → riesgo aceptado por el dueño y por cada usuario. Para reducirlo: tope
  diario, pausas, una apertura por vacante, destinos compartidos, nunca pulsar «Solicitar» en externas y
  pausa de 24 h ante un aviso de seguridad.
- [El permiso amplio asusta o se usa mal] → es opcional, se pide solo a quien aceptó LinkedIn, y el motor
  sigue limitado por `PROHIBIDAS`, hosts prohibidos y la regla de salto. El popup explica para qué es.
- [Una página externa maliciosa] → el motor no ejecuta nada de la página. La IA solo devuelve índices y
  acciones cerradas, y nunca se escriben contraseñas ni se navega a URL de la IA.
- [Los lectores de esquema se rompen si un ATS cambia su API] → el motor genérico sigue sin esquema, y la
  métrica por familia lo muestra.
- [La Solicitud sencilla cambia a menudo] → selectores como datos, vigía diario en ensayo y reparación antes
  del envío.

## Migration Plan

1. Servidor con LinkedIn apagado (`plataformas.linkedin.automatica: false`): todo sigue en respaldo.
2. Extensión 1.3.0 con la plataforma `externa` y el permiso opcional. `version_minima` sube solo al activar
   el ensayo.
3. Ensayo del dueño (2 semanas), luego reales del dueño, luego invitados (aceptación del riesgo y política
   nueva).
4. Vuelta atrás: `plataformas.linkedin.automatica: false` devuelve todo LinkedIn al respaldo. Los
   destinos guardados no estorban.

## Open Questions

- El tope diario (15) y la pausa (240 s) se ajustan con lo que se vea en el ensayo.
- Si Pandapé después del correo pide contraseña, su dominio pasa a `familias_con_cuenta`. Se ve en el
  primer ensayo.
