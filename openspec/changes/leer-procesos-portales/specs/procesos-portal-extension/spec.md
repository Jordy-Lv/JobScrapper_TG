## Purpose

Leer, desde el navegador del usuario y con su sesión, las páginas en que cada portal muestra el estado de sus postulaciones y los mensajes de las empresas, y convertir esos cambios en eventos del seguimiento sin hacer nada más en el portal.

## ADDED Requirements

### Requirement: Lectura programada por el servidor
El servidor SHALL indicar a la extensión, en la respuesta del latido, qué portales leer, y solo cuando se cumple todo esto:
- el portal está declarado con una sección `procesos` verificada;
- la cuenta del usuario está confirmada y su sesión, lista;
- no hay una postulación en curso en ese navegador;
- la hora local está dentro de la ventana configurada (8:00 a 20:00 por defecto);
- la última lectura de ese portal para ese usuario es de hace `cada_h` horas o más (6 por defecto).

La extensión MUST NOT leer por su cuenta sin esa indicación.

#### Scenario: Lectura debida
- **WHEN** pasaron 7 horas desde la última lectura de Computrabajo, son las 10:00 y la sesión está lista
- **THEN** la respuesta del latido pide leer `computrabajo`

#### Scenario: Fuera de la ventana
- **WHEN** son las 22:00
- **THEN** la respuesta del latido no pide leer ningún portal

#### Scenario: Postulación en curso
- **WHEN** el navegador está ejecutando una postulación
- **THEN** no se pide ninguna lectura hasta que termine

### Requirement: Lectura sin acciones en el portal
La extensión SHALL abrir la página de procesos en una pestaña en segundo plano, leer como máximo `max_filas` filas (30 por defecto) con los selectores del portal, seguir solo el paso de página declarado y cerrar la pestaña. MUST NOT pulsar botones, enviar formularios, marcar mensajes como leídos ni navegar fuera de las páginas permitidas del portal. Si la página redirige al inicio de sesión o fuera del portal, MUST informar `sin_sesion` y no enviar filas.

#### Scenario: Página leída
- **WHEN** la página de procesos muestra 12 postulaciones
- **THEN** la extensión envía 12 filas con cargo, empresa, fecha, estado y enlace, y cierra la pestaña

#### Scenario: Sesión vencida
- **WHEN** la página redirige al inicio de sesión
- **THEN** la extensión informa `sin_sesion`, no envía filas y el servidor no registra eventos

### Requirement: Eventos a partir de la foto
El servidor SHALL comparar cada foto con la anterior del mismo usuario y portal. Una fila asociada a un proceso cuyo estado del portal cambió a un texto mapeado MUST generar un evento de origen `portal` y seguridad `alta`, con la clave `{id_oferta}:{estado}` para no duplicarlo. Un texto de estado sin mapear MUST guardarse para revisión y no generar eventos. Que una fila desaparezca de la foto MUST NOT cerrar el proceso.

#### Scenario: CV visto
- **WHEN** una fila pasa de «Postulado» a «CV visto» y el mapa de Computrabajo traduce «CV visto» a `cv_visto`
- **THEN** el proceso recibe un evento `cv_visto` de origen portal y su card se actualiza sin sonido

#### Scenario: Descartado en el portal
- **WHEN** el estado del portal de una fila pasa a un texto mapeado como `descartado`
- **THEN** el proceso recibe el evento `descartado` y se cierra

#### Scenario: Estado desconocido
- **WHEN** una fila trae un texto de estado que no está en el mapa
- **THEN** no se crea ningún evento y el texto queda registrado para el dueño

#### Scenario: Primera foto
- **WHEN** es la primera lectura del portal para ese usuario
- **THEN** los estados leídos se registran como eventos solo si son de mayor avance que el estado actual de cada proceso, sin avisos con sonido

### Requirement: Asociación de filas con procesos
El servidor SHALL asociar cada fila por el id de la oferta, que se saca del enlace con la expresión del portal. Si no hay id, la asociación usa la empresa y el cargo normalizados de los procesos de ese portal, con seguridad `media`. Una fila sin proceso asociado MUST ofrecerse al usuario una sola vez como proceso externo («Vi que te postulaste a X en Computrabajo. ¿Lo sigo?»), y si el usuario acepta se crea el proceso con su estado.

#### Scenario: Postulación hecha fuera de la app
- **WHEN** la foto trae una oferta sin postulación ni proceso del usuario
- **THEN** el usuario recibe una pregunta con «Seguir» y «No», y con «Seguir» queda un proceso externo

### Requirement: Mensajes de empresas en el portal
Si el portal declara un indicador de mensajes, la extensión SHALL leer cuántos hay sin leer y, si se declara, el remitente y el asunto de los nuevos, sin abrirlos ni marcarlos como leídos. Un aumento MUST generar un aviso urgente con el portal, el remitente si se conoce y el enlace a la bandeja, asociado al proceso de esa empresa cuando se pueda.

#### Scenario: Mensaje nuevo
- **WHEN** el contador de mensajes de Computrabajo pasa de 0 a 1
- **THEN** el usuario recibe en el acto «Tienes un mensaje nuevo en Computrabajo», con el enlace a la bandeja

### Requirement: Selectores verificados por portal
La lectura SHALL funcionar solo para portales cuya sección `procesos` está marcada como verificada en su JSON, después de un reconocimiento con una cuenta real y fixtures del marcado. Un cambio del marcado que deje la lectura sin filas MUST registrarse como incidente para el dueño, sin borrar la foto anterior ni generar eventos.

#### Scenario: Marcado cambiado
- **WHEN** la página carga con sesión pero los selectores no encuentran ninguna fila y la foto anterior tenía filas
- **THEN** se registra un incidente para el dueño y no se generan eventos
