# Notas sobre el código de Hermes

Insumos copiados del PC Fedora (`/home/ByLOGAN/.hermes/cron/`) para la tarea 1.2. Son solo
referencia: no se ejecutan ni se copian tal cual al buscador nuevo.

## Inventario

| Archivo | Qué hace |
|---|---|
| `scrape_jobs.py` | Pre-run principal: LinkedIn, Computrabajo, elempleo, RemoteOK, Magneto y GetOnBoard; dedupe contra el historial; prioridad 0–100. |
| `scrape_jobs_extended.py` | Variante más grande del anterior, con filtros más estrictos (`is_valid_job`) y prioridad textual. |
| `scrape_jobs_multifuente.py` | elempleo por JSON-LD, RemoteOK y GetOnBoard. |
| `parse_fuentes_secundarias.py` | Parsea HTML ya descargado de elempleo, RemoteOK y GetOnBoard; Magneto devuelve `[]` (nunca funcionó). Tiene un set `KNOWN` de ids escrito a mano. |
| `fetch_jobs.py` | Prueba suelta de LinkedIn con `f_WT` (modalidad) y salida TSV. |
| `scrape_elempleo.py` | Parsea `/tmp/elempleo.html` con `data-ga4-offerdata`. |
| `send_encabezado.py` | Pre-run que envía el banner con `hermes send` en **cada** corrida. |
| `encabezado_vacantes.jpg` | Banner (1280×426). Copiado a `assets/encabezado_vacantes.jpg`. |
| `historial_vacantes.json` | Historial de vacantes enviadas (354 registros). |
| `prompt_cronjob_d6381ce58395.txt` | Prompt del LLM: solo formatea el JSON del pre-run. |

## Flujo actual de Hermes

1. `send_encabezado.py` envía el banner siempre, haya o no vacantes.
2. Un `scrape_jobs*.py` busca con `curl`, filtra, deduplica, **escribe el historial antes de
   enviar** y entrega un JSON con `cat1_practicas` y `cat2_devops`.
