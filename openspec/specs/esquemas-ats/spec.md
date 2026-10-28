# esquemas-ats Specification

## Purpose
Lee el formulario de postulación de las familias de ATS que lo publican antes de abrir la página, para resolver
todas las respuestas de una vez, y declara como datos el botón y la señal de éxito de cada familia.

## Requirements

### Requirement: Lectura anticipada del formulario
Para un destino de Greenhouse, Ashby, Lever o Typeform, el servidor SHALL leer el esquema del formulario sin
sesión y sin enviar nada, por la fuente pública de cada familia: la API de tableros de Greenhouse con
`questions=true`, la consulta de la página de postulación de Ashby, la página pública de postulación de Lever
y la definición que trae la página de Typeform. El esquema MUST traducirse a preguntas con texto, tipo,
opciones, obligatoriedad y la clave que la extensión verá en la página (`name` o `id` del campo). La lectura
SHALL respetar una pausa mínima por dominio. Si la lectura falla, la postulación sigue sin esquema anticipado,
como un formulario desconocido.

#### Scenario: Greenhouse
- **WHEN** el destino es `job-boards.greenhouse.io/{tablero}/jobs/{id}`
- **THEN** el servidor obtiene las preguntas con sus opciones (por ejemplo «What is your English level?» con A1 a C1) y las claves `question_{id}`, y las resuelve antes de abrir la pestaña

#### Scenario: Typeform
- **WHEN** el destino es un formulario de Typeform de 17 preguntas, una por pantalla
- **THEN** el servidor redacta todas las respuestas en una sola llamada y la extensión solo empareja y pulsa «Continue» en cada pantalla

#### Scenario: API caída
- **WHEN** la API de Greenhouse responde un error
- **THEN** la postulación sigue con el motor genérico leyendo la página

### Requirement: Datos de cada familia
Cada familia con lector SHALL declarar como datos versionados el selector del CV, el botón de enviar y la señal
de éxito, que el motor usa antes que sus reglas genéricas. Los datos de una familia MUST NOT contener código y
SHALL poder actualizarse sin publicar otra versión de la extensión.

#### Scenario: Botón de Greenhouse
- **WHEN** el motor llega al final de un formulario de Greenhouse
- **THEN** usa el botón «Submit application» declarado para la familia, sin consultar al árbitro
