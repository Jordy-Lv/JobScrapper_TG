## Purpose

Define la card única con la que el asistente de Telegram acompaña una postulación de principio a fin: un solo mensaje que se edita, con diseño sobrio y todos los estados, errores y acciones del usuario en el mismo lugar.

## ADDED Requirements

### Requirement: Una sola card por postulación
El asistente SHALL mostrar cada postulación en un único mensaje, creado cuando el usuario toca «Postular» y editado en el lugar hasta el fin del proceso. MUST NOT enviar mensajes sueltos de «En cola», progreso, preguntas, confirmación, bloqueo o seguimiento para esa postulación. Si el mensaje ya no se puede editar, el asistente SHALL enviar una card nueva con el estado actual y seguir desde ahí.

#### Scenario: Toque fuera del alta
- **WHEN** un usuario con el alta terminada toca «Postular» en una vacante
- **THEN** el asistente envía una única card con el título, la empresa y el estado «En cola»

#### Scenario: Toque durante el alta
- **WHEN** el usuario toca «Postular» antes de terminar el alta y la tarjeta de conexión ya existe
- **THEN** esa misma tarjeta pasa a ser la card de la postulación al terminar el alta, sin mensaje nuevo

#### Scenario: Card borrada
- **WHEN** el mensaje de la card ya no existe al intentar editarlo
- **THEN** el asistente envía una card nueva con el estado actual y guarda su identificador

#### Scenario: Reintento de la misma vacante
- **WHEN** el usuario reintenta una postulación que ya tiene card
- **THEN** la card existente vuelve a «En cola» y no se crea otra

### Requirement: Estados de la card
La card SHALL reflejar en cada momento uno de estos estados: en cola, esperando navegador, conexión de cuenta (por vincular, por confirmar, distinta, revisando, completando perfil), pregunta rápida, progreso por etapas, esperando sesión del portal, verificación, bloqueo del portal, confirmada, incierta, respaldo manual y cierre sin éxito (vacante cerrada, fallida). Cada estado MUST decir qué pasa y, si el usuario debe hacer algo, qué hacer y con qué botón.

#### Scenario: Progreso
- **WHEN** la extensión reporta pasos de la postulación
- **THEN** la card marca con ✓ las etapas hechas, con indicador giratorio la actual y atenuadas las que faltan, sin enviar mensajes nuevos

#### Scenario: Cuenta por confirmar
- **WHEN** el portal tiene una sesión cuyo correo hay que confirmar
- **THEN** la card muestra el correo y los botones «Confirmar» y «Cancelar» en su fila; al elegir, la card sigue su camino

#### Scenario: Cuenta distinta
- **WHEN** la sesión abierta en el portal es de otra cuenta
- **THEN** la card avisa que no se postulará con ella y ofrece «Es mi cuenta nueva» y «No es mía»

#### Scenario: Cuenta por vincular
- **WHEN** el usuario no tiene navegador vinculado
- **THEN** la card explica que falta vincularlo, ofrece el botón para hacerlo y, si se pasa a respaldo manual, lo indica en la misma card

#### Scenario: Sesión pendiente
- **WHEN** el portal necesita que el usuario inicie sesión
- **THEN** la card pide iniciar sesión en ese portal, incluye el enlace para crear cuenta y se reanuda sola cuando la sesión aparece

#### Scenario: Bloqueo del portal
- **WHEN** el portal pide una acción en la cuenta del usuario antes de postular
- **THEN** la card explica el bloqueo con la causa concreta, aclara que no se envió nada y ofrece «Reintentar»; al reintentar vuelve a «En cola»

#### Scenario: Incierta
- **WHEN** el envío se hizo pero el portal no mostró confirmación
- **THEN** la card dice que no hubo confirmación, indica revisar «Mis postulaciones» en el portal y conserva las vistas de respuestas y de qué trata

