## MODIFIED Requirements

### Requirement: Tarjetas de portal
El popup SHALL mostrar una tarjeta por portal soportado, con el logo, el nombre, una etiqueta de estado y un borde de color propio de cada portal. La etiqueta MUST ser una de:
- **Listo ✓**: sesión iniciada, cuenta confirmada y perfil completo, mostrando el correo de la cuenta;
- **Sin sesión**, con la acción «Iniciar sesión ↗»;
- **Sin activar**, con la acción «Activar ↗» cuando falta el permiso del portal;
- **Iniciando sesión…**, **Buscando correo**, **Confírmala** o **Perfil incompleto**, según el avance;
- **Próximamente**, para los portales que el servidor aún no habilita, con la tarjeta atenuada.

Los portales habilitados MUST tener un engranaje que abre la configuración de ese portal. El rediseño MUST conservar todas las acciones y reglas de estado que el popup ya tenía: una cuenta solo se muestra como lista cuando el servidor la confirmó explícitamente.

Un portal con sesión iniciada y el permiso `cookies` concedido MUST mostrar además, en su configuración, cuánto dura la sesión («Dura hasta …» o «Se pierde al cerrar el navegador») y el interruptor «Mantener la sesión», desactivado por defecto. Activar el interruptor sin el permiso `cookies` MUST pedirlo en ese momento; si el usuario lo rechaza, el interruptor queda desactivado.

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

#### Scenario: Activar «Mantener la sesión»
- **WHEN** el usuario activa «Mantener la sesión» en elempleo sin haber concedido el permiso `cookies`
- **THEN** el navegador le pide el permiso y, si lo concede, el interruptor queda activo

#### Scenario: Permiso rechazado
- **WHEN** el usuario rechaza el permiso `cookies` al activar «Mantener la sesión»
- **THEN** el interruptor queda desactivado y no se modifica ninguna cookie

#### Scenario: Duración de la sesión
- **WHEN** el permiso `cookies` está concedido y la sesión de Magneto vence en 5 días
- **THEN** la configuración de Magneto muestra «Dura hasta» esa fecha
