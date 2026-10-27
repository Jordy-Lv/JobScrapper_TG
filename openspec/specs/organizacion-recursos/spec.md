# organizacion-recursos Specification

## Purpose
Fijar cómo se organizan los recursos (`assets/`) y la documentación (`docs/`) por pertenencia, para que cada archivo diga a qué parte del sistema sirve y las rutas se mantengan en un solo lugar.

## Requirements

### Requirement: Recursos organizados por pertenencia
`assets/` SHALL organizarse en `marca/` (identidad visual), `radar/` (recursos del buscador) y `asistente/` (recursos del asistente), y no SHALL quedar archivos sueltos en su raíz.

#### Scenario: Recurso del radar
- **WHEN** un recurso lo usa solo el buscador (por ejemplo la imagen de encabezado o el certificado del SPE)
- **THEN** vive bajo `assets/radar/`

#### Scenario: Recurso del asistente
- **WHEN** un recurso lo usa solo el asistente (banco de preguntas, tecnologías, selectores o tipografías del PDF)
- **THEN** vive bajo `assets/asistente/`

### Requirement: Documentación organizada por tema
`docs/` SHALL organizarse en `radar/`, `asistente/`, `referencia/` y `decisiones/`.

#### Scenario: Documento de usuario del asistente
- **WHEN** un documento está dirigido a los usuarios del asistente o a su ficha de tienda
- **THEN** vive bajo `docs/asistente/`

#### Scenario: Registro de decisiones
- **WHEN** se toma una decisión de arquitectura
- **THEN** se registra como un ADR numerado en `docs/decisiones/`

### Requirement: Rutas sin romper
Después del movimiento, toda ruta a un recurso o documento citada en código, configuración, pruebas y documentación SHALL apuntar a la ubicación nueva.

#### Scenario: Búsqueda de rutas viejas
- **WHEN** se busca en el repositorio una ruta antigua de `assets/` o `docs/` movida
- **THEN** no aparece en código, configuración, pruebas, README ni guías (salvo en el historial archivado de los changes)

### Requirement: Comportamiento idéntico
El reordenamiento SHALL NOT cambiar lo que el sistema publica, calcula ni responde.

#### Scenario: Suite y artefactos
- **WHEN** se ejecuta la suite completa y se genera el PDF de un CV y la imagen de encabezado de una publicación
- **THEN** la suite da el mismo resultado que antes y el PDF y la imagen se generan con los mismos recursos

### Requirement: Borrado de recursos sin uso con confirmación
Un recurso sin ninguna referencia SHALL borrarse solo tras confirmación expresa del dueño.

#### Scenario: Logos antiguos
- **WHEN** `logo_v1.jpg` y `logo_v2.jpg` no tienen referencias en el repositorio
- **THEN** se propone su borrado y se ejecuta solo con el sí del dueño
