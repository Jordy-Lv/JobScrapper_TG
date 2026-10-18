## ADDED Requirements

### Requirement: Motivo de la espera en la card en cola
Mientras una postulación espera en cola o espera navegador, su card SHALL mostrar la causa de espera calculada por el servidor, con un mensaje que diga qué falta y cómo resolverlo en el portal de la vacante, y los botones de esa solución cuando existan. Sin causa de espera, la card MUST mostrar «En cola. Te aviso el resultado.». El mensaje MUST nombrar el portal de la vacante y MUST NOT mostrar motivos técnicos internos (por ejemplo `enlace_ingresar`) ni el correo completo de una cuenta que no es la del usuario.

#### Scenario: Sin sesión en el portal
- **WHEN** la causa es «sin sesión» en Magneto
- **THEN** la card dice que hay que iniciar sesión en Magneto en el navegador vinculado y que la postulación sale sola después, con el botón «Iniciar sesión» que abre la página de ingreso de Magneto y el botón «Crear cuenta»

#### Scenario: Sin navegador vinculado
- **WHEN** la causa es «sin navegador vinculado»
- **THEN** la card dice que falta vincular el navegador y ofrece «Vincular navegador»

#### Scenario: Sin latido reciente
- **WHEN** la causa es «sin latido reciente»
- **THEN** la card dice que el navegador no responde desde la hora del último contacto y pide abrirlo con la extensión activa

#### Scenario: Extensión desactualizada
- **WHEN** la causa es «extensión desactualizada»
- **THEN** la card muestra la versión instalada y la mínima, pide actualizar la extensión y ofrece «Actualizar extensión» solo si hay enlace de tienda configurado

#### Scenario: Extensión en pausa
- **WHEN** la causa es «extensión en pausa»
- **THEN** la card dice que las postulaciones están en pausa en la extensión y que se reanudan al quitar la pausa desde su ventana

#### Scenario: Plataforma apagada
- **WHEN** la causa es «plataforma apagada»
- **THEN** la card dice que la postulación automática en ese portal está pausada por ahora, que la postulación sigue en cola y que sale sola cuando se reactive, sin botones de acción para el usuario

#### Scenario: Permiso de dominio
- **WHEN** la causa es «sin permiso» en elempleo
- **THEN** la card pide abrir la ventana de la extensión y activar el permiso de elempleo.com con su botón

#### Scenario: Cuenta por confirmar o distinta
- **WHEN** la causa es «cuenta por confirmar» o «cuenta distinta»
- **THEN** la card explica la situación de la cuenta y ofrece los mismos botones de la conexión de cuenta: «Confirmar» y «Cancelar», o «Es mi cuenta nueva» y «No es mía»

#### Scenario: Correo ilegible
- **WHEN** la causa es «correo ilegible»
- **THEN** la card dice que no se pudo leer el correo de la cuenta del portal, que se vuelve a intentar en la próxima revisión y que no se postula hasta comprobar que la cuenta es suya

#### Scenario: Esperas normales de la cola
- **WHEN** la causa es otra postulación en curso, el tope diario o la pausa entre postulaciones
- **THEN** la card lo dice y, en el tope y la pausa, cuándo sale aproximadamente, sin botones

### Requirement: La card en cola se actualiza sola
La card de una postulación en cola SHALL editarse en su mismo mensaje cada vez que cambie su causa de espera, sin enviar mensajes nuevos, y MUST NOT editarse cuando la causa no cambia. Cuando la causa se resuelve, la card MUST volver a «En cola. Te aviso el resultado.» y seguir con las fases del flujo normal.

#### Scenario: El usuario inicia sesión
- **WHEN** la card muestra «sin sesión» en Magneto y el usuario inicia sesión en su navegador
- **THEN** tras el siguiente latido la card vuelve a «En cola. Te aviso el resultado.» y luego pasa al progreso cuando la extensión toma la postulación

#### Scenario: Cambia la causa
- **WHEN** el usuario activa el permiso de elempleo.com pero todavía no tiene sesión en elempleo
- **THEN** la card cambia de «sin permiso» a «sin sesión» en elempleo, en el mismo mensaje

#### Scenario: Latidos repetidos
- **WHEN** llegan latidos cada 30 segundos con la misma causa
- **THEN** el mensaje de la card no se edita
