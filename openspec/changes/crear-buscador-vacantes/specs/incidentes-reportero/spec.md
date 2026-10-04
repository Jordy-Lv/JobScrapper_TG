# Spec Delta

## Purpose

Detectar de forma determinista cuándo una fuente o el envío fallan, y avisar en el canal con un diagnóstico útil de la IA, sin ruido repetido y sin depender de que la IA esté disponible.

## ADDED Requirements

### Requirement: Detección determinista de incidentes
El sistema SHALL abrir un incidente, identificado por fuente y tipo, cuando se cumple alguna de estas reglas:
- `bloqueo`: HTTP 429, 999 o 403 en 2 corridas seguidas de la misma fuente, o cooldown escalado a 6 h o más.
- `captcha`: respuesta 200 con marcadores de desafío anti-bot y sin la estructura de vacantes.
- `cambio_html`: respuesta 200 con cuerpo normal en la que el parser extrae 0 elementos o falla.
- `sin_resultados`: 0 vacantes crudas en 24 h en una fuente que tuvo resultados en los 7 días anteriores.
- `caida_volumen`: volumen de 24 h por debajo del 30 % del promedio diario de los 7 días anteriores.
- `error_servidor`: HTTP 5xx o timeouts en 3 corridas seguidas.
- `fallo_envio`: Telegram rechaza un mensaje.

La IA MUST NOT participar en la detección.

#### Scenario: Cambio de HTML
- **WHEN** Computrabajo responde 200 sin marcadores de desafío y el parser extrae 0 vacantes
- **THEN** se abre un incidente `computrabajo:cambio_html`

#### Scenario: Error de servidor
- **WHEN** elempleo devuelve 503 en 3 corridas seguidas
- **THEN** se abre un incidente `elempleo:error_servidor`

### Requirement: Distinción entre falla de red local y falla de fuente
Si en una corrida todas las fuentes consultadas fallan por error de conexión o DNS, el sistema SHALL tratarlo como un incidente único `red:sin_conexion`. En ese caso MUST NOT abrir incidentes por fuente, ni aplicar cooldowns, ni contar esa corrida para las reglas de corridas seguidas.

#### Scenario: PC sin internet
- **WHEN** el router se cae y todas las fuentes fallan con error de DNS
- **THEN** se abre solo `red:sin_conexion`, ninguna fuente entra en cooldown y no hay incidentes por fuente

### Requirement: Control de ruido
Mientras un incidente siga abierto, el sistema MUST NOT volver a pedir diagnóstico a la IA para él, y como máximo SHALL enviar un recordatorio en texto plano cada 24 h. Los incidentes nuevos que se abren en la misma corrida MUST agruparse en un único mensaje con una única llamada a la IA.

#### Scenario: Incidente persistente
- **WHEN** un incidente `linkedin:bloqueo` sigue abierto en las corridas siguientes
- **THEN** no se envían mensajes nuevos hasta 24 h después, y entonces se envía un recordatorio plano sin IA

#### Scenario: Varios incidentes a la vez
- **WHEN** en la misma corrida se abren `linkedin:bloqueo` y `magneto:cambio_html`
- **THEN** se hace una sola llamada a la IA y se envía un solo mensaje que cubre ambos

### Requirement: Aviso de recuperación
Cuando una fuente con incidente abierto vuelve a funcionar, el sistema SHALL cerrar el incidente y enviar un aviso corto sin IA con la duración, por ejemplo "✅ LinkedIn se recuperó tras 5 h".

#### Scenario: Fuente recuperada
- **WHEN** LinkedIn vuelve a responder con éxito tras 5 h de bloqueo
- **THEN** se cierra el incidente y se envía "✅ LinkedIn se recuperó tras 5 h"

