## Context

- Las postulaciones viven en `postulaciones`, con la máquina de estados técnica de `cola.py` (`E`). Al terminar, solo quedan las columnas `seguimiento` (texto libre: `postulada`/`descartada` en el respaldo) y `recordado` (el recordatorio único de `Conversacion.recordatorios`, a los `recordatorio_dias`).
- La card (`tarjeta_postulacion.py`) es una función pura de `Card` (estado en `kv`, `card:{pid}`) y `Datos` (leídos de la base). La card confirmada hoy solo tiene vistas y «Generar guía para entrevista». El spec principal habla de los botones Entrevista y Rechazada, que ya no están en el código. El delta de este change fija lo que vale.
- `Servicio.tareas_periodicas` corre cada 60 s (`cola.vigilar`, `recordatorios`, `borrar_vencidos`) y `_tareas_diarias` cada `grupo.comprobar_cada_h`.
- `Detalles.obtener` (en `detalle.py`) descarga el detalle de una vacante con pausas por dominio y cooldown por fuente, y deja `estado_pagina` en `ok | cerrada | bloqueada`.
- La baja borra la fila de `usuarios` y todo lo demás cae por `ON DELETE CASCADE`.
- Cada usuario usa su propia clave de IA (`ia/cliente.py`, tope `ia_usuario_dia`). Las tareas de IA se declaran por proveedor en `config.yaml` y todas son obligatorias.

## Goals / Non-Goals

**Goals:**
- Un modelo de proceso y eventos que los changes de portal y de correo usen sin modificarlo: solo agregan eventos con otro origen.
- Recordatorios que sobreviven a reinicios del servicio y no se duplican.
- Cero cambios en la máquina de estados técnica de la postulación.

**Non-Goals:**
- Leer portales o correo (otros changes).
- Crear eventos en Google Calendar (`gmail-api-y-calendario`). Aquí solo va el `.ics`.
- Enviar mensajes a empresas o reclutadores. El asistente solo redacta borradores.

## Decisions

### 1. Tablas `procesos`, `proceso_eventos` y `recordatorios` (esquema 5)

```sql
CREATE TABLE procesos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  postulacion_id INTEGER UNIQUE REFERENCES postulaciones(id) ON DELETE SET NULL,
  plataforma TEXT, empresa TEXT, cargo TEXT, url TEXT,
  id_oferta TEXT,              -- id de la oferta en el portal (para asociar señales)
  estado TEXT NOT NULL,        -- derivado; se recalcula al agregar un evento
  externo INTEGER NOT NULL DEFAULT 0,
  creado TEXT NOT NULL, actualizado TEXT NOT NULL, ultimo_evento TEXT,
  cerrado_en TEXT, avisos_json TEXT   -- reglas ya avisadas: {"seguimiento": ts, ...}
);
CREATE TABLE proceso_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proceso_id INTEGER NOT NULL REFERENCES procesos(id) ON DELETE CASCADE,
  ts TEXT NOT NULL, tipo TEXT NOT NULL, origen TEXT NOT NULL,
  seguridad TEXT NOT NULL DEFAULT 'alta', confirmado INTEGER,  -- NULL: pendiente (media)
  clave TEXT,                  -- identificador del hecho en su fuente (dedupe)
  datos_json TEXT,
  UNIQUE (proceso_id, origen, clave)
);
CREATE TABLE recordatorios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proceso_id INTEGER NOT NULL REFERENCES procesos(id) ON DELETE CASCADE,
  evento_id INTEGER REFERENCES proceso_eventos(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,          -- entrevista_24h | entrevista_2h | entrevista_15m | diferido
  enviar_en TEXT NOT NULL, vence_en TEXT, enviado_en TEXT, cancelado INTEGER NOT NULL DEFAULT 0,
  datos_json TEXT
);
```

- **Por qué una tabla aparte y no más estados en `postulaciones`:** los procesos externos no tienen postulación ni `id_corto`, y mezclar los estados de selección con los técnicos rompería las transiciones condicionales de `cola.py`.
- **`usuario_id` directo en `procesos`:** sirve para que la cascada de la baja funcione también con los procesos externos.
- **Migración:** las postulaciones `enviada`/`ya_postulada` existentes, y las `respaldo` con `seguimiento = 'postulada'`, reciben un proceso. `seguimiento = 'descartada'` crea el proceso `archivado`. Los valores `entrevista`/`rechazada` que existan pasan a eventos de origen `usuario`. La columna `seguimiento` se deja de escribir, pero no se borra.

### 2. Estado derivado con un orden de avance
`procesos.py` define el rango de cada tipo: `enviado` 0 < `cv_visto` 1 < `en_proceso` 2 < `contacto` 3 < `entrevista` 4 = `prueba` 4 < `oferta` 5 < `contratado` 6. Los cierres son `descartado`, `sin_respuesta` y `archivado`. Hay tres reglas:
- el estado es el evento confirmado de mayor rango;
- un cierre gana si es posterior al último avance;
- un avance posterior a un cierre reabre el proceso.

Los eventos `media` sin confirmar no cuentan. Es una función pura sobre la lista de eventos, fácil de probar con tablas de casos. Se descartó guardar transiciones explícitas: con varias fuentes que llegan en desorden (el portal tarda horas, el correo minutos), derivar es más robusto.

### 3. Una sola entrada para todas las fuentes
`Procesos.registrar(proceso_id, tipo, origen, seguridad, clave, datos, ahora) -> Resultado` inserta el evento (con `INSERT OR IGNORE` por la clave única), recalcula el estado, reprograma los recordatorios si es una entrevista y devuelve qué avisar: nada, editar la card, mensaje urgente o pregunta de confirmación. `Conversacion` pinta según ese resultado. Los changes de portal y de correo llaman solo a esto.

