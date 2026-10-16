# Spec Delta

## ADDED Requirements

### Requirement: Vacantes destacadas
Una vacante a publicar MUST marcarse como destacada si cumple todos los criterios activos de `publicacion.destacadas`. Por defecto son cuatro:
- evidencia de práctica o aprendizaje en el título;
- área de TI identificada en el título;
- en la ciudad base, o remota;
- publicada hace `max_dias` (3) o menos.

Cada criterio MUST poder desactivarse en la configuración.

#### Scenario: Cumple todo
- **WHEN** se publica «Aprendiz SENA Desarrollo de Software», remoto, publicada ayer
- **THEN** la vacante es destacada

#### Scenario: Híbrida en otra ciudad
- **WHEN** se publica «Practicante de sistemas», híbrida en Bogotá
- **THEN** la vacante no es destacada y se publica en el formato compacto

#### Scenario: Sin fecha de publicación
- **WHEN** la fuente no informa la fecha de publicación
- **THEN** el criterio de antigüedad se da por cumplido si la vacante se vio por primera vez en las últimas 24 h

### Requirement: Bloque de destacadas al inicio
Las destacadas MUST ir primero, bajo el título «⭐ DESTACADAS», antes de las categorías. Cada una MUST mostrar la ficha completa: título enlazado, empresa, lugar y modalidad, salario si lo hay, fuente y antigüedad. Además, MUST llevar una línea con los criterios que cumple, por ejemplo «🎓 Contrato de aprendizaje · 💻 Desarrollo · 🏠 Remota».

#### Scenario: Mensaje mixto
- **WHEN** una corrida publica 2 destacadas y 5 vacantes normales
- **THEN** el primer mensaje empieza con el bloque «⭐ DESTACADAS» y sus 2 fichas completas, y luego siguen las 5 normales en su categoría

### Requirement: Formato compacto para las demás vacantes
Las vacantes no destacadas MUST publicarse en formato compacto: el título enlazado y una segunda línea con la empresa, el lugar y la antigüedad. El salario MUST omitirse en este formato.

#### Scenario: Vacante normal
- **WHEN** se publica una vacante no destacada con empresa, ubicación y salario
- **THEN** su ficha ocupa dos líneas y no muestra el salario

### Requirement: Las destacadas se cuentan en el encabezado
El encabezado del primer mensaje de una corrida MUST decir cuántas vacantes son destacadas cuando haya al menos una, por ejemplo «🔔 7 vacantes nuevas · ⭐ 2 destacadas».

#### Scenario: Sin destacadas
- **WHEN** una corrida publica 4 vacantes y ninguna es destacada
- **THEN** el encabezado dice «🔔 4 vacantes nuevas», sin mención a destacadas

### Requirement: El corte de mensajes respeta el bloque de destacadas
Al dividir en mensajes de hasta 4.096 caracteres, una ficha MUST NOT partirse. Si el bloque de destacadas continúa en el mensaje siguiente, ese mensaje MUST repetir el título «⭐ DESTACADAS», igual que se repite el título de una categoría.

#### Scenario: Muchas destacadas
- **WHEN** las fichas destacadas no caben en un solo mensaje
- **THEN** el segundo mensaje empieza con «⭐ DESTACADAS» y sigue con las fichas que faltan
