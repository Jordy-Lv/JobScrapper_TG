## Purpose

Define lo que el popup de la extensión muestra y permite hacer: estado y latencia de la conexión con el servidor, recarga de la conexión, una tarjeta por portal y el pie con el último resultado y el acceso a Telegram. Es la única pantalla que el usuario ve del asistente.

## ADDED Requirements

### Requirement: Cabecera del popup
El popup SHALL mostrar en su cabecera el logo y el nombre **APOLO TI**, un engranaje que abre las opciones de la extensión y, con el navegador vinculado, el botón de pausa de las postulaciones. Sin el navegador vinculado MUST ocultar el botón de pausa y mostrar el bloque para vincular con el código.

#### Scenario: Cabecera con el navegador vinculado
- **WHEN** el usuario abre el popup con el navegador vinculado
- **THEN** ve el nombre APOLO TI, el engranaje de opciones y el botón de pausa

#### Scenario: Engranaje de opciones
- **WHEN** el usuario toca el engranaje de la cabecera
- **THEN** se abre la página de opciones de la extensión

#### Scenario: Navegador sin vincular
- **WHEN** el usuario abre el popup sin haber vinculado el navegador
- **THEN** no hay botón de pausa y aparece el campo para escribir el código de vinculación

### Requirement: Estado de conexión y ping
Con el navegador vinculado, el popup SHALL mostrar en la parte superior, bajo la cabecera, una barra de conexión con el estado del servidor y la latencia en milisegundos entre la extensión y el servidor. La latencia MUST medirse al abrir el popup y al recargar la conexión, y MUST mostrarse con un color según su valor:
- verde, si es menor de 150 ms;
- ámbar, desde 150 ms y menor de 500 ms;
- rojo, desde 500 ms.

Si el servidor no contesta, la barra MUST mostrar «Sin respuesta» en rojo en lugar de un valor. Si la extensión está en pausa, la barra MUST indicarlo sin ocultar la latencia. Mientras llega la primera medición, la barra MUST mostrar el último valor conocido o «Midiendo…».

Cualquier respuesta HTTP del servidor (incluido un error) MUST contar como alcanzado; solo la falta de respuesta (red caída, servidor apagado, tiempo agotado) cuenta como sin respuesta. La medición MUST tener un tiempo máximo de espera de 5 segundos, MUST NOT enviar credenciales ni datos del usuario y MUST NOT contar como latido ni como señal de vida del navegador en el servidor.

#### Scenario: Servidor rápido
- **WHEN** el servidor responde en 42 ms al abrir el popup
- **THEN** la barra muestra «Conectado · 42 ms» en verde

#### Scenario: Servidor lento
- **WHEN** el servidor responde en 650 ms
- **THEN** la barra muestra la latencia en rojo

#### Scenario: Servidor sin respuesta
- **WHEN** el servidor no responde en 5 segundos o la red está caída
- **THEN** la barra muestra «Sin respuesta» en rojo, y las tarjetas de portal siguen mostrando el último estado conocido

#### Scenario: Servidor desactualizado
- **WHEN** el servidor responde con un error HTTP a la medición (por ejemplo, 404 por no tener aún el endpoint de ping)
- **THEN** la barra muestra la latencia de esa respuesta como conectado, no como sin respuesta

#### Scenario: Extensión en pausa
- **WHEN** el usuario pausó las postulaciones y el servidor responde
- **THEN** la barra muestra «En pausa» junto con la latencia

### Requirement: Recarga de la conexión
La barra de conexión SHALL incluir un único botón, con icono de recargar, para recargar la conexión; el popup MUST NOT ofrecer otro botón aparte para revisar los portales. Al tocarlo, la extensión MUST volver a medir la latencia y forzar un latido con revisión de los portales, y la barra MUST mostrar «Reconectando…» con el botón deshabilitado hasta terminar. Al terminar MUST mostrar el estado y la latencia nuevos. Si el servidor no responde, MUST mostrar «Sin respuesta» y volver a habilitar el botón para reintentar.

#### Scenario: Recargar tras una caída
- **WHEN** el popup muestra «Sin respuesta», el servidor vuelve a estar disponible y el usuario toca recargar
- **THEN** la barra pasa por «Reconectando…» y termina en «Conectado» con la latencia nueva, y las tarjetas de portal reflejan el estado devuelto por el servidor

