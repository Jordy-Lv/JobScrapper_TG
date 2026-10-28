# Spec Delta

## Purpose

Mantener el buscador corriendo cada 30 minutos, 24/7, en un PC de escritorio, y que se note de inmediato si deja de hacerlo.

## ADDED Requirements

### Requirement: Ejecución programada cada 30 minutos
El sistema SHALL ejecutar una corrida de búsqueda cada 30 minutos, todos los días, sin que haya una sesión de usuario iniciada. Cada corrida MAY empezar con un retraso aleatorio de hasta 2 minutos para no tener un patrón exacto de horario.

#### Scenario: Funcionamiento sin sesión
- **WHEN** el PC arranca y nadie inicia sesión
- **THEN** las corridas se ejecutan igual cada 30 minutos

### Requirement: Recuperación tras apagado o suspensión
Si el PC estuvo apagado o suspendido durante uno o más horarios de corrida, el sistema SHALL ejecutar una corrida al volver a estar activo, en lugar de esperar al siguiente horario. MUST ejecutar solo una corrida de recuperación, no una por cada horario perdido.

#### Scenario: PC reiniciado
- **WHEN** el PC estuvo apagado de 10:00 a 11:40
- **THEN** al arrancar se ejecuta una sola corrida de inmediato y luego se retoma el ritmo de 30 minutos

### Requirement: Exclusión mutua
Nunca SHALL haber dos corridas al mismo tiempo, tampoco cuando alguien ejecuta el buscador a mano mientras corre la programada. Una corrida que supere el tiempo máximo configurado (25 minutos por defecto) MUST terminarse.

#### Scenario: Ejecución manual concurrente
- **WHEN** se lanza una corrida manual mientras otra está en curso
- **THEN** la segunda termina de inmediato sin hacer requests e informa que hay una corrida activa

#### Scenario: Corrida colgada
- **WHEN** una corrida lleva más de 25 minutos
- **THEN** se termina y la siguiente corrida programada puede ejecutarse

### Requirement: Heartbeat externo
Al terminar cada corrida, el sistema SHALL notificar a un servicio externo de monitoreo (healthchecks.io), que avisa al administrador si no llega ninguna notificación en el periodo de gracia configurado. Una corrida que termina con error interno MUST reportarse como fallo a ese servicio. Si el servicio de monitoreo no responde, la corrida MUST NOT fallar.

#### Scenario: Script detenido
- **WHEN** las corridas dejan de ejecutarse durante más del periodo de gracia
- **THEN** healthchecks.io avisa al administrador

#### Scenario: Monitoreo caído
- **WHEN** healthchecks.io no responde al final de una corrida
- **THEN** la corrida termina normalmente y el fallo del ping queda en el log

### Requirement: Logs de operación
El sistema SHALL escribir un log por día, guardando los últimos 14 días. Por cada corrida MUST registrar los requests por fuente con su código HTTP, las vacantes crudas, los descartes por regla, las duplicadas, las dudosas y su resultado, las enviadas, las llamadas a la IA y la duración total. Los logs MUST NOT contener tokens ni claves de API.

#### Scenario: Retención
- **WHEN** existe un log de hace 15 días
- **THEN** se elimina

### Requirement: Configuración y secretos validados
El sistema SHALL leer la configuración funcional (fuentes, palabras clave, filtros, presupuestos, banner, opciones de IA y resumen) de un archivo de configuración, y los secretos (token del bot, clave de DeepSeek, URL de heartbeat, ids de canal y de chat de prueba) de un archivo de entorno con permisos solo para el propietario. Si la configuración es inválida o falta un secreto obligatorio, MUST fallar al arrancar con un mensaje claro y sin hacer requests.

#### Scenario: Configuración inválida
- **WHEN** el presupuesto de una fuente en la configuración es un texto en lugar de un número
- **THEN** el programa termina al arrancar indicando el campo inválido

### Requirement: Modos de ejecución manual
El sistema SHALL ofrecer estos modos por línea de comandos: `--dry-run` (imprime las fichas en consola sin enviar ni marcar nada como enviado), `--fuente <nombre>` (consulta solo esa fuente), `--seed`, `--chat-prueba` y `--simular-incidente <fuente:tipo>`, además de un subcomando para generar el resumen diario.

#### Scenario: Dry-run de una fuente
- **WHEN** se ejecuta con `--dry-run --fuente getonboard`
- **THEN** se consulta solo GetOnBoard, se imprimen las vacantes crudas, filtradas y los errores, y no se envía nada a Telegram

### Requirement: Retiro controlado de Hermes
Una vez que el usuario apruebe el funcionamiento en el chat de prueba, el cronjob de Hermes `d6381ce58395` y su pre-run `send_encabezado.py` SHALL pausarse, nunca borrarse, y solo con confirmación explícita del usuario.

#### Scenario: Cambio de sistema
- **WHEN** el usuario aprueba el paso a producción
- **THEN** se activa el buscador contra el canal real y se pausa el cronjob de Hermes, que se puede reactivar si hace falta
