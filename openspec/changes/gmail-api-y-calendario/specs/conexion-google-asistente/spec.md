## Purpose

Permitir que el usuario conecte, si quiere, su Gmail en solo lectura y su Google Calendar, para que el seguimiento vea todo el correo nuevo de sus procesos sin filtros y cree sus entrevistas en el calendario, con revocación en cualquier momento.

## ADDED Requirements

### Requirement: Conexión opcional con Gmail
`/correo` SHALL ofrecer «Conectar Gmail» mientras la integración esté activa y el proyecto no haya llegado a `tope_usuarios`. Antes de abrir la autorización, el asistente MUST explicar que Google mostrará la advertencia de app no verificada, que solo se pide lectura y qué se guarda. La autorización MUST pedir solo `gmail.readonly` y acceso sin conexión, con un `state` de un solo uso, atado al usuario y que vence a los 10 minutos.

#### Scenario: Conexión exitosa
- **WHEN** el usuario autoriza en Google y vuelve al servidor con un `state` válido
- **THEN** el token queda guardado cifrado, la página de regreso dice que puede volver a Telegram y el bot confirma «Gmail conectado»

#### Scenario: State inválido o vencido
- **WHEN** el regreso trae un `state` desconocido, ya usado o de hace más de 10 minutos
- **THEN** no se guarda nada y la página indica que se repita desde Telegram

#### Scenario: Permiso rechazado
- **WHEN** el usuario cancela en la pantalla de Google
- **THEN** no se guarda nada y el bot ofrece el reenvío con filtro como alternativa

### Requirement: Tope de usuarios del proyecto sin verificar
El asistente SHALL contar las cuentas de Google que alguna vez se conectaron. Al llegar a `tope_usuarios` (90 por defecto, por debajo del límite de 100 de Google) MUST dejar de ofrecer «Conectar Gmail», ofrecer solo el reenvío y avisar al dueño una vez. Las conexiones existentes siguen funcionando.

#### Scenario: Tope alcanzado
- **WHEN** ya se conectaron 90 cuentas y un usuario nuevo abre `/correo`
- **THEN** solo ve la opción de reenvío, y el dueño recibió un aviso cuando se llegó al tope

### Requirement: Lectura incremental del correo nuevo
Con Gmail conectado, el asistente SHALL consultar cada `cada_min` los mensajes nuevos desde el último punto leído, y en la primera lectura solo los de las últimas 24 horas. A cada mensaje MUST aplicarle el mismo descarte previo y el mismo procesamiento de la capacidad `correo-seguimiento-asistente`, con seguridad sin rebaja, porque el origen es la propia cuenta. Los mensajes descartados MUST NOT descargarse completos ni guardarse. Con Gmail conectado, el reenvío del mismo usuario SHALL desactivarse para no procesar dos veces.

#### Scenario: Correo de un reclutador sin palabras clave del filtro
- **WHEN** llega a la bandeja del usuario un correo de un reclutador que dice «¿podemos hablar mañana a las 3?» y su remitente coincide con el dominio de un proceso
- **THEN** se procesa y se asocia a ese proceso aunque no tenga palabras clave

#### Scenario: Correo personal sin relación
- **WHEN** llega un correo personal sin señales
- **THEN** no se descarga completo ni se guarda nada de él

### Requirement: Calendario opcional
`/correo` SHALL ofrecer «Agregar entrevistas a Google Calendar» por separado, pidiendo solo `calendar.events` con autorización incremental. Con ese permiso, cada entrevista confirmada MUST crear un evento en el calendario principal, con la empresa y el cargo, la hora, el lugar o el enlace y recordatorios emergentes de 60 y 15 minutos. Una reprogramación MUST actualizar el mismo evento y un cierre del proceso antes de la fecha MUST borrarlo. Sin el permiso, el asistente sigue enviando el `.ics`.

#### Scenario: Entrevista confirmada con calendario conectado
- **WHEN** el usuario confirma una entrevista el martes a las 10:00
- **THEN** el evento aparece en su Google Calendar el martes de 10:00 a 11:00 con los recordatorios, y no recibe además el `.ics`

#### Scenario: Entrevista cancelada
- **WHEN** el proceso se cierra como `descartado` antes de la fecha de la entrevista
- **THEN** el evento se borra del calendario

### Requirement: Desconexión, revocación y fallos de token
«Desconectar Gmail» y la baja del usuario SHALL revocar el token en Google, borrarlo de la base y dejar de leer en el acto. Si Google responde que el token fue revocado o venció, el asistente MUST borrarlo, avisarle al usuario una vez y ofrecer reconectar o usar el reenvío.

#### Scenario: Revocado desde la cuenta de Google
- **WHEN** el usuario quita el acceso desde su cuenta de Google y la siguiente lectura recibe `invalid_grant`
- **THEN** el asistente borra el token, deja de leer y le avisa con las dos opciones

### Requirement: Protección de los tokens y uso limitado
Los tokens de Google SHALL guardarse cifrados con la clave maestra del asistente y no aparecer en logs ni en mensajes. Los datos obtenidos de Google MUST usarse solo para el seguimiento de procesos del propio usuario, sin compartirlos ni usarlos para entrenar modelos, como declara la política de privacidad. La IA que clasifique esos correos SHALL ser la del propio usuario.

#### Scenario: Log de un error de Google
- **WHEN** una llamada a Google falla y se registra en el log
- **THEN** el registro no contiene el token de acceso ni el de renovación
