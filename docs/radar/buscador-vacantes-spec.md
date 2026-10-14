# Buscador de Vacantes → Telegram (sin LLM)

> Documento de especificación para Claude Code. Antes de escribir código, lee la sección **0. Antes de empezar** y resuelve las preguntas abiertas con el usuario.

## Objetivo

Reemplazar el cronjob de Hermes **"Buscador Empleo Carlos Mario"** (`job_id: d6381ce58395`), que hoy usa un agente LLM (DeepSeek) para scrapear, por un **script Python determinista** que:

1. Corra **cada 30 minutos**.
2. Busque vacantes de **prácticas / aprendiz / junior TI** en Colombia y remoto, con un abanico amplio de palabras clave.
3. Filtre, deduplique y envíe **solo las vacantes nuevas** al canal de Telegram `-1004429829042` (canal "JOBS - PRACTICAS/APRENDIZ").
4. Tenga **costo casi cero**: el scraping, el filtrado y el envío **no usan LLM**. DeepSeek solo se invoca como **Reportero IA de incidentes** (sección 6B), cuando el script detecta un bloqueo o una falla.
5. Minimice el riesgo de rate limit y bloqueos (ver sección 6).

## Contexto del entorno actual

- Servidor: `/home/ByLOGAN/`
- Directorio de Hermes cron: `/home/ByLOGAN/.hermes/cron/`
- Archivos existentes relevantes:
  - `scrape_jobs.py` (~24 KB): scraper con filtros y prioridad, **hoy no se usa**. Revisarlo y reutilizar lo que sirva.
  - `send_encabezado.py`: envía el banner `encabezado_vacantes.jpg` con `hermes send -t telegram:-1004429829042 "MEDIA:..."`.
  - `historial_vacantes.json`: ~309 vacantes ya enviadas (usado para deduplicar).
  - Existen scripts sueltos para El Empleo, Magneto, RemoteOK y GetOnBoard (no se usan).
- Categorías actuales del reporte: **Prácticas y Aprendizaje** y **DevOps / Cloud (hasta junior)**.

---

## 0. Antes de empezar

### 0.1 Inspección obligatoria (no asumir)

1. Leer completo `scrape_jobs.py` y los scripts de fuentes adicionales. Listar qué fuentes, queries y filtros tienen.
2. Leer el prompt actual del cronjob de Hermes para extraer: palabras clave, ubicaciones, criterios de exclusión y formato de fichas.
3. Revisar la estructura de `historial_vacantes.json` (qué campos usa como clave).
4. Determinar cómo enviar a Telegram, en este orden de preferencia:
   - **a)** Bot API directa (`https://api.telegram.org/bot<TOKEN>/sendMessage`) si existe el token del bot de Hermes en su configuración (`.env` o config de Hermes). Es la opción más simple y controlable (parse_mode HTML, `disable_web_page_preview`, `disable_notification`).
   - **b)** `hermes send -t telegram:-1004429829042 "..."` si no hay token accesible. Verificar si soporta HTML/Markdown y mensajes largos.
5. Verificar si Hermes soporta jobs sin agente (`no_agent=True` o equivalente). Si no, usar **crontab del sistema**.

### 0.2 Preguntas para el usuario (hacerlas antes de implementar)

- ¿Ubicaciones objetivo? Propuesta por defecto: **Colombia (todas las ciudades) + remoto**. ¿Priorizar alguna ciudad (Bogotá, Cartagena, Medellín…)?
- ¿Se incluye remoto internacional (vacantes en inglés) o solo LATAM/Colombia en español?
- ¿Horario silencioso? Propuesta: entre 22:00 y 06:00 (hora Colombia) enviar con `disable_notification=true` o acumular para el primer envío de la mañana.
- ¿Se mantiene la categoría DevOps/Cloud junior además de prácticas?
- ¿El Reportero IA usa la misma API key de DeepSeek que Hermes o una key separada? Se recomienda **separada**, para medir su consumo aparte.
- ¿Quiere además un **resumen diario de salud** generado por el Reportero IA (1 llamada/día), o solo reportes cuando hay incidentes?

---

## 1. Arquitectura

