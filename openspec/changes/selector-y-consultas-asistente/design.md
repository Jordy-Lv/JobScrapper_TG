# Design

## Context

Estado actual, verificado en el código el 2026-10-15 y trasladado sin cambios desde `aprendizaje-primero-canal-y-consultas`:

- **Botones del canal.** `radar/publicacion.py` agrega a cada mensaje un botón `pv:<id_corto>` por vacante (`etiqueta_boton`). El bot asistente atiende el toque en `Conversacion.al_toque_canal`. El enlace `?start=v_<id>` solo se usa para el registro.
- **Asistente.** El índice `vacantes` de `asistente.db` copia de `vistas` la clave, la fuente, el título, la empresa, el enlace, la categoría y `enviada_en`. Se lee en solo lectura y solo tiene las vacantes enviadas.
- **Ya migrado por la fase 1.** La tarea 1.1 de `aprendizaje-primero-canal-y-consultas` creó la tabla `lotes_canal` y las columnas `publicada`, `destacada` y `area` de `vistas`. Este change solo las **escribe y lee**.
- **Change abierto.** `dividir-conversacion-asistente` (0/20) va a partir `conversacion.py` en un paquete con registro de botones.

## Goals / Non-Goals

**Goals:**
- Un solo botón por mensaje del canal y un selector reutilizable en el asistente: lo usan el canal y `/buscar`.
- Consultar las ofertas publicadas con filtros cerrados y, opcionalmente, con una frase traducida por DeepSeek.

**Non-Goals:**
- Personalizar las destacadas por usuario con la afinidad del CV. El canal es compartido.
- Notificaciones o alertas a partir de una consulta.
- Definir qué es una «destacada»: lo hace la fase 2 (`visibilidad-area-y-fecha`).

## Decisions

**1. El botón único abre un enlace al bot, sin editar el mensaje del canal.**
El botón es de tipo URL, `https://t.me/<bot>?start=l_<id_lote>`.
- Se descartó **expandir los botones en el mismo mensaje** (opción 1 del dueño). El teclado de un mensaje del grupo es compartido: al expandirlo, todos los miembros ven la lista y el ruido vuelve, ahora para todos. Además, hay una condición de carrera si dos personas tocan a la vez.
- Se descartó **un botón callback que responda con la URL**. Exige un viaje más al bot, y el enlace directo funciona también para quien nunca abrió el bot.
- Lo que hace hoy el toque en el canal (postulación automática sin salir del canal) pasa al selector. Es un paso más para el usuario registrado, a cambio de un canal limpio.
- `NotificadorBotAPI.enviar_mensaje` acepta botones `url:` con la misma convención que `asistente/bot.py:teclado`.

**2. El lote se guarda en `vacantes.db`, y el asistente lo lee en solo lectura.**
- Tabla `lotes_canal(id TEXT PRIMARY KEY, claves_json TEXT, destacadas_json TEXT, enviado_en TEXT)`, ya creada por la fase 1.
- El `id` es `id_corto("|".join(claves))`: 12 caracteres base32, válidos en un payload de `start`.
- `publicar` la escribe solo después de que Telegram confirma el envío, en la misma transacción que `registrar_vista`.
- El asistente ya abre `vacantes.db` en solo lectura para el índice. `Indice.resolver_lote(id)` lee el lote, indexa sus claves si faltan y devuelve las `VacanteIndexada` en orden.
- Se descartó codificar las claves en el payload: no caben en 64 caracteres. También se descartó guardarlo en `asistente.db`: el radar no escribe en esa base.

