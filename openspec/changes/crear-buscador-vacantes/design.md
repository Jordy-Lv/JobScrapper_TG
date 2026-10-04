# Design

## Context

- El repo está vacío salvo `README.md` y `buscador-vacantes-spec.md` (la especificación de origen). El código de Hermes (`scrape_jobs.py`, scripts de El Empleo, Magneto, RemoteOK y GetOnBoard, `send_encabezado.py`, `historial_vacantes.json`) está en el PC Fedora, en `/home/ByLOGAN/.hermes/cron/`. Sirve de referencia para selectores, endpoints y la estructura del historial, pero no se copia tal cual.
- Se desarrolla en macOS y se ejecuta 24/7 en Fedora con SELinux activo. Es un PC de escritorio con IP residencial: puede apagarse, suspenderse o perder red.
- La motivación y el alcance están en `proposal.md`, y los requisitos en `specs/`.

## Goals / Non-Goals

**Goals:**
- Una corrida típica (~20 requests) termina en menos de 3 minutos, incluidas las pausas.
- Cada módulo se prueba sin red: parsers con fixtures guardados, y HTTP, Telegram y DeepSeek mockeados.
- Agregar una fuente nueva es crear un módulo y una entrada en `config.yaml`.
- Instalación en Fedora reproducible siguiendo `deploy/INSTALAR.md`.

**Non-Goals:**
- No hay panel web ni API propia; Telegram y los logs son la interfaz.
- No se renderiza JavaScript (sin navegador headless) en esta versión.
- No hay multiusuario ni varios canales.
- No se aplican automáticamente las sugerencias de la IA.

## Decisions

### D1. Stack
Python 3.12+ con **uv** (`pyproject.toml` + `uv.lock`), **httpx** (cliente síncrono, uno por fuente), **BeautifulSoup + lxml**, **PyYAML + pydantic v2** para validar `config.yaml`, **python-dotenv** para los secretos, **sqlite3** de la stdlib en modo WAL, y **pytest + respx + ruff** para desarrollo.
- *httpx vs requests*: los timeouts son más finos y `respx` lo mockea limpio. Para ~20 requests no hace falta async.
- *BeautifulSoup vs selectolax*: con este volumen la velocidad no importa y BeautifulSoup tolera mejor HTML roto.
- *Sin SDK de OpenAI ni librería de Telegram*: son 3 endpoints (`chat/completions`, `user/balance`, `sendMessage`/`sendPhoto`) y llamarlos con httpx evita dependencias.
- *Sin Scrapy, Playwright ni curl_cffi*: sobran para este volumen, y curl_cffi y los proxies son evasión, que está prohibida.

### D2. Estructura de módulos
```
buscador.py            CLI (argparse): corrida, --dry-run, --fuente, --seed, --chat-prueba,
                       --simular-incidente, subcomandos `resumen` y `migrar`
config.py              carga y valida config.yaml + .env (pydantic)
modelo.py              dataclass Vacante y enums (Veredicto, Categoria)
fuentes/base.py        clase Fuente: cliente httpx, cabeceras, pausas, presupuesto,
                       detección de desafío, registro de intentos, cooldown
fuentes/<nombre>.py    construir_consultas() + parsear(respuesta) -> list[Vacante]
rotacion.py            lote núcleo + cola larga por fuente
fechas.py              fechas relativas en español → datetime America/Bogota
normalizar.py          minúsculas, sin tildes, huella, limpieza de empresa
filtros.py             veredicto + categoría por reglas
clasificador.py        dudosas → IA en lote, caché, pendientes
ia_cliente.py          DeepSeek: chat JSON, saldo, presupuesto diario, registro de usage
estado.py              SQLite: esquema, migraciones de esquema, acceso
formato.py             fichas HTML, agrupación, división ≤4096
notificador_telegram.py sendMessage/sendPhoto, chat real o de prueba
incidentes.py          reglas deterministas, apertura/cierre, recordatorios
reportero.py           evidencia sanitizada → IA → mensaje; alerta plana
resumen.py             métricas 24 h → IA → mensaje; respaldo plano
salud.py               ping healthchecks (/start, éxito, /fail)
lock.py                fcntl.flock sobre data/buscador.lock
registro.py            logging a logs/AAAA-MM-DD.log + stdout (journald); retención 14 días
migrar_historial.py    historial_vacantes.json → tabla vistas
```
El nombre `notificador_telegram.py` evita chocar con paquetes llamados `telegram`.

