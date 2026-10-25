## Why

Los portales ya muestran al candidato cómo va cada postulación: Computrabajo en `/co/estadisticas/mis-procesos/` y Magneto en `/profile/processes` («Procesos activos»). Hoy nadie mira esas páginas, así que un «CV visto», un «Finalista» o un mensaje de la empresa pueden pasar días sin que el usuario se entere. La extensión ya tiene la sesión del usuario, los permisos y un motor que lee páginas con selectores. Leer esas páginas de vez en cuando es la forma más barata y exacta de alimentar el seguimiento que crea `seguimiento-proceso-postulacion`.

## What Changes

- **Lectura periódica de «Mis procesos»**: el servidor decide cuándo toca leer cada portal (cada `cada_h` horas, solo en la ventana diurna y solo con la sesión lista y sin una postulación en curso) y se lo pide a la extensión en la respuesta del latido. La extensión abre la página en una pestaña en segundo plano, lee las filas con selectores declarados en el JSON del portal, cierra la pestaña y manda una foto al servidor.
- **Selectores `procesos` en el JSON de cada portal**:
  - la URL;
  - la fila y sus campos (cargo, empresa, fecha, estado, enlace);
  - la expresión para sacar el id de la oferta del enlace;
  - el mapa de textos de estado del portal a tipos de evento;
  - opcionalmente, el contador de mensajes sin leer y su página.

  Solo es lectura: no hay clics salvo el paso de página declarado.
- **Comparación en el servidor**: cada foto se compara con la anterior del mismo usuario y portal.
  - Un estado nuevo da un evento de origen `portal` con seguridad `alta`.
  - Una fila sin proceso se ofrece como proceso externo (el usuario se postuló por su cuenta).
  - Los mensajes nuevos de empresas dan un aviso urgente con el enlace.
- **Reconocimiento antes de codificar** (👤 con la cuenta del dueño): qué estados y mensajes muestra cada portal cuando una empresa avanza, con fixtures HTML anonimizados.
- **Computrabajo y Magneto primero**. Elempleo queda para cuando su postulación esté verificada (permiso opcional).
- Documentación de la lectura en `docs/asistente/portales.md`, con su frecuencia y su revisión de términos.

## Capabilities

### New Capabilities
- `procesos-portal-extension`: la lectura periódica, solo de lectura, de las páginas de procesos y mensajes de cada portal desde la extensión, y su conversión en eventos y procesos externos del seguimiento.

### Modified Capabilities
<!-- Ninguna en openspec/specs/: el seguimiento (`seguimiento-proceso-asistente`) llega con `seguimiento-proceso-postulacion`, que se archiva antes que este change. -->

## Impact

- `assets/asistente/selectores/computrabajo.json` y `magneto.json`: sección `procesos` nueva y versión.
- `extension/servicio.js`: atender `procesos` en la respuesta del latido y abrir, leer y cerrar la pestaña. `extension/motor.js`: un lector genérico de filas por selectores. Sube la versión de `manifest.json`.
- `buscador_vacantes/asistente/api.py`: campo `procesos` en la respuesta de `/latido` y endpoint `POST /api/v1/procesos/{plataforma}`. Módulo nuevo `procesos_portal.py` (comparación, asociación y eventos) y tabla `procesos_portal_foto` (la versión de esquema siguiente a la que haya al implementar).
- `config.yaml`: `asistente.seguimiento.portales` (frecuencia, ventana horaria, máximo de filas).
- `tests/fixtures/extension/` (páginas de procesos) y `tests/asistente/test_extension.py`, `test_api.py` y `test_procesos_portal.py`.
- Depende de `seguimiento-proceso-postulacion`. Es independiente de los changes de correo.
