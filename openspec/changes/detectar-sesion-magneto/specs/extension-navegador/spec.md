## ADDED Requirements

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
La extensión SHALL leer el correo de la cuenta de Magneto de la cabecera del portal con sesión iniciada, donde está en un elemento oculto del selector de cuenta. MUST NOT abrir ni modificar páginas de configuración de la cuenta para obtenerlo.

#### Scenario: Correo encontrado en la cabecera
- **WHEN** la extensión revisa Magneto con sesión iniciada
- **THEN** informa el correo de la cuenta sin salir de la página principal del portal
