## ADDED Requirements

### Requirement: Correo de la cuenta de LinkedIn
La extensión SHALL leer el correo de la cuenta de LinkedIn de la ventana «Información de contacto» del propio perfil del usuario, sin depender de que LinkedIn pinte esa ventana ni de que salte de `/in/me/` al perfil en la pestaña de revisión, que está en segundo plano.

Para obtenerlo, la extensión:
- MUST pedir las páginas solo con `GET`, al mismo dominio del portal y con la sesión que ya tiene el navegador;
- MUST tomar el usuario del perfil de la URL de la pestaña o, si aún no cambió, de la página `/in/me/` del propio usuario;
- MUST aceptar el correo solo si la página de contacto del propio perfil trae exactamente un correo válido en un enlace `mailto:`; con ninguno o con varios, no informa correo;
- MUST NOT leer texto libre de la página, ni páginas de configuración de la cuenta;
- MUST seguir buscando el correo en la ventana pintada, como antes, si la lectura anterior no lo encuentra.

Cuando no encuentra el correo, la extensión SHALL informar en el latido el motivo: `sin_perfil` (no se supo el usuario), `sin_correo` (la página de contacto no trae un correo), `varios_correos` o `sin_sesion` (la petición terminó en la página de ingreso).

#### Scenario: LinkedIn no pinta la ventana ni salta al perfil
- **WHEN** la extensión revisa LinkedIn con sesión, `/in/me/` se queda en esa URL sin pintar nada y la página de contacto trae el correo solo en los datos de la página
- **THEN** la extensión informa el correo de la cuenta y la página de contacto donde lo encontró

#### Scenario: La página de contacto no trae correo
- **WHEN** la página de contacto del perfil no trae ningún `mailto:`
- **THEN** la extensión informa LinkedIn con sesión, sin correo y con el motivo `sin_correo`

#### Scenario: Correo ya visible en la ventana pintada
- **WHEN** LinkedIn sí salta al perfil y pinta la ventana de contacto
- **THEN** la extensión informa el mismo correo

### Requirement: Reintento pronto de un portal sin correo
Un portal con sesión iniciada cuyo correo no se encontró SHALL volver a revisarse en el siguiente latido pasados 10 minutos, en vez de esperar el plazo normal de revisión de 6 horas. Un portal con correo o sin sesión MUST conservar el plazo actual.

#### Scenario: LinkedIn quedó sin correo
- **WHEN** la última revisión de LinkedIn terminó con sesión y sin correo hace más de 10 minutos
- **THEN** el siguiente latido vuelve a revisar LinkedIn