### D3. Flujo de una corrida
`lock → cargar config → salud.start → limpieza → por cada fuente activa sin cooldown: lote de rotación → requests → parsear → normalizar → filtros → dedupe (clave y huella) → dudosas nuevas + pendientes → clasificador → aceptadas nuevas → formato → Telegram (marca enviadas una por una según la confirmación de cada mensaje) → guardar corrida y métricas → incidentes.evaluar() → reportero (try/except aislado) → salud.ok o salud.fail`.
El orden garantiza que la IA y el reportero nunca bloqueen el envío de vacantes.

### D4. Esquema SQLite (`data/vacantes.db`, WAL)
- `vistas(clave PK, huella, fuente, titulo, empresa, url, categoria, primera_vez, enviada_en NULL)` con índice en `huella`.
- `fuentes_estado(fuente PK, cooldown_hasta, escalon, fallos_consecutivos, ultimo_exito)`.
- `rotacion(fuente, grupo, indice, PK(fuente, grupo))`.
- `intentos(id, ts, corrida_id, fuente, keyword, url, status, ms, items, tipo_error, desafio BOOL)`.
- `corridas(id, inicio, fin, modo, crudas, descartes_json, duplicadas, dudosas, ia_aceptadas, ia_rechazadas, pendientes, enviadas, error)`.
- `clasificaciones(huella PK, aceptar, categoria, motivo, ts)` y `pendientes(huella PK, vacante_json, desde)`.
- `incidentes(id, fuente, tipo, abierto_desde, ultimo_reporte, cerrado_en, detalle_json)`.
- `ia_uso(id, ts, proposito, tokens_in, tokens_out, ok, motivo)`, que sirve para el presupuesto diario y el resumen.
- `kv(clave PK, valor)` para la fecha del último banner, del último resumen y del último aviso de saldo.

Una tabla `esquema_version` permite migraciones simples. Cada corrida usa transacciones cortas: una vacante se marca enviada en una transacción propia justo después de la confirmación de Telegram.

### D5. Rotación núcleo + cola larga y filtros de nivel nativos
Con todos los roles de TI la lista crece a ~100 consultas. Si se rotara en una sola lista, cada consulta en LinkedIn tardaría ~17 h en repetirse. Por eso el presupuesto de cada fuente se parte en `reservado_nucleo` (p. ej. 1) y el resto va a la cola larga. Además se aprovechan los filtros de nivel de cada fuente:
- **LinkedIn guest**: `f_E=1,2` (Internship, Entry level), `f_TPR=r86400` y `location=Colombia`. Con el filtro de nivel, consultas amplias como "sistemas", "datos" o "soporte" ya traen solo prácticas y entrada.
- **GetOnBoard**: filtrar por `seniority` sin experiencia o junior, y remoto LATAM.
- Las demás fuentes se ajustan según lo que expongan en la validación (tarea de dry-run por fuente).

