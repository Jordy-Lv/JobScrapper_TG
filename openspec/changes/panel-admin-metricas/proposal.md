## Why

Hoy el dueño solo ve cómo va el radar y el asistente en el resumen diario de Telegram y en los comandos `/stats` y `/usuarios`. No puede ver un día o un mes concreto, comparar periodos ni saber cuántas vacantes saca cada plataforma o de qué tipo son (práctica, aprendiz, trainee, junior). Además, el detalle se borra pronto: `vistas` se borra a los 90 días y `corridas`, `intentos` e `ia_uso` a los 30. Así no hay manera de mirar un mes de hace medio año.

Este change crea la base del panel web para administradores: el acceso seguro y las estadísticas de solo lectura. Los changes siguientes, `panel-admin-usuarios` y `panel-admin-filtros`, montan sobre esta base.

## What Changes

- **Panel web en la API del asistente**. Rutas bajo `/panel/` en la misma app FastAPI que ya se publica con Tailscale Funnel, con una página HTML propia sin paso de compilación y Chart.js guardado en el repositorio. La API de la extensión (`/api/v1/`) no cambia.
- **Acceso solo para administradores** con un enlace de un solo uso:
  - un admin escribe `/panel` al bot y recibe un enlace que vence a los 5 minutos;
  - al abrirlo, se crea una sesión de 8 horas con una cookie segura;
  - la lista de admins es el dueño (`dueno_telegram_id`) más `asistente.panel.admins`;
  - cada petición vuelve a comprobar que quien la hace sigue siendo admin;
  - incluye cierre de sesión y registro en `auditoria`.
- **Selector de periodo** en todas las vistas:
  - un día concreto, una semana (de lunes a domingo), un mes o un rango libre;
  - flechas para ir al periodo anterior y al siguiente;
  - comparación con el periodo anterior del mismo largo;
  - el periodo queda en la URL, así que se puede guardar o compartir entre admins.
- **Bajada de detalle**: de un mes o rango a sus días, de un día a sus horas y de una barra a la lista de vacantes que la forman, cuando el detalle todavía existe.
- **Vistas de estadísticas**:
  - **Resumen**: cifras clave con su variación frente al periodo anterior.
  - **Vacantes**: por plataforma, por categoría, por tipo (practicante, aprendiz SENA, pasantía, trainee, intern, junior, otro) y por modalidad; tendencia diaria y tabla filtrable con enlace a cada oferta.
  - **Embudo del radar**: crudas → descartes por regla → duplicadas → dudosas → aceptadas o rechazadas por la IA → enviadas. Incluye el estado de cada fuente: último éxito, fallos seguidos y cooldown.
  - **IA y costos**: llamadas, tokens y errores del clasificador, el reportero y el resumen, más el uso de IA del asistente.
- **Métricas diarias que no se borran**: el radar guarda un resumen por día, fuente, categoría y tipo en una tabla nueva de `vacantes.db`, y el asistente guarda el suyo en `asistente.db`. Se conservan `panel.dias_metricas` días (730 por defecto). El detalle sigue borrándose como hoy.
- **Tipo de vacante** sacado del título con una lista ordenada `panel.tipos` en `config.yaml`. Se calcula también sobre las vacantes ya guardadas, así que sirve para el historial sin tocar la clasificación del radar.

## Capabilities

### New Capabilities

- `panel-admin-acceso`: acceso al panel solo para administradores, con enlace de un solo uso desde el bot, sesión con cookie segura, verificación de admin en cada petición, protección CSRF, límite de intentos y auditoría.
- `panel-admin-estadisticas`: vistas de solo lectura (resumen, vacantes, embudo, IA) con selector de día, semana, mes o rango, comparación con el periodo anterior y bajada de detalle.
- `metricas-historicas`: resumen diario persistente de las cifras del radar y del asistente, que sobrevive a la limpieza del detalle, y cálculo del tipo de vacante a partir del título.

### Modified Capabilities

(ninguna: la API de la extensión, la limpieza y la clasificación conservan sus requisitos)

## Impact

- Código:
  - nuevos `buscador_vacantes/asistente/panel/` (rutas, sesiones, consultas) y `buscador_vacantes/comun/metricas.py` (resumen diario y tipo de vacante);
  - cambios en `asistente/api.py` (montar `/panel`), `asistente/conversacion.py` (comando `/panel`), `asistente/servicio.py` (resumen diario del asistente), `comun/estado.py` (tabla `metricas_dia` y esquema 4), `asistente/datos.py` (tablas `panel_sesiones` y `metricas_dia_asistente`, esquema 4), `comun/config.py` (sección `asistente.panel`) y el ciclo del radar (guardar el resumen antes de limpiar).
- Recursos: `assets/asistente/panel/` (HTML, CSS, JS y Chart.js en una versión fija).
- Configuración: `asistente.panel` en `config.yaml` (activo, admins, vigencia del enlace y de la sesión, `dias_metricas`, `tipos`).
- Pruebas: `tests/asistente/test_panel*.py` y `tests/comun/test_metricas.py`.
- Despliegue: no cambia el puerto ni el Funnel. Requiere el asistente activo y `url_publica` configurada. El dueño prueba el acceso desde su Telegram (tarea del dueño).
- Dependencias: ninguna nueva en Python. Chart.js va como archivo estático.
