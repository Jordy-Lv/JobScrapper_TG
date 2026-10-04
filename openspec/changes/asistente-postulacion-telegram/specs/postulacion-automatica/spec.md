## Purpose

Postular automáticamente, desde el navegador vinculado de cada usuario y con su propia sesión e
IP, a la vacante en la que tocó ⚡ Postularme. Incluye llenar todo, responder las preguntas,
adjuntar el CV adaptado, enviar y confirmar, sin más acciones del usuario y sin evadir
protecciones anti-bot.

## ADDED Requirements

### Requirement: El toque es la orden
Cuando un usuario registrado y activo toca ⚡ Postularme en una vacante de una plataforma soportada (Computrabajo o Magneto), el sistema SHALL encolar la postulación de inmediato, sin pedir más confirmaciones. Para eso el usuario debe tener un navegador vinculado. El bot MUST responder en segundos con la vacante y su estado, y actualizar ese mismo mensaje con el progreso (en cola, postulando, resultado).

Si la plataforma no está soportada o el usuario no tiene navegador vinculado, MUST entregarse el paquete de respaldo con la indicación de cómo hacerla automática.

#### Scenario: Navegador en línea
- **WHEN** un usuario con Edge abierto y Computrabajo listo toca ⚡ en una vacante de Computrabajo
- **THEN** recibe "Postulando…" y, sin otra acción, el resultado final

#### Scenario: Navegador desconectado
- **WHEN** el usuario toca ⚡ y su navegador lleva más de 2 minutos sin reportarse
- **THEN** el bot responde "Se enviará cuando abras tu navegador", y la postulación se ejecuta sola al reconectarse

#### Scenario: Plataforma no soportada
- **WHEN** toca ⚡ en una vacante de LinkedIn
- **THEN** recibe el paquete de respaldo con el aviso de que LinkedIn no admite postulación automática

### Requirement: Preparación en el servidor
Al encolar una postulación, el servidor SHALL preparar el detalle de la vacante, la afinidad y el CV levemente adaptado. Cuando la extensión envía las preguntas reales del formulario, el servidor MUST resolverlas con la cascada de respuestas y devolver, para cada campo, el valor exacto a escribir o la opción exacta a elegir.

#### Scenario: Preguntas del formulario
- **WHEN** la extensión envía 6 campos leídos del formulario de Computrabajo
- **THEN** el servidor devuelve un valor o una opción para cada uno, con su origen

### Requirement: Postulación completa
El adaptador de cada plataforma SHALL seguir estos pasos:
1. Verificar que la sesión esté iniciada, que la vacante siga abierta y que no exista postulación previa.
2. Iniciar la postulación.
3. Llenar **todos** los campos.
4. Usar el CV adaptado a esa vacante: adjuntarlo si el formulario admite archivo; si el portal usa el CV guardado en el perfil, actualizar ese CV con el adaptado antes de postular, según el requisito de CV del portal.
5. Enviar.
6. Confirmar el registro en el portal.

Solo una señal explícita de éxito del portal MUST dejar la postulación como `enviada`.

#### Scenario: Éxito
- **WHEN** el formulario se llena completo, se envía y el portal confirma
- **THEN** la postulación queda `enviada` y el usuario recibe la confirmación con el resumen de preguntas y respuestas

#### Scenario: Ya postulado
- **WHEN** el portal indica que el usuario ya se postuló
- **THEN** queda `ya_postulada` y no se envía nada

#### Scenario: Sesión del portal cerrada
- **WHEN** el usuario no tiene la sesión iniciada en ese portal
- **THEN** la postulación queda `esperando_sesion`, el bot le pide iniciar sesión en ese navegador y se retoma sola al detectarse la sesión

#### Scenario: Cuenta del portal distinta
- **WHEN** la sesión abierta en el portal pertenece a un correo distinto de la cuenta asociada del usuario
- **THEN** no se postula, la postulación queda `cuenta_distinta` y el bot avisa según el requisito de cuenta del portal asociada

#### Scenario: Perfil del portal incompleto
- **WHEN** al postular, el portal exige completar el perfil antes de aceptar la postulación
- **THEN** la extensión completa el perfil según el requisito de cuenta y perfil del portal y continúa la postulación

#### Scenario: Formulario sin campo de archivo
- **WHEN** el portal usa el CV guardado en el perfil del usuario y no permite adjuntar otro
- **THEN** antes de postular se actualiza el CV del perfil con el adaptado a esa vacante, y el registro lo indica

### Requirement: CV del portal actualizado por vacante
Cuando un portal postula con la hoja de vida guardada en el perfil del usuario, el sistema SHALL dejar cargado en el perfil el CV adaptado a esa vacante antes de enviar la postulación:
- si el portal permite guardar varios CV, se sube el adaptado y se selecciona en esa postulación; la cantidad de CV que el sistema conserva tiene el límite del portal y se reemplazan primero los subidos por el sistema, nunca los del usuario;
- si el portal permite uno solo, se reemplaza.

La primera vez que haya que reemplazar un CV subido por el propio usuario, el sistema MUST contar con su autorización explícita, que se pide en el alta (por ejemplo, "Permitir que el asistente actualice mi CV en los portales"). Sin ella, se postula con el CV existente y el registro lo indica.

El reemplazo MUST verificarse (el archivo nuevo aparece en el perfil) antes de enviar la postulación. Si falla, se postula con el CV que haya y se registra el motivo.