```
crontab (*/30) → flock → buscador.py
   ├─ 1. Cargar estado (SQLite): vistos, cooldowns, posición de rotación
   ├─ 2. Elegir lote de (fuente, keyword) según rotación y presupuesto por fuente
   ├─ 3. Scrapear cada par con requests + backoff
   ├─ 4. Normalizar → modelo Vacante
   ├─ 5. Filtrar (nivel + relevancia TI + exclusiones + antigüedad)
   ├─ 6. Deduplicar (id por fuente + huella título/empresa entre fuentes)
   ├─ 7. Clasificar en categoría
   ├─ 8. 0 nuevas → terminar en silencio
   │     N nuevas → formatear y enviar a Telegram
   ├─ 9. Guardar estado + log
   └─ 10. ¿Detector de incidentes disparó? (reglas deterministas)
          ├─ No → fin
          └─ Sí → reportero.py → DeepSeek (1 llamada, sin tools)
                    → diagnóstico + recomendación → mismo canal de Telegram
```

El Reportero IA corre **después** del envío de vacantes y en un bloque `try/except` aislado: si DeepSeek falla o no hay saldo, las vacantes ya se enviaron igual.

### Estructura de archivos sugerida

```
/home/ByLOGAN/buscador-vacantes/
├── buscador.py           # entrypoint
├── config.yaml           # keywords, ubicaciones, filtros, presupuestos por fuente
├── fuentes/
│   ├── base.py           # clase Fuente: fetch con backoff, user-agent, cooldown
│   ├── linkedin.py
│   ├── computrabajo.py
│   ├── elempleo.py
│   ├── magneto.py
│   ├── getonboard.py
│   └── ...               # una por fuente
├── filtros.py
├── formato.py            # fichas de Telegram
├── telegram.py
├── estado.py             # SQLite
├── incidentes.py         # detector determinista de incidentes
├── reportero.py          # Reportero IA (DeepSeek), solo diagnóstico
├── data/
│   ├── vacantes.db
│   └── encabezado_vacantes.jpg
├── logs/
└── tests/
```

Todo lo configurable (keywords, exclusiones, presupuestos, horarios) va en `config.yaml`, no en el código.

### Modelo `Vacante`

```python
@dataclass
class Vacante:
    fuente: str          # "linkedin", "computrabajo", ...
    id_fuente: str       # id nativo de la fuente
    titulo: str
    empresa: str
    ubicacion: str | None
    modalidad: str | None   # Presencial / Híbrido / Remoto
    salario: str | None
    publicada: datetime | None
    url: str
    keyword: str         # keyword que la encontró (para métricas)
    categoria: str | None = None
```

---

## 2. Fuentes

Implementar cada fuente como módulo independiente. **Probar cada una manualmente antes de activarla** y desactivar (con flag en `config.yaml`) las que fallen o bloqueen.

| Fuente | Método esperado | Notas |
|---|---|---|
| LinkedIn | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=...&location=Colombia&f_TPR=r86400&start=0` (HTML) | La más propensa a bloquear (HTTP 429/999). Presupuesto bajo por corrida. Usar `f_TPR=r86400` (últimas 24h). |
| Computrabajo | HTML de `co.computrabajo.com` | Verificar selectores actuales; cambian seguido. |
| elempleo.com | HTML o endpoint JSON interno | Revisar script existente. |
| Magneto365 | Endpoint JSON interno si existe | Revisar script existente. |
| GetOnBoard | API pública `https://www.getonbrd.com/api/v0/search/jobs?query=...` | Verificar que siga vigente. Filtrar por nivel `no_experience` / `junior`. |
| Agencia Pública de Empleo SENA | `agenciapublicadeempleo.sena.edu.co` | Fuente clave para aprendices. **Verificar viabilidad**: si exige login o captcha, descartar y avisar al usuario. |
| Torre.ai | API de búsqueda pública | Opcional; verificar. |
| RemoteOK | `https://remoteok.com/api` | Solo si el usuario quiere remoto internacional. |

**No incluir** Indeed ni Glassdoor: bloquean con Cloudflare y no vale la pena el esfuerzo.

Si una fuente requiere evadir captchas o protecciones anti-bot, **no implementarla**: descartarla y reportarlo.

---

## 3. Palabras clave

Agruparlas en `config.yaml`. La rotación (sección 6) recorre todas, así que la lista puede ser amplia sin aumentar requests por corrida.

### 3.1 Nivel práctica / aprendiz
```
practicante, practicante sistemas, practicante desarrollo, practicante TI,
prácticas profesionales, práctica profesional ingeniería de sistemas,
pasante, pasantía, aprendiz, aprendiz SENA, aprendiz sistemas,
aprendiz desarrollo de software, contrato de aprendizaje, etapa productiva,
etapa práctica, estudiante ingeniería de sistemas, tecnólogo desarrollo de software,
tecnólogo en sistemas, trainee, trainee desarrollo, semillero, programa de talento,
intern, internship, becario
```

