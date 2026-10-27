# Spec Delta

## ADDED Requirements

### Requirement: Plataformas con postulación automática ampliables por habilitación
Una plataforma SHALL postular sola únicamente cuando cumple las cuatro condiciones: su reconocimiento con sesión real está documentado, sus términos de uso permiten la postulación desde el navegador del propio usuario, sus selectores están cargados en el servidor y su ajuste de automática está en verdadero. Mientras falte alguna, sus vacantes MUST seguir el camino del paquete de respaldo con el motivo `plataforma_no_automatica` (o `plataforma_no_soportada` si el dominio no se reconoce). Las plataformas elempleo, GetOnBoard y Servicio Público de Empleo SHALL seguir este mismo proceso; LinkedIn SHALL habilitarse solo por el change `postular-linkedin` (aceptación del riesgo por usuario, interruptores y pilotos), y mientras su ajuste de automática esté en falso MUST seguir en el paquete de respaldo.

#### Scenario: Plataforma reconocida pero sin habilitar
- **WHEN** el usuario toca ⚡ en una vacante de elempleo y elempleo tiene selectores cargados pero no está marcada como automática
- **THEN** la vacante pasa al paquete de respaldo con el motivo `plataforma_no_automatica` y no se abre ninguna pestaña

#### Scenario: Plataforma habilitada
- **WHEN** el usuario con navegador vinculado toca ⚡ en una vacante de una plataforma habilitada
- **THEN** la postulación entra a la cola y la extensión la ejecuta igual que en Computrabajo y Magneto

#### Scenario: Términos que lo prohíben
- **WHEN** la revisión de términos de una plataforma concluye que la postulación asistida está prohibida
- **THEN** la plataforma queda en paquete de respaldo, el motivo se documenta y sus selectores no se habilitan

#### Scenario: LinkedIn
- **WHEN** el usuario toca ⚡ en una vacante de LinkedIn y `plataformas.linkedin.automatica` está en falso
- **THEN** recibe el paquete de respaldo, sin importar la configuración de las demás plataformas (con LinkedIn encendido rige `postular-linkedin`)

### Requirement: Dominio de la vacante determina la plataforma
La plataforma de una vacante SHALL decidirse por el dominio de su enlace final, no por la fuente que la encontró. Una vacante hallada por el Servicio Público de Empleo cuyo enlace apunta a Computrabajo, Magneto, elempleo o GetOnBoard MUST tratarse como de ese portal. Una vacante cuyo enlace apunta a un dominio sin selectores (otras bolsas o sistemas externos de reclutamiento) MUST ir al paquete de respaldo.

#### Scenario: Plaza del SPE que enlaza a Computrabajo
- **WHEN** la fuente es el SPE y el enlace de origen es de `computrabajo.com`
- **THEN** la vacante se postula por el camino de Computrabajo si esa plataforma está habilitada

#### Scenario: Plaza del SPE con bolsa externa
- **WHEN** el enlace de la plaza apunta a una bolsa sin selectores
- **THEN** la vacante va al paquete de respaldo con el motivo `plataforma_no_soportada`

### Requirement: Piloto antes de habilitar una plataforma
Una plataforma nueva MUST pasar por un piloto del dueño antes de marcarse como automática: al menos 3 vacantes reales que terminen en `enviada`, visibles en la sección de postulaciones del portal, con el CV enviado verificado y sin datos inventados. Después SHALL probarse con los invitados durante al menos 3 días sin errores sin resolver. Si el piloto falla por una causa del portal que no se puede corregir con datos, la plataforma MUST quedar en respaldo.

#### Scenario: Piloto exitoso
- **WHEN** las 3 postulaciones del dueño terminan `enviada` y aparecen en el portal
- **THEN** la plataforma puede pasar a `automatica: true` en la configuración

#### Scenario: Piloto con formulario desconocido
- **WHEN** dos de las tres postulaciones terminan en `formulario_desconocido` por una pantalla que los selectores no cubren
- **THEN** la plataforma permanece sin habilitar hasta corregir los selectores y repetir el piloto