3. DeepSeek formatea ese JSON según el prompt (texto plano, 7 líneas por ficha, "💰 No
   especificado", "📅 Reciente", emoji aleatorio, cierre con recomendación). Sin vacantes
   responde `[SILENT]`.

Consecuencias: si el envío falla, las vacantes ya quedaron en el historial y se pierden; y el
perfil está sesgado a desarrollo Java/Spring y DevOps, con prioridad a Cartagena y remoto.

## Fuentes, endpoints y selectores

### LinkedIn (guest API, HTML)
- URL: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=<kw>&location=<Colombia|Cartagena>&f_TPR=<r259200|r604800>&start=0&count=<15-25>`.
- Filtros usados: `f_WT=1` presencial, `f_WT=2` remoto, `f_WT=3` híbrido; `f_TPR` de 3 o 7 días.
  No usaba `f_E` (nivel de experiencia).
- Tarjeta: `div.base-search-card` con `data-entity-urn="urn:li:jobPosting:<id>"`.
- Título: `h3.base-search-card__title` (alternativa: `span.sr-only`).
- Empresa: `h4.base-search-card__subtitle a` (también `a.hidden-nested-link`).
- Ubicación: `span.job-search-card__location`.
- Fecha: `time[datetime]` en formato `AAAA-MM-DD`.
- URL canónica: `https://co.linkedin.com/jobs/view/<id>`; el `href` real trae un slug y termina en el id.
- Id nativo: el número de `urn:li:jobPosting`.

### Computrabajo (HTML)
- URL: `https://www.computrabajo.com.co/trabajo-de-<slug>?pubdate=3` (slug con guiones, p. ej.
  `practicante-desarrollo`). En el historial también aparecen `co.computrabajo.com` y
  `co.computrabajo.com.co`: el dominio cambió; hay que validarlo en la tarea 8.2.
- Solo extraía enlaces `href="/ofertas-de-trabajo/oferta-de-trabajo-de-<titulo>-en-<ciudad>-<ID>"`.
  Título y ciudad salían del slug y la empresa quedaba "Por determinar": no parseaba las tarjetas.
- Id nativo: hexadecimal de 32 caracteres al final de la URL (en mayúsculas).

### elempleo (HTML)
- URL: `https://www.elempleo.com/co/ofertas-empleo/?busqueda=<kw>&modalidad=remoto&pagina=1`.
- Mejor fuente de datos: atributo `data-ga4-offerdata` (JSON con entidades HTML) en el div
  `col-md-12 p-0 js-area-bind area-bind`, junto a `data-url`. Campos: `id`, `title`, `company`,
  `location`, `salary`, `tags`.
- Alternativa: bloque JSON-LD `@type: ItemList` con `itemListElement[].item.@id`.
- Clases antiguas (respaldo): `js-offer-title`, `js-offer-company`, `info-city`.
- URL de oferta: `https://www.elempleo.com/co/ofertas-trabajo/<slug>-<id>`; id nativo: número final.
- La modalidad remota se infería buscando "Remoto" cerca del id en el HTML.

### Magneto (HTML)
- URL: `https://www.magnetoempleos.com.co/busqueda/?q=<kw>&page=1`, enlaces `href="/empleo/..."`.
- Títulos tomados de cualquier `h2`/`h3` por posición: frágil. `parse_mag` devuelve `[]`.
  Hermes nunca obtuvo vacantes útiles de Magneto: hay que investigarla desde cero (tarea 8.4).

### GetOnBoard (API JSON)
- `https://www.getonbrd.com/api/v0/search/jobs?query=junior+java+spring&per_page=20`.
- Usaba `attributes.slug`, que no existe: las URLs quedaban vacías. El slug es `data[].id` y la
  URL pública está en `links.public_url` (ya corregido en `fuentes/getonboard.py`).

### RemoteOK (API JSON)
- `https://remoteok.com/api`. Fuera de alcance por decisión del usuario (remoto internacional).

## Palabras clave que usaba Hermes

- LinkedIn: java junior, spring boot junior, junior desarrollador (Cartagena), entry level software
  developer, aprendiz desarrollo software, practicante desarrollo, junior frontend react, full stack
  junior, junior backend, sin experiencia desarrollador, trainee java; y en `fetch_jobs.py`:
  aprendiz/practicante + remoto/híbrido/presencial + desarrollo/software/sistemas/Cartagena.
- Computrabajo: desarrollador-junior, aprendiz-desarrollo-de-software, practicante-desarrollo,
  java-junior, programador-junior, full-stack-junior.
- elempleo y Magneto: "desarrollador junior" remoto. GetOnBoard: "junior java spring".

Todas están cubiertas por el núcleo o la cola larga de `config.yaml`.

## Filtros de Hermes

- Seniority (título): `senior`, `sr.`, `líder`/`lider`, `arquitecto`, `architect`, `tech lead`,
  `manager`, `director`, `head of`, `principal`, `staff`, `lead`, `semi senior`, `mid level`, y
  "N años de experiencia" desde 2 años.
- No TI (título): contador/contable, financiero, administrativo, secretario, ventas/comercial,
  marketing, community manager, conductor/chofer, mensajero/domiciliario, enfermero/médico/
  odontólogo, abogado/jurídico/legal, docente/profesor, cajero/vendedor, operario, producción,
  vigilante, recepcionista, mesero/cocinero, diseñador gráfico, logística, gestión/talento humano,
  SST/salud ocupacional, ambiental, comunicaciones, auditoría, capacitación, maquillaje/estética,
  alimentos/nutrición.
- "Analista" sin TI: procesos, negocio, financiero, contable, compras, inventarios, logística,
  calidad, crédito.
- Practicante/aprendiz sin contexto técnico → rechazo.
- Ubicación: prioriza remoto, Colombia y Cartagena; no rechaza otras ciudades colombianas.

Candidatos para `areas_no_ti` en la tarea 5.1: operario, vigilante, recepcionista, secretario,
mensajero, domiciliario, médico, odontólogo, esteticista, maquillaje, nutrición, alimentos.
Ojo: Hermes trataba `seguridad` y `seguridad de la información` como no TI; en el buscador nuevo
la ciberseguridad **sí** está en alcance.

## Historial (`historial_vacantes.json`)

- Ruta en Fedora: `~/.hermes/cron/output/historial_vacantes.json`.
- Estructura: `{"vacantes": [ {...}, ... ]}` con **354** registros (la spec estimaba ~309).
  Rango de `descubierto_en`: hasta 2026-09-01.
- Campos comunes: `cargo`, `empresa`, `ciudad`, `url`, `raw_job_id`, `fuente`, `fecha`. Otros
  varían según el script (`modalidad`, `salario`, `prioridad`, `categoria`, `descubierto_en`,
  `fecha_descubrimiento`…).
- Clave de dedupe de Hermes: `raw_job_id`, cualquier número de 6+ dígitos de la URL y
  `key:<empresa>|<cargo>` en minúsculas.
- `raw_job_id` es inconsistente: `ct-<HEX>`, `li-<num>`, número suelto de LinkedIn, `<HEX>` suelto
  de Computrabajo, `elempleo-<num>` o `elempleo-<slug>-<num>`, `rok-<num>`, `gob-<slug>`.
- Dominios de `url`: co.linkedin.com (135), www.computrabajo.com.co (115), www.linkedin.com (58),
  co.computrabajo.com (20), www.elempleo.com (17), remoteok.com (6), www.getonbrd.com (1),
  co.computrabajo.com.co (1) y 1 sin URL (`gob-…`).

### Regla de migración (tarea 3.4)
La clave del buscador nuevo es `fuente:id_nativo`, así que se deriva de la URL (no de
`raw_job_id`) y cada fuente nueva debe producir el mismo id:

| Dominio | Clave |
|---|---|
| `*linkedin.com` | `linkedin:<número final de la ruta>` |
| `*computrabajo.com*` | `computrabajo:<HEX de 32 al final, en mayúsculas>` |
| `elempleo.com` | `elempleo:<número final>` |
| `getonbrd.com` | `getonboard:<slug tras /jobs/>` |
| `remoteok.com` | `remoteok:<número final>` |
| sin URL | según el prefijo de `raw_job_id` (`gob-` → `getonboard:`), o `hermes:<raw_job_id>` |

Además se guarda la huella de `cargo` + `empresa`, que cubre el cruce entre fuentes.

## Telegram

- Canal: `-1004429829042`.
- `send_encabezado.py` usa `hermes send -t telegram:<chat> "MEDIA:<ruta>"` con un reintento y
  nunca falla el cron. La imagen está en `/home/ByLOGAN/.hermes/cron/media/encabezado_vacantes.jpg`.
- Bot de Hermes: `@Jobs_Practicas_Bot` (id 8859411567). El token está en el `.env` de Hermes
  (variable `TELEGRAM_BOT_TOKEN`; usuarios autorizados en `TELEGRAM_ALLOWED_USERS`). El valor
  no se copia aquí.
- Verificado el 2026-10-04 con la Bot API: `getMe` responde; `getChat -1004429829042` es el
  canal "👨🏼‍💻JOBS - PRACTICAS/APRENDIZ" y el bot es administrador con permiso de publicar;
  `getChat 5051574309` es el chat privado de @ByLOGAN, que se usa como chat de prueba.
- Envío real al chat de prueba: banner (sendPhoto), mensaje HTML de vacantes, incidente
  simulado con diagnóstico IA y resumen diario, todos aceptados por Telegram.
- Pendiente en el PC Fedora: confirmar la ruta absoluta del `.env` de Hermes (se asume
  `~/.hermes/.env`, ver `telegram.token_hermes` en `config.yaml`) y revisar `hermes send --help`
  (HTML, vista previa, longitud máxima) por si hiciera falta el modo de respaldo `hermes_cli`.
