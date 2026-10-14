# Spec Delta

## ADDED Requirements

### Requirement: Búsqueda de LinkedIn ordenada por fecha
La fuente LinkedIn SHALL pedir sus resultados ordenados del más reciente al más antiguo, de modo que la primera página contenga lo último publicado. El orden MUST poder cambiarse desde la configuración.

#### Scenario: Petición ordenada por fecha
- **WHEN** el sistema construye una petición a LinkedIn con la configuración por defecto
- **THEN** la petición pide orden por fecha de publicación

### Requirement: Consultas combinadas en LinkedIn
La fuente LinkedIn SHALL cubrir varias palabras clave con una sola petición, uniéndolas con el operador `OR`. El núcleo se agrupa en una o pocas consultas, y la cola larga en una consulta por área de la configuración, partida en grupos de como máximo un número configurable de términos. Cada término compuesto MUST ir entre comillas. La consulta combinada MUST seguir usando las mismas variantes de búsqueda (Colombia remoto o híbrido, y Cartagena), alternadas en orden circular.

En cada corrida, LinkedIn SHALL hacer una consulta de núcleo, salvo una corrida de cada N (configurable) que lee un grupo de la cola larga en su lugar. La posición de rotación de los grupos de núcleo, de los de cola larga y de las variantes MUST persistir entre corridas.

#### Scenario: Una petición cubre el núcleo
- **WHEN** el núcleo tiene 14 palabras clave y el tamaño máximo de grupo admite 14
- **THEN** la corrida hace una sola petición a LinkedIn, con las 14 palabras unidas por `OR`

#### Scenario: Turno de la cola larga
- **WHEN** la cola larga se lee una de cada 4 corridas
- **THEN** tres corridas consultan el núcleo y la cuarta consulta el siguiente grupo de la cola larga, sin superar una petición base por corrida

#### Scenario: Variantes alternadas con consulta combinada
- **WHEN** dos corridas seguidas consultan el núcleo
- **THEN** una usa la variante «Colombia remoto o híbrido» y la otra la variante de Cartagena

### Requirement: Ventana de publicación según el último sondeo
La fuente LinkedIn SHALL limitar la antigüedad de lo pedido al tiempo transcurrido desde el último sondeo exitoso de esa misma consulta y variante, más un margen configurable, con un mínimo y un máximo de 24 h. Si esa consulta no tiene sondeo previo, la ventana es de 24 h. Un sondeo MUST registrarse solo si la respuesta fue exitosa y la corrida no es un dry-run.

#### Scenario: Operación normal
- **WHEN** una variante se sondeó con éxito hace 60 minutos y el margen es de 30 minutos
- **THEN** la petición pide lo publicado en las últimas 1,5 horas, o el mínimo configurado si es mayor

#### Scenario: Recuperación tras un cooldown
- **WHEN** una variante no se sondea durante 5 horas por un cooldown
- **THEN** la siguiente petición pide al menos las últimas 5 horas, para no perder lo publicado durante el cooldown

#### Scenario: Consulta sin sondeo previo
- **WHEN** una consulta nunca se ha sondeado
- **THEN** la petición pide las últimas 24 horas

#### Scenario: El dry-run no mueve el estado
- **WHEN** se ejecuta una corrida en modo dry-run
- **THEN** no se registra ningún sondeo y las ventanas de las corridas reales no cambian

### Requirement: Página adicional solo si la primera viene saturada
La fuente LinkedIn SHALL leer una segunda página de la consulta de núcleo únicamente si la primera vino completa (10 vacantes), porque puede haber más publicaciones nuevas que las que caben en una página. Si la primera no vino completa, MUST NOT pedir la segunda. La cola larga solo lee la primera página.

#### Scenario: Primera página incompleta
- **WHEN** la consulta de núcleo devuelve 6 vacantes
- **THEN** la corrida hace una sola petición a LinkedIn

