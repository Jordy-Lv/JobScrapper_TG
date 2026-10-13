# Buscador de vacantes TI → Telegram

Busca vacantes de **prácticas, aprendiz (incluido SENA) y junior en todos los roles de TI**
(desarrollo, infraestructura/DevOps/cloud, redes, bases de datos, soporte IT, datos, QA y
ciberseguridad) y publica solo las nuevas en el canal de Telegram "JOBS - PRACTICAS/APRENDIZ".
Reemplaza al cronjob de Hermes + DeepSeek.

Alcance geográfico: lo **presencial** solo vale en la ciudad base (Cartagena y su área cercana).
En otra ciudad de Colombia la vacante tiene que ser **remota o híbrida**, y lo remoto sigue
abierto a Colombia o LATAM en español.

- Las reglas deciden los casos claros; DeepSeek clasifica las vacantes **dudosas**, incluidas
  todas las prácticas y aprendices de áreas que no son TI (acepta solo las que tienen funciones
  principales de TI). Topes diarios amplios (clasificador 300, reportero 20, resumen 3); la
  protección económica es el saldo mínimo de DeepSeek.
- Nunca se publica dos veces la misma vacante, aunque aparezca en varias fuentes.
- Antes de publicar, el **guardarraíl de prácticas** revisa todo lo que va a «Prácticas y
  Aprendizaje», lo haya aceptado una regla o la IA: sin evidencia textual de práctica (practicante,
  aprendiz, pasante, etapa productiva, trainee, intern…) la vacante pasa a su categoría por área o
  se rechaza. El resumen diario cuenta cuántas corrigió.
- Corre cada 30 minutos en el PC Fedora con systemd de usuario: guía completa de instalación,
  fase de prueba, paso a producción, operación y rollback en `deploy/INSTALAR.md`.

La especificación completa está en `docs/buscador-vacantes-spec.md` y el plan en
`openspec/changes/crear-buscador-vacantes/`.

## Instalación local

