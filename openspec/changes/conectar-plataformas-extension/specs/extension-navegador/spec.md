# Spec Delta

## ADDED Requirements

### Requirement: Plataformas adicionales guiadas por datos
La extensión SHALL soportar elempleo, GetOnBoard y el Servicio Público de Empleo con el mismo motor y los mismos pasos declarativos que Computrabajo y Magneto, tomando el flujo y los selectores de cada una del servidor. Solo MUST existir código propio de una plataforma (adaptador) cuando su comportamiento no se pueda expresar como datos. Habilitar una plataforma o corregir sus selectores MUST NOT exigir publicar una versión nueva de la extensión.

#### Scenario: Habilitación sin versión nueva
- **WHEN** el servidor carga los selectores de elempleo
- **THEN** la extensión ya instalada muestra elempleo en el popup en su siguiente sincronización, sin reinstalarse

#### Scenario: Adaptador solo si hace falta
- **WHEN** el flujo de una plataforma se puede describir con los pasos declarativos
- **THEN** no se agrega un archivo de adaptador para esa plataforma

### Requirement: Permiso opcional de cada plataforma nueva
El permiso de acceso a los dominios de una plataforma que no viene de fábrica SHALL pedirse al usuario desde el popup solo cuando el servidor habilita esa plataforma, con un texto que diga qué dominios se tocan y para qué. Sin permiso, la extensión MUST NOT leer ni operar en esos dominios y la plataforma se muestra como sin activar. Rechazar el permiso MUST NOT afectar a las demás plataformas.

#### Scenario: Usuario acepta el permiso
- **WHEN** el usuario toca «Activar» en GetOnBoard y acepta el permiso del navegador
- **THEN** la extensión empieza a detectar su sesión en GetOnBoard

#### Scenario: Usuario rechaza el permiso
- **WHEN** el usuario rechaza el permiso
- **THEN** GetOnBoard sigue sin activar, las vacantes de ese portal van al paquete de respaldo y Computrabajo y Magneto siguen funcionando

### Requirement: Sesión, cuenta y perfil en cada plataforma nueva
Para cada plataforma habilitada, la extensión SHALL detectar `sin_sesion`, `incompleto` y `listo`, leer el correo de la cuenta del portal para la cuenta asociada y respetar las páginas prohibidas (contraseña, correo de acceso, privacidad, notificaciones y borrado de cuenta), con las mismas reglas que Computrabajo y Magneto. Si el correo no se puede leer, la postulación MUST terminar en `formulario_desconocido` y no enviarse.

#### Scenario: Sin sesión en la plataforma nueva
- **WHEN** el usuario no tiene sesión iniciada en elempleo
- **THEN** su estado es `sin_sesion` y el bot le indica iniciar sesión o crear la cuenta con el enlace de registro del portal

#### Scenario: Sesión con otra cuenta
- **WHEN** la sesión de GetOnBoard tiene un correo distinto al asociado
- **THEN** no se postula y el bot avisa con el correo enmascarado y los botones habituales

### Requirement: Reconocimiento documentado por plataforma
Cada plataforma habilitada MUST tener un reconocimiento documentado en `docs/asistente/portales.md` y fixtures recortados sin datos personales. La documentación SHALL incluir: indicadores de sesión, de ya postulado y de vacante cerrada, tipos de campo y preguntas, captchas vistos, ubicación del correo de la cuenta, páginas del perfil, modo del CV y páginas prohibidas. Los fixtures MUST estar libres del nombre, correo, teléfono y documento del dueño.

#### Scenario: Fixtures limpios
- **WHEN** se agregan los fixtures de una plataforma
- **THEN** una búsqueda del nombre, correo, teléfono y documento del dueño en esa carpeta no devuelve coincidencias

#### Scenario: Plataforma sin reconocimiento
- **WHEN** una plataforma no tiene su documentación de reconocimiento
- **THEN** no se carga su archivo de selectores en el servidor
