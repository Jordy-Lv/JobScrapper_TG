## ADDED Requirements

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