**3. Selector como tarjeta única con estado en `kv`.**
- Sigue el patrón de las tarjetas existentes: un `message_id` editable y su estado en `kv` (`selector:<usuario_id>` → `{origen: "lote"|"consulta", ids, pagina}`).
- Botones `sel:<n>` para elegir, `selpag:<n>` para paginar y `selx` para cerrar.
- Elegir llama a `procesar_toque(usuario, id_corto, origen="selector")`, sin cambiar ese flujo.
- Si `dividir-conversacion-asistente` se aplica antes, el selector es un módulo propio del paquete con `@boton("sel")`. Si no, va en un archivo nuevo, `asistente/selector.py`, con la lógica pura (páginas, texto y botones), y `conversacion.py` solo lo conecta.
- `pv:` y `v_` se siguen atendiendo (compatibilidad). El lote pendiente durante el alta reutiliza el mecanismo de `fijar_vacante_pendiente`, con un prefijo `l_`.

**4. Consultas: filtros cerrados, código que consulta y DeepSeek solo para traducir.**
- **Índice.** Gana columnas: `ubicacion`, `modalidad`, `publicada`, `destacada` y `area`. Se copian de `vistas` en `indexar`, con la migración 3 de `asistente.db`. Las filas viejas quedan con NULL y se reindexan si su vista aún existe.
- **Filtros.** `ConsultaVacantes` es un dataclass con campos: `nivel`, `areas`, `modalidad`, `dias`, `fuentes`, `solo_destacadas` y `texto`. Lo usan la tarjeta y la IA. La consulta es SQL parametrizado sobre `vacantes`.
- **IA.** Se reutiliza el cliente HTTP de DeepSeek del radar (`ia.base_url`, `DEEPSEEK_API_KEY`), con un prompt corto que devuelve `ConsultaVacantes` en JSON. El uso se cuenta en `asistente.db`, con `asistente.consultas.ia_usuario_dia` (5) y `ia_servidor_dia` (200). La salida se valida con pydantic y lo desconocido se descarta.
- **Restricción del proyecto.** El LLM no busca ni envía vacantes: solo convierte texto en filtros. Es un uso nuevo de la IA, tan acotado como el del clasificador.
- **Privacidad.** Se envía solo la frase, recortada y sin correos, teléfonos ni documentos (regex). Ningún dato del perfil va a la IA. No cambia la política de datos: no se envía nada del usuario más allá de su consulta. Ver «Open Questions».
- Se descartó usar la IA del usuario (Gemini con su clave): obligaría a tener clave para buscar y daría resultados distintos según el proveedor.

**5. Orden de implementación.** Primero el botón único y el selector, después las consultas, porque estas reutilizan el selector. Cada bloque se despliega por separado.

## Risks / Trade-offs

- **[El paso extra del selector]** → Al usuario registrado le cuesta un toque más. Se compensa abriendo el selector directo en el bot, con la vacante elegida en un toque.
- **[DeepSeek interpreta mal una frase]** → La tarjeta de filtros muestra lo que entendió, y el usuario lo corrige con los botones.
- **[Choque con `dividir-conversacion-asistente`]** → La lógica del selector y de las consultas va en módulos nuevos y puros. `conversacion.py` solo gana despachos cortos y la división los mueve sin conflicto.
- **[La definición de «destacada» cambia en la fase 2]** → El filtro «solo destacadas» y la marca ⭐ leen la columna `destacada` de `vistas`, no calculan nada. Cambiar el criterio no toca este change.

## Migration Plan

1. `asistente.db` pasa al esquema 3, con columnas nuevas en `vacantes`. La migración es aditiva.
2. Configuración: agregar `asistente.consultas` a `config.yaml`.
3. Despliegue por bloques, con `git pull` en `~/buscador-vacantes` del Fedora y `systemctl --user restart buscador-asistente`.
4. **Rollback.** `git revert` del bloque. Las columnas nuevas se ignoran sin daño. Los mensajes del canal ya publicados con botón `pv:` se siguen atendiendo.

## Open Questions

- ¿El dueño quiere que la política de datos mencione que la frase de `/buscar` se procesa con DeepSeek? Cambiar el texto obliga a subir `politica.version` y a que todos acepten de nuevo. Por eso, mientras no se decida, solo se avisa en la ayuda de `/buscar`.
- Los criterios de «destacada» y el uso de la fecha exacta de publicación quedan definidos por la fase 2; revisar los specs de este change contra ella antes de aplicarlo.