### 3.2 Junior / entrada
```
desarrollador junior, programador junior, desarrollador trainee,
auxiliar de sistemas, auxiliar TI, auxiliar de soporte, soporte técnico junior,
mesa de ayuda, analista junior TI, analista de datos junior, QA junior, tester junior,
desarrollador backend junior, desarrollador Java junior, desarrollador web junior,
junior developer, entry level developer
```

### 3.3 DevOps / Cloud junior
```
DevOps junior, cloud junior, analista cloud junior, CloudOps, SysOps,
infraestructura TI junior, analista de infraestructura junior,
administrador de sistemas junior, soporte cloud, AWS junior, Azure junior
```

---

## 4. Filtros

Aplicar en este orden, sobre título (y descripción si la fuente la trae sin request extra):

1. **Exclusión de seniority** (descartar): `senior, sr, sr., semi senior, ssr, lead, líder, lider, gerente, manager, director, jefe, arquitecto, architect, head, coordinador, especialista, "5 años", "4 años", "3 años"`.
2. **Relevancia TI** (obligatoria): el título o la descripción debe contener al menos un término técnico: `sistemas, software, desarrollo, desarrollador, programador, TI, IT, tecnología, datos, data, cloud, devops, sysops, infraestructura, soporte, redes, QA, testing, web, backend, frontend, java, python, base de datos, ciberseguridad, automatización`. Esto evita "practicante contable", "aprendiz de cocina", etc.
3. **Antigüedad**: descartar vacantes con fecha de publicación > 15 días (si la fuente la expone).
4. **Ubicación**: según la respuesta del usuario en 0.2.
5. Todo normalizado: minúsculas, sin tildes, con límites de palabra (`\bsr\b`) para no descartar falsos positivos.

Registrar en el log cuántas vacantes descarta cada filtro (para ajustar si llegan pocas).

---

## 5. Deduplicación y estado (SQLite)

Migrar de `historial_vacantes.json` a SQLite (`data/vacantes.db`), porque con corridas cada 30 min el JSON crece y se reescribe completo en cada ejecución.

Tablas:
- `vistas(clave PRIMARY KEY, huella, fuente, titulo, empresa, url, primera_vez, enviada)`
  - `clave` = `f"{fuente}:{id_fuente}"`
  - `huella` = hash de `titulo_normalizado + empresa_normalizada` → evita enviar la misma vacante publicada en LinkedIn y en Computrabajo.
- `fuentes_estado(fuente PRIMARY KEY, cooldown_hasta, fallos_consecutivos, ultimo_exito)`
- `rotacion(fuente PRIMARY KEY, indice_keyword)`

Reglas:
- **Migración**: importar las 309 entradas de `historial_vacantes.json` como ya enviadas.
- **Primera corrida (seed)**: marcar todo lo encontrado como visto **sin enviarlo**, para no inundar el canal. Flag `--seed`.
- **Limpieza**: borrar registros con más de 90 días.

---

## 6. Rate limit y bloqueos

No se puede garantizar "cero rate limit" scrapeando sitios de terceros cada 30 minutos. El diseño debe **minimizar requests por corrida** y **recuperarse solo** cuando una fuente bloquea:

1. **Rotación de keywords**: cada corrida procesa solo un lote pequeño de keywords por fuente y avanza el índice en `rotacion`. Con ~60 keywords y 3 por corrida en LinkedIn, el ciclo completo dura ~10 horas, lo cual basta porque las vacantes de práctica no cambian minuto a minuto.
2. **Presupuesto por fuente y corrida** (en `config.yaml`), punto de partida:
   - LinkedIn: 3 requests
   - Computrabajo: 4
   - elempleo / Magneto / SENA: 3 cada una
   - APIs públicas (GetOnBoard, Torre): 5
3. **Pausa aleatoria** de 4–10 s entre requests a la misma fuente.
4. **User-Agent** de navegador real, cabeceras `Accept-Language: es-CO`. Una sola `requests.Session` por fuente. Sin proxies.
5. **Backoff**: ante HTTP 429, 999 o 403 → poner la fuente en `cooldown` 2 h; si se repite, 6 h; luego 24 h. Resetear al primer éxito.
6. **Alertas**: las gestiona el detector de incidentes y el Reportero IA (sección 6B). Se envían al **mismo canal de Telegram** de las vacantes (`-1004429829042`).
7. **Timeout** de 20 s por request; una fuente que falla no detiene a las demás.
8. **flock** para evitar que dos corridas se solapen.

