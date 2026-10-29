# extension-navegador Specification

## Purpose
La extensión de Chrome del asistente detecta en cada portal si la sesión del dueño está iniciada y con qué correo, y se lo informa al servidor para que la cuenta quede por confirmar. Cubre las señales de sesión, la lectura del correo de cada portal (Magneto, LinkedIn) y el reintento cuando un portal queda sin correo.

## Requirements

### Requirement: Marca de sesión iniciada como señal principal
Cuando los selectores de un portal declaran una marca de sesión iniciada, la extensión SHALL considerar que hay sesión si encuentra esa marca, aunque la página muestre también un enlace de ingreso. La marca cuenta aunque esté oculta, por ejemplo dentro de un menú.

La extensión MUST esperar la marca durante el tiempo que declare el portal antes de concluir que no hay sesión, porque hay portales que la muestran solo después de terminar de cargarse.

Si el portal declara la marca como obligatoria:
- la extensión MUST NOT dar por iniciada la sesión mientras la marca falte, aunque no haya enlace de ingreso. Esto aplica también al vigilar el inicio de sesión desde el popup y antes de cada paso de una postulación;
- un enlace de ingreso visible o una página de ingreso de la lista del portal MUST seguir indicando sin sesión, como hasta ahora.

Los portales que no declaran marca obligatoria (Computrabajo) MUST conservar su comportamiento actual.

#### Scenario: Magneto con sesión y enlace de ingreso en el HTML inicial
- **WHEN** la página principal de Magneto se carga con el enlace «Iniciar sesión» y, segundos después, la reemplaza por el avatar del usuario
- **THEN** la extensión informa Magneto con sesión iniciada y busca el correo de la cuenta

#### Scenario: Magneto sin sesión
- **WHEN** la página de Magneto termina de cargarse sin el avatar del usuario dentro del tiempo de espera del portal
- **THEN** la extensión informa Magneto sin sesión

#### Scenario: Vigilancia del inicio de sesión
- **WHEN** el usuario toca «Iniciar sesión» en el popup para Magneto y la pestaña pasa por una página intermedia vacía antes de llegar al portal
- **THEN** la extensión no cierra la pestaña hasta ver el avatar del usuario

#### Scenario: Computrabajo sin cambios
- **WHEN** la extensión revisa Computrabajo con y sin sesión
- **THEN** el resultado es el mismo que antes de este cambio

### Requirement: Correo de la cuenta de Magneto
La extensión SHALL leer el correo de la cuenta de Magneto del menú de la cuenta, en la página de búsqueda de empleos del portal. Magneto solo genera ese menú, con el correo en un elemento oculto del selector de cuenta, al hacer clic en el avatar del usuario.

Para obtenerlo, la extensión:
- MAY hacer clic en el elemento que los selectores del portal declaran para abrir el menú de la cuenta, y en ningún otro;
- MUST NOT cambiar nada de la cuenta con ese clic, que solo despliega el menú;
- MUST NOT abrir ni modificar páginas de configuración de la cuenta.

#### Scenario: Correo encontrado al abrir el menú de la cuenta
- **WHEN** la extensión revisa Magneto con sesión iniciada
- **THEN** abre el menú del avatar en la página de búsqueda de empleos e informa el correo de la cuenta

#### Scenario: Correo ya visible
- **WHEN** el correo ya está en la página antes del clic
- **THEN** la extensión lo informa sin hacer clic

### Requirement: Correo de la cuenta de LinkedIn
La extensión SHALL leer el correo de la cuenta de LinkedIn de la ventana «Información de contacto» del propio perfil del usuario, sin depender de que LinkedIn pinte esa ventana ni de que salte de `/in/me/` al perfil en la pestaña de revisión, que está en segundo plano.

Para obtenerlo, la extensión:
- MUST pedir las páginas solo con `GET`, al mismo dominio del portal y con la sesión que ya tiene el navegador;
- MUST tomar el usuario del perfil de la URL de la pestaña o, si aún no cambió, de la página `/in/me/` del propio usuario;
- MUST aceptar el correo solo si la página de contacto del propio perfil trae exactamente un correo válido en un enlace `mailto:`; con ninguno o con varios, no informa correo;
- MUST NOT leer texto libre de la página, ni páginas de configuración de la cuenta;
- MUST seguir buscando el correo en la ventana pintada, como antes, si la lectura anterior no lo encuentra.

Cuando no encuentra el correo, la extensión SHALL informar en el latido el motivo: `sin_perfil` (no se supo el usuario), `sin_correo` (la página de contacto no trae un correo), `varios_correos` o `sin_sesion` (la petición terminó en la página de ingreso).

#### Scenario: LinkedIn no pinta la ventana ni salta al perfil
- **WHEN** la extensión revisa LinkedIn con sesión, `/in/me/` se queda en esa URL sin pintar nada y la página de contacto trae el correo solo en los datos de la página
- **THEN** la extensión informa el correo de la cuenta y la página de contacto donde lo encontró

#### Scenario: La página de contacto no trae correo
- **WHEN** la página de contacto del perfil no trae ningún `mailto:`
- **THEN** la extensión informa LinkedIn con sesión, sin correo y con el motivo `sin_correo`

#### Scenario: Correo ya visible en la ventana pintada
- **WHEN** LinkedIn sí salta al perfil y pinta la ventana de contacto
- **THEN** la extensión informa el mismo correo

### Requirement: Reintento pronto de un portal sin correo
Un portal con sesión iniciada cuyo correo no se encontró SHALL volver a revisarse en el siguiente latido pasados 10 minutos, en vez de esperar el plazo normal de revisión de 6 horas. Un portal con correo o sin sesión MUST conservar el plazo actual.

#### Scenario: LinkedIn quedó sin correo
- **WHEN** la última revisión de LinkedIn terminó con sesión y sin correo hace más de 10 minutos
- **THEN** el siguiente latido vuelve a revisar LinkedIn
