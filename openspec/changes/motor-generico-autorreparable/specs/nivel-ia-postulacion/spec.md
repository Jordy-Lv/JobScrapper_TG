## Purpose

Deja que cada usuario elija cuánta IA usa su postulación (Ahorro, Normal o Máximo), para cuidar su cuota o
pedir la mejor calidad, y garantiza que el bot siga funcionando sin IA.

## ADDED Requirements

### Requirement: Nivel de uso de IA por usuario
Cada usuario SHALL tener un nivel de uso de IA en sus postulaciones: **Ahorro**, **Normal** (por defecto) o
**Máximo**, editable por Telegram (`/ia nivel`) y en el popup de la extensión. El nivel decide:

| | Ahorro | Normal | Máximo |
|---|---|---|---|
| Redactar preguntas abiertas | Sí, una llamada por formulario | Sí | Sí, con lo de Máximo |
| Clasificar con IA preguntas nuevas | No: van a la card | Sí | Sí |
| Árbitro de página por postulación | 0 | hasta 3 | hasta 6 |
| Reparaciones antes del envío | 0 | 1 | 2 |
| Modelo | ligero | el configurado | completo, con más razonamiento |
| Funciones de calidad de Máximo | No | No | Sí |

El nivel MUST NOT cambiar las reglas de seguridad: en ningún nivel se envía sin señal explícita de éxito, se
reintenta después del envío, se crean cuentas, se escriben credenciales, se resuelven captchas o se inventan
datos. Los topes de `asistente.motor_generico` son el máximo absoluto de cualquier nivel.

#### Scenario: Usuario en Ahorro con una página ambigua
- **WHEN** un usuario en Ahorro postula y las reglas no deciden qué botón pulsar
- **THEN** no se consulta al árbitro y la postulación va al respaldo con el motivo `nivel_ahorro`, sin enviar nada

#### Scenario: Cambiar el nivel
- **WHEN** el usuario escribe `/ia nivel` y elige «Máximo»
- **THEN** las postulaciones siguientes usan el nivel Máximo y las que ya están en curso terminan con el nivel con que empezaron

### Requirement: Calidad del nivel Máximo
En el nivel Máximo, la postulación SHALL usar, además de lo de Normal:
1. **Modelo completo** con el razonamiento más alto que permita el proveedor en las tareas de la postulación.
2. **Respuestas alineadas a la vacante**: el redactor recibe los requisitos extraídos de la vacante y destaca
   los que el perfil cumple, sin afirmar los que no cumple.
3. **El estilo del usuario**: el redactor recibe hasta 5 respuestas que el usuario escribió o corrigió, como
   ejemplos de tono y estilo, nunca como datos nuevos.
4. **Doble redacción** de las respuestas largas (motivación, experiencia o más de 300 caracteres pedidos): dos
   versiones, y el revisor final elige la mejor.
5. **Revisor final** (tarea de IA `revisar_respuestas`): antes de enviar, compara cada respuesta redactada con
   su pregunta, su idioma, su límite de caracteres y los datos del usuario. Puede corregir el texto o mandar
   la pregunta a la card si detecta un dato dudoso. MUST NOT tocar consentimientos, datos simples ni opciones
   resueltas por datos del usuario, y MUST NOT agregar datos que no estén en el perfil, el cuestionario o lo
   aprendido.
6. **Carta opcional**: si un formulario acepta una carta de presentación opcional en archivo, se adjunta un PDF
   con la carta redactada para esa vacante. En Ahorro y Normal se deja vacía.

#### Scenario: Revisor que corrige el idioma
- **WHEN** en Máximo una respuesta quedó en español y el formulario está en inglés
- **THEN** el revisor la corrige al inglés antes de enviar y la card del resumen lo indica como revisada

#### Scenario: Revisor que detecta un dato dudoso
- **WHEN** el revisor ve que una respuesta afirma tres años de experiencia y el perfil dice uno
- **THEN** la respuesta no se envía así: se corrige con el dato del perfil o, si no se puede saber, se pregunta en la card

#### Scenario: Requisito que el perfil no cumple
- **WHEN** la vacante pide Kubernetes y el perfil no lo menciona
- **THEN** la respuesta de motivación no dice que el usuario sabe Kubernetes

### Requirement: Bajada de nivel por cuota
Si la cuota de IA del usuario se agota durante el día, sus postulaciones SHALL bajar de nivel en vez de fallar:
de Máximo a Normal y de Normal a Ahorro. La card MUST decir que esa postulación usó un nivel menor y por qué.
Al día siguiente vuelve el nivel elegido. En Ahorro sin cuota, se aplica el requisito de funcionamiento sin IA.

#### Scenario: Cuota agotada en Máximo
- **WHEN** a un usuario en Máximo se le agota la cuota del modelo completo
- **THEN** la postulación sigue en Normal con el modelo de respaldo y la card dice «Usé el nivel Normal porque se agotó tu cuota de IA de hoy»

### Requirement: Costo visible del nivel
`/ia nivel` y el popup SHALL mostrar, por nivel, cuántas llamadas de IA usa más o menos una postulación, y
cuántas llamadas y tokens lleva el usuario hoy. Las cifras salen del registro de uso de IA del usuario y de
las estimaciones de la configuración.

#### Scenario: Ver el costo
- **WHEN** el usuario abre `/ia nivel`
- **THEN** ve los tres niveles con su consumo aproximado por postulación, su uso de hoy y el nivel actual marcado

### Requirement: Funcionamiento sin IA
Sin clave de IA, sin cuota o con un proveedor caído, el bot SHALL seguir postulando con reglas, recetas,
parches, datos del usuario y esquemas anticipados. Sin IA: las preguntas abiertas y las preguntas nuevas MUST
pedirse en la card y enviarse tal cual las escriba el usuario; una página que las reglas no entienden y un paso
que falla antes del envío MUST llevar la postulación al respaldo con el motivo `sin_ia`, sin enviar nada. La
card SHALL ofrecer configurar una clave de IA cuando el motivo sea `sin_ia`.

#### Scenario: Formulario conocido sin IA
- **WHEN** un usuario sin clave de IA postula en un sitio con receta y el formulario solo pide datos que el usuario ya dio
- **THEN** la postulación termina `enviada` sin ninguna llamada a la IA

#### Scenario: Pregunta abierta sin IA
- **WHEN** un usuario sin clave de IA postula y el formulario pregunta «¿Por qué te interesa esta vacante?»
- **THEN** la card le pide escribir la respuesta y, al responder, la postulación sigue y la envía tal cual

#### Scenario: Paso que falla sin IA
- **WHEN** un paso falla antes del envío y el usuario no tiene IA ni está activa la clave del dueño
- **THEN** la postulación va al respaldo con el motivo `sin_ia` y la card ofrece configurar una clave
