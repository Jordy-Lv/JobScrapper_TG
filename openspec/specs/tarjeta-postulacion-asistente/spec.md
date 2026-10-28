# tarjeta-postulacion-asistente Specification

## Purpose

Define la card única con la que el asistente de Telegram acompaña una postulación de principio a fin: un solo mensaje que se edita, con diseño sobrio y todos los estados, errores y acciones del usuario en el mismo lugar.

## Requirements

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
La card SHALL reflejar en cada momento uno de estos estados: en cola, esperando navegador, conexión de cuenta (por vincular, por confirmar, distinta, revisando, completando perfil), pregunta rápida, revisión de respuestas, progreso por etapas, esperando sesión del portal, verificación, bloqueo del portal, confirmada, incierta, respaldo manual y cierre sin éxito (vacante cerrada, fallida). Cada estado MUST decir qué pasa y, si el usuario debe hacer algo, qué hacer y con qué botón.

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

#### Scenario: Revisión de respuestas
- **WHEN** el portal tiene encendida «Revisar respuestas antes de enviar» y el formulario trae respuestas redactadas por la IA
- **THEN** la card muestra cada pregunta con su respuesta redactada, aclara que aún no se envió nada y ofrece «✅ Enviar» y «✏️ Corregir»; al enviar, la card vuelve a «En cola»

#### Scenario: Incierta
- **WHEN** el envío se hizo pero el portal no mostró confirmación
- **THEN** la card dice que no hubo confirmación, indica revisar «Mis postulaciones» en el portal y conserva las vistas de respuestas y de qué trata

#### Scenario: Respaldo manual
- **WHEN** la postulación pasa a respaldo manual (plataforma no automática, formulario desconocido, rechazo del portal, sin respuesta del usuario)
- **THEN** la card explica el motivo, ofrece abrir la vacante y marcar «Ya me postulé» o «No me interesa», y no se envía ningún paquete (CV, mensaje ni respuestas) en mensajes aparte

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

### Requirement: Plataforma de la vacante en la cabecera de la card
La card SHALL mostrar en su cabecera la plataforma de la vacante (por ejemplo Computrabajo, Magneto o elempleo), junto a la empresa en la forma «Empresa · Plataforma», o sola si no hay empresa, en todas las fases desde la creación de la card hasta su cierre, incluidas la confirmada y la incierta. Si la plataforma es desconocida, la cabecera MUST omitirla sin dejar líneas vacías ni textos como «None». El nombre MUST escaparse como el resto del contenido.

#### Scenario: Card en progreso
- **WHEN** la card de una vacante de Magneto de la empresa «Maaji» está en progreso
- **THEN** la cabecera muestra el título y debajo «Maaji · 🟢 Magneto», seguida de la afinidad, la barra y las etapas

#### Scenario: Card en cola
- **WHEN** la postulación está en cola o esperando navegador
- **THEN** la cabecera muestra la misma línea con la plataforma, sin cambiar el cuerpo de estado

#### Scenario: Card confirmada o incierta
- **WHEN** la postulación queda confirmada o incierta
- **THEN** la cabecera de la card conserva la plataforma junto a la empresa, y la cita de estado sigue nombrando el portal

#### Scenario: Vacante sin empresa
- **WHEN** la vacante no tiene empresa pero sí plataforma
- **THEN** la línea bajo el título muestra solo la plataforma

#### Scenario: Plataforma desconocida
- **WHEN** la postulación no tiene plataforma
- **THEN** la cabecera queda con título y, si existe, empresa, sin la plataforma

### Requirement: Emoji de color por plataforma
El asistente SHALL identificar cada plataforma con un emoji fijo (🔵 Computrabajo, 🟢 Magneto, 🩵 elempleo) antepuesto a su nombre en la cabecera de la card y en cada línea de cuenta del bloque «Conexión». Una plataforma sin emoji registrado o desconocida MUST mostrarse sin emoji y sin espacios sobrantes. Los textos en prosa y los botones MUST seguir nombrando el portal sin emoji.

