## Purpose

Seguir cada proceso de selección después de la postulación, desde el envío hasta su cierre, para que el usuario no pierda una llamada, una entrevista o una oferta. Reúne en un solo expediente los avances que registra el usuario y los que llegan de otras fuentes.

## ADDED Requirements

### Requirement: Un proceso por postulación enviada
El asistente SHALL abrir un proceso de selección cuando una postulación termina `enviada` o `ya_postulada`, y cuando el usuario marca «Ya me postulé» en un respaldo manual. Cada proceso MUST tener uno de estos estados: `enviado`, `cv_visto`, `en_proceso`, `contacto`, `entrevista`, `prueba`, `oferta`, `contratado`, `descartado`, `sin_respuesta` o `archivado`. Los cuatro últimos y `contratado` son estados de cierre. No se abren dos procesos para la misma postulación.

#### Scenario: Postulación confirmada
- **WHEN** la extensión reporta una postulación `enviada`
- **THEN** existe un proceso en estado `enviado` asociado a esa postulación, con la empresa, el cargo y el portal de la vacante

#### Scenario: Respaldo marcado como postulado
- **WHEN** el usuario toca «Ya me postulé» en la card de un respaldo manual
- **THEN** se abre un proceso `enviado` para esa postulación

#### Scenario: Reintento sobre la misma vacante
- **WHEN** una postulación que ya tiene proceso vuelve a terminar `enviada`
- **THEN** se conserva el mismo proceso y no se crea otro

### Requirement: Procesos externos
El asistente SHALL admitir procesos sin postulación de la app (el usuario se postuló por su cuenta), con empresa, cargo y, si los hay, portal y enlace. Un proceso externo MUST comportarse igual que los demás en eventos, recordatorios, reglas y avisos.

#### Scenario: Proceso externo creado por otra fuente
- **WHEN** una fuente aprobada (portal o correo) reporta un proceso que no corresponde a ninguna postulación del usuario y el usuario acepta seguirlo
- **THEN** se crea un proceso externo con los datos reportados y aparece en `/procesos`

### Requirement: Eventos con origen y seguridad
Todo avance de un proceso SHALL guardarse como un evento con fecha, tipo (`cv_visto`, `en_proceso`, `contacto`, `entrevista`, `prueba`, `oferta`, `contratado`, `descartado`, `sin_respuesta`, `archivado`, `nota`), origen (`usuario`, `portal`, `correo`, `vacante` o `reloj`), seguridad (`alta` o `media`) y datos propios del tipo (para una entrevista: fecha y hora, modalidad, enlace o lugar y contacto). El estado del proceso MUST derivarse de sus eventos: manda el evento más reciente de mayor avance, y un evento de cierre solo lo reabre un evento posterior de avance. Un mismo hecho reportado dos veces por la misma fuente MUST NOT duplicar el evento.

#### Scenario: Evento de mayor avance
- **WHEN** un proceso en `entrevista` recibe después un evento `cv_visto` del portal
- **THEN** el evento se guarda en la línea de tiempo y el estado sigue en `entrevista`

#### Scenario: Reapertura tras un cierre
- **WHEN** un proceso en `sin_respuesta` recibe un evento `entrevista`
- **THEN** el proceso pasa a `entrevista` y vuelve a los procesos activos

#### Scenario: Evento repetido
- **WHEN** la misma fuente reporta dos veces el mismo hecho con el mismo identificador
- **THEN** se guarda un solo evento

#### Scenario: Evento de seguridad media
- **WHEN** una fuente reporta un evento con seguridad `media`
- **THEN** el asistente pregunta al usuario si es correcto antes de cambiar el estado del proceso, y si el usuario lo rechaza no lo cambia