#### Scenario: Portal con un solo CV
- **WHEN** Computrabajo usa el CV del perfil, admite uno solo y el usuario autorizó la actualización
- **THEN** la extensión reemplaza el CV por el adaptado a esa vacante, verifica que quedó cargado y luego postula

#### Scenario: Portal con varios CV
- **WHEN** el portal permite elegir entre varios CV guardados
- **THEN** se sube el adaptado, se elige en la postulación y los CV del usuario no se tocan

#### Scenario: Sin autorización
- **WHEN** el usuario no autorizó actualizar su CV en los portales
- **THEN** se postula con el CV que tiene en el portal y el registro lo indica

### Requirement: Datos faltantes preguntados una sola vez
Si un campo obligatorio no puede responderse con fundamento, el servidor SHALL preguntarle al usuario por el bot, con botones si hay opciones y con texto si es abierta. Mientras tanto, la extensión cierra la pestaña sin enviar. La respuesta MUST guardarse como aprendida y la postulación MUST volver a la cola para ejecutarse sola.

Si el usuario no responde en 12 horas, se entrega el paquete de respaldo. El sistema MUST NOT inventar ni elegir al azar una respuesta obligatoria.

#### Scenario: Pregunta nueva sin dato
- **WHEN** el formulario pregunta "¿Tienes licencia de conducción?" y el perfil no lo sabe
- **THEN** el bot pregunta con Sí/No, el usuario toca "No", la postulación se completa sola y la próxima vez no se pregunta

### Requirement: Ritmo y topes
Cada navegador SHALL ejecutar las postulaciones de su usuario de a una, con una pausa aleatoria configurable entre ellas, y respetar un tope diario por usuario (15 por defecto). Al alcanzar el tope, la postulación queda en cola para el día siguiente con aviso. El sistema MUST NOT usar proxies ni cambiar la IP del usuario.

#### Scenario: Tope diario
- **WHEN** el usuario ya tiene 15 postulaciones hoy y toca ⚡
- **THEN** el bot le indica que se enviará mañana

### Requirement: Captcha y verificaciones
Ante un captcha o una verificación, la extensión SHALL detenerse sin intentar resolverlo, dejar la pestaña visible y abierta, y el bot MUST avisar al usuario: "Completa la verificación en tu navegador". Si el usuario la completa, la extensión MUST continuar la postulación. Si no ocurre en 2 horas, la postulación pasa a `bloqueada` y se entrega el paquete de respaldo.

#### Scenario: Captcha resuelto por el usuario
- **WHEN** aparece un captcha y el usuario lo completa en su navegador
- **THEN** la extensión continúa y termina la postulación

### Requirement: Detención segura
Además de los casos anteriores:
- ante un formulario que el adaptador no reconoce, la postulación SHALL quedar `formulario_desconocido`;
- si tras enviar no aparece una confirmación ni un error claro, MUST quedar `incierta`;
- una postulación que llegó a pulsar el envío MUST NOT reenviarse automáticamente;
- si el navegador se cierra a mitad de una postulación sin haber pulsado el envío, la postulación vuelve a la cola; si ya lo había pulsado, queda `incierta`.

En los casos de problema se informa al usuario, se entrega el paquete de respaldo (salvo en `incierta`, donde se le pide verificar en el portal) y el dueño recibe el reporte con evidencia.

#### Scenario: Navegador cerrado antes de enviar
- **WHEN** el usuario cierra Edge mientras se llenaba el formulario
- **THEN** la postulación vuelve a la cola y se ejecuta cuando Edge se abra de nuevo

#### Scenario: Navegador cerrado después de enviar
- **WHEN** Edge se cierra justo después de pulsar el envío
- **THEN** la postulación queda `incierta` y se pide al usuario verificar en "Mis postulaciones"

### Requirement: Unicidad
Un usuario SHALL tener como máximo una postulación por vacante. Un nuevo toque sobre una vacante en curso o ya enviada MUST mostrar su estado actual sin crear otra.

#### Scenario: Doble toque
- **WHEN** el usuario toca ⚡ dos veces en la misma vacante
- **THEN** existe una sola postulación y el segundo toque muestra su estado

### Requirement: Registro detallado del proceso
Cada postulación SHALL registrar:
- cada paso con su hora;
- cada campo del formulario con su respuesta y su origen (perfil, banco, aprendida, IA o usuario);
- el CV usado;
- el navegador que la ejecutó;
- el resultado.

El usuario MUST verlo con `/detalle <n>`, y el mensaje de resultado MUST incluir el resumen de preguntas y respuestas.

#### Scenario: Consulta del proceso
- **WHEN** el usuario envía `/detalle 5` de una postulación enviada
- **THEN** recibe los pasos con su hora, cada pregunta con su respuesta y origen, y el CV adjunto

### Requirement: Modo automático opcional por usuario
Cada usuario SHALL poder activar con `/automatico [umbral]` que el sistema encole sin tocar ⚡ las vacantes publicadas de sus plataformas listas con afinidad igual o mayor al umbral (70 % por defecto), dentro de su tope. El modo MUST estar desactivado por defecto.

#### Scenario: Automático activo
- **WHEN** el usuario tiene el modo automático con un umbral de 70 % y se publica una vacante de Computrabajo con afinidad del 82 %
- **THEN** se encola su postulación y recibe el resultado sin haber tocado ⚡
