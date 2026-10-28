## MODIFIED Requirements

### Requirement: La respuesta del usuario manda
Lo que el usuario respondió en las preguntas rápidas SHALL prevalecer sobre lo derivado del CV y sobre el banco de preguntas. Las preguntas que el CV ya respondió MUST NOT aparecer en el bloque del alta. El bloque de preguntas frecuentes del alta SHALL cubrir semestre, enlace de portafolio y autorización de trabajo en Colombia cuando no vengan en el CV.

#### Scenario: Semestre presente en el CV
- **WHEN** la formación académica extraída del CV contiene el semestre
- **THEN** la pregunta de semestre no se realiza en la tarjeta del alta y se conserva el valor del CV

#### Scenario: Portafolio o GitHub presente en el CV
- **WHEN** el perfil extraído del CV contiene un enlace a GitHub o portafolio
- **THEN** la pregunta de enlace de portafolio no se realiza en la tarjeta del alta y se conserva el valor del CV

#### Scenario: Autorización de trabajo en Colombia presente en el CV
- **WHEN** el CV contiene documento de identidad colombiano (C.C., T.I., C.E.) o indicación explícita de autorización legal en Colombia
- **THEN** la autorización para Colombia se precarga como «Sí» y no se pregunta en el alta

#### Scenario: Preguntas frecuentes no provistas en el CV
- **WHEN** el CV no contiene semestre, portafolio ni documento/autorización para Colombia
- **THEN** la tarjeta del alta las incluye con sus opciones correspondientes (y omitir cuando aplique)