#### Scenario: Indicador mientras recarga
- **WHEN** el usuario toca recargar
- **THEN** el icono gira y el botón queda deshabilitado hasta que termina

#### Scenario: Doble toque
- **WHEN** el usuario toca recargar mientras la recarga anterior sigue en curso
- **THEN** no se lanza una segunda recarga

#### Scenario: Recarga sin servidor
- **WHEN** el usuario toca recargar y el servidor sigue caído
- **THEN** la barra muestra «Sin respuesta» y el botón queda disponible

### Requirement: Endpoint de ping del servidor
El servidor SHALL ofrecer `GET /api/v1/ping`, público, sin autenticación, que responde de inmediato un JSON con `ok: true` sin consultar la base de datos, sin cambiar ningún estado y sin contar como latido de ningún navegador. MUST aplicar un límite de peticiones por IP para no ser un punto de abuso y MUST NOT revelar datos de usuarios, versiones internas ni configuración.

#### Scenario: Ping sin token
- **WHEN** se pide `GET /api/v1/ping` sin cabecera de autorización
- **THEN** responde 200 con `ok: true`

#### Scenario: El ping no cuenta como latido
- **WHEN** una extensión vinculada mide el ping
- **THEN** el `ultimo_latido` del navegador en el servidor no cambia

#### Scenario: Exceso de peticiones
- **WHEN** una misma IP supera el límite de pings por minuto
- **THEN** el servidor responde 429 y no deja de atender a las demás IP

### Requirement: Tarjetas de portal
El popup SHALL mostrar una tarjeta por portal soportado, con el logo, el nombre, una etiqueta de estado y un borde de color propio de cada portal. La etiqueta MUST ser una de:
- **Listo ✓**: sesión iniciada, cuenta confirmada y perfil completo, mostrando el correo de la cuenta;
- **Sin sesión**, con la acción «Iniciar sesión ↗»;
- **Sin activar**, con la acción «Activar ↗» cuando falta el permiso del portal;
- **Iniciando sesión…**, **Buscando correo**, **Confírmala** o **Perfil incompleto**, según el avance;
- **Próximamente**, para los portales que el servidor aún no habilita, con la tarjeta atenuada.

Los portales habilitados MUST tener un engranaje que abre la configuración de ese portal. El rediseño MUST conservar todas las acciones y reglas de estado que el popup ya tenía: una cuenta solo se muestra como lista cuando el servidor la confirmó explícitamente.

#### Scenario: Portal listo
- **WHEN** la sesión de Computrabajo está iniciada, la cuenta confirmada y el perfil completo
- **THEN** la tarjeta muestra «Listo ✓», el correo de la cuenta y el engranaje

#### Scenario: Portal sin sesión
- **WHEN** no hay sesión en Magneto
- **THEN** la tarjeta muestra «Sin sesión» y la acción para iniciar sesión

#### Scenario: Portal que aún no se habilita
- **WHEN** el servidor no ha habilitado elempleo
- **THEN** la tarjeta aparece atenuada con la etiqueta «Próximamente» y sin engranaje

#### Scenario: Cuenta sin confirmar
- **WHEN** hay sesión y correo pero el servidor no ha confirmado la cuenta
- **THEN** la tarjeta no muestra «Listo ✓» sino que pide confirmarla en el bot

### Requirement: Pie del popup
El pie del popup SHALL mostrar a la izquierda el resultado de la última postulación («Última: Enviada hace 2 h») cuando existe, y a la derecha el botón de Telegram que abre el panel con el bot y el grupo. El botón de Telegram MUST seguir visible sobre el contenido al desplazar la lista. Mientras se postula, el popup MUST mostrar qué vacante se está procesando.

#### Scenario: Última postulación
- **WHEN** la última postulación terminó como enviada hace dos horas
- **THEN** el pie muestra «Última: ✅ Enviada · hace 2 h»

#### Scenario: Sin postulaciones
- **WHEN** el usuario aún no tiene ninguna postulación
- **THEN** el pie no muestra la línea de última postulación y el botón de Telegram sigue disponible

#### Scenario: Acceso a Telegram
- **WHEN** el usuario toca el botón de Telegram
- **THEN** se abre el panel con el acceso al bot y, si el servidor lo informó, al grupo de vacantes
