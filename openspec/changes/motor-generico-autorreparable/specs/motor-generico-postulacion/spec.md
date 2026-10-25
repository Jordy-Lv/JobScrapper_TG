## Purpose

Permite que la extensión postule en formularios que nadie declaró a mano: lee cada pantalla, la llena, avanza y
reconoce el resultado. Sirve de respaldo de los flujos declarados de Computrabajo, Magneto y elempleo.

## ADDED Requirements

### Requirement: Lectura de la pantalla
En cada pantalla del flujo genérico, la extensión SHALL clasificar la página en una sola de estas clases:
`formulario` (hay campos visibles por llenar), `intermedia` (descripción de la vacante con un botón o enlace de
postular y sin campos), `exito` (señal explícita de postulación recibida), `error` (campos marcados como
inválidos o avisos de validación), `barrera` (ver el requisito de barreras) o `desconocida`. Si las reglas no
deciden la clase, MUST consultarse al árbitro según el requisito de árbitro de `autorreparacion-postulacion`.
Antes de leer, si un banner de cookies tapa la página, la extensión SHALL pulsar la opción que rechaza las
cookies no esenciales; si el banner solo ofrece aceptar y no tapa los campos, MUST dejarlo sin pulsar.

#### Scenario: Página de la vacante con botón de postular
- **WHEN** la pestaña muestra la descripción de la vacante con un botón «Apply» y ningún campo
- **THEN** la pantalla se clasifica `intermedia`, se pulsa el botón y ese clic no cuenta como envío

#### Scenario: Página de gracias
- **WHEN** tras enviar aparece «Thank you for applying» y el formulario ya no está
- **THEN** la pantalla se clasifica `exito`

#### Scenario: Banner de cookies con rechazo
- **WHEN** un banner con «Declinar» y «Aceptar cookies» tapa el formulario
- **THEN** se pulsa «Declinar» y después se lee el formulario

### Requirement: Esquema de los campos
En una pantalla `formulario`, la extensión SHALL extraer el esquema de los campos que el usuario puede ver y
llenar, incluidos los controles nativos y los controles ARIA (`combobox`, `listbox`, `radiogroup`, `radio`,
`checkbox`, `switch`, botones con `aria-haspopup=listbox`) y los de texto editable. Por cada campo MUST enviar
al servidor su texto (etiqueta, `aria-labelledby`, `aria-label`, etiqueta envolvente, leyenda o título del
bloque, en ese orden), su ayuda (`aria-describedby`), tipo, opciones, si es obligatorio (`required`,
`aria-required`, validación del portal o «*» en la etiqueta), nombre, `autocomplete`, máximo de caracteres,
tipos de archivo aceptados e idioma de la página. Si las opciones de una lista no están en la página hasta
abrirla, la extensión MUST abrirla, leer las opciones y cerrarla sin elegir nada. En las listas con búsqueda
(país, ciudad) MAY enviar solo la marca de búsqueda en lugar de las opciones. Si no hay `<form>`, el
contenedor SHALL deducirse de los campos visibles.

#### Scenario: Lista de react-select
- **WHEN** una pregunta Sí/No es un `input[role=combobox]` cuyas opciones aparecen solo al abrirla
- **THEN** el esquema incluye la pregunta con las opciones «Yes» y «No», y la lista queda cerrada y sin valor

#### Scenario: Formulario sin form
- **WHEN** la página no tiene `<form>` pero tiene campos con `label[for]` y un botón «Submit Application»
- **THEN** el esquema incluye esos campos y el botón queda como candidato a enviar

#### Scenario: Obligatorio por asterisco
- **WHEN** la etiqueta de un campo termina en «*» y el campo no tiene `required`
- **THEN** el campo se reporta como obligatorio

