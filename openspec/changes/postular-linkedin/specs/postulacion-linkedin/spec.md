## Purpose

Permite postular automáticamente a las vacantes de LinkedIn del canal, por la Solicitud sencilla o por la página
externa de la empresa, con el riesgo aceptado por cada usuario y sin crear cuentas ni escribir credenciales.

## ADDED Requirements

### Requirement: Aceptación del riesgo de LinkedIn
Antes de su primera postulación automática en LinkedIn, cada usuario MUST aceptar de forma expresa, con un botón
de la card, el riesgo de que LinkedIn restrinja su cuenta porque sus condiciones de uso prohíben automatizar
acciones. Sin esa aceptación, sus vacantes de LinkedIn SHALL ir al paquete de respaldo con el motivo
`linkedin_sin_aceptar`. La aceptación se guarda con su fecha y la versión del texto. Si el texto cambia de
versión, MUST pedirse de nuevo.

#### Scenario: Primer ⚡ en LinkedIn
- **WHEN** un usuario que nunca aceptó el riesgo toca ⚡ en una vacante de LinkedIn
- **THEN** la card explica el riesgo con «Acepto y postular» y «Solo paquete», y no se abre ninguna pestaña hasta que elija

#### Scenario: No acepta
- **WHEN** el usuario elige «Solo paquete»
- **THEN** la vacante va al respaldo con el motivo `linkedin_sin_aceptar` y la próxima vez se le vuelve a ofrecer

### Requirement: Interruptores de LinkedIn por usuario
Cada usuario SHALL tener dos interruptores, «Solicitud sencilla» y «Páginas externas», encendidos al aceptar el
riesgo y editables por Telegram (`/linkedin`) y en el popup. Con un interruptor apagado, las vacantes de ese
tipo MUST ir al respaldo con el motivo `linkedin_apagado`.

#### Scenario: Externas apagadas
- **WHEN** el usuario apagó «Páginas externas» y toca ⚡ en una vacante externa
- **THEN** la vacante va al respaldo con el motivo `linkedin_apagado` sin abrir la página externa

### Requirement: Resolución del destino con la sesión del usuario
La extensión SHALL abrir la vacante en LinkedIn con la sesión del usuario y clasificarla: `sencilla` (botón
«Solicitud sencilla»), `externa` (enlace `a[href*="/safety/go"]` con el destino en el parámetro `url`),
`cerrada` («Ya no se aceptan solicitudes») o `pausada` («No se aceptan solicitudes en estos momentos»). En
una externa, la extensión MUST NOT pulsar «Solicitar»: el servidor limpia el destino (quita `trk`, `refId`,
`trackingId` y `utm_*`) y la extensión abre esa URL. Sin sesión de LinkedIn, la postulación SHALL quedar
`esperando_sesion`, como en los demás portales. El destino resuelto de una vacante SHALL guardarse y
compartirse entre usuarios, para no volver a abrir LinkedIn por esa vacante.

#### Scenario: Vacante externa
- **WHEN** la vacante muestra «Solicitar en el sitio web de la empresa» con un enlace `/safety/go?url=…`
- **THEN** la extensión no pulsa el botón, el servidor recibe el destino limpio y la pestaña lo abre

#### Scenario: Vacante pausada
- **WHEN** la vacante dice «No se aceptan solicitudes en estos momentos»
- **THEN** la postulación queda `vacante_cerrada` sin abrir ningún destino

#### Scenario: Destino ya conocido
- **WHEN** otro usuario ya resolvió el destino de esa vacante
- **THEN** la extensión abre directamente el destino guardado sin pasar por LinkedIn

### Requirement: Clasificador de destino
El servidor SHALL clasificar cada destino antes de abrirlo: `mensajeria` (`wa.me`, `api.whatsapp.com`,
`t.me`, `mailto:`) → respaldo con el motivo `destino_mensajeria` y el enlace en el paquete; familia con cuenta
conocida (configurable: Workday, SuccessFactors, Taleo, iCIMS, Gupy…) o dominio barrera aprendido → respaldo
con el motivo `ats_con_cuenta`; cualquier otro → motor genérico, con el esquema y los datos de su familia si
existen. Un acortador SHALL clasificarse después de la redirección, sobre la URL final.

#### Scenario: Acortador hacia WhatsApp
- **WHEN** el destino es `ai-job.link/…` y la redirección lleva a `wa.me/…`
- **THEN** la vacante va al respaldo con el motivo `destino_mensajeria` y el paquete trae el enlace, sin enviar ningún mensaje

#### Scenario: Workday
- **WHEN** el destino es `*.myworkdayjobs.com`
- **THEN** la vacante va al respaldo con el motivo `ats_con_cuenta` sin abrir la página

