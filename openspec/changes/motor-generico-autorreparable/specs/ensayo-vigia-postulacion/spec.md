## Purpose

Permite probar el motor sobre vacantes reales sin enviar nada, detectar cambios de los portales antes de que les
fallen a los usuarios y medir con datos qué tan bien postula cada plataforma y familia de ATS.

## ADDED Requirements

### Requirement: Modo ensayo
Cada plataforma y cada usuario SHALL tener un modo ensayo. En ensayo, la postulación sigue todo el flujo
(leer, resolver, llenar, avanzar y reparar) y se detiene justo antes de registrar el envío. El modo MUST NOT
pulsar un botón `enviar` ni registrar el envío. La postulación SHALL terminar en el estado nuevo `ensayada`, y
la card MUST mostrar lo que se habría enviado (preguntas y respuestas), dónde se habría pulsado enviar y, si
se trabó, en qué pantalla y por qué. Una postulación `ensayada` MUST poder enviarse de verdad después con un
toque, empezando de nuevo desde la vacante.

#### Scenario: Ensayo exitoso
- **WHEN** el ensayo de una vacante llega al botón «Submit application» con todos los campos llenos y comprobados
- **THEN** la postulación queda `ensayada`, la card muestra las respuestas y el botón para enviarla de verdad, y en el portal no se envió nada

#### Scenario: Portal donde postular ya envía
- **WHEN** el ensayo corre en Computrabajo, donde el botón de postular de la vacante ya envía la postulación
- **THEN** el ensayo comprueba la sesión, que la vacante sigue abierta y que el botón existe, se detiene sin pulsarlo y la card aclara que en ese portal el ensayo llega hasta el botón de postular

#### Scenario: Ensayo trabado
- **WHEN** el ensayo no logra avanzar en la tercera pantalla
- **THEN** la card dice «se trabaría en la pantalla 3» con el motivo, y el dueño recibe la evidencia

### Requirement: Ensayo por plataforma
El dueño SHALL poder poner una plataforma en ensayo para todos los usuarios desde la configuración o por
comando. Una plataforma nueva o un motor nuevo MUST pasar por ensayo antes de enviar de verdad. El piloto de una
plataforma SHALL empezar con al menos 10 ensayos sin fallos sin explicar antes de las 3 postulaciones reales.

#### Scenario: Plataforma en ensayo
- **WHEN** la plataforma está en ensayo y un invitado toca ⚡
- **THEN** la postulación termina `ensayada` y la card explica que esa plataforma está en prueba y ofrece enviarla de verdad o usar el paquete de respaldo

### Requirement: Vigía diario de portales
Una vez al día, fuera de las horas de uso, el vigía SHALL ensayar en el navegador del dueño una vacante abierta
de cada plataforma automática, hasta antes de enviar. Si el ensayo falla, MUST intentar la reparación y, con
reparación o sin ella, avisar al dueño con la evidencia. Un fallo del vigía que no se repare SHALL poner esa
plataforma en ensayo para los usuarios hasta que el dueño la revise. El vigía MUST NOT enviar postulaciones
y MUST respetar las pausas y topes de cada portal.

#### Scenario: Portal que cambió
- **WHEN** el vigía no encuentra el botón de postular de una plataforma y la reparación tampoco
- **THEN** el dueño recibe el aviso con la evidencia y la plataforma pasa a ensayo hasta que la revise

#### Scenario: Reparado por el vigía
- **WHEN** el vigía falla, la reparación encuentra el botón nuevo y el ensayo termina bien
- **THEN** queda un parche candidato y el dueño recibe el aviso de que la plataforma cambió y se reparó

### Requirement: Banco de pruebas con páginas reales
El proyecto SHALL mantener copias recortadas, sin datos personales, de formularios reales de cada plataforma y de
cada familia de ATS reconocida, y pruebas automáticas que corren el motor sobre ellas contra un envío falso.
Una versión nueva de la extensión MUST NOT publicarse si baja la cantidad de copias que el motor completa.

#### Scenario: Regresión
- **WHEN** un cambio en el motor hace que la copia del formulario de Greenhouse deje de llenarse
- **THEN** la prueba falla y la versión no se publica

### Requirement: Métricas por plataforma y familia
El servidor SHALL contar, por plataforma y por familia de ATS, las postulaciones enviadas, ensayadas,
`formulario_desconocido`, `incierta`, reparadas, que usaron el árbitro y que fueron al respaldo, con su motivo.
La sección del asistente del resumen diario del dueño MUST incluir esas cifras del día y las recetas y parches nuevos, y el panel de administración SHALL mostrarlas cuando exista.

#### Scenario: Resumen del día
- **WHEN** en el día hubo 20 postulaciones en Greenhouse, 18 enviadas y 2 reparadas
- **THEN** el resumen del dueño muestra Greenhouse con 18 enviadas, 2 reparaciones y ningún respaldo
