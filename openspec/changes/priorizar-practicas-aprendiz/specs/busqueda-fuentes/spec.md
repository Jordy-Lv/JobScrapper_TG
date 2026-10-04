# Spec Delta

## MODIFIED Requirements

### Requirement: Rotación de palabras clave
El sistema SHALL mantener una lista configurable de palabras clave para el nivel práctica/aprendiz y junior/entrada en todos los roles de TI (desarrollo, infraestructura/DevOps/cloud, redes, bases de datos, soporte IT, datos y analítica, QA, ciberseguridad), dividida en dos grupos:
- **núcleo**: consultas de prácticas, pasantías y aprendizaje que se repiten en cada ciclo corto (por ejemplo "practicante sistemas", "aprendiz SENA", "aprendiz ADSO", "práctica profesional ingeniería de sistemas"). El núcleo MUST contener solo términos de nivel práctica, pasantía, aprendiz, trainee, intern o estudiante; los términos de nivel junior van en la cola larga;
- **cola larga**: consultas específicas por rol, de nivel junior o práctica, en español o en inglés con el nivel explícito en el término (por ejemplo "Junior Software Engineer").

En cada corrida el sistema SHALL procesar el siguiente lote de cada fuente: primero el número configurado de palabras clave del núcleo y luego la cola larga con el presupuesto restante. Así las consultas de prácticas se repiten cada pocas horas aunque la lista total sea larga. Cada fuente MAY leer varias páginas de resultados de cada consulta del núcleo, hasta el número de páginas configurado; las consultas de la cola larga leen solo la primera página. Si una página trae menos resultados que una página completa, el sistema MUST NOT pedir las páginas siguientes de esa consulta. En las fuentes sin filtro de nivel nativo, los requests reservados al núcleo (palabras clave × páginas) MUST ser al menos la mitad del presupuesto de la fuente. La posición de rotación de cada grupo MUST persistir entre corridas y reinicios, MUST avanzar por palabra clave (no por página) y al llegar al final MUST volver al inicio.

#### Scenario: Núcleo frecuente
- **WHEN** una fuente reserva 2 palabras clave del núcleo por corrida y el núcleo tiene 14 consultas
- **THEN** cada consulta núcleo se repite cada 7 corridas (~3,5 h)

#### Scenario: Paginación del núcleo
- **WHEN** Computrabajo tiene 3 páginas para el núcleo y la consulta "practicante sistemas" devuelve páginas completas
- **THEN** el sistema pide las páginas 1, 2 y 3 de esa consulta en la misma corrida

#### Scenario: Corte de la paginación
- **WHEN** la página 1 de una consulta del núcleo trae menos resultados que una página completa
- **THEN** el sistema no pide la página 2 de esa consulta y continúa con la siguiente consulta del lote

#### Scenario: La rotación avanza por palabra clave
- **WHEN** una fuente ejecuta 2 palabras clave del núcleo con 3 páginas cada una
- **THEN** la posición del núcleo avanza 2, no 6

#### Scenario: Prioridad de prácticas en el presupuesto
- **WHEN** una fuente sin filtro de nivel nativo (como Computrabajo, elempleo o Magneto) ejecuta una corrida normal con páginas completas
- **THEN** al menos la mitad de sus requests de la corrida son consultas del núcleo de prácticas y aprendizaje

#### Scenario: Núcleo exclusivo de prácticas
- **WHEN** se carga la configuración
- **THEN** ninguna consulta del núcleo es de nivel junior ("junior TI" y "desarrollador junior" están en la cola larga)

#### Scenario: Filtro de nivel nativo de la fuente
- **WHEN** la fuente permite filtrar por nivel de experiencia (como LinkedIn con prácticas y nivel de entrada)
- **THEN** el sistema aplica ese filtro en la consulta para que cada request traiga más vacantes relevantes

#### Scenario: Avance de la rotación
- **WHEN** una fuente usa 2 requests de cola larga y termina una corrida en la posición 6 de esa lista
- **THEN** la siguiente corrida continúa la cola larga en la posición 8

#### Scenario: Fin de la lista
- **WHEN** el lote alcanza la última palabra clave
- **THEN** la rotación continúa desde la primera palabra clave

### Requirement: Presupuesto y ritmo de requests
El sistema SHALL limitar los requests por fuente y por corrida al presupuesto configurado; cada página pedida cuenta como un request. Los valores iniciales (presupuesto / palabras clave del núcleo / páginas del núcleo) son: LinkedIn 3/2/1; Computrabajo 8/2/3; elempleo 5/2/2; Magneto 4/2/1; GetOnBoard 5/1/1; SENA y Torre, desactivadas, 3 y 5. La configuración MUST rechazarse si los requests reservados al núcleo superan el presupuesto. Entre requests consecutivos a la misma fuente MUST esperar una pausa aleatoria dentro del rango configurado (4–10 s por defecto). Cada request MUST tener un timeout (20 s por defecto) y presentarse con un User-Agent de navegador y `Accept-Language: es-CO`.

#### Scenario: Presupuesto agotado
- **WHEN** una fuente alcanza su presupuesto de requests en la corrida
- **THEN** el sistema no hace más requests a esa fuente hasta la siguiente corrida

#### Scenario: Reserva imposible
- **WHEN** una fuente configura 3 palabras clave del núcleo con 3 páginas y presupuesto 8
- **THEN** la configuración se rechaza al cargarla, porque reserva 9 requests

#### Scenario: Timeout
- **WHEN** un request supera el timeout configurado
- **THEN** se aborta, se registra como timeout y la corrida continúa
