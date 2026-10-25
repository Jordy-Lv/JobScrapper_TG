## Context

- `Servicio.tareas_periodicas` corre cada 60 s en el mismo proceso asyncio que el bot y la API. Una tarea lenta o bloqueante frena todo, así que el IMAP (bloqueante en la biblioteca estándar) tiene que ir en un hilo.
- La IA es la de cada usuario (`ia/cliente.py`), con el tope `ia_usuario_dia`, esquemas pydantic y `contrato.datos()` para delimitar contenido de terceros, con la instrucción de ignorar órdenes que contenga. Las tareas son por proveedor en `config.yaml`. `seguimiento-proceso-postulacion` agrega las tareas opcionales con caída a la configuración de `responder`.
- `Cifrador` (`cifrado.py`) ya cifra datos sensibles con la clave maestra `ASISTENTE_CLAVE_CIFRADO`.
- El seguimiento expone `Procesos.registrar`/`abrir`, la prioridad de avisos, las preguntas de confirmación para la seguridad `media` y los recordatorios persistentes (tabla `recordatorios`).
- `comun/normalizar.py` ya normaliza nombres para comparar.

## Goals / Non-Goals

**Goals:**
- Un único procesamiento (`analizar → asociar → registrar`) que reciba un correo ya descargado sin importar la vía. `gmail-api-y-calendario` lo llama con los correos de la API.
- Ningún correo crudo persistido fuera del buzón del bot.
- Costo de IA acotado: descarte barato primero y tope por usuario y día.

**Non-Goals:**
- Enviar o responder correos, o abrir enlaces de los correos.
- Leer el buzón completo del usuario (eso es la opción de Gmail API, en otro change).
- Servidor SMTP propio: se usa un buzón existente.

## Decisions

### 1. Buzón: cuenta dedicada con alias `+token`, leída por IMAP
- **Por defecto:** una cuenta de Gmail del asistente (por ejemplo `asistente.postulador@gmail.com`) con verificación en dos pasos y una contraseña de aplicación en `.env` (`ASISTENTE_CORREO_USUARIO`, `ASISTENTE_CORREO_CLAVE`). Cada usuario recibe `asistente.postulador+<token>@gmail.com`.
- **El destinatario se reconoce** por `Delivered-To` / `X-Original-To` / `To`. Con reenvío, Gmail conserva el `To` original y entrega al alias.
- **Alternativa compatible sin código:** un dominio propio con reenvío catch-all (por ejemplo Cloudflare Email Routing) hacia el mismo buzón. En `config.yaml` solo cambia `dominio_alias` y el formato (`{token}@dominio`). Se descartó un servidor SMTP propio en el Fedora: puertos expuestos, SPF/DKIM y spam para nada.
- **Por qué IMAP con contraseña de aplicación** y no OAuth para el buzón del bot: es una sola cuenta propia del dueño, sin usuarios externos. Si Google retira las contraseñas de aplicación, la misma cuenta puede leerse con la Gmail API en modo de uso personal, sin verificación. Queda como plan B en `buzon.py`, detrás de la misma interfaz.

### 2. Lectura cada `cada_min` en un hilo, con borrado inmediato
- `buzon.py` usa `imaplib` + `email` (biblioteca estándar) dentro de `asyncio.to_thread`.
- Busca `UNSEEN`, descarga cada mensaje y llama al procesamiento. Si sale bien, marca `\Deleted` y hace `EXPUNGE`.
- Si falla por algo transitorio (IA saturada, red), lo deja sin leer y lo reintenta hasta 48 h. Después lo procesa sin IA (decisión 6) y lo borra.
- La tarea corre en `tareas_periodicas` con su propio intervalo (2 min por defecto) y un tope de mensajes por corrida.

### 3. Confirmación del reenvío y huella del origen
- **El correo de `forwarding-noreply@google.com`** se reconoce por el remitente y el asunto. Se extraen el código numérico y la dirección que pidió el reenvío, se le envían al usuario y se guarda `sha256(dirección normalizada + sal)` en `buzones.origen_hash`. Nunca se sigue el enlace de confirmación.
- **Outlook no manda confirmación.** El origen se toma del primer correo reenviado: `X-Forwarded-For`, `Resent-From` o el `To` original. Esa dirección se le muestra al usuario para que la confirme («¿Este es tu correo?»).
- **Seguridad de los correos siguientes:** si el origen de la cadena de reenvío no coincide con la huella, todo lo que se extraiga baja a `media`.

### 4. Pipeline de análisis
1. **Descarte** (`analisis.descartar`): alias inactivo, Message-ID visto (`correos_procesados`) o ninguna señal. Las señales son: remitente en `remitentes_portales`, palabra de `palabras_clave` en el asunto o el texto, o un adjunto `text/calendar`.
2. **Texto útil:** se prefiere `text/plain` y si no hay, `text/html` pasado por BeautifulSoup. Se quitan las citas de respuestas anteriores (`>`, «El … escribió:») y se corta en `max_caracteres` (6000).
3. **Calendario:** se lee con `icalendar` (dependencia nueva). Los `VEVENT` con `DTSTART` futuro dan fecha, hora, lugar y `URL` exactos y una clave de evento = UID del `.ics`. Se eligió `icalendar` porque las invitaciones reales traen `TZID` y reglas que un parser propio leería mal.
4. **Reglas de portales** (`plantillas_portales` en `config.yaml`): remitente más un patrón del asunto, que dan el tipo (por ejemplo, «vio tu hoja de vida» → `cv_visto`) y el enlace de la oferta. No gastan IA.
5. **IA**, solo si las reglas no lo resolvieron: tarea opcional `clasificar_correo` con el esquema `CorreoClasificado` (`tipo`, `empresa`, `cargo`, `fecha_hora` ISO o null, `zona`, `modalidad`, `lugar`, `contacto`, `pide_respuesta`, `plazo` ISO o null, `confianza` 0 a 1, `resumen` ≤ 200 caracteres). El correo va dentro de `datos("correo", …)`.
   - La fecha se valida en código: futura y en un rango razonable de 120 días o menos.
   - Si la IA no puede, se aplica la decisión 6.
