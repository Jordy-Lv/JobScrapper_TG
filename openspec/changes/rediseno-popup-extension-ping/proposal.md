## Why

El popup de la extensión es lo único que el usuario ve del asistente, y hoy no le dice si el
navegador realmente alcanza al servidor: solo muestra «Conectado · hace N min», que se calcula
con el último latido y puede estar desactualizado. Si algo falla (servidor caído, red lenta,
túnel de Tailscale cortado) el usuario no tiene cómo comprobarlo ni cómo reintentar sin esperar
al siguiente latido. Además, el dueño definió una maqueta nueva con la marca «APOLO TI» y un
estilo más vistoso que conviene aplicar ahora, antes de publicar en la tienda de Edge (tarea 9.5
del change `asistente-postulacion-telegram`).

## What Changes

- Rediseño visual del popup según la maqueta del dueño:
  - cabecera con el logo, el nombre **APOLO TI**, el estado de conexión, un engranaje que abre
    las opciones de la extensión y el botón de pausa;
  - tarjetas de portal más grandes, con borde de color propio (tipo neón) sobre fondo oscuro
    translúcido, logo, nombre, etiqueta de estado (Listo ✓, Sin sesión, Próximamente…) y el
    engranaje de cada portal que ya existe;
  - pie con «Última: …» a la izquierda y el botón de Telegram a la derecha.
- **Ping en la parte superior**: una barra de conexión bajo la cabecera muestra la latencia en
  milisegundos entre la extensión y el servidor, con color según el valor (verde, ámbar, rojo) y
  «Sin respuesta» cuando el servidor no contesta.
- **Botón para recargar la conexión** en esa barra: vuelve a medir el ping y fuerza un latido
  con revisión de portales, con indicador de «Reconectando…» mientras tarda.
- Nuevo endpoint público y ligero `GET /api/v1/ping` en el servidor, sin autenticación y sin
  tocar la base de datos, para medir la latencia sin gastar un latido real.
- Sin cambios en el protocolo de latido, en el motor de postulación ni en los permisos de la
  extensión.

## Capabilities

### New Capabilities

- `popup-extension`: lo que el popup de la extensión muestra y permite hacer al usuario:
  cabecera, estado y ping de conexión, recarga de la conexión, tarjetas de portal y pie.
  (Hoy ese comportamiento no tiene spec propia: el spec `extension-navegador` del change
  `asistente-postulacion-telegram` solo lo menciona como «popup con el estado».)

### Modified Capabilities

Ninguna. El spec `extension-navegador` sigue en un change sin archivar, por lo que no existe
aún bajo `openspec/specs/` y no puede llevar un delta; el endpoint `ping` se describe dentro de
la capability nueva.

## Impact

- **Extensión:** `extension/popup.html`, `extension/popup.css`, `extension/popup.js` (rediseño,
  barra de ping, recarga); `extension/api.js` (función `ping()` cronometrada);
  `extension/servicio.js` no cambia salvo que se reutilice el latido forzado que ya existe
  (`tipo: "latido"`).
- **Servidor:** `buscador_vacantes/asistente/api.py` (ruta `GET /api/v1/ping`).
  **Requiere desplegar en el PC Fedora** (tarea del dueño); sin el despliegue el popup sigue
  funcionando porque el ping cuenta cualquier respuesta HTTP del servidor.
- **Pruebas:** `tests/test_extension.py` (popup, marcado `navegador`) y
  `tests/test_asistente_api.py` (endpoint).
- **Documentación:** capturas de la ficha de la tienda en `docs/tienda-edge/` (se rehacen al
  terminar el rediseño) y, si aplica, `docs/guia-usuario.md`.
- **Nombre de la extensión:** el manifiesto y la ficha de la tienda conservan el nombre actual;
  «APOLO TI» se aplica solo dentro del popup.
