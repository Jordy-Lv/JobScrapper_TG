## Context

`tarjeta_postulacion._cabecera(d)` arma título (negrita) y empresa; todas las fases la usan (`texto`, `_texto_confirmacion`). `Datos.plataforma` ya viene de la base y `Datos.portal` ya da el nombre legible (`t.NOMBRES_PLATAFORMA`), con «el portal» como respaldo. La confirmación con resumen se arma aparte en `resumen_postulacion.tarjeta`, que ya calcula `_portal(d)`. Las vistas «Respuestas» y «De qué trata» tienen su propio encabezado y no cambian.

## Goals / Non-Goals

**Goals:**
- Que el nombre del portal se vea en cada estado de la card, sin mensajes nuevos.
- Un solo punto de verdad para la cabecera.

**Non-Goals:**
- No cambia botones, fases, textos del cuerpo ni la barra.
- No agrega logos ni emojis por portal.

## Decisions

**D1. Segunda línea «Empresa · Portal».** Va en la línea de la empresa, separada por « · », en lugar de una línea nueva: la card no crece y se lee como metadato de la vacante. Sin empresa, la línea es solo el portal. Alternativa descartada: línea propia con emoji (📍) o en cursiva; más ruido y rompe el «estilo sobrio» del spec.

**D2. Solo con plataforma conocida.** Se usa `NOMBRES_PLATAFORMA.get(plataforma)`; si `plataforma` es `None` o vacía no se agrega nada (no se usa el respaldo «el portal», que sonaría raro en la cabecera). Una plataforma no registrada en el diccionario se muestra tal cual, escapada.

**D3. Confirmación incluida.** `resumen_postulacion.tarjeta` reutiliza el mismo armado de línea (función pequeña compartida en `textos.py` o `tarjeta_postulacion`, sin crear una dependencia circular: hoy `tarjeta_postulacion` importa `resumen_postulacion`, así que la función vive en `textos.py`).

**Riesgo:** la cita de confirmación repite el portal («Magneto confirmó…»). Se acepta: la cabecera identifica la vacante, la cita da el estado.
