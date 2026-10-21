## ADDED Requirements

### Requirement: Emoji de color por plataforma
El asistente SHALL identificar cada plataforma con un emoji fijo (🔵 Computrabajo, 🟢 Magneto, 🩵 elempleo) antepuesto a su nombre en la cabecera de la card y en cada línea de cuenta del bloque «Conexión». Una plataforma sin emoji registrado o desconocida MUST mostrarse sin emoji y sin espacios sobrantes. Los textos en prosa y los botones MUST seguir nombrando el portal sin emoji.

#### Scenario: Cabecera con empresa
- **WHEN** la card de una vacante de Magneto de la empresa «Maaji» se muestra en cualquier fase
- **THEN** la línea bajo el título es «Maaji · 🟢 Magneto»

#### Scenario: Cabecera sin empresa
- **WHEN** la vacante de Computrabajo no tiene empresa
- **THEN** la línea bajo el título es «🔵 Computrabajo»

#### Scenario: Bloque de conexión
- **WHEN** el bloque «Conexión» muestra la cuenta de elempleo
- **THEN** la línea de esa cuenta nombra el portal como «🩵 elempleo»

#### Scenario: Plataforma sin emoji
- **WHEN** la plataforma no tiene emoji registrado
- **THEN** se muestra solo su nombre, sin espacio inicial

#### Scenario: Botones y prosa
- **WHEN** el bot muestra el botón «Confirmar Magneto» o una frase como «Postular en Magneto»
- **THEN** el nombre del portal aparece sin emoji