Palabras clave iniciales en `config.yaml` (editables):
- **núcleo**: practicante sistemas, practicante TI, aprendiz SENA, aprendiz sistemas, pasante tecnología, trainee tecnología, junior TI, desarrollador junior.
- **cola larga por rol**:
  - *Desarrollo*: programador junior, desarrollador backend/frontend/fullstack junior, desarrollador Java/Python/.NET/web/móvil junior, practicante desarrollo, aprendiz desarrollo de software, tecnólogo desarrollo de software.
  - *Infra/DevOps/Cloud*: DevOps junior, cloud junior, AWS/Azure junior, SysOps, CloudOps, infraestructura junior, administrador de sistemas junior, Linux junior, aprendiz infraestructura.
  - *Redes*: redes junior, técnico de redes, telecomunicaciones junior, NOC junior, aprendiz redes.
  - *Bases de datos*: DBA junior, administrador de bases de datos junior, SQL junior, aprendiz bases de datos.
  - *Soporte IT*: soporte técnico junior, soporte IT, mesa de ayuda, helpdesk, auxiliar de sistemas, auxiliar TI, técnico de sistemas, aprendiz soporte.
  - *Datos*: analista de datos junior, data analyst junior, BI junior, Power BI, ingeniero de datos junior, practicante análisis de datos, aprendiz análisis de datos.
  - *QA*: QA junior, tester junior, analista de pruebas junior, automatización de pruebas junior.
  - *Ciberseguridad*: ciberseguridad junior, analista SOC junior, seguridad informática junior.
  - *General*: analista de sistemas junior, analista TI junior, ingeniero de sistemas recién egresado, estudiante ingeniería de sistemas, semillero, programa de talento, contrato de aprendizaje, etapa productiva, internship, intern, entry level developer.

### D6. Filtros y categorías por reglas
Los términos están en `config.yaml` y se compilan a expresiones regulares con `\b` sobre el texto normalizado. Hay cinco listas: `exclusion_seniority`, `nivel` (aprendiz/práctica vs junior/entrada), `areas` (un diccionario de área a términos, cuyo orden define la prioridad), `ti_generico` y `disparadores_dudosa` (practicante, aprendiz, junior, analista, auxiliar, técnico sin área). El orden de evaluación es el de la spec `filtrado-vacantes`. `exclusion_seniority` se evalúa solo sobre el título; los años de experiencia, el nivel, las áreas y la ubicación, sobre título y descripción. Dos listas auxiliares reducen falsos positivos: `frases_ignoradas` ("redes sociales", "sistemas de gestión", "para ti"…), que se quitan del texto antes de evaluar, y `areas_no_ti` (contable, ventas, logística…), que anulan los disparadores de dudosa para que "Practicante Contable" se rechace. Para ubicación: hay una lista de departamentos y ciudades de Colombia, términos remotos (`remoto`, `remote`, `teletrabajo`, `home office`) y términos LATAM (`latam`, `latinoamérica`, `américa latina`). Las restricciones a otros países se detectan con una lista de países y patrones como "solo residentes en".

### D7. Clasificador IA
- La llamada usa el modelo configurable (por defecto `deepseek-chat`), `temperature: 0`, `response_format: json_object` y `max_tokens` proporcional al lote. El system prompt es fijo y está en `config.yaml`; describe el alcance (roles de TI, nivel aprendiz/junior, Colombia + remoto LATAM) y las categorías válidas.
- Cada vacante viaja con un `id` corto (índice del lote) en lugar de la URL, para ahorrar tokens.
- La respuesta se valida con pydantic. Los ids faltantes o las categorías inválidas se tratan como no clasificados y quedan pendientes.
- Topes iniciales: `max_llamadas_dia: 60`, `max_vacantes_por_llamada: 30` y `politica_sin_ia: descartar`.

### D8. Cliente IA compartido
`ia_cliente.py` concentra la URL base, la clave, el timeout (60 s), la ausencia de reintentos, la consulta de saldo (cacheada 10 min), el presupuesto por propósito (reportero 8/día, clasificador 60/día, resumen 1/día), el registro en `ia_uso` y la sanitización. Esta última aplica una lista blanca de cabeceras y elimina con regex cualquier cosa que parezca un token (`\d+:[A-Za-z0-9_-]{30,}`, `sk-…`) en el payload antes de enviarlo.

