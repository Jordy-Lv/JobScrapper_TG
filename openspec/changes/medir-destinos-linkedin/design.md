## Context

- LinkedIn es hoy un *non-goal* del asistente (`asistente-postulacion-telegram/design.md` y
  `conectar-plataformas-extension/design.md`) y la spec de `postulacion-automatica` lo manda siempre
  al paquete de respaldo. El dueño revirtió esa decisión el 2026-10-21: quiere automatizar la
  «Solicitud sencilla» y las solicitudes externas, para él y para los invitados, con envío final
  automático también en páginas que el bot no conoce.
- El radar ya lee LinkedIn sin sesión: `jobs-guest/jobs/api/jobPosting/{id}` para el detalle
  (`radar/fuentes/linkedin.py`) y registra los bloqueos en `fuentes_estado.cooldown_hasta`.
  `asistente/detalle.py` ya tiene `Ritmo` (pausa mínima por dominio), la lectura del cooldown y el
  cliente `httpx` con el `User-Agent` de `config.red`. `asistente/datos.py` tiene
  `abrir_vacantes_ro`.
- **No se sabe todavía** si las páginas públicas dicen qué tipo de solicitud tiene la vacante ni a
  dónde lleva. El fixture `tests/fixtures/detalle/linkedin.html` es un recorte de la descripción y
  no trae nada de la solicitud. Se cree que la página completa `/jobs/view/{id}` trae un bloque
  oculto con el enlace de solicitud externa, pero hay que comprobarlo (tarea 1).

## Goals / Non-Goals

**Goals:**
- Saber, con unas 100 vacantes reales, qué parte es Solicitud sencilla, qué parte es externa y cómo
  se reparten las externas por familia de ATS, y cuántas exigen cuenta propia.
- Dejar el clasificador de familias en código probado, reutilizable por el change de postulación.
- Registrar la decisión del dueño y su riesgo en `docs/asistente/portales.md`.

**Non-Goals:**
- Postular, llenar formularios o tocar la extensión. El ⚡ de LinkedIn sigue en respaldo.
- Usar la sesión de LinkedIn del dueño de forma automática. La única medición con sesión es el
  respaldo manual (tarea 5), hecha por el dueño con sus propias manos.
- Crear cuentas o escribir credenciales en los ATS.

## Decisions

### 1. Solo páginas públicas de invitado, una petición por vacante
Primero se usa el mismo recurso que el radar (`jobPosting/{id}`). Si no trae la solicitud, se usa
`/jobs/view/{id}`. Se elige **uno** de los dos en la tarea 1, según lo que muestre el
reconocimiento, para no duplicar peticiones. La URL externa se limpia: si LinkedIn la envuelve
(`externalApply/…?url=…`), se desenvuelve el parámetro `url` y se quitan `trk`, `refId`,
`trackingId` y los `utm_*`.

*Alternativa descartada:* seguir la redirección de `externalApply` haciendo la petición. Suma una
petición a LinkedIn por vacante, y el parámetro ya trae el destino.

### 2. Familias de ATS por patrón de dominio, en `config.yaml`
`asistente.medicion_linkedin.familias` es un mapa `familia → [patrones de host]`. Por ejemplo,
`workday: [myworkdayjobs.com, myworkdaysite.com]`, `greenhouse: [greenhouse.io]`,
`lever: [lever.co]`, `successfactors: [successfactors.com, jobs.sap.com]`, `gupy: [gupy.io]`,
`teamtailor: [teamtailor.com]`, `smartrecruiters: [smartrecruiters.com]`, `icims: [icims.com]`,
`taleo: [taleo.net]`, `bamboohr: [bamboohr.com]`, y los tres portales conectados. Coincide si el host
es el patrón o termina en `.patrón`. Sin coincidencia, la familia es `propio`. Una función pura,
`familia_de(url, familias)`, la usará también el change de postulación.

### 3. «Pide cuenta» por señales en la página de destino
Una petición GET al destino, con el `Ritmo` por dominio. `pide_cuenta` es verdadero si hay un
`input[type=password]` visible en el HTML o si el texto incluye señales configurables («crear
cuenta», «create account», «sign in to apply», «inicia sesión para postular»…). Es una heurística:
el resumen la presenta así. Los ATS que arman la página solo con JavaScript (Workday) pueden quedar
como `pide_cuenta: null` (desconocido). Para Workday se documenta que, según su comportamiento
conocido, pide cuenta por empresa, pero se marca como no verificado.