---

## 6B. Reportero IA de incidentes (DeepSeek)

### Rol

DeepSeek actúa como **analista**, no como operador. Recibe la evidencia de un incidente, explica la causa probable y recomienda qué hacer. **Nunca**:
- modifica código ni `config.yaml`,
- reintenta requests ni cambia cooldowns,
- intenta evadir bloqueos, captchas o protecciones anti-bot.

La **detección** es determinista (código Python). El LLM solo interpreta lo que el detector ya encontró.

### Disparadores (en `incidentes.py`)

| Tipo | Regla |
|---|---|
| `bloqueo` | HTTP 429, 999 o 403 en 2 corridas seguidas de la misma fuente, o cuando el cooldown escala a 6 h o más. |
| `captcha` | HTTP 200 pero el body contiene marcadores de desafío (`captcha`, `cf-chl`, `challenge`, `are you a robot`, `unusual traffic`). |
| `cambio_html` | HTTP 200 con body normal, pero el parser extrae 0 elementos o lanza excepción. Señal típica de que el sitio cambió su estructura. |
| `sin_resultados` | 0 vacantes crudas en 24 h en una fuente que en los últimos 7 días traía resultados. |
| `caida_volumen` | Volumen de 24 h < 30 % del promedio diario de los últimos 7 días. |
| `error_servidor` | HTTP 5xx o timeouts en 3 corridas seguidas. |
| `fallo_envio` | Telegram rechaza un mensaje (parse error, chat no encontrado, etc.). |

### Control de ruido

- Un incidente = `fuente + tipo`. Se guarda en SQLite (tabla `incidentes(id, fuente, tipo, abierto_desde, ultimo_reporte, cerrado_en)`).
- Mientras el incidente siga abierto **no se vuelve a llamar a DeepSeek**. Como máximo un recordatorio cada 24 h, en texto plano y sin LLM.
- Cuando la fuente se recupera: cerrar el incidente y enviar un aviso corto "✅ LinkedIn se recuperó tras 5 h", **sin LLM**.
- Si en la misma corrida se abren varios incidentes, agruparlos en **una sola llamada**.

### Evidencia que recibe el LLM (payload)

```json
{
  "fuente": "linkedin",
  "tipo": "bloqueo",
  "abierto_desde": "2026-10-04T10:30:00-05:00",
  "intentos_recientes": [
    {"ts": "...", "url": "https://www.linkedin.com/jobs-guest/...", "status": 429, "ms": 812, "items": 0}
  ],
  "headers_respuesta": {"retry-after": "3600", "server": "...", "content-type": "..."},
  "body_muestra": "primeros 3000 caracteres del body, sin scripts ni estilos",
  "selectores_parser": ["div.base-search-card", "h3.base-search-card__title"],
  "volumen_7_dias": [42, 38, 40, 35, 41, 12, 0],
  "cooldown_actual": "6h",
  "presupuesto_requests": 3,
  "otras_fuentes_ok": ["computrabajo", "getonboard"]
}
```

Sanitización obligatoria antes de enviar: **nunca** incluir tokens, API keys, cookies, variables de entorno ni el chat id. De los headers solo se pasan los de la lista blanca (`retry-after`, `server`, `content-type`, `cf-ray`, `x-ratelimit-*`).

### Llamada a DeepSeek

- API directa (`https://api.deepseek.com/chat/completions`), **no** a través del agente Hermes. Sin tools, sin system prompt de Hermes.
- `model: deepseek-chat`, `temperature: 0.2`, `max_tokens: 700`, `response_format: {"type": "json_object"}`.
- Key desde variable de entorno `DEEPSEEK_API_KEY` (archivo `.env` con permisos 600).
- Timeout 60 s, sin reintentos automáticos.

System prompt (fijo, en `config.yaml`):

```
Eres un analista de incidentes de un scraper de vacantes de empleo.
Recibes evidencia técnica de una fuente que falló. Responde SOLO con un JSON:
{
  "severidad": "baja | media | alta",
  "causa_probable": "1-2 frases",
  "evidencia_clave": "qué dato del payload lo demuestra",
  "accion_recomendada": "qué debe hacer el administrador, concreto",
  "requiere_intervencion": true | false,
  "sugerencia_tecnica": "si es cambio de HTML, propone selectores nuevos basados en body_muestra; si no aplica, null"
}
Reglas: no inventes datos que no estén en el payload. Si la evidencia no alcanza
para concluir, dilo en causa_probable. Nunca recomiendes evadir captchas,
rotar proxies para esquivar bloqueos ni violar los términos del sitio;
para bloqueos recomienda reducir frecuencia, presupuesto o desactivar la fuente.
```