### Requirement: Diagnóstico IA con evidencia sanitizada
Por cada grupo de incidentes nuevos, el sistema SHALL enviar a la IA esta evidencia: fuente, tipo, hora de apertura, intentos recientes (hora, URL, status, duración, items), cabeceras de respuesta permitidas (`retry-after`, `server`, `content-type`, `cf-ray`, `x-ratelimit-*`), una muestra del cuerpo de hasta 3000 caracteres sin scripts ni estilos, los selectores del parser, el volumen de 7 días, el cooldown actual, el presupuesto de requests y las fuentes que siguen funcionando. La evidencia MUST NOT incluir tokens, claves de API, cookies, variables de entorno ni ids de chat. La IA MUST responder con severidad, causa probable, evidencia clave, acción recomendada, si requiere intervención y una sugerencia técnica opcional. La IA MUST NOT inventar datos ni recomendar evadir captchas, rotar proxies o violar los términos del sitio.

#### Scenario: Payload sin secretos
- **WHEN** se arma la evidencia de un incidente
- **THEN** no contiene el token del bot, la clave de DeepSeek, cookies, ids de chat ni cabeceras fuera de la lista permitida

#### Scenario: Mensaje de diagnóstico
- **WHEN** la IA responde con un diagnóstico válido para `linkedin:bloqueo`
- **THEN** llega al canal un mensaje con título, severidad, hora de apertura, cooldown, causa probable, recomendación, evidencia e indicación de si requiere intervención

#### Scenario: Sugerencia de selectores
- **WHEN** el diagnóstico de un `cambio_html` incluye selectores sugeridos
- **THEN** se muestran en un bloque de código para que el administrador los revise, y no se aplican automáticamente

### Requirement: La IA solo diagnostica
El Reportero IA MUST NOT modificar código, configuración, estado ni cooldowns, ni hacer requests a las fuentes. Su único efecto es el texto que se publica en el canal.

#### Scenario: Diagnóstico recomienda cambio
- **WHEN** la IA recomienda bajar el presupuesto de LinkedIn
- **THEN** la configuración no cambia hasta que el administrador la edite

### Requirement: Alerta plana de respaldo
El sistema SHALL enviar una alerta en texto plano, sin IA, con fuente, tipo, el dato principal de la evidencia y el motivo por el que el diagnóstico IA no está disponible, cuando se supera el máximo diario de llamadas del Reportero, el saldo de DeepSeek está por debajo del mínimo configurado, la API falla (402, 5xx, timeout) o la respuesta no es válida o le faltan campos.

#### Scenario: Saldo bajo
- **WHEN** el saldo de DeepSeek está por debajo del mínimo configurado (1.0 USD por defecto)
- **THEN** se envía la alerta plana con "Diagnóstico IA no disponible (motivo: saldo bajo)" y, una vez al día, el aviso "💳 Saldo DeepSeek bajo: $X"

#### Scenario: Respuesta inválida
- **WHEN** la IA responde algo que no es el JSON esperado
- **THEN** se envía la alerta plana con el motivo "respuesta inválida"

### Requirement: Presupuesto de IA y medición de consumo
El sistema SHALL limitar las llamadas del Reportero al máximo diario configurado (8 por defecto), consultar el saldo de DeepSeek antes de cada llamada y registrar los tokens de entrada y salida de cada llamada de IA (reportero, clasificador y resumen).

#### Scenario: Tope diario alcanzado
- **WHEN** ya se hicieron 8 llamadas del Reportero hoy y se abre un incidente nuevo
- **THEN** se envía la alerta plana con el motivo "tope diario alcanzado"

### Requirement: Aislamiento del Reportero
El Reportero SHALL ejecutarse después del envío de vacantes y de forma aislada. Ningún error del Reportero o de la IA MUST impedir que las vacantes de la corrida se envíen o que el estado se guarde.

#### Scenario: Excepción en el Reportero
- **WHEN** el Reportero lanza una excepción inesperada
- **THEN** las vacantes de la corrida ya están enviadas y guardadas, y el error queda en el log

### Requirement: Simulación de incidentes
El sistema SHALL ofrecer un modo que genera evidencia de ejemplo para cualquier `fuente:tipo`, ejecuta el flujo completo del Reportero (incluido el respaldo) y envía el resultado al chat de prueba sin modificar el estado real.

#### Scenario: Simular bloqueo
- **WHEN** se ejecuta la simulación de `linkedin:bloqueo`
- **THEN** llega al chat de prueba el mensaje de diagnóstico y no se crea ningún incidente real
