# Proposal

## Why

Hoy el canal de Telegram "JOBS - PRACTICAS/APRENDIZ" lo alimenta el cronjob de Hermes "Buscador Empleo Carlos Mario" (`d6381ce58395`), en el que un agente LLM (DeepSeek) scrapea, filtra y redacta las vacantes. Esto gasta tokens en cada corrida, es lento y no es determinista: puede repetir vacantes, resumirlas mal o cubrir pocas búsquedas. Además, el mensaje llega con ruido técnico en inglés. La cobertura actual se limita a prácticas y DevOps/Cloud, y queremos abarcar **todo lo junior y de aprendiz en todos los roles de TI** (desarrollo, infraestructura, DBA, soporte IT, análisis de datos, QA, ciberseguridad, redes…). Queremos un buscador determinista que corra 24/7 en un PC Fedora cada 30 minutos y que sea **igual o mejor** que Hermes en cobertura, precisión y legibilidad. La IA queda solo para lo que aporta criterio: clasificar casos dudosos, diagnosticar incidentes y redactar un resumen diario.

## What Changes

- Nuevo buscador en Python que consulta varias fuentes de empleo (LinkedIn guest, Computrabajo, elempleo, Magneto365, GetOnBoard, Torre y, si es viable, la Agencia Pública de Empleo del SENA). Rota palabras clave y respeta un presupuesto de requests por fuente para minimizar bloqueos.
- Cobertura de todos los roles de TI en nivel práctica/aprendiz y junior: palabras clave divididas en un grupo núcleo (consultas amplias frecuentes) y una cola larga por rol, y filtros de nivel nativos de cada fuente cuando existen.
- Filtros deterministas de seniority, relevancia TI, antigüedad y ubicación (Colombia + remoto LATAM en español). Cada vacante queda como aceptar, rechazar o dudosa, y **solo las dudosas** pasan a DeepSeek para clasificarlas en lote.
- Deduplicación persistente: por id de cada fuente y por huella título+empresa entre fuentes. Incluye migración del historial actual (`historial_vacantes.json`, ~309 vacantes) y una corrida inicial `--seed` que no envía nada.
- Mensajes de Telegram rediseñados: HTML, 3 líneas por ficha, agrupadas en Prácticas y Aprendizaje más una categoría por área junior (Desarrollo, Infraestructura/DevOps/Cloud, Bases de datos, Soporte IT, Datos y Analítica, QA, Ciberseguridad, Otros TI), divididas sin cortar fichas y con un banner configurable. Sin vacantes nuevas no se envía nada.
- Detector determinista de incidentes (bloqueo, captcha, cambio de HTML, sin resultados, caída de volumen, error de servidor, fallo de envío, sin red). Hay un Reportero IA que diagnostica cada incidente nuevo, con presupuesto diario, control de saldo y una alerta plana cuando la IA no está disponible.
- Resumen diario a las 08:00 (hora Colombia) redactado por IA, con métricas del día y recomendaciones.
- Operación 24/7 en Fedora: systemd user timers que recuperan corridas perdidas, sin solapamiento, con *heartbeat* a healthchecks.io y logs rotados. CLI con `--dry-run`, `--fuente`, `--seed`, `--chat-prueba` y `--simular-incidente`.
- Al final, y con confirmación del usuario, se pausa (no se borra) el cronjob de Hermes y su pre-run `send_encabezado.py`.

## Capabilities

### New Capabilities
- `busqueda-fuentes`: consulta de fuentes de empleo con rotación de palabras clave, presupuesto por corrida, pausas, cooldown escalonado ante bloqueos y detección de desafíos anti-bot, sin evadirlos nunca.
- `filtrado-vacantes`: normalización, filtros de seniority, relevancia TI, antigüedad y ubicación, cobertura de todos los roles de TI en nivel aprendiz/junior, veredicto aceptar/rechazar/dudosa, clasificación IA de dudosas y asignación de categoría por área.
- `deduplicacion-estado`: estado persistente de vacantes vistas y enviadas, dedupe entre fuentes, migración del historial JSON, modo seed y limpieza por antigüedad.
- `publicacion-telegram`: formato y envío de las vacantes nuevas al canal (escape HTML, división por límite de tamaño, banner diario, orden y agrupación).
- `incidentes-reportero`: detección determinista de incidentes, control de ruido, diagnóstico IA con datos sanitizados, alerta plana de respaldo, avisos de recuperación y modo de simulación.
- `resumen-diario`: resumen diario de salud y resultados redactado por IA, con respaldo sin IA.
- `operacion-continua`: ejecución programada cada 30 min 24/7, recuperación tras apagado o suspensión, exclusión mutua, heartbeat externo, logs y modos de ejecución manual (dry-run, por fuente, chat de prueba).

### Modified Capabilities
<!-- Ninguna: no existen specs previas en el proyecto. -->

## Impact

- **Código nuevo**: todo el proyecto Python (`buscador.py`, `fuentes/`, `config.yaml`, `deploy/`, `tests/`) en este repo. No hay código previo en el repo. El código viejo de Hermes (`scrape_jobs.py`, scripts de fuentes) está en el PC Fedora y se usa como referencia.
- **Dependencias**: Python 3.12+, uv, httpx, beautifulsoup4, lxml, pyyaml, pydantic, python-dotenv; para desarrollo, pytest, respx y ruff.
- **Sistemas externos**: Telegram Bot API (token del bot de Hermes o uno nuevo), API de DeepSeek (`chat/completions` y `user/balance`), healthchecks.io y los sitios de empleo listados.
- **Secretos**: `.env` con permisos 600 (`TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY`, `HEALTHCHECK_URL`, ids de canal y chat de prueba). Nunca se envían a la IA.
- **Operación**: el PC Fedora debe tener la suspensión automática desactivada y `loginctl enable-linger` para el usuario. El cronjob de Hermes `d6381ce58395` se pausa al final del despliegue.
- **Usuarios del canal** (~7 suscriptores): ven el nuevo formato, más vacantes por cobertura, mensajes sin repetidos y alertas técnicas en el mismo canal.
