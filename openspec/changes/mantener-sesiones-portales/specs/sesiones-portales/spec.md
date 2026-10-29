## Purpose

Define cómo la extensión conoce, conserva y vigila la sesión que el usuario tiene abierta en cada portal, para que no se pierda antes de tiempo y, si se pierde, el usuario lo sepa y sepa por qué.

## ADDED Requirements

### Requirement: Diagnóstico de la duración de la sesión
Con el permiso opcional `cookies` concedido, la extensión SHALL leer, por cada portal con sesión iniciada, los metadatos de sus cookies de autenticación: nombre, si es de sesión (sin vencimiento) o persistente, el vencimiento y si es `HttpOnly`. La extensión MUST NOT leer, guardar, registrar ni enviar al servidor el valor de ninguna cookie. Con esos metadatos SHALL clasificar la sesión del portal como «se pierde al cerrar el navegador» (alguna cookie de autenticación es de sesión), «dura hasta <fecha>» (todas son persistentes) o «sin datos» (no hay cookies de autenticación reconocibles), y MUST mostrar esa clasificación en la tarjeta del portal.

#### Scenario: Cookie de autenticación de sesión
- **WHEN** el permiso `cookies` está concedido y la cookie de autenticación de elempleo no tiene vencimiento
- **THEN** la clasificación de elempleo es «se pierde al cerrar el navegador»

#### Scenario: Todas las cookies de autenticación persistentes
- **WHEN** todas las cookies de autenticación de Magneto son persistentes y la más próxima vence en 5 días
- **THEN** la clasificación de Magneto es «dura hasta» esa fecha

#### Scenario: Sin permiso de cookies
- **WHEN** el usuario no ha concedido el permiso `cookies`
- **THEN** la extensión no lee ninguna cookie y la tarjeta no muestra la duración de la sesión

#### Scenario: El valor nunca sale
- **WHEN** la extensión lee las cookies de un portal
- **THEN** ningún valor de cookie queda guardado, en el registro ni en lo que se envía al servidor

### Requirement: Persistencia de la sesión opt-in por portal
El usuario SHALL poder activar «Mantener la sesión» por cada portal; por defecto está desactivado. Con la opción activa, la extensión MUST reescribir cada cookie de autenticación de sesión de ese portal con un vencimiento largo, conservando su valor y sus demás atributos (dominio, ruta, `Secure`, `HttpOnly`, `SameSite`), y MUST volver a hacerlo cada vez que el portal la reemite como cookie de sesión. La extensión MUST NOT tocar las cookies que no sean de autenticación ni las de portales con la opción desactivada. Al desactivar la opción, la extensión MUST dejar de reescribir cookies y no restituir nada por su cuenta.

#### Scenario: La sesión sobrevive al cierre del navegador
- **WHEN** «Mantener la sesión» está activa en elempleo, la cookie de autenticación era de sesión y el usuario cierra y reabre Chrome
- **THEN** la sesión de elempleo sigue iniciada

#### Scenario: El portal renueva la cookie
- **WHEN** el portal emite de nuevo su cookie de autenticación como cookie de sesión
- **THEN** la extensión la vuelve a persistir con el vencimiento largo

#### Scenario: Opción desactivada
- **WHEN** «Mantener la sesión» está desactivada en Magneto
- **THEN** la extensión no modifica ninguna cookie de Magneto

#### Scenario: Cookie que no es de autenticación
- **WHEN** un portal emite una cookie de sesión que no es de autenticación
- **THEN** la extensión no la modifica

### Requirement: Mantenimiento de una sesión que vence por inactividad
Con «Mantener la sesión» activa, la extensión SHALL visitar en segundo plano la página principal del portal con la periodicidad que fijen los datos del portal, sin abrir ventanas visibles ni interrumpir una postulación en curso, para que el portal renueve el vencimiento de la sesión. La extensión MUST registrar si el vencimiento de las cookies avanzó tras la visita, de modo que se sepa si el portal renueva la sesión con el uso.

#### Scenario: Visita periódica
- **WHEN** pasó el intervalo del portal desde la última revisión y «Mantener la sesión» está activa
- **THEN** la extensión revisa el portal en segundo plano y la sesión sigue iniciada

#### Scenario: Postulación en curso
- **WHEN** hay una postulación ejecutándose cuando toca la visita
- **THEN** la visita se aplaza hasta que termine

#### Scenario: El portal renueva el vencimiento
- **WHEN** tras la visita el vencimiento de la cookie de autenticación es posterior al de antes
- **THEN** la extensión registra que el portal renueva la sesión con el uso

### Requirement: Motivo de la pérdida de sesión
Cuando un portal pasa de tener sesión a no tenerla, la extensión SHALL informar un motivo en el latido, elegido entre: `cookie_de_sesion` (la cookie era de sesión y no se persistió), `vencida` (la cookie persistente llegó a su vencimiento), `borrada_al_cerrar` (se había persistido y desapareció al reiniciar el navegador, señal de que Chrome borra las cookies al salir) y `cerrada_por_el_portal` (las cookies siguen presentes pero el portal ya no reconoce la sesión). Sin el permiso `cookies`, el motivo MUST ser el que la extensión ya informa hoy.

#### Scenario: Chrome borra las cookies al salir
- **WHEN** la extensión había persistido la cookie, el navegador se reinició y la cookie ya no existe
- **THEN** el motivo informado es `borrada_al_cerrar`

#### Scenario: El portal cierra la sesión
- **WHEN** las cookies de autenticación siguen presentes y vigentes pero el portal muestra la página de ingreso
- **THEN** el motivo informado es `cerrada_por_el_portal`

#### Scenario: Cookie vencida
- **WHEN** la cookie persistente de autenticación llegó a su fecha de vencimiento
- **THEN** el motivo informado es `vencida`

### Requirement: Permiso de cookies opcional
El permiso `cookies` MUST declararse como permiso opcional y pedirse solo cuando el usuario activa el diagnóstico o «Mantener la sesión». La extensión MUST seguir funcionando sin él, y si el usuario lo revoca, MUST dejar de leer y modificar cookies sin perder el resto de sus funciones.

#### Scenario: Instalación o actualización
- **WHEN** un usuario instala o actualiza la extensión
- **THEN** no se le pide el permiso `cookies` y todas sus funciones actuales siguen disponibles

#### Scenario: Permiso revocado
- **WHEN** el usuario revoca el permiso `cookies` con «Mantener la sesión» activa
- **THEN** la extensión deja de modificar cookies y la tarjeta indica que falta el permiso
