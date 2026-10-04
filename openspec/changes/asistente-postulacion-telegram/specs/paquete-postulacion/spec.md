## Purpose

Resolver el enlace ⚡ Postularme del canal, obtener el detalle de la vacante, calcular la
afinidad, responder preguntas de postulación con el mínimo uso de IA y, cuando la postulación
automática no es posible, entregar un paquete listo para copiar. También registra el
seguimiento de cada vacante del usuario.

## ADDED Requirements

### Requirement: Resolución del enlace del canal
El enlace ⚡ SHALL identificar la vacante publicada con un id corto, estable y derivado de su clave, sin datos personales ni de la vacante en claro. Al abrirlo, el asistente MUST mostrar la vacante y decidir el camino:
- **postulación automática**, si la plataforma está soportada y el usuario tiene un navegador vinculado;
- **paquete de respaldo**, en cualquier otro caso.

Un id desconocido, o de una vacante con más días que la retención configurada, MUST responderse con un mensaje claro.

#### Scenario: Vacante de plataforma soportada con navegador vinculado
- **WHEN** el usuario toca ⚡ en una vacante de Computrabajo con su navegador vinculado
- **THEN** se inicia la postulación automática

#### Scenario: Vacante antigua
- **WHEN** el id corresponde a una vacante de hace 120 días
- **THEN** el bot indica que la vacante ya no está disponible en el asistente

### Requirement: Detalle de la vacante
El asistente SHALL obtener la descripción completa desde la página pública de la vacante:
- bajo demanda y sin iniciar sesión;
- respetando el ritmo y los cooldowns de la fuente;
- con una caché compartida entre usuarios.

Si la página exige sesión, muestra captcha o bloqueo, MUST usarse la información de la publicación, sin evadir nada. Una vacante cerrada MUST informarse y no postularse.

#### Scenario: Detalle en caché
- **WHEN** dos usuarios piden la misma vacante el mismo día
- **THEN** la página pública se consulta una sola vez

#### Scenario: Vacante cerrada
- **WHEN** la página indica que la vacante ya no recibe postulaciones
- **THEN** el bot avisa que está cerrada y no se postula

### Requirement: Afinidad
Para cada vacante pedida, el asistente SHALL calcular una afinidad determinista entre los requisitos de la vacante y el perfil del usuario, con sinónimos. La afinidad se informa en el mensaje de progreso con lo que cumple y lo que no. Los requisitos de cada vacante se extraen una sola vez y se comparten entre usuarios. Si no hay IA disponible, se usa un respaldo por diccionario de tecnologías. La afinidad MUST NOT impedir una postulación que el usuario pidió con ⚡.

#### Scenario: Afinidad informada
- **WHEN** la vacante pide Python, SQL y Git, y el usuario tiene Python y SQL
- **THEN** el mensaje muestra la afinidad y que falta Git, y la postulación continúa

### Requirement: Respuestas en cascada con mínimo uso de IA
Cada pregunta de postulación SHALL resolverse en este orden, deteniéndose en el primero que responde:
1. Campo del perfil o del cuestionario indicado por el banco compartido.
2. Respuesta aprendida del usuario.
3. Clasificación de una pregunta nueva contra los campos del perfil, con una llamada a la IA que se guarda en el banco compartido y no se repite.
4. Redacción con la IA para preguntas abiertas, solo con datos del perfil y de la vacante.

Cada respuesta MUST guardar su origen. En una pregunta de opciones, la respuesta MUST ser una de las opciones. Lo que ningún paso puede sustentar MUST NOT inventarse. El banco compartido MUST guardar solo la correspondencia entre la pregunta normalizada y el campo, nunca respuestas personales.

#### Scenario: Pregunta conocida
- **WHEN** la pregunta es "Aspiración salarial" y el banco la asocia al campo de salario
- **THEN** se responde con el salario del perfil sin llamar a la IA

#### Scenario: Pregunta nueva clasificable
- **WHEN** la pregunta es "¿Cuál es tu pretensión económica mensual?" y no está en el banco
- **THEN** una llamada de clasificación la asocia al salario, se guarda en el banco y la siguiente vez, para cualquier usuario, no llama a la IA

### Requirement: Paquete de respaldo
Cuando la postulación automática no es posible, el usuario SHALL recibir un paquete en mensajes ordenados, cada parte copiable:
- la afinidad;
- el CV adaptado en PDF;
- un mensaje de presentación (máximo 1.000 caracteres por defecto);
- las respuestas a las preguntas típicas de esa fuente;
- sus datos;
- los botones Abrir vacante, Responder preguntas del formulario, Ya me postulé y No me interesa.

Los casos que lo activan son: plataforma no soportada, sin navegador vinculado, navegador sin conectarse en 24 horas, sesión del portal sin iniciar en 24 horas, captcha no resuelto, formulario desconocido o pregunta sin respuesta del usuario.

El paquete también MUST indicar por qué no fue automático y cómo lograrlo la próxima vez. Con "Responder preguntas del formulario", el usuario pega las preguntas del portal y recibe cada respuesta resuelta con la cascada.

#### Scenario: LinkedIn
- **WHEN** el usuario toca ⚡ en una vacante de LinkedIn
- **THEN** recibe el paquete con "LinkedIn no admite postulación automática"

#### Scenario: Preguntas pegadas
- **WHEN** el usuario pega tres preguntas del formulario
- **THEN** recibe tres respuestas copiables con su origen

### Requirement: Seguimiento
Cada vacante pedida por un usuario SHALL tener un estado de seguimiento: enviada, postulada a mano, descartada, entrevista, rechazada u oferta. El usuario lo cambia con botones. `/historial` lista sus vacantes con estado y fecha. Dos días después de un paquete de respaldo sin marcar, el bot MUST preguntar una sola vez si se postuló.

#### Scenario: Recordatorio único
- **WHEN** pasan 2 días de un paquete de respaldo sin marcar
- **THEN** el bot pregunta una vez "¿Te postulaste a …?" con botones

### Requirement: Bot propio, privado y robusto
El asistente SHALL usar un bot propio, distinto del bot que publica en el canal, que consulta actualizaciones por long polling. El bot de Hermes MUST seguir sin consultar actualizaciones.

En grupos, el bot MUST responder solo con la indicación de escribirle en privado. Cada usuario MUST ver y modificar solo sus propios datos. Las tareas largas MUST NOT bloquear la atención de otros usuarios. Un fallo del asistente MUST NOT afectar al buscador ni a la publicación del canal.

#### Scenario: Usuarios simultáneos
- **WHEN** tres usuarios tocan ⚡ al mismo tiempo
- **THEN** los tres reciben respuesta de progreso de inmediato y sus resultados no se mezclan

#### Scenario: Asistente caído
- **WHEN** el servicio del asistente está detenido
- **THEN** el buscador publica normalmente, y los enlaces ⚡ funcionan cuando el servicio vuelve
