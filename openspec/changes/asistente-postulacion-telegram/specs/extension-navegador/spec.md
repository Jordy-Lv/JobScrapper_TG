## Purpose

Extensión de navegador (Edge como navegador principal, y Chrome o Brave por carga manual) que
cada usuario instala gratis y vincula con el bot. Ejecuta las postulaciones en su propio
navegador, con su sesión y su IP, siguiendo las instrucciones del servidor. El servidor nunca
recibe contraseñas ni sesiones.

## ADDED Requirements

### Requirement: Instalación sin costo
La extensión SHALL distribuirse sin costo para el dueño ni para los usuarios:
- publicada en la tienda de complementos de Microsoft Edge;
- como paquete para carga manual en Chrome y Brave, que el bot entrega con una guía paso a paso.

La extensión MUST pedir solo los permisos necesarios: almacenamiento, pestañas, alarmas, los dominios de los portales soportados y la URL del servidor. MUST NOT tener permisos sobre otros sitios ni sobre el historial.

#### Scenario: Instalación en Edge
- **WHEN** el usuario abre en Edge el enlace de la tienda que le da el bot y pulsa Obtener
- **THEN** la extensión queda instalada y se actualiza sola en adelante

#### Scenario: Carga manual desactualizada
- **WHEN** el servidor exige una versión mínima mayor que la de una extensión cargada a mano
- **THEN** el bot avisa al usuario con el paso a paso para actualizarla, y la extensión no ejecuta postulaciones hasta actualizarse

### Requirement: Vinculación por enlace
El usuario SHALL vincular su navegador tocando "Vincular mi navegador" en el bot:
- se abre una página del servidor con un código temporal (10 minutos, un solo uso) que la extensión instalada detecta y canjea por un token propio del usuario, sin que el usuario escriba nada;
- como respaldo, la extensión acepta el código escrito a mano.

El servidor MUST guardar solo el hash del token. Un usuario MUST poder ver y revocar sus navegadores vinculados con `/navegadores`.

#### Scenario: Vinculación automática
- **WHEN** el usuario con la extensión instalada toca "Vincular mi navegador"
- **THEN** la página confirma la vinculación y el bot avisa "✅ Navegador vinculado"

#### Scenario: Extensión no instalada
- **WHEN** el usuario abre el enlace de vinculación sin la extensión
- **THEN** la página le indica cómo instalarla y le permite reintentar

### Requirement: Detección de sesión en los portales
La extensión SHALL informar al servidor, para cada portal soportado:
- si el usuario tiene la sesión iniciada en ese navegador;
- si su perfil del portal está completo;
- el **correo de la cuenta** con la que está iniciada la sesión, leído de la página del perfil o de la cuenta del portal.

Lo hace al vincularse, al visitar el portal y antes de cada postulación. MUST NOT leer ni enviar contraseñas, cookies ni el contenido del almacenamiento del portal.

#### Scenario: Portal listo
- **WHEN** el usuario inicia sesión en Computrabajo en el navegador vinculado
- **THEN** el bot avisa "Computrabajo listo ✅ · cuenta: ana.perez@gmail.com"

### Requirement: Cuenta del portal asociada a cada usuario
La primera vez que se detecta una sesión en un portal, el bot SHALL mostrar al usuario el correo de esa cuenta y pedirle que confirme que es la suya. Desde la confirmación, ese correo queda como **cuenta asociada** del usuario para ese portal. El correo se guarda cifrado, con un hash para compararlo.

El usuario MUST ver los correos asociados de cada plataforma en `/estado` y en `/perfil`, y MUST poder cambiarlos.

Antes de cada postulación y de cada completado de perfil, la extensión MUST comprobar que el correo de la sesión abierta coincide con la cuenta asociada. Si no coincide:
- MUST NOT postular ni modificar nada;
- la postulación queda en `cuenta_distinta`;
- el bot avisa al usuario mostrando su correo asociado y el correo encontrado enmascarado (por ejemplo `l***@hotmail.com`), con los botones "Es mi cuenta nueva, usarla" y "No es mía".

