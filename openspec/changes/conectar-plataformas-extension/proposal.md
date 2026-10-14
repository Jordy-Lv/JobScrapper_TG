> **Alcance decidido el 2026-10-14:** tras medir el volumen real (elempleo 164 vacantes en 30 días; GetOnBoard 1; SPE 0) y revisar los términos, el dueño decidió conectar **solo elempleo**. GetOnBoard y el SPE quedan en paquete de respaldo y se retoman si su volumen crece. El resto de este documento conserva el análisis original de las tres plataformas.

## Why

La extensión del asistente solo postula sola en Computrabajo y Magneto. Las vacantes de elempleo, GetOnBoard y del Servicio Público de Empleo (SPE) ya se publican en el canal, pero quien toca ⚡ en ellas recibe solo el paquete de respaldo (CV adaptado, carta y enlace para copiar). Esas tres fuentes aportan una parte importante de las ofertas del radar, así que es la ampliación más útil que queda para el asistente.

El código ya está preparado: `extension/portales.js` conoce los dominios, los enlaces de ingreso y los permisos opcionales de las tres, y `manifest.json` ya los declara como `optional_host_permissions`. Lo que falta son los **datos de cada portal** (selectores y flujo reconocidos con una sesión real), las pruebas con fixtures reales y el piloto. Como el servidor entrega los selectores como datos versionados, se puede habilitar cada plataforma sin publicar otra versión de la extensión en la tienda de Edge.

## What Changes

- Reconocimiento con sesión real (del dueño) de **elempleo**, **GetOnBoard** y **SPE**, con el mismo método de la tarea 3.1 de `asistente-postulacion-telegram`: indicadores de sesión, ya postulado, vacante cerrada, campos y preguntas, captchas, correo de la cuenta, páginas de perfil, modo del CV y páginas prohibidas. Se documenta en `docs/asistente/portales.md`.
- Revisión previa de los **términos de uso** de cada portal sobre la postulación asistida por el navegador del propio usuario. Una plataforma cuyos términos la prohíban se queda en paquete de respaldo (igual que LinkedIn) y se documenta el motivo.
- Un `assets/asistente/selectores/<plataforma>.json` por cada plataforma aprobada, con sus fixtures recortados y sin datos personales en `tests/fixtures/asistente/<plataforma>/`.
- Adaptador propio en `extension/adaptadores/<plataforma>.js` **solo** donde el flujo no se pueda expresar como datos (por ejemplo, una aplicación de una sola página); `ADAPTADORES` lista únicamente esas.
- `vacantes.PLATAFORMAS` reconoce los dominios nuevos, para que una vacante de esos portales ya no caiga en `plataforma_no_soportada`.
- Habilitación gradual por plataforma en `config.yaml` (`asistente.plataformas.<x>.automatica`): primero la plataforma queda visible en el popup con `automatica: false`, se prueba con el dueño y solo después pasa a `true`.
- Piloto controlado por plataforma (3 vacantes reales del dueño por portal) y después con los invitados.
- Se actualizan la guía de usuario, la política de datos (si nombra a los portales) y la ficha de la tienda de Edge.
- **Sin cambios en**: el motor (`motor.js`), el contrato del servidor ni la cola; las plataformas nuevas usan los mismos pasos declarativos que Computrabajo y Magneto. LinkedIn sigue fuera de alcance.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `postulacion-automatica`: la lista de plataformas con postulación automática deja de ser solo Computrabajo y Magneto; cada plataforma nueva se habilita únicamente tras su reconocimiento, su revisión de términos y su piloto.
- `extension-navegador`: el adaptador, los selectores, la detección de sesión, la cuenta asociada y el engranaje de preferencias del popup cubren las plataformas nuevas, con permiso opcional pedido al usuario solo cuando el servidor habilita la plataforma.

Estas dos specs hoy solo existen dentro del change `asistente-postulacion-telegram` (aún sin archivar), así que los deltas usan `ADDED` y se aplican después de archivarlo, como ya hace `linkedin-detalle-vacantes`.

## Impact

- **Datos**: `assets/asistente/selectores/{elempleo,getonboard,spe}.json` (los que se aprueben), `tests/fixtures/asistente/<plataforma>/`.
- **Código del servidor**: `buscador_vacantes/asistente/vacantes.py` (mapa de dominios) y, si hace falta, `cola.py` y `nucleo.py` solo por casos que el reconocimiento destape.
- **Extensión**: `extension/portales.js` (`ADAPTADORES`), `extension/adaptadores/*.js` y `tests/asistente/test_extension.py`. Sin cambios en `manifest.json`: los permisos ya están como opcionales, así que no exige nueva revisión de la tienda.
- **Configuración y documentación**: `config.yaml`, `docs/asistente/portales.md`, `docs/asistente/guia-usuario.md`, `docs/asistente/tienda-edge`.
- **Riesgos**: cada portal puede cambiar su marcado sin aviso; pueden aparecer captchas o verificaciones que obliguen a dejar la plataforma en respaldo. Mitigación: los selectores son datos corregibles en el servidor y el reporte de errores con evidencia ya existe.
- **Dependencias**: la tarea de reconocimiento es 👤 del dueño (su navegador y sus cuentas). Conviene hacerla tras cerrar 3.1 y 3.2 de `asistente-postulacion-telegram`, porque comparten método y fixtures.
