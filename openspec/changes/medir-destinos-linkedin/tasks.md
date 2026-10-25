## 1. Reconocimiento de las páginas públicas

- [x] 1.1 🟡 Con 6 vacantes de LinkedIn de `vacantes.db` (2 con Solicitud sencilla, 2 externas y 1 cerrada, elegidas mirando LinkedIn en el navegador **sin sesión**), descargar `jobs-guest/jobs/api/jobPosting/{id}` y `/jobs/view/{id}` y anotar en `design.md` (Open Questions) qué recurso trae el tipo de solicitud y el enlace externo, y con qué marcado. Verificar con la tabla de hallazgos escrita en `design.md`.
- [ ] 1.2 🟢 Guardar los recortes sin datos personales en `tests/fixtures/linkedin/solicitud_{sencilla,externa,cerrada}.html`. Si ningún recurso trae la solicitud, anotarlo, saltar al grupo 5 y reducir el grupo 2 a 2.2 y 2.3. Verificar que los fixtures existen y no contienen nombres ni correos.

## 2. Funciones puras (pruebas primero)

- [ ] 2.1 🟡 `tests/asistente/test_medicion_linkedin.py` y `buscador_vacantes/asistente/medicion_linkedin.py`: `extraer_solicitud(html)` devuelve el tipo (`sencilla`, `externa`, `cerrada` o `desconocido`), la URL y el motivo para los tres fixtures y para un HTML vacío. Verificar con las pruebas en verde.
- [ ] 2.2 🟢 `limpiar_destino(url)`: desenvuelve `externalApply…?url=` y quita `trk`, `refId`, `trackingId` y `utm_*`. `familia_de(url, familias)`: host igual al patrón o terminado en `.patrón`, y `propio` si no coincide. Casos: Workday con subdominio `wd3`, Greenhouse `job-boards.`, Computrabajo `co.`, dominio de empresa. Verificar con las pruebas.
- [ ] 2.3 🟢 `pide_cuenta(html, senales)`: `True` con `input[type=password]` o una señal de texto, `False` con un formulario sin contraseña, `None` con una página casi vacía (armada con JS). `resumen(resultados)`: conteos y porcentajes por tipo y por familia, en orden descendente, sin títulos ni empresas. Verificar con las pruebas.

## 3. Comando de medición

- [ ] 3.1 🟢 `config.yaml` y `buscador_vacantes/comun/config.py`: sección `asistente.medicion_linkedin` (`muestra: 100`, `pausa_s: 8`, `salida`, `familias`, `senales_cuenta`), validada con pydantic. Verificar con `tests/comun/test_config.py`.
- [ ] 3.2 🟡 Bucle `async` `medir(...)`: toma la muestra de `vacantes.db` (solo lectura, más recientes primero), reanuda desde el JSON existente, consulta el cooldown de `linkedin` en `fuentes_estado`, hace una petición por vacante con pausa aleatoria alrededor de `pausa_s`, se detiene ante 429, 999 o desafío y guarda lo medido, y abre cada destino una vez con `Ritmo`. Pruebas con `respx`: muestra limitada, reanudación, cooldown vigente sin peticiones, 999 en la vacante 3 (guarda 2 y avisa), destino que exige cuenta. Verificar con las pruebas.
- [ ] 3.3 🟢 Subcomando `buscador.py asistente medir-linkedin [--muestra N] [--salida RUTA]` en `asistente/cli.py`, que imprime el resumen en Markdown. Verificar con una prueba de CLI sobre una base temporal y con `--help`.
- [ ] 3.4 🟡 Suite completa en segundo plano (`.venv/Scripts/python -m pytest`) y `.venv/Scripts/ruff check`. Verificar con las dos cosas en verde.

## 4. Medición real

- [ ] 4.1 👤 En el Fedora, fuera del horario del radar: `git pull --ff-only` en la rama del change y `uv run buscador.py asistente medir-linkedin`. Si paró por bloqueo, esperar al día siguiente y relanzar (reanuda). Verificar con el resumen impreso y el JSON en `data/asistente/`.
- [ ] 4.2 🟡 Revisar a mano 5 resultados por cada una de las 3 familias más frecuentes y 5 `propio`, abriendo el destino sin sesión: ¿la familia y `pide_cuenta` son correctos? Verificar anotando los aciertos en `portales.md`.

## 5. Respaldo manual (solo si 1.2 concluyó que las páginas públicas no muestran la solicitud)

- [x] 5.1 👤 El dueño, en su sesión de LinkedIn y pulsando él mismo, recorre 30 vacantes del canal y anota en una hoja el tipo de solicitud y la URL a la que llega «Solicitar». Verificar con la hoja entregada. *(2026-10-21: por decisión del dueño se hizo con su sesión en Chrome, leyendo el DOM sin pulsar nada; hoja en `data/medicion_linkedin_manual.csv` y resultados en `design.md`.)*
- [ ] 5.2 🟢 Pasar esas URL por `familia_de` y `resumen` con un pequeño script de una sola vez (sin commitear la hoja). Verificar con el resumen en `portales.md`.

## 6. Documentación y siguiente paso

- [x] 6.1 🟢 `docs/asistente/portales.md`, sección «LinkedIn»: la decisión del dueño del 2026-10-21 (externas más Solicitud sencilla, para el dueño y los invitados, con envío automático en páginas desconocidas), el riesgo de restricción de cuentas por la sección 8.2 de las condiciones de LinkedIn, la exigencia de la aceptación expresa de cada invitado y la regla de no crear cuentas ni escribir credenciales en los ATS. Verificar releyendo la sección.
- [ ] 6.2 🟢 Misma sección: resumen de la medición (tipos, familias, cuántas piden cuenta y aciertos de 4.2) y la prioridad de adaptadores que se desprende. Verificar con la tabla en el documento.
- [x] 6.3 🟢 Proponer con el dueño el change de postulación en LinkedIn (clasificador de destino, modo genérico por bucle, controles ARIA e iframes, permisos opcionales amplios, Solicitud sencilla, aceptación del riesgo por usuario y adaptadores de las familias prioritarias). Verificar con el change creado en `openspec/changes/`.
