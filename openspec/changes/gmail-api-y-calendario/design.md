## Context

- `correo-seguimiento-reenvio` deja un procesamiento que recibe un correo ya descargado (`analizar → asociar → registrar`), la tabla `buzones` con `via` y el descarte previo por remitentes, palabras clave y calendario.
- El seguimiento guarda las entrevistas como eventos con fecha y manda `.ics`. Este change agrega el destino Google Calendar.
- La API del asistente (FastAPI) está publicada en `https://postulador.tailf6cdf1.ts.net/api/v1/…` (Tailscale Funnel). Ya sirve páginas HTML simples (`/vincular/{codigo}`, `/privacidad`).
- Google:
  - los permisos `gmail.readonly` (restringido) y `calendar.events` (sensible) son gratis de usar;
  - en «producción sin verificar», cada proyecto admite como máximo 100 usuarios nuevos en toda su vida, muestra la advertencia de app no verificada y no tiene la caducidad de 7 días del modo de prueba;
  - la verificación con auditoría CASA solo hace falta para pasar de ese tope.

## Goals / Non-Goals

**Goals:**
- Conexión de Gmail que no exige que el usuario configure filtros y que reusa todo el análisis del reenvío.
- Calendario sincronizado (crear, actualizar y borrar) sin duplicados.
- Ningún gasto: sin SDK pesado, sin Pub/Sub de pago y sin verificación de Google por ahora.

**Non-Goals:**
- Verificación de Google o auditoría CASA (se decide si se pasan los 100 usuarios).
- Enviar correos o modificar el buzón del usuario (no hay permiso de escritura en Gmail).
- Otros proveedores (Outlook con Microsoft Graph). Siguen con el reenvío.

## Decisions

### 1. OAuth web con `state` firmado
- **Cliente** «Aplicación web» con regreso `https://<servidor>/api/v1/google/vuelta`. Desde Telegram, el usuario recibe un botón con URL a `GET /api/v1/google/conectar?t=<ticket>`, un ticket de un solo uso guardado en `kv` con 10 min de vida. Esa ruta redirige a Google con `access_type=offline`, `prompt=consent`, `include_granted_scopes=true` y `state = ticket`. Al volver, `/vuelta` valida y consume el ticket y canjea el `code`.
- **Por qué un ticket propio y no el id del usuario:** no se puede adivinar, no se reusa y vence. Sin sesión web, el ticket es la única atadura entre Telegram y el navegador.
- **Se descartó el flujo de dispositivo** («ingresa este código en google.com/device») porque Google no lo permite con permisos de Gmail. También se descartó el cliente de escritorio con loopback, que no sirve para un servidor remoto.

### 2. `httpx` directo en vez del SDK de Google
Hacen falta seis llamadas:
- token: canje y renovación;
- revocación;
- `users.history.list` y `users.messages.get`;
- `events.insert`/`patch`/`delete`.

El SDK `google-api-python-client` agrega muchas dependencias y es síncrono. Con `httpx` (ya en el stack) y `respx` para las pruebas queda coherente con los clientes de IA. El access token se renueva cuando vence y se guarda solo en memoria.

### 3. Lectura incremental por `historyId`, sin Pub/Sub
- **La primera vez:** `users.getProfile` da el `historyId` actual y se listan los mensajes de las últimas 24 h con `messages.list?q=newer_than:1d`.
- **Después:** cada `cada_min` (3 por defecto), `history.list?startHistoryId=…&historyTypes=messageAdded`. Si Google responde 404 (historial vencido), se reinicia como la primera vez.
- **Descarte antes de descargar:** por cada mensaje nuevo se pide `messages.get?format=metadata` (From, To, Subject, Content-Type). El descarte previo se aplica con esos datos más los dominios de los procesos del usuario. Solo los que pasan se piden en `format=raw`, se convierten con `email.message_from_bytes` y entran al mismo procesamiento del reenvío.
- **Se descartó `users.watch` con Pub/Sub:** exige un tema y un endpoint público para las notificaciones, y otra pieza que mantener. Para avisos de entrevistas, 3 minutos de latencia sobra.

