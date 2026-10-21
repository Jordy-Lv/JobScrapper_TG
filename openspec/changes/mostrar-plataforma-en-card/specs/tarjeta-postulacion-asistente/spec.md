## ADDED Requirements

### Requirement: Plataforma de la vacante en la cabecera de la card
La card SHALL mostrar en su cabecera la plataforma de la vacante (por ejemplo Computrabajo, Magneto o elempleo), junto a la empresa en la forma «Empresa · Plataforma», o sola si no hay empresa, en todas las fases desde la creación de la card hasta su cierre, incluidas la confirmada y la incierta. Si la plataforma es desconocida, la cabecera MUST omitirla sin dejar líneas vacías ni textos como «None». El nombre MUST escaparse como el resto del contenido.

#### Scenario: Card en progreso
- **WHEN** la card de una vacante de Magneto de la empresa «Maaji» está en progreso
- **THEN** la cabecera muestra el título y debajo «Maaji · Magneto», seguida de la afinidad, la barra y las etapas

#### Scenario: Card en cola
- **WHEN** la postulación está en cola o esperando navegador
- **THEN** la cabecera muestra la misma línea con la plataforma, sin cambiar el cuerpo de estado

#### Scenario: Card confirmada o incierta
- **WHEN** la postulación queda confirmada o incierta
- **THEN** la cabecera de la card conserva la plataforma junto a la empresa, y la cita de estado sigue nombrando el portal

#### Scenario: Vacante sin empresa
- **WHEN** la vacante no tiene empresa pero sí plataforma
- **THEN** la línea bajo el título muestra solo la plataforma

#### Scenario: Plataforma desconocida
- **WHEN** la postulación no tiene plataforma
- **THEN** la cabecera queda con título y, si existe, empresa, sin la plataforma
