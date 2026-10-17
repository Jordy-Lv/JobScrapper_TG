## Purpose

Permite a los administradores ajustar desde el panel las palabras clave, los filtros y las fuentes del radar, viendo antes de guardar qué vacantes cambiarían y pudiendo deshacer cualquier cambio.

## ADDED Requirements

### Requirement: Editor de filtros por sección
La vista Filtros SHALL mostrar y permitir editar los valores vigentes de estas secciones:
- `palabras_clave` (núcleo y cola larga por área);
- `filtros` completo: listas de términos, `max_dias_publicada`, `anios_experiencia_excluidos_desde`, niveles, áreas con su orden, ubicación y lista negra.

Cada lista de términos se edita agregando y quitando términos. El editor MUST cumplir lo siguiente:
- avisar de un término repetido tras normalizarlo (minúsculas, sin tildes);
- impedir guardar una lista que el modelo exige no vacía;
- permitir reordenar las áreas, porque el orden es la prioridad;
- marcar en cada sección si su valor viene del repositorio o del panel.

#### Scenario: Agregar a la lista negra
- **WHEN** el admin agrega «Empresa X» a la lista negra de empresas y guarda
- **THEN** desde la siguiente corrida las vacantes de esa empresa se rechazan por `lista_negra`

#### Scenario: Término repetido
- **WHEN** el admin agrega «Práctica» a una lista que ya tiene «practica»
- **THEN** el editor avisa que el término ya existe y no lo duplica

#### Scenario: Lista obligatoria vacía
- **WHEN** el admin quita todos los términos de `exclusion_seniority`
- **THEN** el panel no deja guardar y explica que la lista no puede quedar vacía

#### Scenario: Reordenar áreas
- **WHEN** el admin pasa «datos» antes de «qa» y guarda
- **THEN** una vacante que coincide con las dos áreas queda en «datos»

### Requirement: Editor de fuentes
La vista Fuentes SHALL permitir activar o desactivar cada fuente de `fuentes` y cambiar su `presupuesto` (de 0 a 20), su `reservado_nucleo` (de 0 a `presupuesto`) y sus `paginas_nucleo` (de 1 a 5). La nota de la fuente se muestra cuando la tiene. Los demás campos de la fuente (ritmo, detalle, opciones, pausas) MUST NOT ser editables desde el panel.

#### Scenario: Desactivar una fuente
- **WHEN** el admin desactiva «magneto» y guarda
- **THEN** la siguiente corrida no consulta Magneto

#### Scenario: Valor fuera de límites
- **WHEN** el admin pone `presupuesto: 50` en Computrabajo
- **THEN** el panel no deja guardar y muestra el rango permitido

### Requirement: Probar antes de guardar
El panel SHALL ofrecer «Probar con vacantes reales». Evalúa con las reglas actuales y con las editadas las vacantes de los últimos `asistente.panel.dias_prueba` días: las aceptadas o enviadas y las descartadas que guardó el radar. Muestra:
- cuántas y cuáles pasan de aceptada a rechazada, con la regla que las rechaza;
- cuáles pasan de rechazada a aceptada;
- cuáles cambian de categoría;
- cuántas quedarían dudosas.

La prueba MUST NOT llamar a la IA, publicar en Telegram ni cambiar ningún dato. Las vacantes que hoy serían dudosas se informan como «irían a la IA».

#### Scenario: Ver lo que se pierde
- **WHEN** el admin agrega «auxiliar» a `exclusion_seniority` y prueba
- **THEN** ve la lista de vacantes de los últimos 7 días que pasarían a rechazadas por seniority, con título, fuente y enlace

#### Scenario: Ver lo que se gana
- **WHEN** el admin quita «especialista» de `exclusion_seniority` y prueba
- **THEN** ve las vacantes descartadas por esa palabra que ahora pasarían

#### Scenario: Prueba sin efectos
- **WHEN** el admin prueba y no guarda
- **THEN** la configuración, las tablas del radar y el canal siguen igual

### Requirement: Guardar con validación y control de versión
Guardar SHALL seguir estos pasos:
1. mostrar las diferencias contra la versión vigente y pedir confirmación, con un comentario opcional;
2. validar la configuración completa resultante con los mismos modelos que usa el radar;
3. escribir de forma atómica las secciones editadas en `config.panel.yaml`;
4. registrar la versión con el autor, la fecha, el comentario y las diferencias.

Si otro admin guardó después de que se abrió el editor, el guardado MUST rechazarse con «Otro admin cambió los filtros; recarga para ver su versión», sin perder lo editado en la página. Cada guardado MUST exigir el token CSRF y quedar en `auditoria`. Tras guardar, el panel muestra «Rige desde la próxima corrida (HH:MM)».

#### Scenario: Guardado correcto
- **WHEN** el admin confirma un cambio válido
- **THEN** `config.panel.yaml` queda con el cambio, se crea una versión nueva y la página muestra la hora de la próxima corrida

#### Scenario: Configuración inválida
- **WHEN** el cambio deja `reservado_nucleo` mayor que `presupuesto` u otra combinación que el modelo rechaza
- **THEN** no se escribe nada y el panel muestra el error del modelo junto al campo

#### Scenario: Dos admins a la vez
- **WHEN** el admin A guarda y luego el admin B guarda desde un editor abierto antes
- **THEN** el guardado de B se rechaza con el aviso de recargar, y su edición sigue en la página

### Requirement: Historial y deshacer
El panel SHALL listar las versiones guardadas, de la más reciente a la más vieja, con su autor, fecha, comentario y diferencias. Ofrece:
- «Restaurar» para cualquier versión, que crea una versión nueva con ese contenido;
- «Volver al valor del repositorio» para cada sección, que la quita de `config.panel.yaml`.

Ambas acciones pasan por las mismas diferencias, confirmación, validación y auditoría que un guardado.

#### Scenario: Restaurar
- **WHEN** el admin restaura la versión de ayer
- **THEN** se crea una versión nueva igual a la de ayer, y la siguiente corrida usa esos valores

#### Scenario: Volver al repositorio
- **WHEN** el admin pulsa «Volver al valor del repositorio» en `palabras_clave`
- **THEN** esa sección desaparece de `config.panel.yaml` y rige la de `config.yaml`