Validar la respuesta: si no es JSON válido o le faltan campos, enviar la **alerta plana** (abajo) con una nota "diagnóstico IA no disponible".

### Mensaje al canal

```
🚨 <b>Incidente: LinkedIn · bloqueo</b> (severidad alta)
Abierto desde: hoy 10:30 · cooldown 6 h

🔍 <b>Causa probable</b>
HTTP 429 con retry-after de 1 h: LinkedIn limitó la IP por volumen de requests.

🛠 <b>Recomendación</b>
Bajar el presupuesto de LinkedIn de 3 a 2 requests por corrida y subir la pausa a 8–15 s.

📎 Evidencia: 4 intentos seguidos con 429 · otras fuentes OK
⚠️ Requiere intervención: no (se recupera solo con el cooldown)
```

Si hay `sugerencia_tecnica` (por ejemplo, selectores nuevos), se adjunta en un bloque `<pre>` para que el administrador la revise. **No se aplica automáticamente.**

### Alerta plana (fallback sin LLM)

Se usa cuando: se superó el presupuesto diario de llamadas, el saldo de DeepSeek está bajo, la API falla (402, timeout, 5xx) o la respuesta no es válida.

```
🚨 Incidente: LinkedIn · bloqueo
HTTP 429 en 4 intentos seguidos · cooldown 6 h
Diagnóstico IA no disponible (motivo: saldo bajo)
```

### Presupuesto y saldo

- Máximo de llamadas al Reportero por día: `reportero.max_llamadas_dia: 8` (configurable).
- Antes de cada llamada consultar `GET https://api.deepseek.com/user/balance`. Si el saldo < `reportero.saldo_minimo_usd: 1.0`, usar la alerta plana y avisar **una vez al día**: "💳 Saldo DeepSeek bajo: $X".
- Registrar en el log: tokens de entrada/salida (campo `usage` de la respuesta) por llamada, para medir el costo real.
- Con este diseño el consumo esperado es de pocas llamadas a la semana, cada una de unos pocos miles de tokens.

### Resumen diario (opcional, según respuesta en 0.2)

Si está activo (`reportero.resumen_diario: true`), una vez al día (hora configurable, por defecto 08:00 Colombia) enviar al canal un resumen generado con **una** llamada: vacantes enviadas por fuente y categoría, descartes por filtro, incidentes abiertos/cerrados, y 1–3 recomendaciones (por ejemplo: "la keyword X no trajo resultados en 7 días", "el filtro de seniority descartó 40 % de LinkedIn, revisar"). Si está desactivado, no se envía nada.

### Modo de prueba

`python buscador.py --simular-incidente linkedin:bloqueo` (y los demás tipos) debe generar un payload de ejemplo, llamar al Reportero y enviar el resultado al **chat de prueba**, sin tocar el estado real.

---

## 7. Formato de Telegram

### 7.1 Análisis del formato actual

Basado en una captura del canal:

| Problema | Impacto |
|---|---|
| Encabezado "Cronjob Response: Buscador Empleo Carlos Mario (job_id: …)" y "Report is ready. Here is the final deliverable:" | Ruido técnico en inglés que ven los 7 suscriptores. |
| "10 nuevas oportunidades **esta semana**" | Inexacto: es por corrida, no por semana. |
| 7 líneas por ficha | Con corridas cada 30 min, el canal se vuelve muy largo de leer. |
| "💰 No especificado" | Línea entera sin información en casi todas las fichas. |
| Emoji del título aleatorio (👨‍💻, ⚙️, 📊, ☁️, 🛠) | No aporta significado; parece decoración del LLM. |
| Fecha "30/09" sin contexto | No queda claro si es publicación o cierre. |
| "Ver oferta" en línea aparte | El título mismo puede ser el enlace. |
| Banner enviado siempre | Cada 30 min sería spam; además hoy llega aunque no haya vacantes. |

### 7.2 Propuesta (parse_mode HTML)

Mensaje por corrida:

