## Purpose

Registro y gestión de los usuarios del asistente de postulación: autorización de datos, alta
guiada con el CV, perfil, cuestionario base, baja con borrado total y administración por el
dueño.

## ADDED Requirements

### Requirement: Autorización de tratamiento de datos
Antes de guardar cualquier dato de una persona, el bot SHALL mostrar el texto de autorización y la política de tratamiento de datos (Ley 1581 de 2012), configurables, y pedir aceptación explícita con un botón. El texto MUST indicar:
- qué datos se guardan y para qué;
- que la IA usada es Gemini con la clave del propio usuario y que, en su plan gratuito, Google puede usar el contenido enviado;
- que, si instala y vincula la extensión, esta postula desde su navegador y con su sesión solo a las vacantes que pida (o a las de su modo automático), que el servidor nunca recibe sus contraseñas ni sesiones y que los portales podrían restringir el uso automatizado de su cuenta;
- cómo pedir el borrado.

Sin aceptación MUST NOT guardarse nada más que el id de Telegram y la negativa. La aceptación MUST registrarse con su fecha y la versión del texto. Si el texto cambia de versión, el usuario MUST aceptarlo de nuevo antes de seguir usando el asistente.

#### Scenario: Acepta
- **WHEN** una persona nueva pulsa "Acepto"
- **THEN** se registra la aceptación con fecha y versión y continúa el alta

#### Scenario: No acepta
- **WHEN** la persona pulsa "No acepto"
- **THEN** el bot explica que sin autorización no puede ayudarle y no guarda datos personales

#### Scenario: Nueva versión del texto
- **WHEN** el dueño publica una nueva versión de la política y un usuario existente usa el bot
- **THEN** debe aceptar la nueva versión antes de continuar

### Requirement: Acceso solo para miembros del grupo
El asistente SHALL atender solo a personas que son miembros del grupo privado de Telegram donde se publican las vacantes. La membresía MUST comprobarse con Telegram:
- al iniciar el alta;
- en cada toque de ⚡;
- una vez al día para todos los usuarios.

Una persona que no es miembro MUST recibir un mensaje indicando que el asistente es exclusivo del grupo, sin guardarse ningún dato suyo. Un usuario que deja el grupo, o es expulsado, MUST quedar suspendido: no se encolan postulaciones y las pendientes se cancelan. Si vuelve al grupo, MUST reactivarse en la siguiente comprobación.

Si Telegram no permite comprobar la membresía (por ejemplo, porque el bot dejó de ser administrador del grupo), el asistente MUST negar las altas nuevas, conservar el estado de los usuarios existentes y avisar al dueño.

#### Scenario: Miembro del grupo
- **WHEN** un miembro del grupo toca ⚡ por primera vez
- **THEN** inicia el alta y, al terminarla (y vincular su navegador, si quiere), se procesa esa vacante sin volver al grupo

#### Scenario: No es miembro
- **WHEN** una persona que no está en el grupo escribe al bot
- **THEN** el bot responde que el asistente es exclusivo del grupo y no guarda datos

#### Scenario: Sale del grupo
- **WHEN** un usuario registrado deja el grupo
- **THEN** en la siguiente comprobación queda suspendido y sus postulaciones pendientes se cancelan

#### Scenario: Bot sin permisos en el grupo
- **WHEN** la consulta de membresía falla porque el bot ya no es administrador
- **THEN** no se aceptan altas nuevas y el dueño recibe el aviso

### Requirement: Perfil a partir del CV
Durante el alta, el usuario SHALL enviar su CV en PDF (tamaño máximo configurable, 5 MB por defecto). El asistente MUST extraer con Gemini un perfil estructurado:
- nombre y ciudad;
- formación (institución, programa, semestre o nivel, estado);
- experiencia y proyectos;
- habilidades técnicas y blandas;
- idiomas con su nivel;
- certificaciones y enlaces (GitHub, portafolio, LinkedIn).

El perfil extraído MUST mostrarse en **un solo mensaje de resumen** con los datos de contacto encontrados (nombre, ciudad, correo, celular), formación, experiencia, proyectos, habilidades, idiomas y el enfoque propuesto, con dos botones: **Información correcta** y **Editar**.
- Con **Información correcta**, no se vuelve a preguntar nada de lo que el CV ya dice: el alta sigue con las preguntas del cuestionario base que el CV no responde.
- Solo con **Editar** se revisa sección por sección, se ajusta el enfoque y se responde el cuestionario base completo.

Un campo que el CV no trae MUST quedar vacío, nunca inventado.

Si el archivo no es un PDF, supera el tamaño, no parece un CV o no se puede leer, el bot MUST explicarlo y pedir otro archivo. Si el usuario aún no tiene clave de Gemini, o la suya falla, MUST poder llenar el perfil a mano con preguntas guiadas.

#### Scenario: CV legible
- **WHEN** el usuario envía un PDF de 300 KB con su hoja de vida
- **THEN** recibe un solo resumen de su perfil con los botones "Información correcta" y "Editar"

#### Scenario: Información correcta
- **WHEN** el usuario pulsa "Información correcta"
- **THEN** el bot hace solo las preguntas del cuestionario base que el CV no responde (por ejemplo aspiración salarial y disponibilidad) y no repite las que ya respondió el CV (nombre, correo, celular, ciudad)

