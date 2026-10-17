## ADDED Requirements

### Requirement: Barra de progreso en la card
Mientras la postulación está en progreso, la card SHALL mostrar bajo la cabecera una barra de progreso suave con el porcentaje y el tiempo restante estimado, además de las etapas marcadas. La barra MUST avanzar por etapa y por subpaso dentro de la etapa, nunca retroceder y no pasar de 99 % mientras la postulación siga en curso; el 100 % SHALL mostrarse solo en la confirmación. El tiempo restante MUST ser una estimación que se muestra con «~» y nunca menor a 1 s. La card SHALL editarse como máximo una vez cada 2 s por chat.

#### Scenario: Etapa inicial
- **WHEN** la postulación entra en la primera etapa
- **THEN** la card muestra la barra casi vacía, un porcentaje bajo y un tiempo restante estimado, con la primera etapa marcada como en curso

#### Scenario: Cambio de etapa
- **WHEN** la extensión reporta un paso que corresponde a una etapa posterior
- **THEN** la barra salta al avance de esa etapa, las anteriores quedan con ✓ y el porcentaje no baja

#### Scenario: Etapa lenta
- **WHEN** una etapa dura más de lo estimado
- **THEN** la barra se acerca al final de esa etapa sin completarla, el porcentaje no supera 99 % y el tiempo restante muestra «~1 s»

#### Scenario: Cuadro de animación perdido
- **WHEN** Telegram rechaza una edición del progreso o el mensaje no cambió
- **THEN** el siguiente cuadro la reemplaza sin enviar mensajes nuevos ni detener la postulación

### Requirement: Confeti al confirmar la postulación
Cuando la postulación queda confirmada por el portal, el asistente SHALL entregar la card de confirmación con el efecto de confeti de Telegram. Como el efecto solo se aplica al enviar, el asistente MUST enviar la card de confirmación como mensaje nuevo con el efecto, guardar su identificador como el de la card y borrar el mensaje de progreso anterior, de modo que la postulación conserve una sola card. Si Telegram rechaza el efecto, el asistente SHALL reenviar la confirmación sin efecto; si no se puede borrar el mensaje anterior, MUST ignorarlo. La postulación incierta MUST NOT llevar confeti. Cualquier repintado posterior de la card (vistas, seguimiento) MUST editarla sin volver a lanzar el efecto.

#### Scenario: Confirmación con confeti
- **WHEN** el portal confirma la postulación de un usuario en chat privado
- **THEN** el asistente envía una card de confirmación con el efecto de confeti, borra la card de progreso y la nueva card queda como la card de esa postulación

#### Scenario: Efecto rechazado
- **WHEN** Telegram rechaza el envío con el efecto
- **THEN** el asistente envía la card de confirmación sin efecto y la postulación queda confirmada igual

#### Scenario: Mensaje anterior no borrable
- **WHEN** el mensaje de progreso ya no existe o no se puede borrar
- **THEN** el asistente deja la nueva card como la vigente y no muestra error al usuario

#### Scenario: Postulación incierta
- **WHEN** el envío se hizo pero el portal no mostró confirmación
- **THEN** la card pasa a «incierta» editándose en el lugar, sin confeti

#### Scenario: Vistas y seguimiento después del confeti
- **WHEN** el usuario toca «Respuestas», «Volver» o «Entrevista» en la card confirmada
- **THEN** la card se edita en el lugar y el efecto no se repite

## MODIFIED Requirements

### Requirement: Confirmación, vistas y seguimiento en la card
Al confirmarse la postulación, la card SHALL mostrar el título «Postulación enviada» con ✅, el título de la vacante, la empresa, la barra de progreso al 100 % y, en un `<blockquote>`, el portal que confirmó, la fecha y hora, la duración del proceso, el folio, si hubo encuesta y qué hoja de vida recibió el portal. La duración y el folio MUST omitirse si el dato no está disponible. «Respuestas» y «De qué trata» MUST abrirse como vistas de la misma card con un botón «Volver», y la oferta como enlace. Los botones Entrevista y Rechazada SHALL marcar el seguimiento: la opción elegida queda marcada con ✓, puede cambiarse y se refleja en el historial. La hoja de vida adjunta sigue enviándose como documento aparte.

#### Scenario: Mensaje de confirmación
- **WHEN** el portal confirma la postulación
- **THEN** la card muestra «Postulación enviada», el título y la empresa, la barra al 100 % y el portal, la hora, la duración, el folio, la encuesta y la hoja de vida en la cita

#### Scenario: Sin duración disponible
- **WHEN** la postulación no tiene hora de inicio o de fin registrada
- **THEN** la card de confirmación omite la duración y el resto del mensaje se muestra completo

#### Scenario: Ver respuestas
- **WHEN** el usuario toca «Respuestas» en una card confirmada
- **THEN** la card muestra cada pregunta con su respuesta y su origen, y «Volver» regresa a la confirmación

#### Scenario: Vista larga
- **WHEN** el contenido de una vista excede el límite de Telegram
- **THEN** la vista se recorta con «…» o se acorta sin enviar mensajes nuevos

#### Scenario: Marcar seguimiento
- **WHEN** el usuario toca «Entrevista»
- **THEN** el seguimiento se guarda, la card marca «Entrevista» con ✓ y los demás botones siguen disponibles para corregir
