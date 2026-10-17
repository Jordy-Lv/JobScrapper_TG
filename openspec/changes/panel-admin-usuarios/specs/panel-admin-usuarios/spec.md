## Purpose

Permite a los administradores ver en el panel quién usa el bot y en qué punto va, cómo crece el grupo y cómo van las postulaciones, y suspender o reactivar usuarios sin escribir comandos.

## ADDED Requirements

### Requirement: Tabla de usuarios
La vista Usuarios SHALL listar todos los usuarios del bot con estos datos:
- id interno, nombre de Telegram, estado (alta, activo, suspendido, inactivo) y motivo del estado;
- paso del alta en curso, fecha de alta, última actividad y última verificación de membresía;
- versión de la política aceptada;
- número de navegadores vinculados no revocados y el último latido de cualquiera de ellos;
- portales con cuenta confirmada (solo el nombre del portal);
- modo automático (umbral o apagado);
- postulaciones creadas en el periodo elegido.

La tabla MUST permitir buscar por nombre, filtrar por estado y por portal, y ordenar por cualquier columna. Debe paginar de 50 en 50.

#### Scenario: Filtrar suspendidos
- **WHEN** el admin filtra por estado «suspendido»
- **THEN** la tabla muestra solo los suspendidos con su motivo, por ejemplo «salió del grupo»

#### Scenario: Extensión caída
- **WHEN** el último latido de los navegadores de un usuario tiene más de `extension.navegador_caido_min` minutos
- **THEN** la fila marca la extensión como «desconectada» con la hora del último latido

### Requirement: Ficha del usuario
Al abrir un usuario, el panel SHALL mostrar:
- los datos de la tabla;
- sus navegadores (nombre, versión, fecha de vínculo, último latido, revocado o no);
- sus postulaciones del periodo (vacante con enlace, plataforma, estado, origen, afinidad, fechas y motivo).

La ficha MUST NOT mostrar CV, perfil, cuestionario, respuestas enviadas, claves de IA, correos, teléfonos ni documentos.

#### Scenario: Historial en la ficha
- **WHEN** el admin abre la ficha de un usuario con 3 postulaciones en el mes
- **THEN** ve las 3 con su vacante, estado y fechas, sin ninguna respuesta del formulario

### Requirement: Suspender y reactivar desde el panel
La ficha SHALL ofrecer «Suspender» a un usuario activo o en alta, y «Reactivar» a uno suspendido. Antes de hacerlo pide confirmación. El efecto MUST ser el mismo que el de `/suspender` y `/reactivar`, incluido cancelar los pendientes al suspender. Cada acción MUST exigir el token CSRF y quedar en `auditoria` con el id de Telegram del admin.

#### Scenario: Suspender
- **WHEN** el admin confirma «Suspender» en la ficha de un usuario activo
- **THEN** el usuario queda suspendido, sus postulaciones pendientes se cancelan y `auditoria` registra la acción con el admin

#### Scenario: Sin confirmar
- **WHEN** el admin pulsa «Suspender» y cancela la confirmación
- **THEN** no cambia nada

### Requirement: Embudo de altas
La vista Usuarios SHALL mostrar, para los usuarios creados en el periodo, cuántos llegaron a cada paso:
1. iniciaron;
2. aceptaron la política;
3. subieron el CV;
4. configuraron la IA con una clave válida;
5. vincularon un navegador;
6. hicieron su primera postulación.

Cada paso muestra también el porcentaje sobre el anterior.

#### Scenario: Dónde se quedan
- **WHEN** en el mes 20 usuarios iniciaron y 8 vincularon un navegador
- **THEN** el embudo muestra 20 en «iniciaron» y 8 en «vincularon un navegador», con su porcentaje sobre el paso previo

### Requirement: Vista Grupo
La vista Grupo SHALL mostrar:
- los miembros actuales del grupo, según el conteo de Telegram, en caché de `grupo.cache_min` minutos;
- la serie diaria de miembros, entradas y salidas del periodo;
- cuántos usuarios activos del bot son miembros;
- cuántos usuarios del bot están suspendidos por haber salido.

Si no hay registros de entradas y salidas anteriores a la activación de este change, MUST indicarlo con «sin registro antes del <fecha>».

#### Scenario: Entradas del día
- **WHEN** el día elegido entraron 5 personas al grupo y salieron 2
- **THEN** la vista muestra 5 entradas y 2 salidas ese día

#### Scenario: Antes del registro
- **WHEN** el admin elige un mes anterior a la activación
- **THEN** ve el aviso «sin registro antes del <fecha>» en lugar de ceros

### Requirement: Vista Postulaciones
La vista Postulaciones SHALL mostrar, para el periodo:
- postulaciones por estado, por plataforma y por origen (botón o automático);
- la tasa de éxito (enviadas sobre terminadas);
- los 10 motivos de fallo más frecuentes;
- la mediana de la duración entre tomada y terminada;
- una tabla filtrable con enlace a la ficha del usuario.

Usa el selector de periodo y la comparación con el periodo anterior de `panel-admin-estadisticas`.

#### Scenario: Éxito por plataforma
- **WHEN** en la semana Computrabajo tuvo 30 terminadas y 24 enviadas
- **THEN** la vista muestra para Computrabajo una tasa de éxito del 80 %
