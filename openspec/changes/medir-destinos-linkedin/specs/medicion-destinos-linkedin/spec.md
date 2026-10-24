## Purpose

Medir, sin sesión de LinkedIn y sin enviar nada, qué tipo de solicitud tienen las vacantes de
LinkedIn del radar y a qué página o ATS llevan, para decidir qué adaptadores de postulación
automática construir primero.

## ADDED Requirements

### Requirement: Muestra de vacantes de LinkedIn
El comando de medición SHALL tomar las vacantes de LinkedIn más recientes de la base del radar, hasta
el tamaño de muestra configurado, y MUST abrir la base en modo de solo lectura. Una vacante que ya
tenga resultado en un archivo de medición anterior MUST NOT pedirse de nuevo.

#### Scenario: Muestra limitada
- **WHEN** la base tiene 474 vacantes de LinkedIn y la muestra configurada es 100
- **THEN** el comando mide las 100 más recientes y la base queda sin cambios

#### Scenario: Reanudar una medición cortada
- **WHEN** un archivo de medición anterior ya tiene el resultado de 40 vacantes de la muestra
- **THEN** el comando pide solo las 60 que faltan y conserva los 40 resultados anteriores

### Requirement: Tipo de solicitud y destino
Para cada vacante, el comando SHALL registrar el tipo de solicitud (`sencilla`, `externa`, `cerrada`
o `desconocido`) leyendo solo las páginas públicas de invitado de LinkedIn, sin cookies ni sesión.
Para las solicitudes externas SHALL registrar la URL de destino real, sin los parámetros de
seguimiento de LinkedIn. Cuando la página pública no indique el tipo, el resultado MUST ser
`desconocido`, nunca una suposición.

#### Scenario: Vacante con solicitud externa
- **WHEN** la página pública de la vacante trae el enlace de solicitud hacia `empresa.wd3.myworkdayjobs.com`
- **THEN** el resultado es `externa` con esa URL de destino

#### Scenario: Vacante con Solicitud sencilla
- **WHEN** la página pública indica Solicitud sencilla (Easy Apply)
- **THEN** el resultado es `sencilla` y no tiene URL de destino

#### Scenario: Página sin indicio
- **WHEN** la página pública no muestra ni el botón ni el enlace de solicitud
- **THEN** el resultado es `desconocido` y se guarda el motivo

### Requirement: Familia del destino y cuenta propia
El comando SHALL clasificar cada URL de destino en una familia según los patrones de dominio
configurados (por ejemplo Workday, Greenhouse, Lever, SuccessFactors, Gupy, Teamtailor,
SmartRecruiters, iCIMS, Taleo, BambooHR, Computrabajo, Magneto, elempleo), o como `propio` si no
coincide ninguno. SHALL abrir la página de destino una sola vez con una petición de lectura y anotar
si pide iniciar sesión o crear una cuenta antes de postular. MUST NOT enviar formularios, crear
cuentas ni escribir credenciales en ningún sitio.

#### Scenario: Destino en un portal ya conectado
- **WHEN** el destino es una vacante de `co.computrabajo.com`
- **THEN** la familia es `computrabajo`

#### Scenario: ATS que exige cuenta
- **WHEN** la página de destino muestra un campo de contraseña o un aviso de crear cuenta para postular
- **THEN** el resultado marca `pide_cuenta: true` y no se hace ninguna otra petición a ese destino

### Requirement: Ritmo y bloqueos
El comando MUST respetar el cooldown de LinkedIn que registró el radar, esperar entre peticiones la
pausa configurada y no hacer más de una petición por vacante a LinkedIn. Ante un 429, un 999 o una
página de verificación, MUST detenerse, guardar lo medido hasta ese momento y decir por qué paró, sin
reintentar ni evadir la protección.

#### Scenario: LinkedIn en cooldown
- **WHEN** la base registra un cooldown de LinkedIn vigente
- **THEN** el comando no hace peticiones a LinkedIn y avisa hasta cuándo dura el cooldown

#### Scenario: Bloqueo a mitad de la medición
- **WHEN** LinkedIn responde 999 en la vacante 37
- **THEN** el comando se detiene, guarda los 36 resultados anteriores e indica que paró por bloqueo

### Requirement: Resultados
El comando SHALL guardar un archivo JSON con un registro por vacante (clave, tipo, URL de destino,
familia, `pide_cuenta` y motivo) y SHALL imprimir un resumen en Markdown con el número y el
porcentaje de vacantes por tipo de solicitud y por familia de destino, y cuántas piden cuenta. Los
resultados MUST NOT incluir datos personales del dueño ni de los usuarios.

#### Scenario: Resumen de la medición
- **WHEN** termina la medición de 100 vacantes
- **THEN** el resumen muestra cuántas son `sencilla`, `externa`, `cerrada` y `desconocido`, la tabla de familias ordenada de mayor a menor y cuántas exigen cuenta