#### Scenario: Greenhouse por enlace corto
- **WHEN** el destino es `grnh.se/…` y redirige a `job-boards.greenhouse.io/{tablero}/jobs/{id}`
- **THEN** se clasifica como Greenhouse y se postula con su esquema anticipado

### Requirement: Plataforma externa y permiso amplio
La extensión SHALL operar en páginas externas solo si el usuario concedió desde el popup el permiso opcional
para todos los sitios `https`. Sin ese permiso, las vacantes externas MUST ir al respaldo con el motivo
`sin_permiso_externo`, y la card SHALL explicar cómo concederlo. En las páginas externas, el motor MUST NOT
operar en páginas de inicio de sesión, registro, recuperar contraseña, OAuth (`accounts.google.com`,
`login.microsoftonline.com`, `linkedin.com/oauth`…), pagos ni banca. Si la navegación salta a un dominio que no
es el del destino, uno de su misma empresa ni una familia de ATS conocida, el flujo MUST detenerse sin enviar
con el motivo `salto_de_dominio`.

#### Scenario: Sin permiso amplio
- **WHEN** el usuario no concedió el permiso de todos los sitios y toca ⚡ en una vacante externa
- **THEN** la vacante va al respaldo con el motivo `sin_permiso_externo` y la card le dice cómo activarlo en el popup

#### Scenario: Redirección a un inicio de sesión de Google
- **WHEN** el formulario externo lleva a `accounts.google.com`
- **THEN** el motor no actúa en esa página y la postulación va al respaldo con el motivo `oauth`

### Requirement: Solicitud sencilla
En una vacante `sencilla`, la extensión SHALL pulsar «Solicitud sencilla» y correr el motor genérico dentro del
modal de LinkedIn hasta «Enviar solicitud», con la confirmación «Se envió tu solicitud» (u otra señal
explícita) como éxito. Debe desmarcar «Seguir a la empresa». El CV adaptado SHALL subirse en el modal solo si el
usuario autorizó actualizar el CV del portal; si no, se elige el CV más reciente que LinkedIn ya tenga.
LinkedIn MUST tener un archivo de selectores revisado con la sesión real antes de habilitar este tipo.

#### Scenario: Solicitud sencilla con preguntas
- **WHEN** el modal tiene tres pasos con preguntas de años de experiencia y de nivel de inglés
- **THEN** el motor las resuelve, pulsa «Siguiente» y «Revisar», registra el envío, pulsa «Enviar solicitud» y la postulación queda `enviada` con la confirmación

#### Scenario: Seguir a la empresa
- **WHEN** la revisión final trae marcada la casilla «Seguir a la empresa»
- **THEN** la casilla se desmarca antes de enviar

### Requirement: Ritmo y tope de LinkedIn
Las postulaciones de LinkedIn de un usuario SHALL ejecutarse de a una, con una pausa mínima configurable entre
dos aperturas de LinkedIn y un tope diario configurable (por defecto 15). Al alcanzar el tope, las siguientes
MUST esperar al día siguiente en la cola, y la card lo dice. Un aviso de LinkedIn de actividad inusual o de
verificación MUST detener las postulaciones de LinkedIn de ese usuario por 24 horas y avisar al usuario y al
dueño.

#### Scenario: Tope alcanzado
- **WHEN** un usuario ya tuvo 15 postulaciones de LinkedIn en el día y toca ⚡ en otra
- **THEN** la postulación queda en cola para el día siguiente y la card lo explica

#### Scenario: Aviso de actividad inusual
- **WHEN** LinkedIn muestra una página de verificación de seguridad durante la resolución del destino
- **THEN** no se resuelve nada, LinkedIn queda en pausa 24 horas para ese usuario y el usuario y el dueño reciben el aviso

### Requirement: Piloto de LinkedIn
LinkedIn MUST pasar por: (1) dos semanas de ensayo con la cuenta del dueño, con la cobertura por familia en el
resumen; (2) al menos 3 postulaciones reales del dueño por la Solicitud sencilla y 3 por páginas externas que
terminen `enviada` y se vean en el portal o en el correo de confirmación; (3) al menos 3 días con invitados sin
errores sin resolver. Hasta completar cada etapa, la plataforma SHALL quedar en el nivel anterior: respaldo,
ensayo o solo el dueño.

#### Scenario: Ensayo antes de enviar
- **WHEN** LinkedIn está en la etapa de ensayo y el dueño toca ⚡
- **THEN** la postulación termina `ensayada` con lo que se habría enviado, sin enviar nada en LinkedIn ni en la página externa
