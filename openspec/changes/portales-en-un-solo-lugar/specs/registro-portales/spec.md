## Purpose
Mantener en un solo lugar los datos de cada portal de empleo (nombre, dominios, enlaces y si el asistente postula en él), para que el radar, el asistente y la extensión los usen igual y que sumar un portal no exija copiar datos a mano.

## ADDED Requirements

### Requirement: Registro único de portales
El proyecto SHALL tener una sola definición de datos por portal: identificador, nombre, nombre corto, dominios, página de inicio, página de ingreso, descripción para el popup, selector del texto de la oferta y si el asistente postula en él. El radar, el asistente y la extensión SHALL tomar esos datos de esa definición y SHALL NOT mantener copias propias escritas a mano.

#### Scenario: Nombre de un portal en el canal y en el bot
- **WHEN** el radar publica una vacante de una fuente o el bot nombra la plataforma de una postulación
- **THEN** el nombre sale del registro de portales

#### Scenario: Plataforma a partir del enlace de la vacante
- **WHEN** el asistente decide la plataforma de una vacante por el dominio de su enlace
- **THEN** usa los dominios del registro, y solo devuelve una plataforma si el registro la marca como conectada al asistente

#### Scenario: Identificador desconocido
- **WHEN** se pide el nombre de una fuente o plataforma que no está en el registro
- **THEN** se devuelve el identificador tal cual, como hoy

### Requirement: Datos de la extensión generados desde el registro
Los datos de portales que usa la extensión SHALL generarse desde el registro en un archivo propio de la extensión, guardado en el repositorio. La extensión SHALL seguir funcionando sin pedir esos datos al servidor ni ejecutar código remoto.

#### Scenario: Archivo generado al día
- **WHEN** se ejecuta la suite de pruebas
- **THEN** una prueba regenera los datos en memoria y falla si difieren del archivo guardado en `extension/`

#### Scenario: Cambio en el registro
- **WHEN** se cambia un dato de un portal en el registro y se ejecuta el comando de generación
- **THEN** el archivo de la extensión queda actualizado y la prueba de sincronía pasa

### Requirement: Coherencia del registro con el resto del proyecto
Las pruebas SHALL fallar si el registro deja de cubrir lo que el proyecto usa:
- cada fuente que el radar sabe consultar y cada fuente de `config.yaml` tiene registro;
- cada plataforma de `asistente.plataformas` en `config.yaml` es un portal conectado al asistente;
- cada portal con dominios tiene permiso en el `manifest.json`, fijo u opcional;
- la política de privacidad nombra a cada portal conectado al asistente.

#### Scenario: Fuente nueva sin registro
- **WHEN** se agrega una fuente al radar o a `config.yaml` sin su entrada en el registro
- **THEN** una prueba de coherencia falla y nombra la fuente

#### Scenario: Plataforma activable sin estar conectada
- **WHEN** `config.yaml` lista en `asistente.plataformas` un portal que el registro no marca como conectado
- **THEN** una prueba de coherencia falla

#### Scenario: Dominio sin permiso en la extensión
- **WHEN** un portal del registro tiene un dominio que no aparece en `host_permissions` ni en `optional_host_permissions`
- **THEN** una prueba de coherencia falla

### Requirement: Registro inválido detectado al cargar
El registro SHALL validarse al cargarse. Un registro mal formado SHALL producir un error que nombre el portal y el campo con problema, y SHALL NOT dejar pasar datos incompletos en silencio.

#### Scenario: Campo obligatorio ausente
- **WHEN** un portal del registro no tiene nombre
- **THEN** la carga falla con un mensaje que nombra ese portal y el campo `nombre`

#### Scenario: Identificador repetido
- **WHEN** dos entradas del registro usan el mismo identificador
- **THEN** la carga falla con un mensaje que nombra el identificador repetido

### Requirement: Comportamiento idéntico
Tras pasar a leer del registro, el sistema SHALL comportarse igual que antes del cambio:
- los mismos nombres de fuente en el canal, el resumen y el reportero;
- los mismos textos y enlaces del bot;
- la misma plataforma para cada enlace de vacante;
- el mismo texto de oferta extraído;
- los mismos nombres, enlaces, orden de tarjetas y descripciones en la extensión.

No SHALL cambiar `config.yaml`, el esquema de las bases SQLite, el contrato de la API ni la versión de la extensión.

#### Scenario: Equivalencia con los mapas anteriores
- **WHEN** se compara lo que devuelve el registro con los mapas escritos a mano que existían antes del cambio
- **THEN** cada nombre, dominio, enlace y descripción coincide carácter por carácter

#### Scenario: Suite sin cambiar aserciones de comportamiento
- **WHEN** se ejecuta la suite completa tras el cambio
- **THEN** pasa sin modificar aserciones sobre textos, nombres ni plataformas
