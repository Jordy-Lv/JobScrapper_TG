# Tasks

## 1. Insumos de Hermes

- [x] 1.1 Copiar desde el PC Fedora a `referencia_hermes/` (versionado en git: no contiene secretos) `scrape_jobs.py`, los scripts de El Empleo, Magneto, RemoteOK y GetOnBoard, `send_encabezado.py`, `encabezado_vacantes.jpg`, `historial_vacantes.json` y el prompt del cronjob `d6381ce58395`. Verificar que los archivos existen y que no contienen tokens ni claves.
- [x] 1.2 Revisar esos archivos y anotar en `referencia_hermes/NOTAS.md` las fuentes, endpoints, selectores, palabras clave, exclusiones y la clave que usa el historial. Verificar que las notas cubren cada script.
- [ ] 1.3 Ubicar en la configuración de Hermes el token de su bot de Telegram (anotar la ruta en `NOTAS.md`, sin copiar el valor) y revisar `hermes send --help` para saber si soporta HTML, la desactivación de la vista previa y qué longitud máxima admite. Verificar con `getMe` y `getChat` sobre el canal `-1004429829042` y sobre el chat de prueba usando ese token.

## 2. Esqueleto del proyecto

- [x] 2.1 Crear `pyproject.toml` con uv (Python ≥3.12, httpx, beautifulsoup4, lxml, pyyaml, pydantic, python-dotenv; dev: pytest, respx, ruff) y generar `uv.lock`. Verificar que `uv sync` y `uv run python -c "import httpx, bs4, pydantic"` funcionan.
- [x] 2.2 Crear la estructura de carpetas de design D2, más `.gitignore` (`.env`, `data/`, `logs/`) y `.env.example`. Verificar con `ls` y `git status`.
- [x] 2.3 Implementar `config.py` con modelos pydantic para `config.yaml` (fuentes, presupuestos, palabras clave núcleo y cola larga, filtros, categorías, banner, IA, resumen) y secretos de `.env`. Verificar con tests: configuración válida, campo inválido con mensaje claro y secreto faltante.
- [x] 2.4 Escribir el `config.yaml` inicial con las palabras clave de design D5 y los términos de D6 para todos los roles de TI. Verificar que la configuración carga sin errores en el test.
- [x] 2.5 Implementar `registro.py` (archivo diario + stdout, retención de 14 días, máscara de secretos) y `lock.py` (fcntl). Verificar con tests: la retención borra el log de hace 15 días, el token no aparece en el log y un segundo lock falla de inmediato.

## 3. Estado y deduplicación

- [x] 3.1 Implementar `estado.py` con el esquema de design D4, WAL, `esquema_version` y transacciones cortas. Verificar con un test que crea la base en un directorio temporal y abre todas las tablas.
- [x] 3.2 Implementar `normalizar.py` (minúsculas, sin tildes, limpieza de sufijos de empresa, huella). Verificar con tests de los escenarios "Misma vacante en dos fuentes" y "Límite de palabra".
- [x] 3.3 Implementar el dedupe por clave y huella, la limpieza (90 días para vistas, 30 para intentos y corridas, sin tocar incidentes abiertos) y el bloqueo de envío si la base no está inicializada. Verificar con tests de cada escenario de `deduplicacion-estado`.
- [x] 3.4 Implementar `migrar_historial.py` (subcomando `migrar`) según la estructura anotada en 1.2. Verificar con un test con un fixture de historial que importa N registros y que una segunda corrida no duplica.

## 4. Base de fuentes y rotación

- [x] 4.1 Implementar `fechas.py` (hoy, ayer, "hace N horas/días/semanas", fechas absolutas, zona America/Bogota). Verificar con tests de cada formato observado en las fuentes.
- [x] 4.2 Implementar `rotacion.py` con lote núcleo + cola larga persistente. Verificar con tests de los escenarios "Núcleo frecuente", "Avance de la rotación" y "Fin de la lista".
- [x] 4.3 Implementar `fuentes/base.py`: cliente por fuente, cabeceras, timeout, pausa aleatoria, presupuesto, detección de desafío, cooldown escalonado 2/6/24 h con reinicio al éxito, registro en `intentos` y clasificación de errores de red. Verificar con tests usando respx: 429 → cooldown 2 h, repetido → 6 h, éxito → reinicio, 200 con `cf-chl` → desafío, y timeout registrado.
- [ ] 4.4 Implementar `fuentes/getonboard.py` (API, filtro junior/sin experiencia y remoto LATAM) con un fixture JSON real. Verificar con un test del parser y con `uv run buscador.py --dry-run --fuente getonboard` contra la API real.