#### Scenario: Editar
- **WHEN** el usuario pulsa "Editar"
- **THEN** revisa cada sección con "Correcto" o "Corregir", ajusta su enfoque y responde el cuestionario base

#### Scenario: CV escaneado
- **WHEN** el PDF es una imagen escaneada y el usuario confirma el envío del archivo completo
- **THEN** Gemini lo lee como imagen y el flujo sigue igual

#### Scenario: Archivo que no es CV
- **WHEN** el usuario envía un PDF de una factura
- **THEN** el bot indica que no parece una hoja de vida y pide otro archivo

#### Scenario: Sin IA disponible
- **WHEN** la clave del usuario no funciona
- **THEN** el bot ofrece llenar el perfil con preguntas guiadas

### Requirement: Datos de contacto y cuestionario base
El perfil SHALL tomar del CV, sin preguntar, todo lo que este trae: nombre, ciudad, correo, celular, documento, si estudia actualmente y nivel de inglés. Durante el alta, tras confirmar el resumen, el bot MUST preguntar **solo** los datos del cuestionario base que el CV no respondió, que son los que los formularios de las vacantes suelen pedir. El cuestionario completo, incluidas las preguntas que el CV respondió, se recorre solo al elegir "Editar" o con `/cuestionario`. Si más adelante un formulario pide un dato que aún falta, se pregunta una sola vez y queda guardado. Los datos del cuestionario son:
- correo, teléfono y documento (opcional);
- aspiración salarial;
- disponibilidad de inicio y horario;
- modalidades y ciudades aceptadas;
- si estudia actualmente y el tipo de práctica que busca (contrato de aprendizaje, práctica universitaria o pasantía);
- nivel de inglés;
- equipo propio y conexión;
- disponibilidad para trasladarse;
- autorización para que el asistente actualice su hoja de vida en los portales con la versión adaptada a cada vacante (sí o no, modificable después en `/perfil`). Si el usuario no la ha dado, se le pregunta la primera vez que un portal la necesite.

Cada pregunta del cuestionario MUST poder responderse con botones cuando tiene opciones cerradas. El cuestionario MUST poder retomarse donde quedó y editarse luego con `/cuestionario`.

#### Scenario: Dato que el CV no trae
- **WHEN** el CV no dice la aspiración salarial y el usuario confirma el resumen
- **THEN** el bot se la pregunta durante el alta y queda guardada para todas las postulaciones

#### Scenario: Dato que falta al postular
- **WHEN** un formulario pide un dato que todavía no está en el perfil
- **THEN** el bot lo pregunta una sola vez, lo guarda en el perfil y la siguiente postulación lo usa sin preguntar

#### Scenario: Cuestionario interrumpido
- **WHEN** el usuario eligió "Editar", respondió 4 preguntas y vuelve al día siguiente
- **THEN** el bot retoma desde la quinta

#### Scenario: Respuesta con botones
- **WHEN** la pregunta es el nivel de inglés
- **THEN** el bot ofrece botones A1–C2 y "Ninguno"

### Requirement: Enfoque profesional del usuario
El perfil SHALL incluir el enfoque del usuario: los roles que busca (por ejemplo desarrollo backend, soporte, datos), las tecnologías que quiere destacar y una frase sobre su objetivo. El enfoque MUST usarse para adaptar el CV y las respuestas. Gemini MUST poder proponerlo a partir del CV; el usuario lo confirma junto con el resumen del perfil o lo cambia al elegir "Editar".

#### Scenario: Enfoque propuesto
- **WHEN** termina la lectura del CV
- **THEN** el enfoque propuesto aparece en el resumen y se confirma con "Información correcta"

### Requirement: Consulta, edición y baja
El usuario SHALL poder:
- ver su perfil con `/perfil` y editar cualquier sección;
- reemplazar el CV;
- pausar las respuestas con `/pausa`.

Con `/borrarme`, y una confirmación, MUST borrarse en forma definitiva:
- su perfil, CV y PDF generados;
- su clave de Gemini;
- sus respuestas aprendidas e historial.

Solo se conserva un registro anónimo de la baja con la fecha. Los usuarios sin actividad durante el plazo configurado (12 meses por defecto) MUST recibir un aviso y, si no responden en 30 días, sus datos MUST borrarse.

#### Scenario: Baja
- **WHEN** el usuario confirma `/borrarme`
- **THEN** sus archivos y filas se eliminan y el bot confirma el borrado

#### Scenario: Inactividad
- **WHEN** un usuario lleva 12 meses sin usar el asistente y no responde al aviso en 30 días
- **THEN** sus datos se borran

### Requirement: Administración por el dueño
El bot SHALL reconocer al dueño por su id de Telegram configurado y le SHALL ofrecer estos comandos:
- `/usuarios`: lista los usuarios con su estado y última actividad.
- `/suspender <usuario>` y `/reactivar <usuario>`.
- `/stats`: métricas agregadas.

Los comandos de administración MUST rechazarse para cualquier otro usuario. El dueño MUST NOT poder ver la clave de Gemini de ningún usuario, y MUST ver los perfiles solo con un comando explícito que queda registrado.

#### Scenario: Usuario suspendido
- **WHEN** el dueño suspende a un usuario y este toca ⚡ Postularme
- **THEN** el bot le indica que su acceso está suspendido

#### Scenario: Comando de administración ajeno
- **WHEN** un usuario común envía `/usuarios`
- **THEN** el bot responde como a un comando desconocido
