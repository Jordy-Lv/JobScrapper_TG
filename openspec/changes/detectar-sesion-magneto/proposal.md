## Why

La extensión marca Magneto como «Sin sesión» aunque el usuario la tenga iniciada. Así nunca llega a pedirle confirmar la cuenta, y una vacante de Magneto queda en cola sin poder postularse. Además, la card de esa vacante muestra en su bloque «Conexión con tus portales» la cuenta de Computrabajo, que no tiene nada que ver con ella.

Causa, verificada el 2026-10-15 en el navegador del dueño con sesión real:
- El HTML que entrega `www.magneto365.com` trae el enlace «Iniciar sesión» a `web.magneto365.com/sign-in` **aunque haya sesión**. El avatar del usuario (`img[alt='User Avatar']` dentro de `[class*='logoutBlock_avatar']`) lo reemplaza después, cuando la página termina de cargarse con JS.
- El motor decide «sin sesión» apenas encuentra ese enlace, antes de mirar la marca de sesión iniciada. Además, `magneto.json` no tiene marca (`"iniciada": []`), porque las páginas con sesión nunca se reconocieron.
- El bloque de conexión de la card lista todas las cuentas conocidas del usuario, no la del portal de la vacante.

## What Changes

- **Selectores de Magneto** (`assets/asistente/selectores/magneto.json`), verificados con sesión real:
  - marca de sesión iniciada: el avatar del usuario;
  - el enlace «Iniciar sesión» a `web.magneto365.com/sign-in` deja de contar como señal de «sin sesión», porque aparece también con sesión;
  - correo de la cuenta: está en la cabecera, en un tooltip oculto del selector de cuenta (`[class*='mg_account_select'] [class*='tooltip'] strong`);
  - tiempo de espera de la marca más largo que el de Computrabajo.
  - Este cambio de datos ya corrige el caso con la extensión publicada, sin esperar una versión nueva.
- **Motor de la extensión** (`extension/motor.js`):
  - la marca de sesión iniciada prevalece sobre el enlace de ingreso;
  - un portal puede declarar que la marca es obligatoria, y entonces sin marca no hay sesión;
  - el tiempo de espera de la marca se configura por portal.
  - Computrabajo sigue igual. La extensión sube de versión.
- **Card de la postulación** (bot): el bloque «Conexión con tus portales» muestra solo el portal de la vacante:
  - si ese portal no tiene cuenta, muestra su línea pendiente («inicia sesión con tu cuenta en ese navegador»);
  - los avisos de cuenta de **otros** portales que lleguen mientras la card está abierta van a un mensaje aparte, para que sus botones Confirmar y Cancelar sigan disponibles sin mezclarse con la vacante.
- Pruebas: un fixture de Magneto con sesión, armado con el marcado real (enlace «Iniciar sesión» que se cambia por el avatar con JS), en las pruebas de la extensión en Chromium, y pruebas del bloque de conexión filtrado.

## Capabilities

### New Capabilities

(ninguna)

### Modified Capabilities

- `extension-navegador`: la detección de sesión toma la marca de sesión iniciada como señal principal cuando el portal la declara. Cubre portales cuyo HTML inicial muestra el enlace de ingreso aunque haya sesión. La capacidad vive en el change sin archivar `asistente-postulacion-telegram`, así que el delta usa ADDED.
- `tarjeta-postulacion-asistente`: el bloque de conexión de la card se limita al portal de la vacante. La capacidad vive en el change sin archivar `tarjeta-unica-flujo-postulacion`, así que el delta usa ADDED.

## Impact

- Código:
  - `extension/motor.js` y `extension/manifest.json` (versión);
  - `assets/asistente/selectores/magneto.json`;
  - `buscador_vacantes/asistente/tarjeta.py` y `buscador_vacantes/asistente/conversacion.py` (`_datos_card`, `_actualizar_tarjeta` y los avisos de cuenta).
- Pruebas:
  - `tests/asistente/test_extension.py`, con el nuevo fixture `tests/fixtures/extension/mg_con_sesion.html`;
  - `tests/asistente/test_tarjeta.py` y `tests/asistente/test_bot.py`.
- Despliegue:
  - en el servidor Fedora, `git pull` y reiniciar `buscador-asistente`, porque los selectores se cargan al arrancar;
  - recargar la extensión en el navegador del dueño y tocar ↻ en el popup.
- Fuera de alcance: el flujo de postulación de Magneto con sesión (`verificado.postulacion` sigue en `false`) y su perfil. Siguen pendientes del reconocimiento con sesión.
