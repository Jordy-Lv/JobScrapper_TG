# traspaso-piloto-asistente Specification

## Purpose
Definir cómo se traspasa el asistente de la copia de desarrollo a producción sin perder datos de los usuarios y con una vuelta atrás probada.

## Requirements

### Requirement: Respaldo antes de tocar nada
Antes de parar el servicio, el traspaso SHALL contar con un respaldo reciente de las bases y del `.env` de ambas carpetas, con verificación de integridad.

#### Scenario: Respaldo fresco
- **WHEN** va a comenzar el traspaso
- **THEN** existe un respaldo hecho ese mismo día cuyas bases pasan la comprobación de integridad

### Requirement: Datos conservados e íntegros
Los datos del asistente SHALL copiarse completos a producción y SHALL verificarse antes de arrancar el servicio.

#### Scenario: Copia verificada
- **WHEN** se copian `asistente.db` y la carpeta de evidencia
- **THEN** la base copiada pasa la comprobación de integridad y tiene los mismos recuentos de usuarios, postulaciones y respuestas que la original

### Requirement: Clave de cifrado idéntica y confidencial
`ASISTENTE_CLAVE_CIFRADO` SHALL copiarse sin alteración y SHALL NOT mostrarse ni registrarse en informes, registros ni mensajes.

#### Scenario: Clave que descifra
- **WHEN** el servicio arranca en producción
- **THEN** puede descifrar un dato existente de un usuario del piloto, comprobado sin imprimir el valor

#### Scenario: Clave distinta o ausente
- **WHEN** la clave de producción no coincide o falta
- **THEN** el servicio no se deja arrancado y se ejecuta la vuelta atrás

### Requirement: Un solo origen de ejecución
Tras el traspaso, el servicio `buscador-asistente` SHALL ejecutarse desde `~/buscador-vacantes` y no SHALL existir `prueba.conf` activo.

#### Scenario: Directorio de trabajo
- **WHEN** se consulta la unidad después del traspaso
- **THEN** su directorio de trabajo es `~/buscador-vacantes` y el servicio está activo

### Requirement: Servicio comprobado
Después de arrancar, el bot SHALL responder y la API pública SHALL responder desde su URL de Tailscale.

#### Scenario: Comprobación posterior
- **WHEN** termina el arranque
- **THEN** el registro no muestra errores de arranque, el bot atiende un comando del dueño y la URL pública responde

### Requirement: Vuelta atrás disponible
La copia de desarrollo SHALL conservarse intacta hasta que el dueño confirme su retiro, de modo que restaurar `prueba.conf` devuelva el servicio a su estado anterior.

#### Scenario: Fallo tras el traspaso
- **WHEN** la comprobación posterior falla
- **THEN** se restaura `prueba.conf`, se recarga systemd y el servicio vuelve a correr desde la copia de desarrollo con sus datos originales

### Requirement: Confirmación del dueño por fases
Cada paso que modifique producción SHALL ejecutarse solo tras la confirmación explícita del dueño.

#### Scenario: Antes de parar el servicio
- **WHEN** el respaldo y las comprobaciones previas están listos
- **THEN** se pide confirmación antes de parar el servicio
