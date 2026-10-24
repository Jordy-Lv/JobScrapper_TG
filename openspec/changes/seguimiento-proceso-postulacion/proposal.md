## Why

Hoy el asistente acompaña la postulación solo hasta que se envía (`enviada`, `ya_postulada`, `respaldo`). Lo que pasa después (CV visto, una llamada, una entrevista, una oferta o el silencio) no queda en ninguna parte, y las oportunidades se pierden por un correo sin responder o una entrevista olvidada. Este change es la base del seguimiento de punta a punta: un expediente por proceso al que después se le conectan los portales (`leer-procesos-portales`) y el correo (`correo-seguimiento-reenvio`, `gmail-api-y-calendario`).

## What Changes

- **Proceso de selección separado de la postulación**: cada postulación enviada (o marcada «Ya me postulé» en el respaldo) abre un *proceso* con su propio estado (`enviado`, `cv_visto`, `en_proceso`, `contacto`, `entrevista`, `prueba`, `oferta`, `contratado`, `descartado`, `sin_respuesta`, `archivado`). Se admiten también procesos externos, sin postulación de la app.
- **Eventos con origen y seguridad**: todo avance es un evento con su origen (`usuario`, `portal`, `correo`, `vacante`, `reloj`), su nivel de seguridad y sus datos (por ejemplo, fecha, enlace y lugar de la entrevista). El estado del proceso se deriva de los eventos.
- **Botones mínimos de confirmación en la card**: «Me contactaron», «Entrevista» (pide fecha y hora y las confirma), «Me descartaron» y «Más» (prueba, oferta, contratado, archivar). Reemplazan a los botones Entrevista y Rechazada de la card confirmada. Son la única forma de registrar llamadas y WhatsApp.
- **Línea de tiempo en la card**: la card confirmada muestra el estado del proceso y sus últimos eventos con su origen. Los avances importantes llegan además como mensaje nuevo.
- **Reglas de cierre y de inactividad**:
  - a los N días sin señales, sugiere hacer seguimiento con un borrador;
  - si la vacante aparece cerrada sin contacto, pregunta si se archiva;
  - a los M días sin señales pasa a `sin_respuesta`;
  - unos días después de una entrevista, pregunta «¿Cómo te fue?».
- **Recordatorios de entrevista**: 24 h, 2 h y 15 min antes, con la guía para entrevista, la hoja de vida y las respuestas enviadas y el enlace o lugar. También se envía un archivo `.ics` por Telegram para agregarla a cualquier calendario.
- **Prioridad de avisos y horas de silencio**: urgente (mensaje nuevo con sonido), normal (edita la card en silencio) y silencioso (solo en el resumen). De noche solo pasan los urgentes.
- **Comando `/procesos`** con los procesos activos ordenados por urgencia, y **resumen semanal** (domingo) con activos, entrevistas próximas y pendientes del usuario.
- **Revisión de vacantes con proceso abierto**: el asistente vuelve a revisar cada pocos días si la oferta sigue publicada, para la regla de cierre.
- **Privacidad**: la baja borra procesos, eventos y recordatorios, y la política de privacidad lo menciona.

## Capabilities

### New Capabilities
- `seguimiento-proceso-asistente`: el proceso de selección de cada postulación (estados, eventos con origen y seguridad, procesos externos), las reglas de cierre e inactividad, los recordatorios de entrevista con `.ics`, la prioridad de avisos, `/procesos` y el resumen semanal.

### Modified Capabilities
- `tarjeta-postulacion-asistente`: el requisito «Confirmación, vistas y seguimiento en la card» cambia los botones Entrevista y Rechazada por los botones de avance del proceso y agrega la línea de tiempo. La card también se actualiza con eventos posteriores a la confirmación.

## Impact

- `buscador_vacantes/asistente/datos.py`: tablas nuevas `procesos`, `proceso_eventos` y `recordatorios`, una versión de esquema nueva y la migración de las postulaciones con `seguimiento` ya marcado.
- Módulo nuevo `buscador_vacantes/asistente/procesos.py` (estado derivado, reglas, recordatorios) y `ics.py` (archivo de calendario).
- `buscador_vacantes/asistente/tarjeta_postulacion.py`, `conversacion.py` (botones, entrada de fecha y hora, `/procesos`, `/historial`), `textos.py`, `servicio.py` (tareas periódicas y semanales) y `detalle.py` (revisión de vacantes con proceso abierto).
- `config.yaml` (sección `asistente.seguimiento`: días, recordatorios, horas de silencio, día del resumen) y `comun/config.py`.
- Texto de privacidad en `config.yaml` y `docs/asistente/guia-usuario.md`.
- Pruebas en `tests/asistente/` (procesos, card, conversación, ics, servicio).
- Base para `leer-procesos-portales`, `correo-seguimiento-reenvio` y `gmail-api-y-calendario`, que agregan eventos con origen `portal` y `correo`. Este change se archiva antes que ellos.
