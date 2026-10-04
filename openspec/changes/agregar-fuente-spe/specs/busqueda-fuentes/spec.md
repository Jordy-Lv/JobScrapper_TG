# Spec Delta

## MODIFIED Requirements

### Requirement: Fuentes independientes y activables
El sistema SHALL consultar cada fuente de empleo (LinkedIn, Computrabajo, elempleo, Magneto365, GetOnBoard, Torre, Agencia Pública de Empleo SENA y Servicio Público de Empleo) de forma independiente. Cada fuente MUST poder activarse o desactivarse desde la configuración sin cambiar código. El fallo de una fuente MUST NOT impedir que las demás se consulten en la misma corrida.

#### Scenario: Fuente desactivada en configuración
- **WHEN** una fuente está marcada como desactivada en la configuración
- **THEN** el sistema no le hace ningún request en la corrida

#### Scenario: Una fuente falla
- **WHEN** una fuente lanza error, timeout o respuesta inválida durante la corrida
- **THEN** el sistema registra el fallo y continúa con las demás fuentes

## ADDED Requirements

### Requirement: Fuente Servicio Público de Empleo
El sistema SHALL consultar el buscador público del Servicio Público de Empleo (buscadordeempleo.gov.co) pidiendo solo plazas de práctica, ordenadas de la más reciente a la más antigua, y leer en cada corrida tantas páginas como permita su presupuesto, sin usar las palabras clave de la rotación. Cada plaza MUST normalizarse al modelo común de vacante:
- el título se limpia del prefijo "PL-";
- la ubicación se arma con municipio y departamento ("Colombia" si la plaza es para todo el territorio);
- la modalidad es Remoto solo si la plaza indica teletrabajo, y si no queda vacía;
- el salario es el rango publicado, salvo "A Convenir";
- la empresa queda vacía, porque el SPE solo expone el prestador intermediario, no el empleador.

Cuando el enlace de detalle de la plaza pertenece a un portal que el sistema ya consulta (elempleo o Magneto), la vacante MUST identificarse con la clave de ese portal (`elempleo:<id>` o `magneto:<id>`) y su enlace original, para que la deduplicación la reconozca. Las plazas sin enlace de detalle público (sin enlace, o cuyo único enlace exige iniciar sesión, como las bolsas en Symplicity o Coally) o con fecha de vencimiento pasada MUST descartarse. La conexión MUST verificar el certificado TLS; si el servidor no envía su certificado intermedio, el sistema MUST usar el intermedio público incluido en el proyecto y MUST NOT desactivar la verificación.

#### Scenario: Solo plazas de práctica
- **WHEN** la fuente consulta el SPE en una corrida con presupuesto 2
- **THEN** pide las páginas 1 y 2 de las plazas marcadas como práctica, más recientes primero

#### Scenario: Copia de elempleo
- **WHEN** una plaza del SPE con código 1886772064 tiene como enlace de detalle una oferta de elempleo
- **THEN** la vacante tiene la clave `elempleo:1886772064` y el enlace de elempleo, y no se reenvía si esa clave ya fue enviada

#### Scenario: Plaza de una bolsa universitaria
- **WHEN** una plaza tiene como enlace de detalle la bolsa de empleo de una universidad
- **THEN** la vacante tiene la clave `spe:<código>`, el enlace de la bolsa universitaria y la empresa vacía

#### Scenario: Plaza vencida o sin enlace
- **WHEN** una plaza tiene fecha de vencimiento anterior a hoy o no trae enlace de detalle
- **THEN** la plaza se descarta sin llegar al filtrado

#### Scenario: Certificado intermedio ausente
- **WHEN** el servidor del SPE presenta solo su certificado final, sin el intermedio
- **THEN** la conexión se verifica con el intermedio incluido en el proyecto y la consulta se completa sin desactivar la verificación TLS

#### Scenario: Enlace que exige iniciar sesión
- **WHEN** el único enlace de detalle de una plaza lleva a una página de inicio de sesión (por ejemplo `coallytalent.com/.../auth/login` o un portal `*.symplicity.com`)
- **THEN** la plaza se descarta, porque el lector del canal no podría ver la oferta