### Requirement: Campos que nunca se llenan
La extensión MUST NOT llenar ni reportar campos ocultos, fuera de pantalla, marcados como trampa (por
ejemplo `beecatcher` u `honeypot`), de contraseña o de respuesta de captcha. Cuando haya varios
`input[type=file]`, el CV SHALL adjuntarse en el que la etiqueta identifica como CV o currículo, nunca en
uno sin etiqueta destinado a rellenar el formulario automáticamente.

#### Scenario: Campo trampa
- **WHEN** la página tiene un campo de texto oculto llamado `beecatcher`
- **THEN** el campo no aparece en el esquema y queda vacío

#### Scenario: Dos campos de archivo
- **WHEN** hay un `input[type=file]` sin etiqueta («Autofill from resume») y otro con la etiqueta «Curriculum»
- **THEN** el CV se adjunta solo en «Curriculum»

### Requirement: Llenado comprobado
La extensión SHALL llenar cada respuesta y comprobar que el portal la aceptó: el valor escrito, la opción que
quedó mostrada en una lista, `checked` o `aria-checked` en radios y casillas, y el archivo en el campo de
archivo. En las listas con búsqueda MUST escribir el valor, esperar las opciones y elegir la que coincide.
Si un campo no quedó como se quería, MUST NOT avanzar ni enviar: la postulación pasa a la reparación según
`autorreparacion-postulacion` y, si no se repara, queda `formulario_desconocido` con la evidencia sin valores.

#### Scenario: Ciudad con búsqueda
- **WHEN** «Location (City)» es un combobox con búsqueda y la respuesta es «Medellín»
- **THEN** la extensión escribe «Medellín», elige la opción que empieza por «Medellín» y comprueba que quedó mostrada

#### Scenario: Opción que no se marcó
- **WHEN** tras pulsar la opción «No» el control sigue sin valor
- **THEN** no se pulsa ningún botón de avanzar ni de enviar

### Requirement: Botones de avanzar y de enviar
La extensión SHALL clasificar los botones del contenedor del formulario y los de justo debajo como `avanzar`
(siguiente, continuar, next, continue, próximo, revisar, review), `enviar` (enviar, submit, apply, postular,
aplicar, enviar solicitud, enviar candidatura) o `nunca` (cancelar, volver, guardar borrador, subir, adjuntar,
autocompletar, ubicarme, iniciar sesión, «apply with…», compartir). Un botón `nunca` MUST NOT pulsarse. Antes de
pulsar un botón `enviar`, la extensión MUST registrar el envío en el servidor, como en los flujos declarados,
y esperar a que el botón se habilite. Si la clase de los botones es ambigua, decide el árbitro.

#### Scenario: Formulario de varias pantallas
- **WHEN** la pantalla tiene «Back» y «Continue»
- **THEN** se pulsa «Continue» como `avanzar` y no se registra envío

#### Scenario: Botón de enviar
- **WHEN** la pantalla tiene «Submit application» de tipo submit
- **THEN** se registra el envío en el servidor y después se pulsa el botón

### Requirement: Resultado de cada pantalla
Tras pulsar `avanzar` o `enviar`, la extensión SHALL esperar hasta 25 s, también a través de una navegación,
y decidir: `exito` → la postulación queda `enviada` con el texto de la confirmación; campos nuevos → otra
vuelta del bucle; `error` → una sola vuelta de corrección (releer los campos marcados y resolverlos de
nuevo) y, si persiste, `formulario_desconocido`; `barrera` → respaldo; nada cambió tras `avanzar` → reparación;
nada claro tras `enviar` → `incierta`. Solo una señal explícita de éxito MUST dejar la postulación `enviada`.

#### Scenario: Error de validación corregible
- **WHEN** tras enviar, un campo de teléfono queda con `aria-invalid="true"` y el aviso «formato inválido»
- **THEN** se relee ese campo, se escribe en el formato pedido y se envía una sola vez más dentro de la misma pantalla, sin registrar un segundo envío nuevo

#### Scenario: Envío sin señal
- **WHEN** tras pulsar enviar no hay página de gracias, ni errores, ni campos nuevos
- **THEN** la postulación queda `incierta` y se le pide al usuario revisar en el portal o en su correo

