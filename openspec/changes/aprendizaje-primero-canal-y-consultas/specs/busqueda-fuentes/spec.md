# Spec Delta

## ADDED Requirements

### Requirement: Palabras clave junior en su propio grupo
Las consultas de nivel junior MUST vivir en `palabras_clave.junior`, separadas del núcleo y de la cola larga de prácticas. Con el nivel junior pausado, la rotación MUST NOT incluirlas. Con el nivel activo, MUST rotar con la cola larga.

#### Scenario: Junior pausado
- **WHEN** corre una búsqueda en Computrabajo con el nivel junior pausado
- **THEN** ninguna consulta de la corrida es del grupo `junior`

#### Scenario: Junior activo
- **WHEN** el administrador enciende el nivel junior
- **THEN** las consultas del grupo `junior` vuelven a la rotación desde la posición que tenían guardada

### Requirement: La cola larga del canal es solo de prácticas y sin experiencia
Con el nivel junior pausado, cada palabra clave de `palabras_clave.nucleo` y `palabras_clave.cola_larga` MUST contener un término de práctica, aprendizaje, pasantía, etapa productiva, trainee o intern, o de «sin experiencia» o «primer empleo». Una prueba de configuración MUST verificarlo.

#### Scenario: Término junior en la cola larga
- **WHEN** alguien agrega «QA junior» a `cola_larga`
- **THEN** la prueba de configuración falla e indica que va en `palabras_clave.junior`

### Requirement: El núcleo cubre la jerga del aprendizaje
El núcleo MUST incluir, además de los términos actuales: «contrato de aprendizaje», «etapa productiva», «aprendiz desarrollo de software», «aprendiz soporte técnico», «aprendiz redes», «aprendiz análisis de datos», «practicante desarrollo», «practicante soporte» y «pasante sistemas».

#### Scenario: Contrato de aprendizaje
- **WHEN** se carga la configuración
- **THEN** «contrato de aprendizaje» está en el núcleo y no en la cola larga

### Requirement: Consultas de sin experiencia
El núcleo o la cola larga MUST incluir consultas de TI sin experiencia, como «desarrollador sin experiencia», «soporte TI sin experiencia» y «primer empleo sistemas».

#### Scenario: Primer empleo
- **WHEN** se carga la configuración
- **THEN** hay al menos una consulta de «primer empleo» y una de «sin experiencia» en el núcleo o en la cola larga

### Requirement: Filtros de nivel nativos acordes al alcance
Con el nivel junior pausado, GetOnBoard MUST pedir solo `no_experience`. LinkedIn MUST pedir el nivel configurado en `opciones.f_E`: `1` (solo prácticas) cuando los datos de `descartes` muestren que el nivel de entrada (`2`) trae sobre todo profesionales, y `1,2` si la cobertura cae.

#### Scenario: GetOnBoard
- **WHEN** corre GetOnBoard con el nivel junior pausado
- **THEN** la petición solo incluye el nivel `no_experience`

### Requirement: El presupuesto liberado va al núcleo
Con el nivel junior pausado, en las fuentes sin filtro de nivel nativo, `reservado_nucleo × paginas_nucleo` MUST cubrir al menos el 75 % del presupuesto de la fuente. Ninguna corrida MUST superar el número total de requests que tenía antes de este cambio.

#### Scenario: Computrabajo
- **WHEN** corre Computrabajo con presupuesto 8 y el nivel junior pausado
- **THEN** al menos 6 de sus requests son del núcleo y la corrida no hace más de 8 requests