### Requirement: Registro manual de avances
La card de un proceso abierto SHALL ofrecer «Me contactaron», «Entrevista», «Me descartaron» y «Más». «Más» MUST abrir, como vista de la misma card, «Prueba técnica», «Oferta», «Me contrataron», «Archivar» y «Volver». «Entrevista» MUST pedir la fecha y la hora por texto libre, interpretar formas comunes en español («martes 10am», «20/10 3:30 pm», «mañana 9») en la zona America/Bogota y mostrar lo entendido para confirmar o corregir antes de guardar. Opcionalmente pide también el enlace o el lugar.

#### Scenario: Entrevista con fecha entendida
- **WHEN** el usuario toca «Entrevista» y escribe «martes 10am»
- **THEN** la card muestra la fecha completa entendida con «Confirmar» y «Corregir», y al confirmar se guarda el evento `entrevista` con origen `usuario`

#### Scenario: Fecha que no se entiende
- **WHEN** el texto no permite obtener una fecha y una hora futuras
- **THEN** la card pide escribirla de otra forma, con un ejemplo, y no guarda nada

#### Scenario: Corrección de un avance
- **WHEN** el usuario toca un avance distinto al marcado
- **THEN** se agrega el evento nuevo y la card refleja el estado resultante

### Requirement: Reglas de cierre e inactividad
Una vez al día, el asistente SHALL revisar los procesos abiertos y aplicar estas reglas, con los plazos configurables:
- sin eventos desde hace `seguimiento_dias` (10 por defecto) en `enviado` o `cv_visto`: ofrece una sola vez un borrador de mensaje de seguimiento para que el usuario lo envíe;
- vacante cerrada en el portal sin eventos de contacto o posteriores: pregunta si se archiva;
- sin eventos desde hace `sin_respuesta_dias` (30 por defecto): pasa a `sin_respuesta` con un evento de origen `reloj`, sin sonido;
- `postentrevista_dias` (3 por defecto) después de la fecha de una entrevista, sin eventos nuevos: pregunta «¿Cómo te fue?» con los botones de avance.

Cada pregunta o sugerencia MUST enviarse una sola vez por proceso y regla. El asistente MUST NOT enviar mensajes a terceros en nombre del usuario.

#### Scenario: Sugerencia de seguimiento
- **WHEN** un proceso lleva 10 días en `enviado` sin eventos
- **THEN** el usuario recibe una vez la sugerencia con un borrador para copiar, sin que el asistente envíe nada a la empresa

#### Scenario: Vacante cerrada sin contacto
- **WHEN** la revisión de vacantes encuentra cerrada la oferta de un proceso en `enviado`
- **THEN** se registra un evento de origen `vacante` y se pregunta si se archiva el proceso

#### Scenario: Silencio prolongado
- **WHEN** un proceso lleva 30 días sin eventos
- **THEN** pasa a `sin_respuesta`, sale de los procesos activos y solo aparece en el resumen semanal

### Requirement: Revisión de vacantes con proceso abierto
El asistente SHALL volver a consultar, cada `revisar_vacante_dias` (3 por defecto), la página de las vacantes con procesos abiertos en estado `enviado` o `cv_visto`, respetando las pausas y límites existentes para cada fuente. MUST NOT consultar vacantes de procesos cerrados ni de procesos sin enlace.

#### Scenario: Oferta que sigue publicada
- **WHEN** la revisión encuentra la oferta disponible
- **THEN** no se registra ningún evento

### Requirement: Recordatorios de entrevista
Por cada entrevista con fecha futura, el asistente SHALL programar recordatorios a las 24 h, 2 h y 15 min antes (configurables). El de 24 h MUST incluir la guía para entrevista, la hoja de vida y las respuestas enviadas en esa postulación si existen. El de 2 h, el lugar o el enlace. El de 15 min, el enlace para entrar con un toque. Si la fecha cambia o el proceso se cierra, los recordatorios pendientes MUST reprogramarse o cancelarse. Un recordatorio vencido durante una caída del servicio MUST enviarse al volver solo si la entrevista aún no empezó.