#### Scenario: Cabecera con empresa
- **WHEN** la card de una vacante de Magneto de la empresa «Maaji» se muestra en cualquier fase
- **THEN** la línea bajo el título es «Maaji · 🟢 Magneto»

#### Scenario: Cabecera sin empresa
- **WHEN** la vacante de Computrabajo no tiene empresa
- **THEN** la línea bajo el título es «🔵 Computrabajo»

#### Scenario: Bloque de conexión
- **WHEN** el bloque «Conexión» muestra la cuenta de elempleo
- **THEN** la línea de esa cuenta nombra el portal como «🩵 elempleo»

#### Scenario: Plataforma sin emoji
- **WHEN** la plataforma no tiene emoji registrado
- **THEN** se muestra solo su nombre, sin espacio inicial

#### Scenario: Botones y prosa
- **WHEN** el bot muestra el botón «Confirmar Magneto» o una frase como «Postular en Magneto»
- **THEN** el nombre del portal aparece sin emoji

### Requirement: Cuenta regresiva antes de postular
Al tocar «Postular», el asistente SHALL mostrar en la card de la postulación una cuenta regresiva animada, de 5 segundos por defecto, con un botón «Cancelar», y MUST NOT encolar la vacante ni avisar a la extensión hasta que la cuenta termine sin cancelarse. La animación SHALL editar la misma card (una edición por segundo) y no enviar mensajes nuevos. La duración SHALL ser configurable, y con 0 segundos el toque encola de inmediato como antes.

#### Scenario: Toque y cuenta
- **WHEN** un usuario con el alta terminada toca «Postular» en una vacante disponible
- **THEN** la card muestra el título, la empresa, los segundos restantes con una barra que avanza cada segundo y el botón «Cancelar», y la postulación aún no existe en la cola

#### Scenario: La cuenta termina
- **WHEN** pasan los 5 segundos sin que el usuario cancele
- **THEN** la vacante se encola y la card pasa a «En cola» (o a «Esperando navegador» o al respaldo, según corresponda), en el mismo mensaje

#### Scenario: Toque desde el canal
- **WHEN** el usuario toca ⚡ en un mensaje del canal
- **THEN** el aviso corto responde de inmediato que tiene 5 segundos para cancelar en el bot, y la cuenta corre en la card del bot

#### Scenario: Vacante pendiente del alta
- **WHEN** el usuario termina el alta con una vacante pendiente
- **THEN** la cuenta regresiva corre en la tarjeta del alta, bajo el bloque de conexión, antes de encolar

#### Scenario: Cuenta desactivada
- **WHEN** la duración configurada es 0
- **THEN** el toque encola de inmediato y la card muestra «En cola», sin cuenta ni botón «Cancelar»

### Requirement: Cancelar durante la cuenta
Mientras corre la cuenta, el botón «Cancelar» SHALL detenerla sin encolar nada, y la card SHALL pasar a un estado cerrado que diga que no se envió nada y ofrezca «Postular» para volver a empezar.

#### Scenario: Cancelar a tiempo
- **WHEN** el usuario toca «Cancelar» antes de que termine la cuenta
- **THEN** no se crea ninguna postulación en la cola y la card dice «Cancelaste la postulación. No envié nada.» con el botón «Postular»

#### Scenario: Postular otra vez tras cancelar
- **WHEN** el usuario toca «Postular» en la card cancelada
- **THEN** la misma card vuelve a mostrar una cuenta regresiva nueva, sin crear otro mensaje

#### Scenario: Cancelar tarde
- **WHEN** el usuario toca «Cancelar» después de que la cuenta terminó
- **THEN** el aviso corto dice que ya se está postulando, la card sigue su curso y no se cancela nada

### Requirement: Un solo toque activo por vacante
El asistente SHALL permitir una sola cuenta regresiva por usuario y vacante a la vez.

#### Scenario: Doble toque
- **WHEN** el usuario toca «Postular» en la misma vacante mientras su cuenta corre
- **THEN** no se abre otra cuenta ni otra card, y el aviso corto dice que ya está contando

