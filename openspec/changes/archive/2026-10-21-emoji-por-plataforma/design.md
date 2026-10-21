## Context

`textos.NOMBRES_PLATAFORMA` se usa en ~12 sitios: cabecera de la card (`linea_empresa`), bloque «Conexión» (`tarjeta.lineas`), botones («Confirmar Magneto») y frases («el portal…»). Meter el emoji dentro de ese diccionario lo propagaría a botones y prosa, donde estorba y puede romper pruebas y el escape HTML.

## Goals / Non-Goals

**Goals:**
- Pista visual del portal en la cabecera y el bloque de conexión.
- Un solo lugar donde se define el emoji de cada portal.

**Non-Goals:**
- No usa logos, emojis personalizados de Telegram ni imágenes.
- No cambia botones, prosa, la extensión ni la base.

## Decisions

**D1. Diccionario aparte.** `EMOJI_PLATAFORMA = {"computrabajo": "🔵", "magneto": "🟢", "elempleo": "🩵"}` junto a `NOMBRES_PLATAFORMA`; este último no se toca. Los colores son una convención del dueño, no la identidad oficial de las marcas.

**D2. `nombre_con_emoji(plataforma)` en `textos.py`.** Devuelve «🟢 Magneto»; sin emoji registrado devuelve el nombre solo; con plataforma vacía, cadena vacía. Sin escapar (el emoji y los nombres fijos son seguros); el escape de nombres no registrados lo sigue haciendo quien arma la línea.

**D3. Dos puntos de uso.** `linea_empresa` (cabecera y confirmación, que ya la comparten) y `tarjeta.lineas` para el nombre pasado a `_linea_cuenta`. El resto de usos de `NOMBRES_PLATAFORMA` queda igual. En `lineas`, el `nombre` también alimenta `_linea_cuenta`; los botones de `botones()` siguen con el nombre plano.

**Riesgo:** el emoji de color podría confundirse con un estado (🟢 como «listo»). Se acepta; solo aparece pegado al nombre del portal.