#### Scenario: Recordatorio del día anterior
- **WHEN** faltan 24 horas para una entrevista registrada
- **THEN** el usuario recibe un mensaje con sonido con la fecha, la empresa, el acceso a la guía para entrevista y lo enviado en la postulación

#### Scenario: Entrevista reprogramada
- **WHEN** se registra una fecha nueva para la misma entrevista
- **THEN** los recordatorios anteriores se cancelan y se programan los de la fecha nueva

#### Scenario: Servicio caído
- **WHEN** el servicio vuelve después de la hora de un recordatorio y la entrevista ya pasó
- **THEN** ese recordatorio no se envía

### Requirement: Archivo de calendario
Al guardar o cambiar una entrevista con fecha, el asistente SHALL enviar por Telegram un archivo `.ics` válido (RFC 5545) con la empresa y el cargo en el título, la hora con zona America/Bogota, el lugar o el enlace y una alarma de 1 h. Una reprogramación MUST enviar un `.ics` con el mismo identificador y una secuencia mayor, para que el calendario actualice el evento en vez de duplicarlo.

#### Scenario: Agregar al calendario
- **WHEN** el usuario confirma una entrevista el martes a las 10:00
- **THEN** recibe un archivo `.ics` que, al abrirlo, crea el evento del martes de 10:00 a 11:00 en su calendario

### Requirement: Prioridad de avisos y horas de silencio
Cada evento SHALL avisarse según su prioridad:
- urgente (entrevista, prueba, oferta, contacto, pedido de respuesta con plazo): mensaje nuevo con sonido, además de actualizar la card;
- normal (`cv_visto`, `en_proceso`): solo edita la card, sin sonido;
- silencioso (cierres por reglas): solo en el resumen semanal y en la card.

Entre `silencio_desde` y `silencio_hasta` (21:00 a 7:00 por defecto) los avisos normales y las sugerencias MUST esperar al final del silencio. Los urgentes y los recordatorios de entrevista se envían igual.

#### Scenario: Aviso urgente de noche
- **WHEN** a las 23:00 llega un evento `entrevista` de una fuente
- **THEN** el usuario recibe el aviso en el acto

#### Scenario: Sugerencia de noche
- **WHEN** una regla genera una sugerencia a las 22:00
- **THEN** se envía a las 7:00

### Requirement: Comando /procesos
El asistente SHALL responder a `/procesos` con los procesos activos ordenados por urgencia (primero las entrevistas y pruebas próximas, luego lo que espera una acción del usuario, luego el resto por fecha del último evento). Cada línea MUST mostrar el cargo, la empresa, el estado, la fecha del último evento y, si hay, la de la entrevista, con acceso a su card. `/historial` SHALL mostrar el estado del proceso en lugar del antiguo valor de seguimiento.

#### Scenario: Sin procesos activos
- **WHEN** el usuario no tiene procesos abiertos
- **THEN** el asistente lo dice en una línea y no lista procesos cerrados

### Requirement: Resumen semanal
Cada semana, en el día y la hora configurados (domingo 18:00 por defecto), el asistente SHALL enviar a cada usuario con procesos abiertos, o cerrados en esa semana, un resumen con los procesos activos por estado, las entrevistas de la semana siguiente, lo que espera una acción del usuario y los procesos cerrados en la semana. Un usuario sin nada de eso MUST NOT recibir resumen.

#### Scenario: Semana con entrevistas próximas
- **WHEN** el usuario tiene dos entrevistas la semana siguiente
- **THEN** el resumen las lista con fecha y hora antes que el resto

### Requirement: Datos del seguimiento y baja
Los procesos, eventos y recordatorios SHALL pertenecer al usuario y borrarse con su baja o con su borrado por inactividad. Los datos de eventos MUST limitarse a lo necesario para el seguimiento: fechas, tipo, empresa, cargo, enlace o lugar y un fragmento de texto de 500 caracteres o menos.

#### Scenario: Baja del usuario
- **WHEN** el usuario se da de baja
- **THEN** no queda ningún proceso, evento ni recordatorio suyo en la base