### 4. Ritmo y bloqueos como el radar
Antes de empezar se lee `fuentes_estado` de `linkedin` y, si hay cooldown vigente, no se pide nada.
Entre peticiones a LinkedIn hay una pausa con variación aleatoria (`pausa_s`, por defecto 8 s).
Un 429, un 999 o una página con desafío detiene todo. **No** se escribe el cooldown en `vacantes.db`:
la base se abre en solo lectura y el radar lo detectará en su propia corrida. Se avisa por consola
para no lanzar el radar justo después.

### 5. Resultado reanudable en JSON
`data/asistente/medicion_linkedin.json`, con un registro por clave de vacante. Si existe, se cargan
los resultados previos y solo se piden las vacantes que faltan. El resumen en Markdown se imprime y
se copia a mano a `portales.md`, sin títulos de vacantes ni empresas: solo conteos y dominios.

### 6. Dónde vive el código
`buscador_vacantes/asistente/medicion_linkedin.py`, con funciones puras (extraer solicitud, limpiar
URL, familia, señales de cuenta, resumen) separadas del bucle `async` que hace las peticiones.
Subcomando `asistente medir-linkedin [--muestra N] [--salida RUTA]` en `asistente/cli.py`. Va en el
asistente y no en el radar porque prepara la postulación y reutiliza `Ritmo` y `abrir_vacantes_ro`.

## Risks / Trade-offs

- [Las páginas públicas no muestran el tipo de solicitud] → la tarea 1 lo comprueba antes de escribir
  código. Si no lo muestran, el código se reduce a clasificar URLs y la medición la hace el dueño a
  mano (tarea 5) sobre unas 30 vacantes.
- [La medición dispara un bloqueo de LinkedIn que afecta al radar] → la muestra es pequeña, hay pausa
  de 8 s, se corta al primer bloqueo y se corre fuera del horario del radar.
- [Riesgo de cuenta en el change siguiente] → las condiciones de LinkedIn (sección 8.2) prohíben bots
  y extensiones que automaticen acciones. Automatizar la Solicitud sencilla puede llevar a que
  LinkedIn restrinja la cuenta del dueño y la de los invitados. Aquí solo se documenta: el change de
  postulación debe pedir a cada invitado una aceptación expresa de ese riesgo (por ejemplo, subiendo
  la versión de la autorización) y permitir apagar LinkedIn por usuario.
- [Heurística de «pide cuenta» imprecisa] → se reporta como estimación, con `null` cuando no se puede
  saber. El reconocimiento de cada familia en el change siguiente la confirma.

## Open Questions

- ¿Qué recurso público trae la solicitud: `jobPosting/{id}` o `/jobs/view/{id}`? (tarea 1)
- ¿La página pública distingue «Solicitud sencilla» de una vacante cerrada?

### Hallazgos de la tarea 1.1 (2026-10-21)

Reconocimiento sin sesión desde el PC Windows, con el `User-Agent` y el `Accept-Language` de
`config.red`, una petición cada ~8 s y sin seguir redirecciones. Diez vacantes de `vacantes.db`
para `jobPosting/{id}` y cuatro para `/jobs/view/{id}`. Ningún 429 ni 999. El navegador integrado,
sin sesión, muestra lo mismo (por ejemplo, la vacante sin botón no tiene «Solicitar» a la vista).

| Caso (vacantes) | Marcado en `jobPosting/{id}` | `/jobs/view/{id}` | ¿URL de destino? |
|---|---|---|---|
| En LinkedIn, que se toma por Solicitud sencilla (4292039131, 4264876204) | `<button class="apply-button apply-button--default …" data-tracking-control-name="public_jobs_apply-link-onsite">Solicitar` | 200, el mismo marcado | No aplica |
| Externa (4477307684, 4479214936, 4476600479, 4479059847) | `<button class="sign-up-modal__outlet …" data-modal="job-details-topcard-apply-modal">Solicitar` con el ícono `apply-button__offsite-apply-icon-svg` y el modal `contextual-sign-in-modal` con `data-impression-id="public_jobs_apply-link-offsite_contextual-sign-in-modal"` | 200 (~300 KB), el mismo marcado | **No**: ni `code#applyUrl` ni `externalApply` ni un host fuera de LinkedIn. El botón abre el modal de inicio de sesión |
| Cerrada (4458389254, 4460595981, 4479146592) | `<figcaption class="closed-job__flavor--closed">Ya no se aceptan solicitudes</figcaption>` y sin botón | **301** a `…/jobs/…-empleos?trk=expired_jd_redirect` | No |
| Sin botón y sin aviso de cierre (4479099142) | `div.top-card-layout__cta-container` vacío (solo `<!---->`) | 200, tampoco hay botón | No: `desconocido` |