## 5. Filtros y clasificación

- [x] 5.1 Implementar `filtros.py` con el veredicto en el orden de la spec, el alcance geográfico y la categoría por área. Verificar con tests parametrizados con todos los escenarios de `filtrado-vacantes`, incluidos DBA, datos, soporte, redes, QA, ciberseguridad, "Junior sin área", "Practicante Contable" y remoto restringido.
- [x] 5.2 Implementar `ia_cliente.py` (chat JSON, saldo cacheado, presupuesto por propósito, `ia_uso` y sanitización). Verificar con tests usando respx: saldo bajo, 402, timeout, JSON inválido, tope diario, y que el payload no contiene token, clave ni chat id.
- [ ] 5.3 Implementar `clasificador.py` (lote, ids cortos, validación pydantic, caché por huella, pendientes con vencimiento de 24 h y política sin IA). Verificar con tests de cada escenario de "Clasificación IA", "Caché" y "Respaldo", y probar con un fixture de 20 títulos dudosos reales contra DeepSeek, revisando los veredictos a mano.
- [ ] 5.4 Agregar las métricas de descarte por regla y del clasificador a la tabla `corridas` y al log. Verificar con un test de una corrida simulada que comprueba los conteos.

## 6. Publicación en Telegram

- [x] 6.1 Implementar `formato.py` (encabezado singular y plural, orden de categorías, fichas de 3 o 4 líneas, fecha relativa, escape HTML y división ≤4096 repitiendo el título de categoría). Verificar con tests de cada escenario de `publicacion-telegram`, incluidas 40 vacantes y un título con `&`, `<` y `>`.
- [ ] 6.2 Implementar `notificador_telegram.py` con los backends `bot_api` (token del bot de Hermes leído de su configuración o del `.env`; solo sendMessage sin vista previa y sendPhoto) y `hermes_cli` (respaldo con `hermes send`), con chat real o de prueba y manejo de errores, incluido 401 por token inválido. Verificar con tests usando respx para `bot_api`, con un comando falso para `hermes_cli`, y con un envío real al chat de prueba con el bot de Hermes.
- [x] 6.3 Implementar el banner diario, nunca o siempre con la fecha persistida en `kv`, y la marca de enviada por mensaje confirmado. Verificar con tests: primer y segundo envío del día, y rechazo parcial de Telegram.

## 7. Orquestación y CLI

- [ ] 7.1 Implementar `buscador.py` con el flujo de design D3 y los modos `--dry-run`, `--fuente`, `--seed` y `--chat-prueba`, más los subcomandos `migrar` y `resumen`. Verificar con un test de extremo a extremo con fuentes mockeadas: vacantes nuevas → mensaje; sin novedades → nada; seed → nada enviado y todo visto.
- [ ] 7.2 Implementar `salud.py` (healthchecks start, éxito y fail, sin romper la corrida si falla). Verificar con tests usando respx y con un ping real al check de prueba.
- [ ] 7.3 Documentar en `README.md` la instalación local, los modos de ejecución y la configuración. Verificar ejecutando cada comando documentado.

## 8. Fuentes restantes