### 4. Señal extra para Gmail: dominios de procesos
Como no hay filtro del usuario, el descarte previo agrega una señal: un remitente cuyo dominio coincide con `procesos.dominio_contacto` o con el de la empresa de un proceso abierto. Así entra «¿podemos hablar mañana?» del reclutador, que el filtro de palabras perdería.

### 5. Tablas (versión de esquema siguiente)

```sql
CREATE TABLE conexiones_google (
  usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
  cuenta_hash TEXT NOT NULL,          -- huella del correo de Google (contar usuarios únicos)
  token_cifrado TEXT NOT NULL,        -- refresh token cifrado con Cifrador
  permisos TEXT NOT NULL,             -- gmail.readonly[,calendar.events]
  history_id TEXT, conectada TEXT NOT NULL, ultima_lectura TEXT, error TEXT
);
```

- `kv` guarda `google_cuentas_conectadas` (conjunto de huellas, nunca se borra) para respetar el tope de por vida aunque el usuario se desconecte. Así lo cuenta Google: el tope no se reinicia.
- Los eventos de calendario guardan su `id` de Google en `proceso_eventos.datos_json` (`calendario_id`).

### 6. Gmail conectado desactiva el reenvío del usuario
Al conectar, `buzones.via = 'gmail'` y el alias pasa a `inactivo`. El asistente le recuerda al usuario quitar el filtro de reenvío para no duplicar. Si de todos modos llega un correo por las dos vías, la deduplicación por Message-ID lo procesa una sola vez.

### 7. Calendario: autorización incremental y sincronización por evento
- «Agregar entrevistas a Google Calendar» pide `calendar.events` con `include_granted_scopes=true`. Con ese permiso, al confirmar una entrevista se llama a `events.insert` en `primary` con `reminders.overrides` de 60 y 15 min y `extendedProperties.private.proceso = id`.
- Una reprogramación hace `patch` con el `calendario_id` guardado, y un cierre antes de la fecha hace `delete`.
- **Si Calendar falla**, se manda el `.ics` como respaldo y se registra el error.

### 8. Página de regreso y textos de Google
- `/vuelta` responde con una página HTML mínima (mismo estilo que `/vincular`): «Listo, vuelve a Telegram» o el error.
- La pantalla de consentimiento usa:
  - la página de privacidad existente, ampliada con la declaración de Limited Use;
  - una página de inicio, que puede ser la misma `/privacidad`.

## Risks / Trade-offs

- [Google no acepta el dominio `*.ts.net` como dominio autorizado o URL de regreso] → Probarlo primero (tarea 1.1). Si falla, se usa un dominio propio barato apuntando al Funnel, o un proxy en Cloudflare, y solo cambia `url_regreso`.
- [Tope de 100 cuentas de por vida] → Tope propio más bajo (90), aviso al dueño y reenvío como alternativa sin límite. Para pasarlo, verificación más CASA (decisión del dueño a futuro).
- [Las cuentas institucionales (SENA, universidades) bloquean las apps no verificadas] → El mensaje de error de Google se traduce a «tu cuenta no permite apps externas: usa el reenvío», con el botón directo.
- [La advertencia de app no verificada asusta] → El bot la explica antes, con una captura y el paso «Avanzado → Ir a…».
- [Robo de la base] → Tokens cifrados con la clave maestra, que vive solo en el `.env`, y permiso de solo lectura de Gmail. El dueño puede revocar todos los tokens desde la consola de Google en caso de incidente.

## Migration Plan

1. 👤 Crear el proyecto de Google Cloud y el cliente, probar el dominio de regreso y cargar `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` en el `.env`.
2. Desplegar con `asistente.google.activo: false`.
3. Activar y probar solo con la cuenta del dueño, con el proyecto todavía en modo de prueba para no gastar el tope.
4. Pasar el proyecto a «producción sin verificar» y abrirlo a los usuarios.
5. **Para volver atrás:** `activo: false`. Deja de leer y de ofrecer la conexión, y los tokens quedan cifrados. Si se abandona del todo, revocarlos con el subcomando de limpieza.