Respuestas:

- **Tipo de solicitud: sí lo trae `jobPosting/{id}`**, el mismo recurso que ya usa el radar, unas 7
  veces más liviano que `/jobs/view/{id}`. Los marcadores son `public_jobs_apply-link-onsite`
  (sencilla), `public_jobs_apply-link-offsite` (externa) y `closed-job__flavor--closed` (cerrada). El
  botón dice «Solicitar» en los dos primeros casos. Que `onsite` sea la Solicitud sencilla es una
  inferencia, porque sin sesión LinkedIn no muestra la etiqueta «Solicitud sencilla». La muestra
  manual del dueño (tarea 5.1) la confirma.
- **El enlace externo no está en ningún recurso público.** Sin sesión, «Solicitar» abre el modal de
  inicio de sesión. La URL de destino, la familia de ATS y «pide cuenta» solo se pueden medir con
  la muestra manual del dueño (grupo 5).
- **Sí distingue Solicitud sencilla de cerrada**: la cerrada trae `closed-job` y no tiene botón.
  Una vacante reciente (4479146592, vista el 15 de octubre) ya estaba cerrada.
- Hay un cuarto caso: una vacante abierta sin botón ni aviso, que queda como `desconocido`. Con
  sesión resultó estar pausada (ver abajo).

### Muestra con sesión del dueño (tarea 5.1, 2026-10-21)

El dueño aceptó el riesgo para su cuenta y pidió que la muestra de la tarea 5.1 se hiciera con su
sesión en Chrome, en vez de a mano. Se recorrieron las 30 vacantes de LinkedIn enviadas al canal
más recientemente (del 12 al 15 de octubre), una cada ~8 s. Solo se leyó el DOM: no se pulsó
«Solicitar» ni se abrió ningún destino. La hoja quedó en `data/medicion_linkedin_manual.csv`, fuera
de git.

Marcado con sesión:

- Externa: `a[href*="/safety/go"]` con el texto «Solicitar en el sitio web de la empresa». El
  destino real viene en el parámetro `url` de ese enlace, así que no hace falta pulsar.
- Solicitud sencilla: `button` con el texto «Solicitud sencilla». Esto confirma que `onsite` es
  Solicitud sencilla.
- Cerrada: «Ya no se aceptan solicitudes». **Pausada** (un caso nuevo): «No se aceptan solicitudes en
  estos momentos», con el botón oculto. En las dos, «Respuestas gestionadas fuera de LinkedIn» indica
  que la solicitud era externa.

| Tipo | Vacantes | % |
|---|---|---|
| externa | 11 | 37 % |
| cerrada | 9 | 30 % |
| pausada | 6 | 20 % |
| sencilla | 4 | 13 % |

- De las 15 abiertas, 11 son externas (73 %) y 4 son sencillas (27 %). De las 15 cerradas o
  pausadas, 9 eran externas. Al menos 20 de las 30 (67 %) eran externas.
- **La mitad ya no recibía solicitudes** entre 6 y 9 días después de llegar al canal.
- Familias de las 11 externas: Greenhouse 4 (3 por el enlace corto `grnh.se` y 1 por
  `job-boards.greenhouse.io`), Workday 2 (`wd12`, `wd501`), Computrabajo 1 (Pandapé,
  `*.pandape.computrabajo.com`), Ashby 1 (`jobs.ashbyhq.com`), Typeform 1, sitio propio 1
  (`careers.holcimgroup.com`, que parece SuccessFactors, sin verificar) y un acortador 1
  (`ai-job.link`, sin resolver).
- Para `familias`: falta `ashby: [ashbyhq.com]`, hay que añadir `grnh.se` a Greenhouse y los
  acortadores necesitan seguir la redirección. Typeform es un formulario, no un ATS.
- «Pide cuenta» no se midió, porque no se abrió ningún destino.