#### Scenario: Toque en una vacante ya existente
- **WHEN** el usuario toca «Postular» en una vacante que ya está en la cola
- **THEN** no hay cuenta regresiva: se muestra el estado actual como hasta ahora

### Requirement: Cuenta interrumpida por reinicio
Si el asistente se reinicia con una cuenta en curso, SHALL descartarla sin postular y dejar la card en un estado que avise que se interrumpió y ofrezca «Postular».

#### Scenario: Reinicio durante la cuenta
- **WHEN** el bot se reinicia a mitad de una cuenta regresiva
- **THEN** no se encola la vacante y la card dice que la cuenta se interrumpió y ofrece «Postular»

### Requirement: Conexión de la card limitada al portal de la vacante
El bloque «Conexión con tus portales» de la card de una postulación SHALL mostrar:
- el navegador vinculado;
- una sola línea de cuenta: la del portal de esa vacante, con sus botones si tiene una acción pendiente.

Si el usuario aún no tiene cuenta conocida en ese portal, la línea MUST indicar que debe iniciar sesión en él en el navegador vinculado. La card MUST NOT mostrar cuentas ni botones de otros portales.

Si llega un aviso de cuenta de otro portal mientras la card está abierta (cuenta por confirmar, distinta, confirmada o perfil en preparación), el bot MUST mostrarlo en un mensaje de conexión aparte. Ese mensaje reúne solo los portales distintos al de la vacante, se edita en su sitio con avisos posteriores y conserva los botones Confirmar y Cancelar.

#### Scenario: Vacante de Magneto con Computrabajo ya confirmado
- **WHEN** el usuario tiene la cuenta de Computrabajo confirmada, no tiene sesión en Magneto y toca una vacante de Magneto
- **THEN** la card muestra «· Magneto: inicia sesión con tu cuenta en ese navegador» y no menciona Computrabajo

#### Scenario: Cuenta por confirmar del mismo portal
- **WHEN** una card de Magneto está abierta y llega el aviso de que la cuenta de Magneto debe confirmarse
- **THEN** la card muestra el correo de Magneto con los botones «Confirmar Magneto» y «Cancelar»

#### Scenario: Aviso de otro portal con la card abierta
- **WHEN** una card de Magneto está abierta y llega el aviso de que la cuenta de Computrabajo debe confirmarse
- **THEN** la card no cambia y el bot muestra la confirmación de Computrabajo en un mensaje de conexión aparte, con sus botones

#### Scenario: Sin card abierta
- **WHEN** no hay una card de postulación con bloque de conexión
- **THEN** la tarjeta de conexión muestra todos los portales, como hasta ahora

### Requirement: Motivo de la espera en la card en cola
Mientras una postulación espera en cola o espera navegador, su card SHALL mostrar la causa de espera calculada por el servidor, con un mensaje que diga qué falta y cómo resolverlo en el portal de la vacante, y los botones de esa solución cuando existan. Sin causa de espera, la card MUST mostrar «En cola. Te aviso el resultado.». El mensaje MUST nombrar el portal de la vacante y MUST NOT mostrar motivos técnicos internos (por ejemplo `enlace_ingresar`) ni el correo completo de una cuenta que no es la del usuario.

#### Scenario: Sin sesión en el portal
- **WHEN** la causa es «sin sesión» en Magneto
- **THEN** la card dice que hay que iniciar sesión en Magneto en el navegador vinculado y que la postulación sale sola después, con el botón «Iniciar sesión» que abre la página de ingreso de Magneto y el botón «Crear cuenta»

#### Scenario: Sin navegador vinculado
- **WHEN** la causa es «sin navegador vinculado»
- **THEN** la card dice que falta vincular el navegador y ofrece «Vincular navegador»

#### Scenario: Sin latido reciente
- **WHEN** la causa es «sin latido reciente»
- **THEN** la card dice que el navegador no responde desde la hora del último contacto y pide abrirlo con la extensión activa