#### Scenario: Respaldo manual
- **WHEN** la postulación pasa a respaldo manual (plataforma no automática, formulario desconocido, rechazo del portal, sin respuesta del usuario)
- **THEN** la card explica el motivo, ofrece abrir la vacante y marcar «Ya me postulé» o «No me interesa», y el paquete se envía en mensajes aparte

### Requirement: Preguntas rápidas dentro de la card
Cuando la postulación necesita un dato del usuario, la card SHALL cambiar a «Pregunta rápida» con la pregunta, el avance si hay más de una y los botones de opciones, o la indicación de escribir la respuesta. Al guardar la respuesta, la card MUST volver al estado anterior y el texto escrito por el usuario SHALL borrarse del chat sin interrumpir el flujo si no se puede.

#### Scenario: Pregunta con opciones
- **WHEN** hay una pregunta pendiente con opciones
- **THEN** la card muestra las opciones como botones y, al elegir una, pasa a la siguiente pregunta o regresa al progreso

#### Scenario: Pregunta de texto libre
- **WHEN** la pregunta pendiente exige escribir
- **THEN** la card pide la respuesta, y al recibir el texto lo guarda, lo borra del chat y avanza

#### Scenario: Texto fuera de turno
- **WHEN** el usuario escribe cuando la card no espera texto
- **THEN** el asistente no cambia la card ni responde con un mensaje nuevo

### Requirement: Confirmación, vistas y seguimiento en la card
Al confirmarse la postulación, la card SHALL mostrar el título, la empresa y, en un `<blockquote>`, el portal, la fecha, si hubo encuesta y qué hoja de vida recibió el portal. «Respuestas» y «De qué trata» MUST abrirse como vistas de la misma card con un botón «Volver», y la oferta como enlace. Los botones Entrevista, Rechazada y Oferta SHALL marcar el seguimiento: la opción elegida queda marcada con ✓, puede cambiarse y se refleja en el historial. La hoja de vida adjunta sigue enviándose como documento aparte.

#### Scenario: Ver respuestas
- **WHEN** el usuario toca «Respuestas» en una card confirmada
- **THEN** la card muestra cada pregunta con su respuesta y su origen, y «Volver» regresa a la confirmación

#### Scenario: Vista larga
- **WHEN** el contenido de una vista excede el límite de Telegram
- **THEN** la vista se recorta con «…» o se acorta sin enviar mensajes nuevos

#### Scenario: Marcar seguimiento
- **WHEN** el usuario toca «Entrevista»
- **THEN** el seguimiento se guarda, la card marca «Entrevista» con ✓ y los demás botones siguen disponibles para corregir

### Requirement: Estilo sobrio de la card
La card SHALL usar `<blockquote>` para el cuerpo de estado, botones en filas ordenadas (acciones principales primero, vistas después, seguimiento al final) y emojis solo cuando aportan estado (✅ confirmada, ❔ incierta, 🔒 acción del usuario, ⚠️ cuenta distinta; ✓ y · en etapas). Los botones SHALL llevar texto sin emojis decorativos. El texto MUST respetar el límite de 4096 caracteres y escapar el contenido de usuario y de portales.

#### Scenario: Máximo de botones por fila
- **WHEN** la card tiene más de tres acciones
- **THEN** se reparten en filas de a lo sumo tres botones, con las acciones de seguimiento juntas en la última fila

### Requirement: Toques viejos y compatibilidad
Los botones de una card que ya no corresponde a su estado MUST ignorarse o repintar la card actual, sin enviar mensajes. Los botones de tarjetas enviadas antes de este cambio SHALL seguir respondiendo.

#### Scenario: Toque sobre estado superado
- **WHEN** el usuario toca «Reintentar» en una card que ya está confirmada
- **THEN** no se reencola nada y la card se mantiene

#### Scenario: Tarjeta anterior al cambio
- **WHEN** el usuario toca «Ver respuestas» en una tarjeta enviada con la versión anterior
- **THEN** el asistente responde con el comportamiento previo sin errores
