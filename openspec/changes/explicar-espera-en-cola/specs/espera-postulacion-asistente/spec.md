## Purpose

Determinar, para cada postulación en cola de cualquier plataforma, la causa concreta por la que el servidor todavía no la entrega a la extensión, para que el usuario sepa qué hacer.

## ADDED Requirements

### Requirement: Estado de cada portal guardado en el latido
El servidor SHALL guardar, con cada latido de un navegador, el último estado reportado de cada plataforma habilitada: sesión (`sin_sesion`, `incompleto` o `listo`) con su motivo cuando no hay sesión, estado de la cuenta (`ok`, `por_confirmar`, `distinta`, `sin_correo`) y la hora del reporte. Una plataforma con selectores cargados que no aparece en el latido MUST quedar registrada como sin permiso en ese navegador. El servidor MUST NOT guardar el correo de la cuenta en ese estado, solo su verificación.

#### Scenario: Portal sin sesión
- **WHEN** el latido reporta `magneto` con estado `sin_sesion` y motivo `enlace_ingresar`
- **THEN** el estado guardado del navegador para `magneto` es sin sesión, con ese motivo, y el estado de cuenta previo se conserva

#### Scenario: Portal ausente por permiso
- **WHEN** `elempleo` tiene selectores cargados y el latido no incluye `elempleo`
- **THEN** el estado guardado del navegador para `elempleo` es sin permiso de dominio

#### Scenario: Latido de una versión anterior de la extensión
- **WHEN** llega un latido sin el campo `pausado`
- **THEN** el servidor lo acepta y considera que la extensión no está en pausa

### Requirement: Causa de la espera de una postulación en cola
Para cada postulación en cola o esperando navegador, el servidor SHALL calcular una sola causa de espera, la primera que aplique en este orden: (1) sin navegador vinculado; (2) sin latido reciente de ningún navegador del usuario; (3) extensión por debajo de la versión mínima; (4) extensión en pausa por el usuario; (5) plataforma apagada o sin selectores; (6) sin permiso de dominio del portal; (7) sin sesión en el portal; (8) cuenta del portal por confirmar, distinta o con correo ilegible; (9) perfil del portal incompleto o completándose; (10) otra postulación del usuario en curso; (11) tope diario alcanzado; (12) pausa entre postulaciones. Si ninguna aplica, la postulación no tiene causa de espera. Con varios navegadores vigentes, si alguno no tiene causa no hay causa de espera; si todos tienen una, se muestra la del navegador con el latido más reciente. El cálculo MUST valer igual para Computrabajo, Magneto, elempleo y cualquier plataforma configurada, sin código propio por portal.

#### Scenario: Sin sesión en Magneto
- **WHEN** la postulación es de Magneto, el navegador tiene latido reciente, versión vigente, permiso y la plataforma encendida, y el último latido reportó Magneto sin sesión
- **THEN** la causa es «sin sesión» en Magneto

#### Scenario: Prioridad entre causas
- **WHEN** la extensión está desactualizada y además Magneto no tiene sesión
- **THEN** la causa es «extensión desactualizada», porque con ella no se asigna ningún trabajo

#### Scenario: Cuenta por confirmar
- **WHEN** el portal tiene sesión pero la cuenta está por confirmar
- **THEN** la causa es «cuenta por confirmar» en ese portal

#### Scenario: Tope diario
- **WHEN** todo el portal está listo y el usuario ya alcanzó su tope de postulaciones del día
- **THEN** la causa es «tope diario» e incluye cuándo vuelve a haber cupo

#### Scenario: Sin causa
- **WHEN** el portal está listo, la cuenta confirmada y la cola no tiene restricciones activas
- **THEN** la postulación no tiene causa de espera

### Requirement: Plataforma apagada no se asigna
Mientras una plataforma esté apagada con `/plataformas`, el servidor SHALL dejar de entregar a la extensión trabajos nuevos de esa plataforma; las postulaciones ya en cola MUST quedar en cola y retomarse solas cuando la plataforma se encienda. Las postulaciones que ya están en curso MUST NOT interrumpirse.

#### Scenario: Apagar con una postulación en cola
- **WHEN** el administrador apaga Magneto y un usuario tiene una postulación de Magneto en cola
- **THEN** el latido no entrega esa postulación y su causa de espera es «plataforma apagada»

#### Scenario: Encender de nuevo
- **WHEN** el administrador vuelve a encender Magneto
- **THEN** el siguiente latido con el portal listo entrega la postulación, sin que el usuario haga nada

### Requirement: Recalcular la espera cuando cambia algo
El servidor SHALL recalcular la causa de espera de las postulaciones en cola de un usuario después de cada latido de sus navegadores, en cada vigilancia periódica de la cola y cuando se enciende o apaga una plataforma. Solo un cambio de causa MUST producir un aviso a la card.

#### Scenario: Latido sin cambios
- **WHEN** llegan varios latidos seguidos con la misma causa
- **THEN** no se produce ningún aviso nuevo para la card

#### Scenario: El usuario inicia sesión
- **WHEN** un latido reporta Magneto listo con la cuenta confirmada después de haberlo reportado sin sesión
- **THEN** la causa de espera de la postulación de Magneto desaparece y se avisa a la card