### 4. Botones y entrada de fecha
- Callbacks nuevos `pav:{pid}:{tipo}` (avance) y `pmas:{pid}` (vista «Más»). El callback viejo `seg` sigue respondiendo: `postulada`/`descartada` en el respaldo, y `entrevista`/`rechazada` de cards viejas se traducen a eventos.
- «Entrevista» pone la card en una fase nueva, `FECHA`, que espera texto, igual que las preguntas de texto libre: el texto se borra del chat y la card muestra lo entendido.
- **Parser de fechas propio** (`fechas_es.py`, en `comun/` o `asistente/`): días de la semana, «hoy», «mañana», «pasado mañana», `dd/mm`, `dd de <mes>`, `h`, `h:mm`, `am/pm`, «m.», «del mediodía».
  - Siempre devuelve fechas futuras en America/Bogota.
  - Si falla, la IA del usuario resuelve la fecha con la tarea opcional `interpretar_fecha`, y si no hay IA se pide reescribir.
  - Se descartó `dateparser` por su peso y por su ambigüedad con el español.
- Después de la fecha, la card ofrece «Agregar enlace o lugar» y «Listo». Así la confirmación no se alarga.

### 5. Recordatorios persistentes
- `Conversacion.recordatorios(ahora)` pasa a atender también la tabla `recordatorios`, cada 60 s: envía los que tienen `enviar_en <= ahora`, no están enviados ni cancelados y su `vence_en` (la hora de la entrevista) es posterior a `ahora`.
- Al reprogramar se cancelan los pendientes del mismo evento y se crean los nuevos.
- Los avisos diferidos por las horas de silencio se guardan como recordatorios de tipo `diferido`, así sobreviven a un reinicio.

### 6. `.ics` generado a mano
- Se usa un generador mínimo en `ics.py`: `VCALENDAR` con `VTIMEZONE` fijo de America/Bogota (UTC-5, sin horario de verano), `VEVENT` con `UID = proceso-{id}-entrevista@<bot>`, `SEQUENCE` igual al número de reprogramaciones, `DTSTART`/`DTEND` (duración por defecto 1 h) y `VALARM` de 1 h.
- El texto se escapa según RFC 5545 y las líneas se pliegan a 75 octetos.
- Se descartó la librería `icalendar` para generar porque no hace falta. `correo-seguimiento-reenvio` decidirá si la usa para *leer* invitaciones.

### 7. Reglas diarias y revisión de vacantes
- `_tareas_diarias` llama a `procesos.aplicar_reglas(ahora)`. Cada regla anota en `avisos_json` cuándo avisó y no repite.
- El borrador de seguimiento sale de una plantilla con empresa, cargo y fecha. Si el usuario toca «Mejorar con IA», usa la tarea opcional `redactar_seguimiento`. Nunca se envía a la empresa.
- La revisión de vacantes usa `Detalles.obtener` con un tope por corrida (`revisar_vacantes_max`, 30 por defecto) y solo para procesos `enviado`/`cv_visto` con `url`. Si sale `cerrada`, se registra el evento de origen `vacante` y la regla pregunta si se archiva.

### 8. Prioridad y silencio en un solo lugar
Una tabla en `procesos.py` mapea `(tipo, origen)` a prioridad. `Conversacion` decide con ella si edita la card, si envía un mensaje con sonido (`disable_notification=False`) o si difiere. Las horas de silencio y el resto de los valores salen de `asistente.seguimiento` en `config.yaml`.

### 9. Tareas de IA opcionales
Hoy las tareas de cada proveedor son obligatorias. Se agrega en `comun/config.py` la noción de tarea opcional (`interpretar_fecha`, `redactar_seguimiento`). Si el proveedor no la declara, usa la configuración de su tarea `responder`. Así no hay que tocar los tres proveedores para cada tarea nueva.

## Risks / Trade-offs

- [Muchos mensajes molestan al usuario] → Solo los urgentes llegan con sonido, cada regla avisa una vez y existe el silencio nocturno. El resumen semanal reúne lo demás.
- [Fecha mal interpretada que da una entrevista a la hora equivocada] → Siempre se muestra la fecha completa para confirmar, y el `.ics` se manda después de la confirmación.
- [La revisión de vacantes sube el tráfico a los portales] → Tope por corrida, intervalo de días, mismas pausas y cooldown de `Detalles`, y solo procesos tempranos.
- [Migración sobre una base en producción] → La migración es idempotente, se prueba con una copia de la base del Fedora antes de desplegar y se puede volver atrás: las tablas nuevas no tocan las existentes.
- [El spec principal describe botones que el código ya no tiene] → El delta MODIFIED reescribe el requisito completo y documenta la compatibilidad con los callbacks viejos.

## Migration Plan

1. Copiar `asistente.db` antes de desplegar (`sqlite3 … ".backup"`).
2. Desplegar con la migración a esquema 5, que crea las tablas y procesos para las postulaciones ya enviadas.
3. Reiniciar `buscador-asistente`. Las cards viejas siguen funcionando por el callback `seg`.
4. **Para volver atrás:** volver al commit anterior y poner `esquema_version = 4`. La versión anterior se niega a arrancar con una base de esquema mayor (`_migrar_esquema` lanza `RuntimeError`). Las tablas nuevas quedan sin uso, y si hay que limpiar todo se restaura la copia.

## Open Questions

- ¿Los valores por defecto (10, 30 y 3 días, silencio de 21:00 a 7:00, resumen el domingo a las 18:00) le sirven al dueño? Se ajustan en `config.yaml` sin tocar el diseño.
