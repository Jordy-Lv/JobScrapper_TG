## ADDED Requirements

### Requirement: Card de un portal que no procesó «Aplicar»
Cuando la extensión reporta que el portal no procesó el clic de postular (sin encuesta, sin confirmación y con el botón de postular aún en la vacante), la card MUST decir que el portal no cargó la postulación, MUST aclarar que no se envió nada y MUST ofrecer «Reintentar». La card MUST NOT usar el aviso «no mostró la confirmación» en ese caso, porque ese aviso indica que el envío sí se hizo.

#### Scenario: Aplicar sin respuesta del portal
- **WHEN** la postulación termina con el motivo de que el portal no procesó «Aplicar»
- **THEN** la card dice que el portal no cargó la postulación, que no se envió nada y muestra «Reintentar»

#### Scenario: Reintento
- **WHEN** el usuario toca «Reintentar» en esa card
- **THEN** la postulación vuelve a «En cola» y se ejecuta de nuevo

#### Scenario: Sin confirmación tras enviar
- **WHEN** el envío se hizo (se pulsó «Enviar respuestas» o «Aplicar» y la página cambió) pero el portal no mostró confirmación
- **THEN** la card conserva el aviso de que no hubo confirmación y de revisar «Mis postulaciones»