Si el correo no se puede leer, la postulación MUST detenerse como `formulario_desconocido` en lugar de continuar sin verificar.

#### Scenario: Confirmación inicial
- **WHEN** la extensión detecta por primera vez la sesión de Magneto con el correo ana.perez@gmail.com
- **THEN** el bot pregunta "¿Esta es tu cuenta de Magneto: ana.perez@gmail.com?" y, al confirmar, queda asociada

#### Scenario: Otra persona inició sesión en el navegador
- **WHEN** la cuenta asociada de Ana en Computrabajo es ana.perez@gmail.com y en su navegador hay una sesión abierta de luis.g@hotmail.com
- **THEN** no se postula y Ana recibe "La cuenta de Computrabajo abierta en tu navegador (l***@hotmail.com) no es la tuya (ana.perez@gmail.com)"

#### Scenario: Cambio legítimo de cuenta
- **WHEN** Ana pulsa "Es mi cuenta nueva, usarla"
- **THEN** el nuevo correo queda asociado y la postulación vuelve a la cola

#### Scenario: Consulta de cuentas
- **WHEN** el usuario envía `/estado`
- **THEN** ve, por plataforma, el estado (listo, sin sesión, incompleto) y el correo asociado

### Requirement: Cuenta y perfil del portal
La extensión SHALL distinguir tres estados por portal: sin sesión o sin cuenta, perfil incompleto y listo.

**Sin cuenta.** La cuenta del portal MUST crearla el propio usuario, porque implica su contraseña, la verificación de su correo y la aceptación de los términos del portal. El bot MUST indicarle qué falta con el enlace directo de registro del portal y una guía paso a paso. Al detectarse la sesión, MUST avisarle que ese paso quedó listo.

**Perfil incompleto.** Si el usuario tiene sesión, la extensión MUST revisar las secciones del perfil del portal que exige la postulación: datos personales, formación, experiencia y hoja de vida cargada. Si falta alguna, MUST completarla automáticamente con el perfil confirmado del usuario y su CV base, en una pestaña en segundo plano y con un reporte de cada paso, igual que una postulación.

**Límites del completado:**
- MUST NOT cambiar la contraseña, el correo de acceso, los datos de verificación ni las preferencias de privacidad y notificación del portal;
- MUST NOT borrar información que el usuario ya tenga en el portal. La única excepción es el archivo de hoja de vida, que se reemplaza según el requisito de CV del portal y la autorización del usuario;
- un campo del portal sin dato en el perfil MUST preguntarse una sola vez por el bot.

#### Scenario: Sin cuenta en Magneto
- **WHEN** un usuario vinculado no tiene cuenta en Magneto
- **THEN** el bot le indica "Te falta crear tu cuenta en Magneto" con el enlace de registro, y al detectar su sesión le avisa que Magneto quedó listo

#### Scenario: Perfil incompleto
- **WHEN** el usuario tiene sesión en Computrabajo pero no tiene hoja de vida cargada ni formación registrada
- **THEN** la extensión carga su CV base y registra su formación desde el perfil, y el bot avisa "Tu perfil de Computrabajo quedó completo"

#### Scenario: Datos existentes
- **WHEN** el perfil del portal ya tiene una experiencia que no está en el perfil del bot
- **THEN** la extensión no la borra ni la modifica

### Requirement: Ejecución de la cola en el navegador del usuario
Mientras el navegador está abierto, la extensión SHALL consultar al servidor la cola de su usuario cada 30 segundos como máximo y reportar que está en línea. Por cada postulación lista, en orden y de a una:
1. Abre la vacante en una pestaña en segundo plano.
2. Ejecuta el adaptador del portal con los selectores vigentes recibidos del servidor.
3. Envía al servidor las preguntas del formulario y recibe las respuestas y el CV.
4. Llena, adjunta, envía y confirma.
5. Reporta cada paso.
6. Cierra la pestaña al terminar, salvo cuando el usuario debe intervenir.

