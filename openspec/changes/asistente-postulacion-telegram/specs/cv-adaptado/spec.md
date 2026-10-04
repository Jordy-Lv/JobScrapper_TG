## Purpose

Generar para cada oferta una versión del CV del usuario **levemente** ajustada: el mismo CV, con
el resumen y el orden de habilidades inclinados hacia la oferta, sin intentar cumplir todos sus
requisitos y sin inventar nada. El PDF resultante debe ser legible por sistemas ATS.

## ADDED Requirements

### Requirement: Adaptación leve
El CV adaptado SHALL conservar la estructura, las secciones, las experiencias, los proyectos y sus viñetas del CV base del usuario. Solo MAY cambiar:
- el resumen profesional, reescrito en 2 a 4 líneas con un enfoque hacia el cargo de la oferta, partiendo del resumen y el enfoque del usuario;
- el orden de las habilidades, subiendo hasta 6 que coinciden con la oferta;
- hasta 3 términos reemplazados por el nombre equivalente que usa la oferta, solo si son sinónimos de algo que el usuario tiene (por ejemplo "JS" → "JavaScript").

El CV adaptado MUST NOT agregar habilidades, tecnologías, títulos, cargos, empresas, fechas, niveles de idioma ni logros, ni intentar cubrir requisitos que el usuario no cumple.

#### Scenario: Oferta de backend
- **WHEN** la oferta pide Python y SQL y el CV base lista Java, Excel, Python y SQL
- **THEN** el CV adaptado es igual al base, salvo un resumen orientado a desarrollo backend y Python y SQL al inicio de las habilidades

#### Scenario: Requisito que no cumple
- **WHEN** la oferta pide Docker y el usuario no lo tiene
- **THEN** el CV adaptado no menciona Docker

### Requirement: Validador de veracidad
Antes de generar el PDF, el resultado SHALL compararse en forma determinista con el CV base:
- toda habilidad debe existir en el perfil o ser un sinónimo de la tabla configurable;
- experiencias, proyectos, formación, fechas e idiomas se copian del perfil, no de la salida de la IA;
- el resumen no puede mencionar tecnologías ausentes del perfil;
- no se pueden superar los límites de cambio de la adaptación leve.

Lo que no pasa MUST descartarse. Si el resumen falla, MUST usarse el resumen base.

#### Scenario: Habilidad inventada en el resumen
- **WHEN** el resumen propuesto menciona "Kubernetes" y el perfil no lo tiene
- **THEN** se usa el resumen base

#### Scenario: Demasiados reemplazos
- **WHEN** la salida reemplaza 5 términos
- **THEN** solo se aplican los 3 primeros válidos

### Requirement: CV base del usuario
Al terminar el alta, el sistema SHALL generar el CV base del usuario a partir de su perfil confirmado, con la misma plantilla. El usuario MUST poder descargarlo con `/cv`. Si el usuario no tiene clave de IA o la IA falla, el CV de la postulación MUST ser el CV base sin cambios.

#### Scenario: Sin IA
- **WHEN** la cuota de Gemini del usuario está agotada
- **THEN** la postulación adjunta el CV base

### Requirement: PDF apto para ATS
El PDF SHALL generarse con una plantilla de una columna:
- sin foto;
- texto real seleccionable;
- títulos de sección estándar en español;
- fuente con tildes y ñ;
- como máximo 2 páginas.

El archivo MUST llamarse `CV_<Nombre>_<Apellido>.pdf`, con el mismo nombre en todas las ofertas, para no revelar la adaptación. Los datos de contacto MUST tomarse del perfil local.

#### Scenario: Texto extraíble
- **WHEN** se extrae el texto del PDF
- **THEN** aparecen las secciones, las habilidades y el contacto como texto, con tildes correctas
