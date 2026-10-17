## Why

Para ver quién usa el asistente, el dueño hoy solo tiene `/usuarios`: una lista de texto con nombre, estado y última actividad, cortada a 4000 caracteres. No sabe:
- cuántas personas tiene el grupo ni cuántas entran y salen;
- en qué paso del alta se queda la gente;
- quién tiene la extensión conectada;
- cómo van las postulaciones por plataforma.

Este change agrega esas vistas al panel que crea `panel-admin-metricas`, con el mismo selector de periodo.

## What Changes

- **Vista Usuarios** del panel:
  - tabla de los usuarios del bot con nombre de Telegram, estado, paso del alta, fecha de alta, última actividad, membresía verificada, versión de la política aceptada, navegadores vinculados (versión y último latido), portales con cuenta confirmada (solo el nombre del portal), modo automático y número de postulaciones del periodo;
  - búsqueda por nombre y filtros por estado y por portal;
  - **ficha de cada usuario** con su historial de postulaciones (vacante, plataforma, estado, fechas y motivo) y sus navegadores;
  - acciones **Suspender** y **Reactivar** con confirmación, iguales a `/suspender` y `/reactivar`, auditadas;
  - **embudo de altas** para el periodo: iniciaron, aceptaron la política, subieron el CV, configuraron la IA, vincularon un navegador e hicieron la primera postulación.
- **Vista Grupo**:
  - miembros actuales del grupo, que Telegram da solo como número;
  - entradas y salidas por día;
  - cuántos miembros usan el bot y cuántos usuarios del bot ya no están en el grupo.

  Las entradas y salidas se registran desde que se activa este change, con los avisos `chat_member` de Telegram. Telegram no deja listar a los miembros ni recuperar el historial anterior.
- **Salida inmediata del grupo**: cuando un usuario del bot sale del grupo, el aviso `chat_member` lo suspende en el acto, en lugar de esperar a la comprobación cada `comprobar_cada_h` horas. Lo reactiva si vuelve.
- **Vista Postulaciones** con el selector de periodo:
  - conteo por estado, plataforma y origen (botón o automático);
  - tasa de éxito;
  - motivos de fallo más frecuentes;
  - duración típica (de tomada a terminada);
  - tabla con bajada a la ficha del usuario.
- **Privacidad**:
  - De los miembros del grupo que nunca usaron el bot no se guarda ningún dato personal, solo conteos por día. Así se respeta la regla «sin datos hasta aceptar la política».
  - La ficha del usuario no muestra CV, perfil, respuestas, claves ni correos.

## Capabilities

### New Capabilities

- `panel-admin-usuarios`: vistas Usuarios (tabla, ficha, suspender y reactivar, embudo de altas), Grupo (miembros, entradas y salidas) y Postulaciones del panel de administración.

### Modified Capabilities

- `usuarios-asistente`: el aviso `chat_member` del grupo suspende o reactiva al usuario del bot en el acto, y alimenta los conteos de entradas y salidas sin guardar datos de quien no es usuario. La capacidad vive en el change sin archivar `asistente-postulacion-telegram`, así que el delta usa ADDED.

## Impact

- Depende de `panel-admin-metricas`: sesión, CSRF, selector de periodo y resumen diario.
- Código:
  - `asistente/panel/` (rutas y consultas de usuarios, grupo y postulaciones);
  - `asistente/bot.py` (`ChatMemberHandler` del grupo);
  - `asistente/membresia.py` y `asistente/usuarios.py` (aplicar el aviso);
  - `asistente/datos.py` (tabla `eventos_grupo` sin ids, esquema 5);
  - `comun/metricas.py` (miembros y entradas o salidas en `metricas_dia_asistente`).
- Recursos: secciones nuevas en `assets/asistente/panel/`.
- Pruebas: `tests/asistente/test_panel_usuarios.py`, `test_membresia.py` y `test_bot.py`.
- Telegram: el bot asistente ya es administrador del grupo. Hay que confirmar que recibe `chat_member` (`allowed_updates` ya pide todos los tipos).