- [ ] 8.1 Implementar `fuentes/linkedin.py` (guest API con `f_E=1,2`, `f_TPR=r86400`, `location=Colombia`) con un fixture HTML. Verificar con un test del parser y con `--dry-run --fuente linkedin`.
- [ ] 8.2 Implementar `fuentes/computrabajo.py` con fixture y fechas relativas. Verificar con un test del parser y con `--dry-run --fuente computrabajo`.
- [ ] 8.3 Implementar `fuentes/elempleo.py`, reutilizando lo anotado del script viejo. Verificar con un test del parser y con `--dry-run --fuente elempleo`.
- [ ] 8.4 Implementar `fuentes/magneto.py` (endpoint JSON si existe). Verificar con un test del parser y con `--dry-run --fuente magneto`.
- [ ] 8.5 Implementar `fuentes/torre.py` filtrando a remoto LATAM/Colombia. Verificar con un test del parser y con `--dry-run --fuente torre`.
- [ ] 8.6 Evaluar la Agencia Pública de Empleo del SENA: implementarla si no exige login ni captcha, o dejarla desactivada y documentar el motivo. Verificar con `--dry-run --fuente sena` o con la nota en `config.yaml`.
- [ ] 8.7 Entregar al usuario un reporte del dry-run de todas las fuentes (crudas, filtradas por regla, dudosas, aceptadas y errores) con una muestra de fichas. Verificar que no hay senior ni vacantes fuera de TI en la muestra aceptada.

## 9. Incidentes, reportero y resumen

- [ ] 9.1 Implementar `incidentes.py` con las 7 reglas, el caso `red:sin_conexion`, la apertura y cierre, el recordatorio cada 24 h y la agrupación por corrida. Verificar con tests con historial simulado en SQLite para cada regla y para la falla de red total.
- [ ] 9.2 Implementar `reportero.py` (evidencia sanitizada, prompt fijo, validación de la respuesta, mensaje HTML con bloque `<pre>` para sugerencias, alerta plana, aviso de recuperación y aviso de saldo bajo una vez al día) aislado en try/except. Verificar con tests de cada escenario de `incidentes-reportero` y uno donde el reportero lanza una excepción y las vacantes quedan enviadas.
- [ ] 9.3 Implementar `--simular-incidente <fuente:tipo>`, que envía al chat de prueba sin tocar el estado. Verificar ejecutándolo para cada tipo, más saldo bajo y API caída, y mostrar los mensajes al usuario.
- [ ] 9.4 Implementar `resumen.py` (métricas de 24 h, una llamada a la IA, respaldo plano y control de una vez al día). Verificar con tests de los escenarios de `resumen-diario` y con un envío real al chat de prueba.

## 10. Despliegue en Fedora

- [ ] 10.1 Crear `deploy/buscador.service`, `deploy/buscador.timer`, `deploy/buscador-resumen.service` y `deploy/buscador-resumen.timer` según design D9. Verificar con `systemd-analyze --user verify` en Fedora.
- [ ] 10.2 Escribir `deploy/INSTALAR.md`: uv, clonar en `~/buscador-vacantes`, `.env` con chmod 600, `migrar`, `--seed`, copiar las unidades, `loginctl enable-linger`, desactivar la suspensión, crear el check en healthchecks.io y comandos de diagnóstico y rollback. Verificar siguiendo la guía en el PC Fedora.
- [ ] 10.3 Instalar en Fedora apuntando al chat de prueba, correr la migración y el seed, y activar los timers. Verificar con `systemctl --user list-timers` y con que healthchecks está en verde.

## 11. Verificación integral y paso a producción

- [ ] 11.1 Reiniciar el PC sin iniciar sesión y comprobar que la corrida se ejecuta (linger y `Persistent=true`). Verificar con `journalctl --user -u buscador` y healthchecks.
- [ ] 11.2 Desconectar la red durante una corrida y comprobar que solo aparece `red:sin_conexion`, sin cooldowns. Detener el timer 90 min y comprobar que healthchecks avisa.
- [ ] 11.3 Correr 24 h en paralelo con Hermes (buscador → chat de prueba) y entregar al usuario una comparación de cantidad, duplicados y relevancia.
- [ ] 11.4 Con aprobación explícita del usuario, apuntar `.env` al canal real y pausar (no borrar) el cronjob de Hermes `d6381ce58395` y `send_encabezado.py`. Verificar que el primer envío real llega al canal y que Hermes figura pausado.
- [ ] 11.5 Revisar los logs y el resumen diario tras 24 h en producción y ajustar presupuestos, palabras clave o filtros en `config.yaml`. Verificar que el ajuste queda registrado en la configuración.
