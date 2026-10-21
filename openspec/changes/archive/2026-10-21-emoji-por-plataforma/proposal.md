## Why

Los mensajes del bot nombran la plataforma (Computrabajo, Magneto, elempleo) solo con texto. Con varias postulaciones abiertas en portales distintos, el nombre en texto plano se pierde entre el resto de la card. Los logos de los portales no existen como emoji de Telegram, pero un emoji de color por portal da una pista visual inmediata, sin configurar nada en Telegram ni usar marcas de terceros.

## What Changes

- Cada plataforma tiene un emoji fijo: 🔵 Computrabajo, 🟢 Magneto, 🩵 elempleo.
- La cabecera de la card muestra el emoji antes del nombre del portal («Maaji · 🟢 Magneto»; «🟢 Magneto» si no hay empresa).
- El bloque «Conexión» de la card muestra el emoji antes del nombre del portal en cada línea de cuenta.
- Una plataforma sin emoji registrado o desconocida se muestra como hoy, sin emoji y sin espacios sobrantes.
- Los textos en prosa («postular en Magneto», botones «Confirmar Magneto», avisos) no cambian.

## Capabilities

### New Capabilities
<!-- ninguna -->

### Modified Capabilities
- `tarjeta-postulacion-asistente`: la cabecera de la card y el bloque de conexión identifican cada plataforma con su emoji.

## Impact

- `buscador_vacantes/asistente/textos.py` (nuevo `EMOJI_PLATAFORMA` y función `nombre_con_emoji`; `linea_empresa` la usa) y `buscador_vacantes/asistente/tarjeta.py` (`lineas`, para el bloque «Conexión»).
- Pruebas de la cabecera y del bloque de conexión en `tests/asistente`; las que comparan el texto exacto se actualizan.
- Sin cambios en la extensión, la base ni los botones. Reemplaza el non-goal «sin emojis por portal» del change `mostrar-plataforma-en-card`.