6. **Enlaces de reunión:** se sacan del correo con expresiones por dominio (`dominios_reuniones`), nunca de la salida de la IA. Así un correo malicioso no puede hacer que el bot muestre un enlace de phishing.

### 5. Asociación (`asociacion.py`)
1. Enlace de oferta reconocido por las expresiones `id_oferta` de los JSON de selectores (las mismas de `leer-procesos-portales`) → `alta`.
2. Dominio del remitente, quitando dominios genéricos (gmail, hotmail, outlook, portales), que coincide con `procesos.dominio_contacto` → `alta`. La columna se llena cuando el usuario confirma una asociación.
3. Similitud de empresa y cargo normalizados con los procesos abiertos del usuario, por encima de un umbral → `media`.

Sin coincidencia se crea una pregunta de proceso nuevo. La IA no decide la asociación: solo extrae empresa y cargo.

### 6. Modo sin IA
Se usa cuando no hay clave, la clave es inválida, el tope está agotado o el correo lleva 48 h en reintento. Se aplican el calendario y las reglas de portales. Lo demás con señales genera la pregunta de clasificación manual, con empresa (dominio), asunto y botones. Se deduplica por remitente y día para no inundar al usuario.

### 7. Pedido de respuesta y borrador
- `pide_respuesta` genera recordatorios del tipo `respuesta` en la tabla `recordatorios` del seguimiento (mitad del plazo y 2 h antes, o 24 h sin plazo). «Ya respondí» los cancela.
- «Ver borrador» usa la tarea opcional `redactar_seguimiento` con un prompt de respuesta, y sin IA usa una plantilla. Se muestra para copiar.

### 8. Tablas (versión de esquema siguiente)

```sql
CREATE TABLE buzones (
  usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
  token TEXT NOT NULL UNIQUE, estado TEXT NOT NULL,  -- esperando | activo | inactivo
  via TEXT NOT NULL DEFAULT 'reenvio',               -- reenvio | gmail (otro change)
  origen_hash TEXT, creado TEXT NOT NULL, ultimo_correo TEXT
);
CREATE TABLE correos_procesados (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  mensaje_hash TEXT NOT NULL, ts TEXT NOT NULL, remitente TEXT, resultado_json TEXT,
  fragmento TEXT, proceso_id INTEGER REFERENCES procesos(id) ON DELETE SET NULL,
  UNIQUE (usuario_id, mensaje_hash)
);
```

Más la columna `procesos.dominio_contacto`. Un alias desactivado conserva su token como `inactivo` para reconocer y descartar los correos tardíos. La baja lo borra todo por la cascada, y desde ese momento los correos a ese token son de alias desconocido y se descartan igual.

## Risks / Trade-offs

- [Gmail no acepta un reenvío a una dirección `+alias`, o la marca como spam] → Probarlo en el piloto. Si falla, se cambia a dominio propio con catch-all (decisión 1), solo con configuración.
- [Google retira las contraseñas de aplicación] → Plan B: la Gmail API en modo de uso personal para el buzón del bot, detrás de la misma interfaz de `buzon.py`.
- [Prompt injection o phishing en los correos] → `datos()` más un esquema fijo, enlaces solo por expresiones de dominios permitidos, ninguna acción fuera de registrar y preguntar, y seguridad `media` para orígenes no confirmados.
- [Falsos positivos que molestan al usuario] → Descarte previo, umbral de confianza (por debajo de `confianza_min` se pregunta en vez de registrar) y deduplicación por remitente y día.
- [Costo de IA] → Tope `correos_ia_dia` (20 por defecto) dentro del `ia_usuario_dia` existente. Las reglas de portales y los calendarios no gastan IA.
- [Ley 1581 y confianza del usuario] → Solo se ve lo que el usuario filtra, no se guarda el correo, la retención es corta y la baja es inmediata. La política de privacidad se actualiza antes del piloto.

## Migration Plan

1. 👤 Crear la cuenta del buzón del bot con verificación en dos pasos y contraseña de aplicación, y cargar las variables en el `.env` del Fedora.
2. Desplegar con `asistente.correo.activo: false` y comprobar con `uv run buscador.py asistente correo probar` (nuevo subcomando de `cli.py`) que el IMAP conecta.
3. Activarlo y hacer un piloto con el correo del dueño: reenvío desde Gmail, un correo de portal real y uno de prueba con `.ics`.
4. **Para volver atrás:** `activo: false`. Los alias quedan, pero no se lee el buzón. Avisar a los usuarios con alias si se apaga por mucho tiempo.

## Open Questions

- El nombre exacto de la cuenta del buzón del bot (o el dominio propio) lo elige el dueño al crearla. Solo afecta a `config.yaml`.