### Requirement: Barreras
La extensión MUST detenerse sin enviar ante: un campo de contraseña visible; `autocomplete`
`current-password` o `new-password`; textos de crear cuenta o iniciar sesión para postular junto al formulario
(«crear cuenta», «create account», «inicia sesión para postular», «sign in to apply», «criar conta»); botones
de OAuth como único camino; un desafío de captcha **visible**; o un campo de código de verificación antes del
envío. La postulación SHALL ir al paquete de respaldo con el motivo de la barrera (`ats_con_cuenta`,
`captcha`, `oauth`, `codigo_verificacion`), salvo en las plataformas declaradas, donde el captcha sigue el
requisito actual de verificación por el usuario. Un script o un iframe de captcha **oculto** (captcha
invisible) MUST NOT contar como barrera.

#### Scenario: Paso de crear cuenta
- **WHEN** «Solicitar manualmente» lleva a un paso con correo, contraseña y verificar contraseña
- **THEN** no se escribe nada, la postulación va al respaldo con el motivo `ats_con_cuenta` y el dominio queda como barrera

#### Scenario: Captcha invisible
- **WHEN** la página carga reCAPTCHA Enterprise con sus iframes ocultos y no muestra ningún desafío
- **THEN** el bucle sigue normalmente

### Requirement: Topes del bucle
El bucle genérico SHALL detenerse en `formulario_desconocido` al pasar 12 pantallas (40 si cada pantalla tiene
una sola pregunta), al pasar 10 minutos desde que se abrió la vacante o al repetirse 3 veces la misma pantalla
sin cambios. MUST registrar en el historial de la postulación cada pantalla (clase, cantidad de campos, botón
pulsado), sin valores.

#### Scenario: Pantalla que se repite
- **WHEN** después de pulsar «Next» vuelve a aparecer la misma pantalla por tercera vez
- **THEN** la postulación queda `formulario_desconocido` con la evidencia y no se envía nada

### Requirement: Formularios dentro de iframes
Si el formulario está dentro de un iframe de un dominio permitido (por ejemplo, un formulario de ATS incrustado
en el sitio de la empresa), la extensión SHALL operar en ese marco como si fuera la página. Un iframe de un
dominio no permitido MUST tratarse como si no existiera.

#### Scenario: Formulario incrustado
- **WHEN** el sitio de la empresa muestra el formulario dentro de un iframe del ATS y la extensión tiene permiso en ese dominio
- **THEN** el esquema, el llenado y el envío ocurren dentro del iframe

### Requirement: Respaldo de los flujos declarados
En Computrabajo, Magneto y elempleo, los pasos declarados SHALL seguir siendo el camino principal. Si un paso
declarado falla **antes** de que se registre el envío (no apareció un elemento, un formulario no esperado, un
botón que no se encontró), la postulación MUST continuar con el bucle genérico desde la pantalla actual en vez
de terminar en `formulario_desconocido`. Si el paso falla **después** de registrar el envío, MUST aplicarse la
regla actual (`incierta` o `formulario_desconocido`, sin reintentar).

#### Scenario: Paso anterior al primer envío
- **WHEN** un paso declarado anterior al primero que registra envío (`envia: true`) no encuentra su elemento
- **THEN** el bucle genérico lee la pantalla actual, el servidor la resuelve y la postulación sigue hasta la confirmación

#### Scenario: Cuestionario adicional de elempleo
- **WHEN** tras guardar la postulación (el primer clic ya registró el envío) elempleo muestra «Cuestionario adicional» y el flujo declarado falla
- **THEN** el bucle genérico no se ejecuta y la postulación termina según la regla de después del envío

#### Scenario: Fallo después del envío
- **WHEN** el paso `confirmar` de Computrabajo no ve la confirmación después de pulsar enviar
- **THEN** la postulación queda `incierta` y el bucle genérico no se ejecuta
