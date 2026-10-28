## Purpose

Define cómo el buscador consulta GetOnBoard, cuya búsqueda exige todas las palabras de la consulta, y cómo una fuente puede usar palabras clave propias distintas de las globales.

## ADDED Requirements

### Requirement: Palabras clave propias de una fuente
El sistema SHALL permitir que una fuente declare en `config.yaml` su propia lista de palabras clave, con un núcleo (obligatorio, al menos una palabra) y una cola larga (opcional). Una fuente que la declara MUST usar solo esas listas para su rotación; una fuente que no la declara MUST seguir usando las palabras clave globales. La rotación de cada fuente MUST conservar su posición persistente por grupo, sin mezclarse con la de otra fuente. La configuración MUST rechazarse si el núcleo propio está vacío o si una palabra aparece vacía.

#### Scenario: Fuente con palabras propias
- **WHEN** GetOnBoard declara su propio núcleo y la corrida consulta esa fuente
- **THEN** las consultas del lote salen del núcleo y la cola larga de GetOnBoard, no de las globales

#### Scenario: Fuente sin palabras propias
- **WHEN** Computrabajo no declara palabras clave propias
- **THEN** sus consultas siguen saliendo del núcleo y la cola larga globales

#### Scenario: Núcleo propio vacío
- **WHEN** una fuente declara palabras propias con el núcleo vacío
- **THEN** la configuración se rechaza al cargarla

### Requirement: Consultas de una sola palabra en GetOnBoard
El sistema SHALL consultar GetOnBoard solo con palabras sueltas, porque su búsqueda devuelve únicamente las ofertas que contienen todas las palabras de la consulta y no admite `OR`. El núcleo de GetOnBoard MUST contener solo términos de práctica, pasantía, aprendizaje o trainee (`practicante`, `aprendiz`, `pasante`, `pasantía`, `trainee`, `internship`); los términos de nivel junior y de rol van en su cola larga. Ninguna consulta de GetOnBoard MUST contener más de una palabra. El filtro de nivel (`no_experience` y `junior`) y el descarte de remotos en inglés MUST seguir aplicándose a lo que devuelve la API.

#### Scenario: Palabra suelta con resultados
- **WHEN** el núcleo consulta «practicante» y la API devuelve ofertas de nivel sin experiencia o junior
- **THEN** esas ofertas pasan a los filtros de ubicación y de nivel del buscador

#### Scenario: Configuración sin frases
- **WHEN** se carga la configuración
- **THEN** ninguna palabra clave propia de GetOnBoard contiene un espacio

#### Scenario: Filtro de nivel intacto
- **WHEN** la API devuelve una oferta `semi_senior` para la consulta «soporte»
- **THEN** la oferta se descarta como antes

### Requirement: Paginación de GetOnBoard según el total de páginas
El sistema SHALL pedir a GetOnBoard la página indicada por la consulta (`page`), no siempre la primera. Después de leer una página, el sistema MUST pedir la siguiente de esa misma palabra clave solo si `meta.total_pages` indica que existe, sin depender de cuántas ofertas queden tras el filtro de nivel. Si la respuesta no trae `meta.total_pages`, el sistema MUST tratar la página leída como la última. Las páginas siguientes cuentan contra el presupuesto de la fuente, igual que en las demás fuentes.

#### Scenario: Segunda página
- **WHEN** «junior» responde con `total_pages = 3` y el núcleo (o la consulta) permite 2 páginas
- **THEN** el sistema pide la página 1 y luego la página 2 con `page=2`

#### Scenario: Palabra de una sola página
- **WHEN** «practicante» responde con `total_pages = 1`
- **THEN** el sistema no pide la página 2 de esa palabra y sigue con la siguiente consulta

#### Scenario: Página llena que el filtro deja casi vacía
- **WHEN** la página 1 trae 50 ofertas de las que solo 2 pasan el filtro de nivel y `total_pages` es 3
- **THEN** el sistema sí pide la página 2

#### Scenario: Respuesta sin meta
- **WHEN** la respuesta no incluye `meta.total_pages`
- **THEN** el sistema no pide más páginas de esa palabra

### Requirement: Presupuesto de GetOnBoard
El sistema SHALL configurar GetOnBoard con presupuesto 6, 2 palabras del núcleo por corrida y 2 páginas por palabra del núcleo, de modo que el núcleo ocupe como máximo 4 requests y la cola larga al menos 2. La configuración MUST seguir rechazándose si `reservado_nucleo × paginas_nucleo` supera el presupuesto.

#### Scenario: Reparto del presupuesto
- **WHEN** GetOnBoard ejecuta una corrida normal con todas sus páginas disponibles
- **THEN** hace como máximo 4 requests de núcleo y 2 de cola larga, 6 en total

#### Scenario: Páginas omitidas
- **WHEN** las dos palabras del núcleo de la corrida tienen una sola página cada una
- **THEN** la corrida hace 2 requests de núcleo y 2 de cola larga, y no gasta más