### D9. Operación en Fedora (systemd de usuario)
- `buscador.service` (Type=oneshot, `WorkingDirectory=%h/buscador-vacantes`, `ExecStart=%h/.local/bin/uv run buscador.py`, `TimeoutStartSec=28min`, unos minutos por encima del límite interno de 25 min para que este registre el error y avise a healthchecks, `Nice=10`).
- `buscador.timer`: `OnCalendar=*:00,30`, `Persistent=true`, `RandomizedDelaySec=120`. Con `Persistent=true` systemd recupera una sola corrida perdida, y como el servicio es oneshot no hay solapamiento.
- `buscador-resumen.service` y `.timer`: `OnCalendar=*-*-* 08:00 America/Bogota`, `Persistent=true`.
- `loginctl enable-linger $USER` para correr sin sesión, y desactivar la suspensión de GNOME (`gsettings … sleep-inactive-ac-type 'nothing'`). Todo vive bajo `$HOME`, así que no hace falta tocar contextos SELinux.
- Secretos: manda el `.env` del proyecto; una variable de entorno solo se usa si el `.env` no la trae. En el PC el `~/.bashrc` exporta la `DEEPSEEK_API_KEY` de Hermes, y una corrida manual por SSH no debe tomarla en lugar de la propia.
- Para el heartbeat, un check en healthchecks.io con periodo de 30 min y gracia de 45 min; se hace ping a `/start`, a la URL base al terminar bien y a `/fail` ante un error interno.
- Fase de prueba: drop-ins `deploy/prueba/*.conf` en `~/.config/systemd/user/<unidad>.d/` cambian `ExecStart` para añadir `--chat-prueba`. Al pasar a producción se borran y `buscador.py promover-prueba` marca como enviadas al canal las vacantes que ya salieron en el chat de prueba, para no reenviar ese atraso. Las unidades de usuario no dependen de `network-online.target` (no existe en el gestor de usuario); la falta de red la maneja el incidente `red:sin_conexion`.

### D10. Formato y división
Se compone por bloques (encabezado, título de categoría, ficha) y se va empaquetando hasta llegar a 4096 caracteres medidos sobre el texto que envía la API. Al abrir un mensaje nuevo a mitad de una categoría se repite su título. Se escapa con `html.escape(…, quote=False)`.

### D11. Detector de red local
Si en una corrida todos los intentos fallan con `httpx.ConnectError`/`ConnectTimeout` o error de DNS y ningún intento obtiene respuesta HTTP, la corrida se marca `sin_red`. En ese caso no se aplican cooldowns ni cuenta para las reglas de "corridas seguidas", y se abre o mantiene `red:sin_conexion`. Como no hay red, el aviso se envía en la primera corrida con conexión (apertura y cierre juntos: "⚠️ El PC estuvo sin internet de 10:00 a 11:40").

### D12. Telegram reutilizando la integración de Hermes
Decisión del usuario: el buscador corre **en el mismo PC que Hermes** y **reutiliza su integración con Telegram**, es decir, el mismo bot que ya publica en el canal. `notificador_telegram.py` tiene dos backends, que se eligen con `telegram.modo` en `config.yaml`:
- **`bot_api` (preferido)**: llama directo a `api.telegram.org` con el **token del bot de Hermes**. El buscador lee el token de la configuración de Hermes (ruta en `config.yaml`, p. ej. su `.env`) o de `TELEGRAM_BOT_TOKEN` en el `.env` propio. Reutiliza el bot y sus permisos en el canal sin depender de que el proceso Hermes esté corriendo, y soporta todo lo que piden las specs: HTML, sin vista previa de enlaces, confirmación por mensaje y `sendPhoto` para el banner. Solo usa métodos de envío (`sendMessage`, `sendPhoto`), nunca `getUpdates` ni webhooks, así no interfiere con la recepción de mensajes de Hermes.
- **`hermes_cli` (respaldo)**: ejecuta `hermes send -t telegram:<chat> "<texto>"` (y `"MEDIA:<ruta>"` para el banner), como hoy `send_encabezado.py`. Se usa si el token no es accesible. La confirmación es el código de salida del comando. Antes de elegirlo hay que verificar si soporta HTML, si desactiva la vista previa y cuál es su límite de longitud. Si no soporta HTML, el formato se degrada a texto plano con los mismos datos.

