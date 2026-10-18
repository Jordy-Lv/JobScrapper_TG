## MODIFIED Requirements

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
