## Purpose

Permite que solo los administradores del bot entren al panel web, sin contraseñas: el bot les entrega un enlace de un solo uso y el panel mantiene una sesión segura y auditada.

## ADDED Requirements

### Requirement: Lista de administradores
El sistema SHALL considerar administradores al dueño (`asistente.dueno_telegram_id`) y a los ids de Telegram de `asistente.panel.admins`. Nadie más MUST poder entrar al panel. Un id que se quita de la lista MUST perder el acceso en su siguiente petición, aunque tenga una sesión abierta.

#### Scenario: Admin de la lista
- **WHEN** el id de Telegram 111 está en `asistente.panel.admins`
- **THEN** el sistema lo trata como administrador del panel

#### Scenario: Admin retirado con sesión abierta
- **WHEN** un admin con sesión abierta deja de estar en la lista y se reinicia el servicio con la configuración nueva
- **THEN** su siguiente petición al panel responde 403, y la sesión se cierra

### Requirement: Enlace de entrada de un solo uso
Cuando un administrador envía `/panel` al bot por chat privado, el bot SHALL responderle con un enlace a `<url_publica>/panel/entrar/<token>`:
- el token es aleatorio de al menos 32 bytes;
- vence a los `asistente.panel.enlace_min` minutos (5 por defecto);
- sirve una sola vez;
- el servidor guarda solo su hash.

El mensaje con el enlace MUST borrarse solo al vencer. Un usuario que no es administrador MUST recibir la misma respuesta que con cualquier comando desconocido.

#### Scenario: Admin pide el enlace
- **WHEN** un admin envía `/panel` por chat privado
- **THEN** recibe un enlace de entrada que vence en 5 minutos, y el mensaje se borra al vencer

#### Scenario: No admin pide el enlace
- **WHEN** un usuario que no es admin envía `/panel`
- **THEN** el bot responde como ante un comando desconocido y no crea ningún token

#### Scenario: Enlace usado dos veces
- **WHEN** se abre por segunda vez un enlace de entrada ya usado
- **THEN** el panel muestra «Este enlace ya se usó o venció. Pide otro con /panel» y no crea sesión

#### Scenario: Enlace vencido
- **WHEN** se abre un enlace de entrada después de su vencimiento
- **THEN** el panel muestra el mismo aviso y no crea sesión

#### Scenario: Panel desactivado
- **WHEN** `asistente.panel.activo` es false
- **THEN** `/panel` responde que el panel está desactivado, y toda ruta bajo `/panel/` responde 404

### Requirement: Sesión del panel
Al canjear un enlace válido, el sistema SHALL crear una sesión que dura `asistente.panel.sesion_h` horas (8 por defecto) y redirigir a la portada del panel. La sesión se identifica con una cookie con estas características:
- `HttpOnly`, `Secure`, `SameSite=Strict` y `Path=/panel`;
- su valor es aleatorio y el servidor guarda solo el hash.

Sin una sesión válida, toda ruta del panel salvo la de entrada MUST mostrar la página «Pide un enlace con /panel en el bot», o responder 401 si es de datos. El panel MUST ofrecer «Cerrar sesión», que invalida la sesión en el servidor.

#### Scenario: Canje correcto
- **WHEN** un admin abre un enlace válido
- **THEN** el panel crea la sesión, pone la cookie y redirige a `/panel/`

#### Scenario: Sesión vencida
- **WHEN** pasan 8 horas desde el canje
- **THEN** la siguiente petición pide un enlace nuevo

#### Scenario: Cerrar sesión
- **WHEN** el admin pulsa «Cerrar sesión»
- **THEN** la sesión deja de valer en el servidor aunque alguien conserve la cookie

### Requirement: Protecciones del panel
El panel SHALL cumplir lo siguiente:
- limitar los intentos de canje por IP (20 por minuto);
- exigir un token CSRF de la sesión en toda petición que no sea GET;
- enviar `Content-Security-Policy` que solo permita recursos del propio origen, junto con `X-Frame-Options: DENY` y `Cache-Control: no-store`;
- no cargar recursos de terceros.

Cada entrada, salida y entrada rechazada MUST quedar en `auditoria`, con el id de Telegram cuando se conozca.

#### Scenario: Petición de cambio sin CSRF
- **WHEN** llega un POST al panel con una sesión válida pero sin el token CSRF
- **THEN** responde 403 y no hace nada

#### Scenario: Auditoría de entrada
- **WHEN** un admin canjea un enlace
- **THEN** `auditoria` registra la acción `panel_entrar` con su id de Telegram

### Requirement: Datos personales en el panel
El panel MUST NOT mostrar:
- hojas de vida, perfiles ni respuestas de cuestionarios;
- claves de IA;
- correos de las cuentas de portales;
- teléfonos ni documentos.

En las estadísticas, los usuarios aparecen solo como conteos.

#### Scenario: Estadísticas sin datos personales
- **WHEN** un admin abre cualquier vista de estadísticas
- **THEN** ninguna respuesta del panel contiene campos de perfil, CV, clave ni correo