Una postulación que la extensión tomó MUST quedar asignada a ese navegador, para que otro navegador del mismo usuario no la ejecute dos veces.

#### Scenario: Navegador abierto
- **WHEN** el usuario toca ⚡ desde el celular y su Edge está abierto en el PC
- **THEN** en menos de un minuto la extensión toma la postulación y la ejecuta sin que el usuario haga nada

#### Scenario: Dos navegadores vinculados
- **WHEN** el usuario tiene Edge en dos PC abiertos
- **THEN** la postulación la ejecuta solo uno

### Requirement: Selectores entregados por el servidor
Los selectores y textos de referencia de cada portal SHALL entregarse a la extensión como datos versionados, no como código. La extensión MUST NOT descargar ni ejecutar código remoto. Al cambiar los selectores en el servidor, la extensión MUST usar la versión nueva en la siguiente postulación, sin reinstalarse.

#### Scenario: Corrección sin publicar versión
- **WHEN** el dueño corrige un selector de Magneto en el servidor
- **THEN** la siguiente postulación de cualquier usuario usa el selector corregido

### Requirement: Reporte de errores con evidencia
Ante un fallo, la extensión SHALL reportar al servidor:
- el paso;
- el tipo de error;
- la versión de los selectores;
- el HTML del formulario con los valores de los campos borrados.

MUST NOT enviar capturas de pantalla ni datos personales del usuario. Si la pestaña está visible al terminar con éxito, MAY enviar una captura de la confirmación.

#### Scenario: Formulario cambiado
- **WHEN** un selector esperado no aparece
- **THEN** el servidor recibe el paso, el error y el HTML sin valores, y el dueño recibe el aviso

### Requirement: Preferencias por portal
Cada tarjeta de portal en la extensión SHALL tener un botón de engranaje que abre la configuración de ese portal: estado de la sesión, acciones rápidas (pausar o reanudar el modo automático en ese portal, olvidar la cuenta asociada, abrir la web del portal), el detalle de la cuenta asociada (correo, estado y fecha de confirmación) y tres ajustes propios del portal, guardados en el servidor por usuario y plataforma:
- **Postular automáticamente**: si está apagado, ese portal queda fuera del encolado automático por afinidad, sin afectar el toque ⚡ manual ni los demás portales;
- **Afinidad mínima**: un umbral propio del portal que, si está definido, reemplaza ahí al umbral general del modo automático del usuario;
- **Avisar en Telegram**: si está apagado, la ficha de éxito de las postulaciones automáticas de ese portal no se envía; los avisos que piden una acción (sesión, verificación, error) y el resultado de un toque ⚡ manual MUST enviarse siempre, sin importar este ajuste.

Sin preferencias guardadas rigen los valores por defecto: participa del modo automático, sin afinidad propia y avisa por Telegram.

#### Scenario: Apagar un portal del modo automático
- **WHEN** el usuario apaga "Postular automáticamente" en Magneto
- **THEN** las vacantes nuevas de Magneto no se encolan solas, pero el toque ⚡ y el modo automático de Computrabajo siguen igual

#### Scenario: Afinidad propia de un portal
- **WHEN** el usuario fija 85 % de afinidad mínima en Computrabajo, con un umbral general del 70 %
- **THEN** en Computrabajo solo se encolan solas las vacantes con 85 % o más

#### Scenario: Avisos apagados en un portal
- **WHEN** el usuario apaga "Avisar en Telegram" en Computrabajo y una postulación automática ahí se envía
- **THEN** no llega la ficha de "Postulación enviada", pero un toque ⚡ manual en Computrabajo sigue avisando igual

#### Scenario: Olvidar la cuenta desde la extensión
- **WHEN** el usuario toca "Olvidar cuenta" (con una segunda confirmación) en el engranaje de un portal
- **THEN** la cuenta asociada se desasocia y la próxima sesión detectada vuelve a pedirse confirmar en el bot
