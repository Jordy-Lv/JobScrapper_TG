## 1. Google Cloud (del dueño)

- [ ] 1.1 👤 Crear el proyecto en Google Cloud con una cuenta dedicada y activar Gmail API y Calendar API. Configurar la pantalla de consentimiento externa (nombre, logo, correo de soporte, página de privacidad) y agregar los permisos `gmail.readonly` y `calendar.events`. Crear el cliente OAuth «Aplicación web» con la URL de regreso del servidor. Verificar que Google acepta el dominio `*.ts.net`. Si no, decidir el dominio propio antes de seguir y anotarlo en la memoria.
- [ ] 1.2 👤 Dejar el proyecto en modo de prueba con el correo del dueño como usuario de prueba y cargar `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` en el `.env` del Fedora. Verificar con el subcomando de 5.3.

## 2. Configuración y datos

- [ ] 2.1 🟢 `Secretos` (`google_client_id`, `google_client_secret`), `.env.example` y la sección `asistente.google` en `config.yaml` / `comun/config.py` (activo, tope de usuarios, intervalo, URL de regreso, recordatorios del calendario). Verificar con la prueba de configuración y el enmascarado de secretos en los logs.
- [ ] 2.2 🟡 Tabla `conexiones_google` en la versión de esquema siguiente, conjunto de cuentas conectadas en `kv` y `buzones.via = 'gmail'`. Verificar con pruebas de `test_datos.py`, incluida la cascada de la baja.

## 3. OAuth

- [ ] 3.1 🟡 `google/oauth.py`: ticket de un solo uso con 10 min de vida, URL de autorización (`offline`, `consent`, `include_granted_scopes`), canje, renovación y revocación con `httpx`, y tokens cifrados con `Cifrador`. Verificar con `respx`: canje válido, `state` vencido o reusado, `invalid_grant` y revocación.
- [ ] 3.2 🟡 Rutas `GET /api/v1/google/conectar` y `GET /api/v1/google/vuelta` con su página HTML mínima, y aviso por Telegram al conectar o fallar. Verificar con pruebas en `test_api.py` para cada escenario de «Conexión opcional con Gmail».
- [ ] 3.3 🟡 `/correo`: «Conectar Gmail» (explicación de la advertencia), «Agregar entrevistas a Google Calendar», «Desconectar Gmail», tope de usuarios con aviso al dueño y error de cuenta institucional traducido. Verificar con pruebas en `test_bot.py`, incluido el escenario «Tope alcanzado».

## 4. Lectura de Gmail y calendario

- [ ] 4.1 🟡 `google/gmail.py`: primera lectura (`getProfile` y las últimas 24 h), `history.list` incremental, reinicio ante 404, `format=metadata` para el descarte con la señal de dominios de procesos, `format=raw` solo para los que pasan, y entrega al procesamiento de `correo/`. Verificar con `respx` y los `.eml` de `tests/fixtures/correo/`: el correo personal no se descarga completo y el del reclutador sin palabras clave sí.
- [ ] 4.2 🟢 Desactivar el alias de reenvío al conectar Gmail y comprobar que la deduplicación procesa una sola vez un correo que llega por las dos vías. Verificar con una prueba.
- [ ] 4.3 🟡 `google/calendario.py`: `insert` al confirmar una entrevista, `patch` al reprogramar, `delete` al cerrar antes de la fecha, y `.ics` de respaldo si falla. Verificar con `respx` para cada escenario de «Calendario opcional».
- [ ] 4.4 🟢 Tarea periódica de lectura en `servicio.py` (solo si `activo`) y manejo de `invalid_grant` con un aviso único al usuario. Verificar con pruebas de `test_servicio.py`.

## 5. Privacidad, documentación y herramientas

- [ ] 5.1 🟢 Ampliar la política de privacidad (qué se lee de Gmail, Limited Use, revocación) y `guia-usuario.md` (conectar Gmail y Calendar, la advertencia, cómo revocar). Verificar leyendo el texto y con la prueba de la página de privacidad.
- [ ] 5.2 🟢 `deploy/INSTALAR.md`: pasos de Google Cloud, modo de prueba, publicación sin verificar y el tope de 100. Verificar leyendo el texto.
- [ ] 5.3 🟢 Subcomandos `asistente google probar` (valida el cliente contra el endpoint de descubrimiento) y `asistente google revocar-todo` (para incidentes). Verificar con pruebas de `test_cli.py` y `respx`.

## 6. Cierre local

- [ ] 6.1 🔴 Suite completa y `ruff` en segundo plano. Verificar con todo en verde. Recomendar sesión nueva antes de empezar si el contexto está cargado.
- [ ] 6.2 🟢 Commit solo de los archivos de este change, en español y sin atribuciones a la IA. Verificar con `git show --stat` y `git log -1 --format=%B`.

## 7. Despliegue y piloto

- [ ] 7.1 👤 Desplegar con `activo: false`, activar y conectar el Gmail del dueño con el proyecto en modo de prueba. Mandarse un correo de un «reclutador» sin palabras clave desde un dominio de un proceso y verificar el aviso y la card.
- [ ] 7.2 👤 Conectar el calendario, confirmar una entrevista de prueba, reprogramarla y cerrar el proceso. Verificar en Google Calendar que se crea, se mueve y se borra el evento.
- [ ] 7.3 👤 Pasar el proyecto a «producción sin verificar» y repetir la conexión con una segunda cuenta de prueba. Verificar que no caduca a los 7 días (revisar a los 8 días).
- [ ] 7.4 🟢 Archivar con `/opsx:archive` (después de `correo-seguimiento-reenvio`). Verificar con `openspec validate` y `openspec list`.