```
🔔 <b>3 vacantes nuevas</b>

🎓 <b>PRÁCTICAS Y APRENDIZAJE</b>

<b><a href="URL">Practicante de Proyectos de TI</a></b>
🏢 Redeban · 📍 Bogotá (Híbrido)
🔎 LinkedIn · 🕒 hace 2 días

<b><a href="URL">Aprendiz SENA Desarrollo de Software</a></b>
🏢 Empresa X · 📍 Cartagena (Presencial)
💰 1 SMMLV + auxilio
🔎 Computrabajo · 🕒 hoy

🚀 <b>DEVOPS / CLOUD JUNIOR</b>

<b><a href="URL">Analista Jr CloudOps (SysOps AWS)</a></b>
🏢 Accenture Colombia · 📍 Bogotá (Remoto)
🔎 LinkedIn · 🕒 hace 5 días
```

Reglas:
- 3 líneas por ficha; la línea 💰 **solo si hay salario**.
- Fecha relativa: "hoy", "ayer", "hace N días". Si no hay fecha, se omite.
- Título como enlace; `disable_web_page_preview=true`.
- Escapar `<`, `>` y `&` en todos los campos (títulos con "C++", "&", etc.).
- Categorías vacías no se muestran.
- Orden dentro de cada categoría: más reciente primero.
- Telegram limita a 4096 caracteres por mensaje: dividir en varios mensajes **sin cortar fichas** (aprox. 12–15 fichas por mensaje).
- **Banner**: enviarlo solo en el primer envío con vacantes de cada día (registrar la fecha en el estado), o eliminarlo. Dejarlo configurable: `banner: diario | nunca | siempre`.
- Horario silencioso según la respuesta del usuario (0.2).

---

## 8. Programación

Opción preferida (crontab del sistema):

```cron
*/30 * * * * cd /home/ByLOGAN/buscador-vacantes && /usr/bin/flock -n /tmp/buscador.lock /usr/bin/python3 buscador.py >> logs/cron.log 2>&1
```

Si Hermes soporta jobs sin agente y el usuario prefiere gestionarlo ahí, usar esa opción, pero **sin toolsets ni modelo**.

Logs: un archivo por día en `logs/`, retención de 14 días. Por corrida registrar: requests por fuente, código HTTP, vacantes crudas, descartadas por cada filtro, duplicadas, enviadas y duración.

---

## 9. Plan de despliegue

1. Implementar con `--dry-run`: imprime las fichas en consola sin enviar a Telegram.
2. Correr `--dry-run` por cada fuente individual (`--fuente linkedin`) y reportar al usuario: resultados crudos, filtrados y errores.
3. Migrar el historial JSON y correr `--seed`.
4. Enviar una corrida real a un **chat de prueba** (no al canal) y mostrarle el resultado al usuario.
4b. Probar el Reportero IA con `--simular-incidente` para cada tipo (incluido el fallback con saldo bajo y con API caída) y mostrarle los mensajes al usuario.
5. Con aprobación del usuario: activar el cron cada 30 min contra el canal.
6. **Pausar** (no borrar) el cronjob de Hermes `d6381ce58395` y quitar `send_encabezado.py` como pre-run. Confirmar con el usuario antes de hacerlo.
7. Revisar logs después de 24 h y ajustar presupuestos o filtros.

---

## 10. Criterios de aceptación

- [ ] Cero llamadas a LLM en el camino normal (scraping, filtrado, deduplicación, envío).
- [ ] DeepSeek solo se llama cuando el detector abre un incidente nuevo (o para el resumen diario, si está activo), sin superar `max_llamadas_dia`.
- [ ] El Reportero no modifica código, configuración ni estado; solo envía diagnósticos al canal.
- [ ] Si DeepSeek falla o no hay saldo, llega la alerta plana y las vacantes se siguen enviando con normalidad.
- [ ] El payload enviado a DeepSeek nunca contiene tokens, keys, cookies ni el chat id.
- [ ] Corre cada 30 min sin solaparse.
- [ ] Una fuente caída o bloqueada no detiene las demás y entra en cooldown automático.
- [ ] Ninguna vacante se envía dos veces, ni siquiera si aparece en dos fuentes.
- [ ] Sin vacantes nuevas → no se envía nada (ni banner).
- [ ] No llegan vacantes senior ni no-TI (validado con una muestra del dry-run).
- [ ] Las alertas técnicas y los diagnósticos del Reportero llegan al mismo canal de las vacantes.
- [ ] Mensajes en español, formato de la sección 7.2, sin texto técnico de cron.
- [ ] Tests unitarios para filtros, deduplicación, formato (incluido escape HTML y división de mensajes) y parsers de cada fuente con HTML/JSON de ejemplo guardado en `tests/fixtures/`.