*Por qué no depender del proceso Hermes*: corre en una terminal interactiva. Si se cierra la terminal o el PC se reinicia, Hermes se detiene hasta que alguien lo vuelva a abrir, mientras que el buscador corre con systemd y debe seguir publicando. Con `bot_api` se aprovecha la integración de Hermes (bot, token y permisos) sin heredar esa fragilidad.

## Risks / Trade-offs

- [LinkedIn bloquea la IP residencial] → presupuesto bajo, filtro de nivel nativo para rendir más por request, cooldown escalonado e incidente con diagnóstico. Si persiste, se desactiva desde `config.yaml`.
- [Los selectores de Computrabajo, elempleo o Magneto cambian] → fixtures y tests por parser, incidente `cambio_html` con selectores sugeridos por la IA y arreglo manual.
- [SENA APE exige login o captcha] → se valida en el dry-run; si es así, queda desactivada y se informa.
- [La huella título+empresa fusiona la misma vacante en distintas ciudades] → se acepta para este canal; queda documentado.
- [La IA clasifica mal] → `temperature: 0`, prompt con ejemplos, motivo guardado y métricas en el resumen. Los patrones frecuentes se pasan a reglas fijas.
- [Más roles → más ruido no TI] → la exclusión de no-TI es por reglas y la IA solo ve lo ambiguo. El dry-run con muestra real valida antes de producción.
- [Corte de luz a mitad de la escritura en SQLite] → WAL y transacciones cortas; una vacante solo se marca tras la confirmación de Telegram.
- [El PC se apaga días enteros] → healthchecks avisa; al volver, el filtro de 15 días evita publicar vacantes viejas en masa.
- [Hermes rota o cambia el token de su bot] → el buscador lo lee desde la configuración de Hermes en cada corrida (no lo copia), y un `fallo_envio` abre incidente. Si Telegram responde 401, el mensaje de incidente lo indica explícitamente.
- [En modo `hermes_cli`, Hermes no está disponible o su CLI cambia] → se prefiere `bot_api`; el fallo del comando se trata como `fallo_envio`.
- [Spam si se pierde el estado] → si la base no existe al arrancar, el sistema se niega a enviar y exige `--seed` o la migración.

## Migration Plan

1. Copiar al repo (en `referencia_hermes/`, versionado en git porque no contiene secretos) `scrape_jobs.py`, los scripts de fuentes, el prompt del cronjob y `historial_vacantes.json` desde el PC de Hermes, y ubicar en la configuración de Hermes el token de su bot.
2. Implementar y probar en la Mac con `--dry-run` por fuente.
3. En Fedora: clonar el repo en `~/buscador-vacantes`, `uv sync`, crear `.env` (600), `migrar` y `--seed`.
4. Corridas manuales con `--chat-prueba`, más `--simular-incidente` para cada tipo.
5. Activar los timers apuntando al chat de prueba durante 24 h en paralelo con Hermes y comparar.
6. Con aprobación: apuntar al canal real y pausar el cronjob de Hermes y `send_encabezado.py`.
7. **Rollback**: `systemctl --user disable --now buscador.timer` y reactivar el cronjob de Hermes. El estado SQLite se conserva.

## Open Questions

- ID del chat de prueba: se define al crear el `.env`. Debe ser un chat donde el bot de Hermes pueda escribir (un grupo de prueba con el bot, o el chat privado con el bot).
- Ruta exacta del token dentro de la configuración de Hermes: se ubica en la tarea 1.3.