#### Scenario: Primera página completa
- **WHEN** la consulta de núcleo devuelve 10 vacantes
- **THEN** la corrida lee la segunda página, con la pausa propia de la fuente, y no más de dos páginas

### Requirement: Respaldo cuando LinkedIn no acepta el OR
El sistema SHALL poder usar LinkedIn con una palabra clave por petición, sin `OR`, cambiando una opción de la configuración. En ese modo MUST seguir aplicando el orden por fecha, la ventana de publicación y el ritmo adaptativo. El modo combinado MUST activarse solo después de comprobar, con una petición real de prueba, que LinkedIn acepta el orden por fecha y el `OR`.

#### Scenario: Modo sin OR
- **WHEN** la configuración de LinkedIn pide una palabra clave por petición
- **THEN** cada consulta lleva una sola palabra clave, ordenada por fecha y con la ventana de publicación

### Requirement: Ritmo adaptativo ante bloqueos
La fuente LinkedIn SHALL espaciar sus peticiones según una escala de intervalos mínimos configurable (por defecto 30, 60 y 120 minutos entre peticiones). Tras un bloqueo, la fuente MUST pasar al siguiente intervalo de la escala, sin pasar del último. Tras un número configurable de peticiones exitosas seguidas, MUST volver al intervalo anterior, hasta llegar al primero. Una corrida que llegue antes de cumplirse el intervalo vigente MUST omitir la fuente y dejar constancia del motivo. El ritmo adaptativo MUST sumarse al cooldown escalonado, no reemplazarlo.

#### Scenario: Bloqueo sube el intervalo
- **WHEN** LinkedIn responde 429 con el intervalo en 30 minutos
- **THEN** tras el cooldown, LinkedIn se consulta como máximo cada 60 minutos

#### Scenario: Corrida adelantada
- **WHEN** pasan 30 minutos desde la última petición y el intervalo vigente es de 60
- **THEN** la corrida omite LinkedIn indicando que el ritmo adaptado aún no permite consultarla

#### Scenario: Recuperación gradual
- **WHEN** LinkedIn acumula las peticiones exitosas seguidas configuradas con el intervalo en 120 minutos
- **THEN** el intervalo vuelve a 60 minutos

#### Scenario: Sin bloqueos
- **WHEN** LinkedIn no ha tenido bloqueos recientes
- **THEN** el intervalo es el primero de la escala y se consulta en cada corrida

### Requirement: El cooldown respeta Retry-After
Ante un 429, 403 o 999, si la respuesta trae la cabecera `Retry-After`, el cooldown SHALL durar al menos ese tiempo, con un tope configurable. Si la cabecera no está o no se entiende, se aplica el cooldown escalonado de siempre. Cuando ambos existen, MUST aplicarse el mayor.

#### Scenario: Retry-After mayor que el escalón
- **WHEN** el primer bloqueo trae `Retry-After: 14400` (4 h) y el escalón es de 2 h
- **THEN** la fuente queda en cooldown 4 h

#### Scenario: Retry-After menor que el escalón
- **WHEN** el bloqueo trae `Retry-After: 60` y el escalón es de 2 h
- **THEN** la fuente queda en cooldown 2 h

#### Scenario: Retry-After absurdo
- **WHEN** el bloqueo trae un `Retry-After` de varios días y el tope es de 24 h
- **THEN** el cooldown es de 24 h

### Requirement: Pausa entre peticiones propia de cada fuente
Cada fuente SHALL poder definir su propio rango de pausa entre peticiones consecutivas. Si no lo define, MUST usar el rango global. LinkedIn usa por defecto una pausa más larga que el rango global.

#### Scenario: Fuente con pausa propia
- **WHEN** LinkedIn define una pausa de 20 a 45 s y el rango global es de 4 a 10 s
- **THEN** entre dos páginas de LinkedIn la pausa está entre 20 y 45 s, y las demás fuentes siguen entre 4 y 10 s
