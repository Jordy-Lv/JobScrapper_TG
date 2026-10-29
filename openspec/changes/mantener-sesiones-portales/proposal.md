## Why

Las sesiones de elempleo, Magneto y los demás portales se cierran antes de un día. Cada vez que
pasa, la extensión ve `sin_sesion`, las postulaciones quedan en `esperando_sesion` y el usuario
tiene que volver a iniciar sesión a mano. Las sesiones viven en las cookies del Chrome del
usuario: la extensión no las crea ni las borra, y hoy ni siquiera puede verlas, así que nadie
sabe si la causa es una cookie de sesión que muere al cerrar Chrome, un vencimiento corto del
servidor del portal o un ajuste de Chrome que borra las cookies al salir.

## What Changes

- **Diagnóstico por portal.** Con un permiso opcional `cookies`, la extensión lee solo los
  **metadatos** de las cookies de autenticación de cada portal (nombre, si es de sesión o
  persistente, vencimiento, `HttpOnly`); nunca el valor. El resultado se muestra en el popup
  («Tu sesión de elempleo dura hasta …» o «se pierde al cerrar Chrome») y se registra para saber
  la causa real de cada portal antes de elegir el arreglo.
- **Persistir las cookies de sesión (opt-in por portal).** Si una cookie de autenticación es de
  sesión (sin vencimiento), la extensión la reescribe con un vencimiento largo para que sobreviva
  al cierre de Chrome, y la vuelve a persistir cada vez que el portal la renueva
  (`chrome.cookies.onChanged`). Solo se toca el vencimiento: el valor y los atributos de la cookie
  no cambian.
- **Mantener viva la sesión.** Una visita periódica y liviana al portal en segundo plano, para
  los portales cuyo vencimiento se renueva con el uso (vencimiento deslizante). Se reutiliza la
  revisión que la extensión ya hace cada 6 h, sin abrir pestañas nuevas por separado cuando no
  haga falta.
- **Aviso cuando se pierde la sesión.** Hoy el servidor avisa por Telegram al pasar a «listo», pero
  no al pasar de «listo» a `sin_sesion`. Se avisa una vez, con el portal y el motivo, para que el
  usuario reinicie la sesión antes de que una postulación se quede esperando.
- **Sin evadir nada.** No se guardan ni se envían credenciales ni valores de cookies al servidor;
  un vencimiento absoluto del portal (que cierra la sesión pase lo que pase) no se evade: solo se
  detecta y se avisa.

## Capabilities

### New Capabilities

- `sesiones-portales`: diagnóstico de las cookies de autenticación de cada portal, persistencia
  opt-in de las de sesión, mantenimiento periódico y aviso al perder la sesión.

### Modified Capabilities

- `popup-extension`: la tarjeta de portal muestra cuánto dura la sesión y ofrece el interruptor de
  «Mantener la sesión» (pide el permiso `cookies` al activarlo).
- `confirmacion-cuenta-portal`: el aviso por Telegram también cubre el paso de listo a sin sesión
  (hoy solo cubre el regreso a listo).

## Impact

- `extension/manifest.json`: permiso opcional `cookies` (en `optional_permissions`, no obligatorio:
  agregarlo como obligatorio desactivaría la extensión de los demás usuarios hasta que lo acepten y
  obligaría a una nueva revisión en la tienda de Edge).
- `extension/servicio.js` y un módulo nuevo para las cookies; `extension/portales.js` (dominios de
  autenticación por portal); `extension/popup.js` y `popup.html` (estado y interruptor).
- `assets/asistente/selectores/*.json`: nombres de las cookies de autenticación por portal (datos
  versionados del servidor, como el resto de los selectores).
- `buscador_vacantes/asistente/api.py` y `textos.py`: aviso de sesión perdida, y el motivo
  (`cookie_de_sesion`, `vencida`, `cerrada_por_el_portal`) que viaja en el latido.
- `docs/asistente/portales.md` y `docs/asistente/tienda-edge/ficha.md`: la ficha de la tienda debe
  justificar el permiso `cookies`.
- Privacidad: persistir una sesión alarga el tiempo que alguien con acceso al PC puede usarla; por
  eso es opt-in por portal y se puede desactivar, lo que devuelve las cookies a su comportamiento
  original.