Requiere [uv](https://docs.astral.sh/uv/) (instala Python 3.12 por su cuenta).

```bash
uv sync                      # crea .venv con las dependencias
cp .env.example .env         # completar los secretos
chmod 600 .env
uv run pytest                # pruebas (sin red)
PRUEBA_REAL=1 uv run pytest  # incluye DeepSeek y healthchecks reales (usa la red)
```

## Modos de ejecución

```bash
uv run buscador.py --dry-run --fuente getonboard   # consulta una fuente e imprime el resultado
uv run buscador.py --dry-run                       # todas las fuentes activas, sin enviar nada
uv run buscador.py migrar --archivo docs/referencia_hermes/historial_vacantes.json
uv run buscador.py --seed                          # marca lo actual como visto, sin enviar
uv run buscador.py --chat-prueba                   # envía al chat de prueba
uv run buscador.py                                 # corrida normal (la que ejecuta systemd)
uv run buscador.py resumen                         # resumen diario (una vez al día, 08:00)
uv run buscador.py --dry-run resumen               # muestra el resumen sin enviarlo
uv run buscador.py promover-prueba                 # al pasar a producción (ver deploy/INSTALAR.md)
uv run buscador.py --simular-incidente linkedin:bloqueo --dry-run
uv run buscador.py --simular-incidente magneto:cambio_html --simular-falla-ia saldo_bajo
```

`--simular-incidente FUENTE:TIPO` arma evidencia de ejemplo y corre el reportero completo
(diagnóstico IA o alerta plana) sobre una base en memoria: no toca el estado real. Tipos:
`bloqueo`, `captcha`, `cambio_html`, `sin_resultados`, `caida_volumen`, `error_servidor`, además
de `telegram:fallo_envio` y `red:sin_conexion`. Sin `--dry-run` envía al chat de prueba.

| Modo | Envía | Marca vistas | Llama a la IA | Necesita secretos |
|---|---|---|---|---|
| `--dry-run` | no | no | no | no |
| `migrar` | no | sí (como enviadas) | no | no |
| `--seed` | no | sí | no | no |
| `--chat-prueba` | al chat de prueba | solo para el chat de prueba | sí | sí, más `TELEGRAM_CHAT_PRUEBA` |
| normal | al canal | sí | sí | sí |
| `resumen` | al canal (o al chat de prueba) | no | una llamada | sí |

- `--fuente <nombre>` limita la corrida a una fuente. En dry-run sirve también para probar una
  fuente desactivada.
- Antes de la primera corrida que envía hay que correr `migrar` o `--seed`. Si la base no
  tiene historial, el buscador se niega a enviar para no inundar el canal.
- Si hay otra corrida en curso, la nueva termina de inmediato sin hacer requests.

## Configuración

- **`config.yaml`**: fuentes (activa, presupuesto de requests, palabras clave del núcleo por
  corrida y páginas leídas de cada una), palabras clave (núcleo y cola larga por rol), filtros
  (seniority, nivel, áreas de TI, áreas
  que no son TI, ubicación), Telegram, banner (`diario`, `nunca` o `siempre`), IA (modelo,
  presupuesto diario, saldo mínimo, prompts), resumen diario, incidentes y retención. Se valida
  al arrancar: un campo inválido detiene el programa indicando cuál es.
- **Filtros de ubicación y calidad** (`filtros` en `config.yaml`):
  - `ubicacion.ciudad_base`: ciudades donde lo presencial sirve. La modalidad sale del portal, el
    título y la ubicación y, solo para remoto o híbrido, de la descripción
    (`ubicacion.hibrido`, `ubicacion.presencial`). Si no se sabe y hay descripción, decide la IA
    exigiendo un indicio de remoto o híbrido; sin descripción se rechaza sin llamarla.
  - `call_center`: los puestos de atención o soporte al cliente solo valen si son remotos, también
    en la ciudad base.
  - `lista_negra.empresas` y `lista_negra.palabras`: rechazo directo por empresa o por palabra del
    título. Empiezan vacías; se editan aquí.
  - `nivel.evidencia_practica` y `nivel.evidencia_practica_descripcion`: evidencia que exige el
    guardarraíl de prácticas.
  - `anios_experiencia_excluidos_desde: 2`: se acepta hasta 1 año de experiencia.
  - Una práctica cuya descripción y título no tienen ningún término de TI se rechaza sin llamar
    a la IA. Sin descripción no se rechaza: la decide la IA.
- **Variantes de LinkedIn** (`fuentes.linkedin.opciones.variantes`): cada corrida usa una variante,
  en orden circular y sin gastar más peticiones: Colombia filtrando a remoto o híbrido (`f_WT`) y
  solo Cartagena con cualquier modalidad. Las vacantes de la primera salen con modalidad «Remoto
  o híbrido». Sin `variantes`, LinkedIn usa solo sus `opciones`.
- **Prompt del clasificador**: la caché de clasificaciones guarda un hash del prompt
  (`clasificaciones.version_prompt`); al cambiar el prompt, lo clasificado antes se vuelve a
  consultar.
- **Prioridad de prácticas**: el grupo núcleo contiene solo términos de prácticas, pasantías y
  aprendizaje (practicante, aprendiz SENA/ADSO, pasantía, trainee). Se consulta en cada corrida
  (`reservado_nucleo` palabras clave por fuente) y, en las fuentes que paginan (Computrabajo y
  elempleo), se leen hasta `paginas_nucleo` páginas de cada una; una página incompleta corta
  las siguientes. El presupuesto cuenta requests, así que cada página es uno. Los términos
  junior van en la cola larga, que lee solo la primera página.
- **Fuentes**: LinkedIn, Computrabajo, elempleo, Magneto, GetOnBoard y el Servicio Público de
  Empleo (buscadordeempleo.gov.co). El SPE no usa palabras clave: pide las plazas de práctica
  (`PLAZA_PRACTICA=1`) más recientes. Sus copias de elempleo y Magneto se identifican con la
  clave y el enlace del portal de origen, para no duplicarlas, y se descartan las plazas
  vencidas, sin enlace o cuyo enlace exige iniciar sesión (`opciones.dominios_con_login`). Su
  servidor no envía el certificado intermedio: se completa la cadena con
  `assets/certs/geotrust-tls-rsa-ca-g1.pem` (DigiCert), sin desactivar la verificación TLS.
- **`.env`** (permisos 600, nunca en git): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `TELEGRAM_CHAT_PRUEBA`, `DEEPSEEK_API_KEY` y `HEALTHCHECK_URL`. Si `TELEGRAM_BOT_TOKEN` está
  vacío, el token se lee del archivo indicado en `telegram.token_hermes` (el bot de Hermes).

## Estado y logs

- `data/vacantes.db` (SQLite): vacantes vistas y enviadas (con su ubicación y modalidad),
  cooldowns, rotación, intentos, corridas (con las correcciones del guardarraíl),
  clasificaciones de la IA e incidentes. El esquema está en la versión 2 y una base anterior se
  migra sola al abrirla, sin perder datos. Para volver al código anterior hay que bajar la
  versión: `UPDATE esquema_version SET version = 1` (las columnas nuevas no le estorban).
- `logs/AAAA-MM-DD.log`: un archivo por día, se conservan 14 días. Los secretos se enmascaran.

## Estructura

```
buscador.py                 punto de entrada (uv run buscador.py ...)
config.yaml                 configuración funcional (fuentes, filtros, presupuestos)
buscador_vacantes/          código del buscador
  corrida.py                CLI y flujo de la corrida
  config.py                 carga y validación de config.yaml y .env
  fuentes/                  una clase por fuente sobre fuentes/base.py
  filtros.py                veredicto aceptar/rechazar/dudosa y categoría
  clasificador.py           dudosas → DeepSeek (ia_cliente.py)
  estado.py                 SQLite
  formato.py                mensajes HTML de Telegram
  publicacion.py            banner y envío con confirmación (notificador_telegram.py)
  incidentes.py             detección determinista de incidentes
  reportero.py              diagnóstico IA de incidentes y alertas planas
  resumen.py                resumen diario con métricas y recomendaciones
  simulacion.py             --simular-incidente
  salud.py                  heartbeat a healthchecks.io
  migrar_historial.py       importación del historial de Hermes
tests/                      pruebas (pytest + respx) y fixtures
deploy/                     unidades systemd y guía de instalación en Fedora
assets/                     banner del canal y certs/ (certificado intermedio del SPE)
docs/                       especificación de origen y referencia_hermes/ (scripts
                            originales de Hermes y NOTAS.md, solo referencia)
```

Para agregar una fuente: crear `buscador_vacantes/fuentes/<nombre>.py` con
`construir_peticion()` y `parsear()`, registrarla en `FUENTES` de
`buscador_vacantes/corrida.py` y agregarla a `fuentes:` en `config.yaml`.
