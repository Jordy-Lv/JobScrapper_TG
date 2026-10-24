# Spec Delta

## Purpose

Permite a los usuarios del bot asistente consultar las vacantes ya publicadas en el canal, filtrándolas con botones o con una frase propia, y postularse desde los resultados.

## ADDED Requirements

### Requirement: Punto de entrada de las consultas
El bot asistente MUST ofrecer el comando `/buscar` y un botón «🔎 Buscar vacantes» en la ayuda. Ambos MUST estar disponibles solo para usuarios activos con el alta terminada. El comando MUST aparecer en el texto de ayuda.

#### Scenario: Usuario activo
- **WHEN** un usuario activo escribe `/buscar`
- **THEN** el bot muestra la tarjeta de filtros

#### Scenario: Usuario en alta
- **WHEN** un usuario que no terminó el alta escribe `/buscar`
- **THEN** el bot retoma el alta donde iba, como con los demás comandos

### Requirement: Tarjeta de filtros con botones
La tarjeta de filtros MUST ser un único mensaje editable con estos filtros: nivel, área de TI, modalidad (remota, híbrida o presencial en la ciudad base), antigüedad (hoy, 3 días o 7 días), fuente y «solo destacadas». Cada toque MUST editar la misma tarjeta para mostrar los filtros elegidos. La tarjeta MUST ofrecer «Ver resultados» y «Limpiar filtros».

#### Scenario: Elegir filtros
- **WHEN** el usuario toca «Remota» y luego «Últimos 3 días»
- **THEN** la misma tarjeta muestra los dos filtros marcados y un contador de vacantes que los cumplen

#### Scenario: Limpiar
- **WHEN** el usuario toca «Limpiar filtros»
- **THEN** la tarjeta vuelve a no tener filtros y el contador muestra todas las vacantes disponibles

### Requirement: Nivel junior pausado en las consultas
Mientras el nivel junior esté pausado, el filtro de nivel MUST mostrar «Junior» como pausado y MUST NOT permitir elegirlo. Al tocarlo, el bot MUST explicar que el grupo publica por ahora solo prácticas y aprendizaje. Con el nivel junior activo, el filtro MUST funcionar como los demás.

#### Scenario: Junior pausado
- **WHEN** el nivel junior está pausado y el usuario toca «🔒 Junior (pausado)»
- **THEN** el bot responde con un aviso breve y la tarjeta no cambia

### Requirement: Resultados paginados con postulación
«Ver resultados» MUST listar las vacantes del índice del asistente que cumplen todos los filtros, de la más reciente a la más antigua y con las destacadas primero. La lista MUST mostrar 6 por página en un mensaje editable, y cada resultado MUST poder elegirse para postularse con el mismo comportamiento del selector de vacantes.

#### Scenario: Consulta con resultados
- **WHEN** el usuario pide «Aprendizaje» y «Desarrollo» y hay 14 vacantes que cumplen
- **THEN** el bot muestra las 6 primeras con «Siguiente ➡️» y cada una se puede elegir para postularse

#### Scenario: Sin resultados
- **WHEN** ninguna vacante cumple los filtros
- **THEN** el bot lo dice y ofrece volver a los filtros, sin enviar una lista vacía

### Requirement: Alcance de los datos consultados
Las consultas MUST mostrar solo vacantes publicadas en el canal real y dentro de la retención del índice del asistente. MUST NOT mostrar vacantes rechazadas, de prueba ni descartadas por el nivel pausado.

#### Scenario: Vacante descartada
- **WHEN** una vacante junior se descartó por el nivel pausado
- **THEN** no aparece en ninguna consulta

### Requirement: Búsqueda con las palabras del usuario
`/buscar <frase>` MUST convertir la frase en los mismos filtros de la tarjeta, usando DeepSeek solo para traducir el texto a un objeto con campos y valores de una lista cerrada. El código MUST validar ese objeto, descartar lo que no esté en la lista y hacer la consulta. La IA MUST NOT recibir ni devolver vacantes.

#### Scenario: Frase con filtros
- **WHEN** el usuario escribe `/buscar prácticas remotas de Python de esta semana`
- **THEN** la tarjeta queda con «Remota» y «Últimos 7 días», el término «python» se busca en el título y se muestran los resultados

#### Scenario: Respuesta de la IA fuera de la lista
- **WHEN** DeepSeek devuelve un campo o un valor que no existe en la lista cerrada
- **THEN** ese campo se ignora y la consulta sigue con los campos válidos

### Requirement: Búsqueda por texto cuando la IA no está disponible
Si DeepSeek no responde, no hay saldo, o el usuario o el servidor alcanzaron su tope diario de consultas con IA, el bot MUST buscar las palabras de la frase en el título y la empresa, y MUST avisar que la búsqueda fue literal.

#### Scenario: Tope del usuario alcanzado
- **WHEN** el usuario ya hizo hoy su máximo de búsquedas con IA y escribe `/buscar soporte en Cartagena`
- **THEN** el bot busca «soporte» y «cartagena» en el título y la empresa, y avisa que fue una búsqueda literal

### Requirement: La frase del usuario no lleva datos personales a la IA
Antes de enviar la frase a DeepSeek, el bot MUST recortarla a 200 caracteres y quitar los correos, los teléfonos y los números de documento. El bot MUST NOT enviar a la IA ningún otro dato del usuario.

#### Scenario: Frase con teléfono
- **WHEN** el usuario escribe `/buscar soporte, mi número es 3001234567`
- **THEN** la IA recibe la frase sin el número
