## 1. Preparación

- [ ] 1.1 👤 Crear la cuenta de correo del buzón del bot con verificación en dos pasos y una contraseña de aplicación, y probar a mano desde el Gmail del dueño que se puede agregar `cuenta+prueba@gmail.com` como dirección de reenvío. Verificar anotando el resultado en la memoria. Si Gmail rechaza el `+alias`, decidir el dominio propio antes de seguir (diseño, decisión 1).
- [ ] 1.2 🟡 Juntar correos de ejemplo anonimizados en `tests/fixtures/correo/` (`.eml`):
  - confirmación de reenvío de Gmail;
  - CV visto y postulación de Computrabajo, Magneto y elempleo;
  - invitación con `.ics` y `TZID`;
  - entrevista de un reclutador sin `.ics`;
  - rechazo;
  - pedido de disponibilidad con plazo;
  - boletín sin señales;
  - correo con instrucciones maliciosas y un enlace de phishing;
  - reenvío desde Outlook.

  Verificar con una prueba que los lee todos con `email`.

## 2. Configuración y datos

- [ ] 2.1 🟢 `Secretos` (`asistente_correo_usuario`, `asistente_correo_clave`), `.env.example` y la sección `asistente.correo` en `config.yaml` / `comun/config.py` (servidor IMAP, formato del alias, intervalo, remitentes y palabras del filtro, plantillas de portales, dominios de reuniones, topes, `confianza_min`, retención, `activo: false`). Verificar con la prueba de carga de configuración y el enmascarado de secretos en los logs.
- [ ] 2.2 🟢 Agregar `icalendar` a `pyproject.toml` y `uv.lock`. Verificar con `uv sync` y que importa.
- [ ] 2.3 🟡 Tablas `buzones` y `correos_procesados` y la columna `procesos.dominio_contacto`, en la versión de esquema siguiente. Verificar con pruebas en `test_datos.py` (base nueva, migración y cascada de la baja).

## 3. Buzón y alta

- [ ] 3.1 🟡 `correo/buzon.py`: conexión IMAP en `asyncio.to_thread`, `UNSEEN`, descarga, borrado con `EXPUNGE`, reintento hasta 48 h y tope por corrida, detrás de una interfaz que admita otro lector. Verificar con pruebas sobre un IMAP falso (servidor en memoria o un doble de `imaplib`).
- [ ] 3.2 🟡 `correo/alta.py` y `/correo` en `conversacion.py`: crear el alias con token aleatorio, pasos para Gmail y Outlook con el filtro para copiar, estados `esperando`/`activo`/`inactivo`, «Desconectar» con los pasos para quitar el reenvío. Verificar con pruebas en `test_bot.py` para cada escenario de «Dirección personal de reenvío» y «Desconexión».
- [ ] 3.3 🟡 Correo de confirmación de Gmail: extraer el código y la dirección, enviarlos al usuario, guardar la huella del origen y no seguir el enlace. Reenvío de Outlook: confirmar el origen con el usuario. Verificar con los fixtures de 1.2.

## 4. Análisis y asociación

- [ ] 4.1 🟡 `correo/analisis.py`: descarte previo (sin IA), texto útil sin citas, `.ics` con `icalendar` y plantillas de portales. Verificar con pruebas sobre los fixtures: el boletín se descarta sin llamar a la IA, el `.ics` da la hora exacta en America/Bogota y el CV visto de Computrabajo sale por regla.
- [ ] 4.2 🟡 Tarea de IA opcional `clasificar_correo` con el esquema `CorreoClasificado`, `datos()`, validación de fechas en código, `confianza_min`, tope `correos_ia_dia` y enlaces de reunión solo por expresiones de dominios permitidos. Verificar con un cliente IA falso: el rechazo da `descartado`, el correo malicioso no cambia nada fuera de su evento y el enlace de phishing no aparece en el aviso.
- [ ] 4.3 🟡 Modo sin IA (sin clave, tope agotado, 48 h de reintento) con la pregunta de clasificación manual deduplicada por remitente y día. Verificar con pruebas del escenario «Tope agotado».
- [ ] 4.4 🟡 `correo/asociacion.py`: enlace de oferta, dominio del remitente confirmado, empresa y cargo parecidos, y pregunta de proceso nuevo. Llenar `dominio_contacto` al confirmar. Verificar con pruebas para cada escenario de «Asociación con un proceso», incluida la seguridad `media` con un origen no confirmado.

## 5. Avisos y recordatorios

- [ ] 5.1 🟡 Registrar los eventos con `Procesos.registrar` (clave = UID del `.ics` o huella del Message-ID) y pintar los avisos según la seguridad: alta → aviso, media → pregunta con «Sí», «Es de otra» y «No es nada». Verificar con pruebas de punta a punta, desde el `.eml` hasta el mensaje de Telegram falso.
- [ ] 5.2 🟡 Pedido de respuesta: aviso urgente con plazo, «Ver borrador» y «Ya respondí», y recordatorios a mitad del plazo y 2 h antes (o 24 h sin plazo) en la tabla `recordatorios`. Verificar con pruebas de reloj fijo del escenario «Confirmar disponibilidad».
- [ ] 5.3 🟢 Tarea periódica en `servicio.py` cada `cada_min` (solo si `activo`) y limpieza diaria de `correos_procesados` por retención. Verificar con pruebas de `test_servicio.py`.
- [ ] 5.4 🟢 Subcomando `asistente correo probar` en `cli.py` que conecta al IMAP y cuenta los mensajes sin leer, sin procesarlos. Verificar con una prueba de `test_cli.py` y un IMAP falso.

## 6. Documentación y cierre local

- [ ] 6.1 🟢 Política de privacidad en `config.yaml` (qué se lee, qué se guarda, cuánto tiempo y cómo desconectar), `guia-usuario.md` (cómo activar el reenvío en Gmail y Outlook) y `deploy/INSTALAR.md` (buzón del bot y variables). Verificar leyendo el texto y con la prueba de la página de privacidad.
- [ ] 6.2 🔴 Suite completa y `ruff` en segundo plano. Verificar con todo en verde. Recomendar sesión nueva antes de empezar si el contexto está cargado.
- [ ] 6.3 🟢 Commit solo de los archivos de este change, en español y sin atribuciones a la IA. Verificar con `git show --stat` y `git log -1 --format=%B`.

## 7. Despliegue y piloto

- [ ] 7.1 👤 Cargar las variables del buzón en el `.env` del Fedora, desplegar con `activo: false` y correr `uv run buscador.py asistente correo probar`. Verificar que conecta.
- [ ] 7.2 👤 Activar y hacer el piloto con el Gmail del dueño: `/correo`, agregar el reenvío con el código que entrega el bot, crear el filtro y mandarse un correo de prueba con «entrevista» y una invitación de calendario. Verificar el aviso, la card, el `.ics` y que el correo ya no está en el buzón del bot.
- [ ] 7.3 👤 Esperar un correo real de un portal (CV visto o postulación) y revisar que se clasifica y asocia bien. Verificar en la card y en `correos_procesados`.
- [ ] 7.4 🟢 Archivar con `/opsx:archive` (después de `seguimiento-proceso-postulacion`). Verificar con `openspec validate` y `openspec list`.
