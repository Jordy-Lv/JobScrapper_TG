# Buscador de vacantes TI → Telegram

Busca vacantes de **prácticas, aprendiz (incluido SENA) y junior en todos los roles de TI**
(desarrollo, infraestructura/DevOps/cloud, redes, bases de datos, soporte IT, datos, QA y
ciberseguridad) en Colombia y remoto LATAM, y publica solo las nuevas en el canal de Telegram
"JOBS - PRACTICAS/APRENDIZ". Reemplaza al cronjob de Hermes + DeepSeek.

- Las reglas deciden los casos claros; DeepSeek solo clasifica las vacantes **dudosas**.
- Nunca se publica dos veces la misma vacante, aunque aparezca en varias fuentes.
- Corre cada 30 minutos en el PC Fedora con systemd de usuario: guía completa de instalación,
  fase de prueba, paso a producción, operación y rollback en `deploy/INSTALAR.md`.

La especificación completa está en `buscador-vacantes-spec.md` y el plan en
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
uv run buscador.py migrar --archivo referencia_hermes/historial_vacantes.json
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

- **`config.yaml`**: fuentes (activa, presupuesto de requests, reserva para el grupo núcleo),
  palabras clave (núcleo y cola larga por rol), filtros (seniority, nivel, áreas de TI, áreas
  que no son TI, ubicación), Telegram, banner (`diario`, `nunca` o `siempre`), IA (modelo,
  presupuesto diario, saldo mínimo, prompts), resumen diario, incidentes y retención. Se valida
  al arrancar: un campo inválido detiene el programa indicando cuál es.
- **`.env`** (permisos 600, nunca en git): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `TELEGRAM_CHAT_PRUEBA`, `DEEPSEEK_API_KEY` y `HEALTHCHECK_URL`. Si `TELEGRAM_BOT_TOKEN` está
  vacío, el token se lee del archivo indicado en `telegram.token_hermes` (el bot de Hermes).

## Estado y logs

- `data/vacantes.db` (SQLite): vacantes vistas y enviadas, cooldowns, rotación, intentos,
  corridas, clasificaciones de la IA e incidentes.
- `logs/AAAA-MM-DD.log`: un archivo por día, se conservan 14 días. Los secretos se enmascaran.

## Estructura

```
buscador.py            CLI y flujo de la corrida
config.py              carga y validación de config.yaml y .env
fuentes/               una clase por fuente sobre fuentes/base.py
filtros.py             veredicto aceptar/rechazar/dudosa y categoría
clasificador.py        dudosas → DeepSeek (ia_cliente.py)
estado.py              SQLite
formato.py             mensajes HTML de Telegram
publicacion.py         banner y envío con confirmación (notificador_telegram.py)
incidentes.py          detección determinista de incidentes
reportero.py           diagnóstico IA de incidentes y alertas planas
resumen.py             resumen diario con métricas y recomendaciones
simulacion.py          --simular-incidente
salud.py               heartbeat a healthchecks.io
migrar_historial.py    importación del historial de Hermes
referencia_hermes/     scripts originales de Hermes y NOTAS.md (solo referencia)
```

Para agregar una fuente: crear `fuentes/<nombre>.py` con `construir_peticion()` y `parsear()`,
registrarla en `FUENTES` de `buscador.py` y agregarla a `fuentes:` en `config.yaml`.
