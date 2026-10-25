## Why

El reenvío con filtro (`correo-seguimiento-reenvio`) no ve los correos de reclutadores que no usan ninguna palabra clave, y obliga a configurar un filtro. Conectar Gmail directamente, en solo lectura, cubre todo el correo nuevo sin filtros, y el mismo acceso a Google permite crear las entrevistas en Google Calendar con sus recordatorios. La Gmail API es gratis. En modo «producción sin verificar» admite hasta 100 usuarios en toda la vida del proyecto, sin la caducidad de 7 días del modo de prueba, con la advertencia de app no verificada. Alcanza para el dueño y los primeros usuarios, y el reenvío sigue siendo la vía para los demás.

## What Changes

- **Proyecto de Google Cloud** (👤 del dueño):
  - Gmail API y Calendar API activadas;
  - pantalla de consentimiento externa con marca y política de privacidad;
  - un cliente OAuth web con la URL de regreso del servidor;
  - publicación en «producción sin verificar».
- **«Conectar Gmail» en `/correo`**:
  1. el bot explica la advertencia de app no verificada y qué se va a leer;
  2. abre la autorización de Google con el permiso `gmail.readonly`;
  3. el servidor recibe el regreso, valida el `state` atado al usuario y guarda el *refresh token* cifrado.
- **Lectura incremental**: cada pocos minutos, el servidor pide a Gmail los mensajes nuevos desde el último `historyId`, aplica el mismo descarte previo y pasa los que tienen señales al procesamiento de `correo-seguimiento-reenvio`. No guarda nada del resto del buzón.
- **Tope de 100 usuarios**: el asistente cuenta las conexiones. Cerca del tope (`tope_usuarios`, 90 por defecto) deja de ofrecer «Conectar Gmail» y ofrece solo el reenvío. El dueño recibe un aviso.
- **Google Calendar (opcional y aparte)**: con el permiso `calendar.events` (pedido con autorización incremental, solo si el usuario lo quiere), las entrevistas confirmadas se crean, actualizan o borran en su calendario principal. Sin ese permiso sigue el `.ics` del seguimiento.
- **Desconexión y revocación**: «Desconectar Gmail» y la baja revocan el token en Google y lo borran. Un token revocado desde la cuenta de Google se detecta y se le avisa al usuario.
- **Requisitos de Google**: la política de privacidad declara el cumplimiento de la «Limited Use» de la API Services User Data Policy.

## Capabilities

### New Capabilities
- `conexion-google-asistente`: la conexión OAuth opcional con Gmail (solo lectura) y Google Calendar, la lectura incremental del correo hacia el procesamiento de correos del seguimiento, el tope de usuarios del proyecto sin verificar, la sincronización de entrevistas con el calendario y la revocación.

### Modified Capabilities
<!-- Ninguna en openspec/specs/: `correo-seguimiento-asistente` y `seguimiento-proceso-asistente` llegan con sus changes, que se archivan antes que este. -->

## Impact

- Módulo nuevo `buscador_vacantes/asistente/google/`:
  - `oauth.py`: URL de autorización, `state` firmado, canje y renovación del token, revocación;
  - `gmail.py`: `history.list` y `messages.get`, que entrega los correos al análisis de `correo/`;
  - `calendario.py`: `events.insert`, `patch` y `delete`.

  Todo con `httpx` directo, sin el SDK de Google.
- `api.py`: `GET /api/v1/google/vuelta`. `datos.py`: tabla `conexiones_google` (versión de esquema siguiente) y la columna `buzones.via = 'gmail'`.
- `servicio.py` (lectura de Gmail cada `cada_min`), `conversacion.py` y `textos.py` (`/correo`: conectar y desconectar Gmail y Calendar).
- `config.yaml` (`asistente.google`: activo, tope de usuarios, intervalo, URL de regreso), `Secretos` y `.env.example` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).
- Política de privacidad (Limited Use), `guia-usuario.md` y `deploy/INSTALAR.md` (pasos de Google Cloud).
- Depende de `seguimiento-proceso-postulacion` y `correo-seguimiento-reenvio`.