#### Scenario: Extensión desactualizada
- **WHEN** la causa es «extensión desactualizada»
- **THEN** la card muestra la versión instalada y la mínima, pide actualizar la extensión y ofrece «Actualizar extensión» solo si hay enlace de tienda configurado

#### Scenario: Extensión en pausa
- **WHEN** la causa es «extensión en pausa»
- **THEN** la card dice que las postulaciones están en pausa en la extensión y que se reanudan al quitar la pausa desde su ventana

#### Scenario: Plataforma apagada
- **WHEN** la causa es «plataforma apagada»
- **THEN** la card dice que la postulación automática en ese portal está pausada por ahora, que la postulación sigue en cola y que sale sola cuando se reactive, sin botones de acción para el usuario

#### Scenario: Permiso de dominio
- **WHEN** la causa es «sin permiso» en elempleo
- **THEN** la card pide abrir la ventana de la extensión y activar el permiso de elempleo.com con su botón

#### Scenario: Cuenta por confirmar o distinta
- **WHEN** la causa es «cuenta por confirmar» o «cuenta distinta»
- **THEN** la card explica la situación de la cuenta y ofrece los mismos botones de la conexión de cuenta: «Confirmar» y «Cancelar», o «Es mi cuenta nueva» y «No es mía»

#### Scenario: Correo ilegible
- **WHEN** la causa es «correo ilegible»
- **THEN** la card dice que no se pudo leer el correo de la cuenta del portal, que se vuelve a intentar en la próxima revisión y que no se postula hasta comprobar que la cuenta es suya

#### Scenario: Esperas normales de la cola
- **WHEN** la causa es otra postulación en curso, el tope diario o la pausa entre postulaciones
- **THEN** la card lo dice y, en el tope y la pausa, cuándo sale aproximadamente, sin botones

### Requirement: La card en cola se actualiza sola
La card de una postulación en cola SHALL editarse en su mismo mensaje cada vez que cambie su causa de espera, sin enviar mensajes nuevos, y MUST NOT editarse cuando la causa no cambia. Cuando la causa se resuelve, la card MUST volver a «En cola. Te aviso el resultado.» y seguir con las fases del flujo normal.

#### Scenario: El usuario inicia sesión
- **WHEN** la card muestra «sin sesión» en Magneto y el usuario inicia sesión en su navegador
- **THEN** tras el siguiente latido la card vuelve a «En cola. Te aviso el resultado.» y luego pasa al progreso cuando la extensión toma la postulación

#### Scenario: Cambia la causa
- **WHEN** el usuario activa el permiso de elempleo.com pero todavía no tiene sesión en elempleo
- **THEN** la card cambia de «sin permiso» a «sin sesión» en elempleo, en el mismo mensaje

#### Scenario: Latidos repetidos
- **WHEN** llegan latidos cada 30 segundos con la misma causa
- **THEN** el mensaje de la card no se edita

### Requirement: Card de un portal que no procesó «Aplicar»
Cuando la extensión reporta que el portal no procesó el clic de postular (sin encuesta, sin confirmación y con el botón de postular aún en la vacante), la card MUST decir que el portal no cargó la postulación, MUST aclarar que no se envió nada y MUST ofrecer «Reintentar». La card MUST NOT usar el aviso «no mostró la confirmación» en ese caso, porque ese aviso indica que el envío sí se hizo.

#### Scenario: Aplicar sin respuesta del portal
- **WHEN** la postulación termina con el motivo de que el portal no procesó «Aplicar»
- **THEN** la card dice que el portal no cargó la postulación, que no se envió nada y muestra «Reintentar»

#### Scenario: Reintento
- **WHEN** el usuario toca «Reintentar» en esa card
- **THEN** la postulación vuelve a «En cola» y se ejecuta de nuevo

#### Scenario: Sin confirmación tras enviar
- **WHEN** el envío se hizo (se pulsó «Enviar respuestas» o «Aplicar» y la página cambió) pero el portal no mostró confirmación
- **THEN** la card conserva el aviso de que no hubo confirmación y de revisar «Mis postulaciones»

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
