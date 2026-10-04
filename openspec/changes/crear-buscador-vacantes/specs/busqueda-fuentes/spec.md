# Spec Delta

## Purpose

Obtener vacantes crudas de varias fuentes de empleo de forma sostenible, con el menor número de requests posible, recuperándose sola de bloqueos y sin evadir nunca protecciones anti-bot.

## ADDED Requirements

### Requirement: Fuentes independientes y activables
El sistema SHALL consultar cada fuente de empleo (LinkedIn, Computrabajo, elempleo, Magneto365, GetOnBoard, Torre y Agencia Pública de Empleo SENA) de forma independiente. Cada fuente MUST poder activarse o desactivarse desde la configuración sin cambiar código. El fallo de una fuente MUST NOT impedir que las demás se consulten en la misma corrida.

#### Scenario: Fuente desactivada en configuración
- **WHEN** una fuente está marcada como desactivada en la configuración
- **THEN** el sistema no le hace ningún request en la corrida

#### Scenario: Una fuente falla
- **WHEN** una fuente lanza error, timeout o respuesta inválida durante la corrida
- **THEN** el sistema registra el fallo y continúa con las demás fuentes

### Requirement: Fuentes que exigen login o captcha quedan fuera
El sistema MUST NOT implementar ni mantener activa una fuente que exija iniciar sesión, resolver captchas o evadir protecciones anti-bot para obtener vacantes. Tampoco MUST usar proxies, rotación de IP ni suplantación de huella TLS para esquivar bloqueos. Indeed y Glassdoor quedan excluidas.

#### Scenario: Fuente exige login
- **WHEN** durante la validación inicial una fuente solo devuelve vacantes tras autenticarse
- **THEN** la fuente queda desactivada y se informa al usuario

### Requirement: Rotación de palabras clave
El sistema SHALL mantener una lista configurable de palabras clave para el nivel práctica/aprendiz y junior/entrada en todos los roles de TI (desarrollo, infraestructura/DevOps/cloud, redes, bases de datos, soporte IT, datos y analítica, QA, ciberseguridad), dividida en dos grupos:
- **núcleo**: consultas amplias que se repiten en cada ciclo corto (por ejemplo "practicante sistemas", "aprendiz SENA", "junior TI");
- **cola larga**: consultas específicas por rol.

En cada corrida el sistema SHALL procesar el siguiente lote de cada fuente según su presupuesto, reservando una parte configurable para el grupo núcleo. Así las consultas amplias se repiten cada pocas horas aunque la lista total sea larga. La posición de rotación de cada grupo MUST persistir entre corridas y reinicios, y al llegar al final MUST volver al inicio.

#### Scenario: Núcleo frecuente
- **WHEN** LinkedIn tiene presupuesto 3 con 1 reservado para núcleo, 8 consultas núcleo y 90 de cola larga
- **THEN** cada consulta núcleo se repite cada 8 corridas (~4 h) y la cola larga se recorre completa en ~45 corridas

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
El sistema SHALL limitar los requests por fuente y por corrida al presupuesto configurado. Los valores iniciales son: LinkedIn 3; Computrabajo 4; elempleo, Magneto y SENA 3; GetOnBoard y Torre 5. Entre requests consecutivos a la misma fuente MUST esperar una pausa aleatoria dentro del rango configurado (4–10 s por defecto). Cada request MUST tener un timeout (20 s por defecto) y presentarse con un User-Agent de navegador y `Accept-Language: es-CO`.

#### Scenario: Presupuesto agotado
- **WHEN** una fuente alcanza su presupuesto de requests en la corrida
- **THEN** el sistema no hace más requests a esa fuente hasta la siguiente corrida

#### Scenario: Timeout
- **WHEN** un request supera el timeout configurado
- **THEN** se aborta, se registra como timeout y la corrida continúa

### Requirement: Cooldown escalonado ante bloqueos
Ante una respuesta HTTP 429, 999 o 403, el sistema SHALL poner la fuente en cooldown: 2 h la primera vez, 6 h la segunda consecutiva y 24 h a partir de la tercera. Mientras dure el cooldown, la fuente MUST NOT recibir requests. El primer request exitoso tras el cooldown MUST restablecer el escalón y el contador de fallos.

#### Scenario: Primer bloqueo
- **WHEN** LinkedIn responde 429 y no tenía fallos consecutivos
- **THEN** LinkedIn queda en cooldown 2 h y se omite en las corridas de ese periodo

#### Scenario: Bloqueo repetido
- **WHEN** al terminar el cooldown de 2 h LinkedIn vuelve a responder 429
- **THEN** el cooldown pasa a 6 h

#### Scenario: Recuperación
- **WHEN** tras un cooldown la fuente responde con éxito
- **THEN** el contador de fallos vuelve a cero y el próximo bloqueo empieza de nuevo en 2 h

### Requirement: Detección de desafíos anti-bot
El sistema SHALL considerar desafío anti-bot una respuesta HTTP 200 cuyo cuerpo contenga marcadores como `captcha`, `cf-chl`, `challenge`, `are you a robot` o `unusual traffic` y en la que el parser no encuentre la estructura de vacantes. La trata como bloqueo (aplica cooldown) y MUST NOT intentar resolverla. Una página que trae el listado normal no es un desafío aunque contenga un marcador, porque algunos sitios incluyen reCAPTCHA en formularios de todas sus páginas (como elempleo).

#### Scenario: Página de captcha con 200
- **WHEN** Computrabajo responde 200 con una página que contiene `cf-chl`
- **THEN** la respuesta no se parsea como vacantes, la fuente entra en cooldown y se registra un intento de tipo captcha

#### Scenario: Marcador en una página normal
- **WHEN** elempleo responde 200 con su listado de vacantes y un script de reCAPTCHA para un formulario
- **THEN** las vacantes se procesan normalmente y no se aplica cooldown

### Requirement: Registro de cada intento
El sistema SHALL registrar cada request con su fecha y hora, fuente, palabra clave, URL, código HTTP, duración, cantidad de elementos extraídos y error si lo hubo. Este historial alimenta la detección de incidentes y las métricas.

#### Scenario: Intento exitoso registrado
- **WHEN** GetOnBoard responde 200 y se extraen 12 vacantes
- **THEN** queda un registro con status 200, items 12 y la duración del request

### Requirement: Modelo común de vacante
Cada fuente SHALL entregar sus resultados normalizados con estos campos: fuente, id nativo, título, empresa, ubicación, modalidad (Presencial/Híbrido/Remoto), salario, fecha de publicación, URL, palabra clave que la encontró y, si la fuente la trae sin request extra, un fragmento de descripción. Los campos que la fuente no expone MUST quedar vacíos, nunca inventados. Las fechas relativas en español ("hace 3 horas", "ayer", "hace 2 días") MUST convertirse a fecha absoluta en hora de Colombia.

#### Scenario: Fecha relativa
- **WHEN** Computrabajo muestra "Hace 2 días" en una vacante consultada el 2026-10-03
- **THEN** la vacante normalizada tiene fecha de publicación 2026-10-01

#### Scenario: Sin salario
- **WHEN** la fuente no publica salario
- **THEN** el campo salario queda vacío
