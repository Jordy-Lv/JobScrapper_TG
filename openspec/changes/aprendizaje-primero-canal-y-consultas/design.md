# Design

## Context

Estado actual, verificado en el código el 2026-10-15:

- **Botones del canal.** `radar/publicacion.py` agrega a cada mensaje un botón `pv:<id_corto>` por vacante (`etiqueta_boton`). El bot asistente atiende el toque en `Conversacion.al_toque_canal`. El enlace `?start=v_<id>` solo se usa para el registro.
- **Formato.** `radar/formato.py` arma todas las fichas iguales: título, empresa · lugar, salario, fuente · antigüedad. Las ordena por categoría (`TITULOS_CATEGORIA`) y por fecha.
- **Descartes.** `corrida._aplicar` solo suma el motivo en `resumen.descartes`. Una vacante rechazada no queda en `vistas` ni en otra tabla. Las rechazadas por la IA quedan en `clasificaciones`, pero solo con la huella, sin título ni enlace. Por eso hoy no se puede saber por qué no llegó una vacante concreta.
- **Nivel.** No hay ningún interruptor de nivel. El núcleo ya es solo de prácticas (`priorizar-practicas-aprendiz`), pero la cola larga tiene unas 45 consultas junior de un total de unas 75. El prompt del clasificador acepta junior, y `categoria_por_terminos` manda a su área lo que no es práctica.
- **Reglas que pueden perder aprendizaje** (hipótesis, `filtros.py`):
  - **H1.** `_anios_excesivos` mira cada frase de la descripción que contenga «experiencia». «Empresa con más de 20 años de experiencia» rechaza la vacante.
  - **H2.** `exclusion_seniority` se aplica al título antes que cualquier evidencia de práctica: «Practicante … Coordinador …» se rechaza.
  - **H3.** El paso 4 rechaza «práctica sin TI» con cualquier descripción. elempleo solo trae el fragmento `li.result-info-hover-li-description`, y Magneto y SPE recortan a `MAX_DESCRIPCION`.
  - **H4.** `evidencia_practica` no incluye «sena», «semillero» ni «programa de talento», aunque `nivel.practica` sí los incluye.
  - **H5.** `huella()` usa título y empresa, y `ya_vista` la compara durante `dias_vistas: 90`. Una empresa que vuelve a publicar «Aprendiz SENA Sistemas» un mes después se descarta como duplicada.
  - **H6.** Las dudosas sin respuesta de la IA vencen a las 24 h (`horas_vencimiento_pendiente`) y se pierden sin dejar rastro, salvo un `log.warning`.
  - **H7.** Computrabajo no trae descripción ni detalle: una oferta de otra ciudad sin modalidad en la tarjeta se rechaza como `presencial_fuera`. Es la política vigente; solo se mide.
- **IA.** `ClienteIA.chat_json` devuelve `realizada=False` por tope, saldo o falta de clave. El clasificador guarda la dudosa como pendiente. No hay incidente de IA: el reportero solo cubre fuentes, red y Telegram.
- **Asistente.** El índice `vacantes` de `asistente.db` copia de `vistas` la clave, la fuente, el título, la empresa, el enlace, la categoría y `enviada_en`. Se lee en solo lectura y solo tiene las vacantes enviadas.
- **Change abierto.** `dividir-conversacion-asistente` (0/20) va a partir `conversacion.py` en un paquete con registro de botones.

## Goals / Non-Goals

**Goals:**
- Que ningún descarte de una vacante con evidencia de práctica sea invisible para el dueño.
- Corregir cada hipótesis H1–H6 que el corpus de vacantes perdidas confirme. Ninguna se corrige «a ciegas».
- Pausar el nivel junior con un solo interruptor, reversible y sin código muerto.
- Un solo botón por mensaje del canal y un selector reutilizable en el asistente: lo usan el canal y `/buscar`.

**Non-Goals:**
- Cambiar la política de ubicación: Cartagena presencial, o remoto o híbrido para el resto de Colombia.
- Pedir el detalle de Computrabajo o elempleo. Si el corpus muestra que H3 o H7 pierden muchas vacantes, va en otro change.
- Personalizar las destacadas por usuario con la afinidad del CV. El canal es compartido y las destacadas son las mismas para todos.
- Notificaciones o alertas a partir de una consulta.

## Decisions

**1. El botón único abre un enlace al bot, sin editar el mensaje del canal.**
El botón es de tipo URL, `https://t.me/<bot>?start=l_<id_lote>`.
- Se descartó **expandir los botones en el mismo mensaje** (opción 1 del dueño). El teclado de un mensaje del grupo es compartido: al expandirlo, todos los miembros ven la lista y el ruido vuelve, ahora para todos. Además, hay una condición de carrera si dos personas tocan a la vez.
- Se descartó **un botón callback que responda con la URL**. Exige un viaje más al bot, y el enlace directo funciona también para quien nunca abrió el bot.
- Lo que hace hoy el toque en el canal (postulación automática sin salir del canal) pasa al selector. Es un paso más para el usuario registrado, a cambio de un canal limpio.
- `NotificadorBotAPI.enviar_mensaje` acepta botones `url:` con la misma convención que `asistente/bot.py:teclado`.

**2. El lote se guarda en `vacantes.db`, y el asistente lo lee en solo lectura.**
- Nueva tabla `lotes_canal(id TEXT PRIMARY KEY, claves_json TEXT, destacadas_json TEXT, enviado_en TEXT)`.
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

**4. `alcance.junior.activo` se aplica en un solo punto, después del guardarraíl.**
- `corrida` gana `_aplicar_alcance(aceptadas)`. Va después de `_aplicar_guardarrail` y antes de publicar. Descarta con `nivel_pausado` todo lo que no sea `Categoria.PRACTICAS`.
- `Filtros.evaluar` no cambia. Así, encender junior no toca las reglas, y la prueba de casos reales sigue evaluando categorías.
- **Búsqueda.** `palabras_clave.junior` es un grupo de la cola larga con su propia posición en `rotacion`. Se excluye en `grupos_cola` y `calcular_lote` cuando el nivel está pausado. Al reactivarlo, retoma donde iba.
- **GetOnBoard.** `seniorities` pasa a `[no_experience]` con el nivel pausado.
- **LinkedIn.** Mantiene `f_E=1,2`: en LinkedIn muchos aprendices SENA se publican como «nivel de entrada».
- **Prompt.** `clasificador.prompt_sistema` gana un marcador `{alcance}` que se reemplaza por `clasificador.textos_alcance.practicas` o por `practicas + junior`. `version_prompt` se calcula sobre el texto ya resuelto, así que cambiar el alcance renueva la caché sin código extra.
- **Formato.** `TITULOS_CATEGORIA` conserva las categorías junior; simplemente no reciben vacantes.
- Se descartó rechazar junior dentro de `Filtros`: el guardarraíl puede mover una práctica a un área, y el alcance tiene que verse después de esa corrección.

**5. Auditoría en una tabla `descartes` con upsert por clave.**
- Esquema:

  ```
  descartes(clave PK, huella, fuente, keyword, titulo, empresa, url, ubicacion, modalidad,
  etapa, motivo, detalle, veces, primera_vez, ultima_vez)
  ```

- Se escribe en cinco puntos:
  - `_aplicar`, al rechazar por reglas;
  - `_clasificar`, con las rechazadas por la IA y su `motivo`;
  - `_aplicar_guardarrail`, al rechazar;
  - `_aplicar_alcance`;
  - las vencidas del clasificador y de la cola de detalle.
- Retención con `estado.dias_descartes: 14`, limpiada en `Estado.limpiar`. Volumen estimado: unas 300 crudas por corrida, que con el upsert dejan pocos miles de filas vivas.
- `buscador.py diagnosticar` busca la URL normalizada, la clave o el título (`LIKE`) en `vistas`, `por_enviar`, `pendientes`, `pendientes_detalle` y `descartes`. Si no hay nada, resume `intentos` de la fuente que se deduce del dominio.
- `--evaluar` construye una `Vacante` y llama a `Filtros.evaluar` y `guardarrail_practicas`. Con `--con-ia` llama al clasificador sin guardar caché, usando un `Estado` en memoria.

**6. Correcciones de reglas, cada una con su prueba y su caso real.**
- **H1.** Antes de buscar años, se quitan las frases de trayectoria. Hay una lista configurable `filtros.frases_trayectoria` («años de experiencia en el sector», «años en el mercado», «trayectoria», «empresa con», «contrato de aprendizaje por», «duración»). Además, el valor solo cuenta si la frase menciona la experiencia del candidato o es un requisito.
- **H2.** En `evaluar`, si `coincidencias(self._evidencia_practica, titulo)`, un término de seniority deja la vacante como dudosa con el detalle «seniority en práctica», en lugar de rechazarla.
- **H3.** `Vacante` no sabe si la descripción está completa. Se usa `len(descripcion) >= filtros.min_caracteres_descripcion_completa` o `permite_detalle` con el detalle ya leído. Se descartó marcar la completitud por fuente: SPE a veces trae textos largos y a veces cortos.
- **H4.** Se agregan términos a `filtros.nivel.evidencia_practica`.
- **H5.** `Estado.ya_vista` compara la huella solo con las vistas de menos de `republicar_tras_dias`. La comparación por clave sigue sin límite.
- **H6.** El clasificador vence las pendientes con `horas_vencimiento_practicas` cuando el título tiene evidencia de práctica. Al vencer, se registran en `descartes`.
- **Corpus.** `tests/fixtures/casos_aprendizaje_perdidos.yaml`, con el formato de `casos_reales_2026-10.yaml`. Se arma con las vacantes que el dueño encuentra a mano, más su diagnóstico.

**7. DeepSeek verificable.**
- **`buscador.py ia --verificar`**
  - Consulta el saldo y una llamada mínima.
  - Clasifica `tests/fixtures/clasificador_oro.yaml`: unas 25 dudosas etiquetadas (aprendiz con TI en la descripción, aprendiz genérico, modalidad confirmada o no, junior con el nivel pausado).
  - Imprime los aciertos y los errores, sin escribir en `clasificaciones`.
  - Gasta una llamada de presupuesto, con el propósito `verificacion`.
- **Incidente.** `ia:clasificador` se agrega a `incidentes.TIPOS` con su propia regla de apertura y cierre. Los datos salen de `ResultadoClasificacion` (`motivo_fallo`, `pendientes` y `vencidas`) y de `saldo_bajo()`.
- **Resumen.** `resumen.py` agrega `ia_uso` por motivo para `proposito='clasificador'`. Las prácticas rechazadas por la IA salen de `descartes` (etapa `ia`) con evidencia en el título.

**8. Destacadas: criterio en el radar, presentación en `formato`.**
- `publicacion.destacadas`:

  ```
  {activo, practica_en_titulo, area_en_titulo, ubicacion_preferida, max_dias: 3}
  ```

- `Filtros.es_destacada(vacante, ahora) -> list[str]` devuelve los criterios cumplidos, que se convierten en la línea de insignias. Si la lista está vacía, la vacante no es destacada.
- `componer` arma primero el bloque «⭐ DESTACADAS» con `ficha_completa` y luego las categorías con `ficha_compacta`.
- La ubicación preferida es la ciudad base o remoto: la misma lógica de `_geografia`, expuesta como un método público.
- Se descartó un mensaje aparte para cada destacada: multiplica los mensajes, que es justo el ruido que se quiere quitar.

**9. Consultas: filtros cerrados, código que consulta y DeepSeek solo para traducir.**
- **Índice.** Gana columnas: `ubicacion`, `modalidad`, `publicada`, `destacada` y `area`. Se copian de `vistas` en `indexar`, con la migración 3 de `asistente.db`. Las filas viejas quedan con NULL y se reindexan si su vista aún existe.
- **Filtros.** `ConsultaVacantes` es un dataclass con campos: `nivel`, `areas`, `modalidad`, `dias`, `fuentes`, `solo_destacadas` y `texto`. Lo usan la tarjeta y la IA. La consulta es SQL parametrizado sobre `vacantes`.
- **IA.** Se reutiliza el cliente HTTP de DeepSeek del radar (`ia.base_url`, `DEEPSEEK_API_KEY`), con un prompt corto que devuelve `ConsultaVacantes` en JSON. El uso se cuenta en `asistente.db`, con `asistente.consultas.ia_usuario_dia` (5) y `ia_servidor_dia` (200). La salida se valida con pydantic y lo desconocido se descarta.
- **Restricción del proyecto.** El LLM no busca ni envía vacantes: solo convierte texto en filtros. Es un uso nuevo de la IA, tan acotado como el del clasificador.
- **Privacidad.** Se envía solo la frase, recortada y sin correos, teléfonos ni documentos (regex). Ningún dato del perfil va a la IA. No cambia la política de datos: no se envía nada del usuario más allá de su consulta. Ver «Open Questions».
- Se descartó usar la IA del usuario (Gemini con su clave): obligaría a tener clave para buscar y daría resultados distintos según el proveedor.

**10. Orden de implementación.**
1. Auditoría y diagnóstico.
2. Corpus y reglas.
3. Alcance junior.
4. DeepSeek.
5. Destacadas.
6. Botón único y selector.
7. Consultas.

La auditoría va primero porque las correcciones de reglas dependen de sus datos, y el selector va antes de las consultas porque estas lo reutilizan. Cada bloque se despliega por separado.

## Risks / Trade-offs

- **[Pausar junior reduce el volumen del canal]** → Es lo que pidió el dueño. Lo pausado queda en `descartes` y se mide en el resumen. Reactivarlo es cambiar un `false` por un `true`.
- **[Más prácticas a la IA (H2, H3) → más costo]** → Son pocas: solo títulos con evidencia de práctica. El tope `presupuesto_dia.clasificador: 300` sobra, y dejar de clasificar junior libera llamadas.
- **[La republicación (H5) puede repetir una vacante que sigue abierta]** → Solo pasa con otra clave de la fuente y tras 30 días. Es configurable, y con `republicar_tras_dias: 0` se apaga.
- **[El paso extra del selector]** → Al usuario registrado le cuesta un toque más. Se compensa abriendo el selector directo en el bot, con la vacante elegida en un toque.
- **[`descartes` hace crecer `vacantes.db`]** → Hay upsert por clave y una retención de 14 días. Se vigila en el resumen con el número de filas.
- **[DeepSeek interpreta mal una frase]** → La tarjeta de filtros muestra lo que entendió, y el usuario lo corrige con los botones.
- **[Choque con `dividir-conversacion-asistente`]** → La lógica del selector y de las consultas va en módulos nuevos y puros. `conversacion.py` solo gana despachos cortos y la división los mueve sin conflicto.

## Migration Plan

1. **Esquemas.**
   - `vacantes.db` pasa a la siguiente versión de esquema, con las tablas `descartes` y `lotes_canal` y las columnas `publicada`, `destacada` y `area` en `vistas`.
   - `asistente.db` pasa al esquema 3, con columnas nuevas en `vacantes`.
   - Ambas migraciones son aditivas.
2. **Configuración.**
   - Mover las consultas junior de `cola_larga` a `palabras_clave.junior`.
   - Agregar `alcance.junior.activo: false`, `publicacion.destacadas`, `estado.dias_descartes`, `estado.republicar_tras_dias`, `clasificador.horas_vencimiento_practicas`, `clasificador.textos_alcance` y `asistente.consultas`.
3. **Despliegue por bloques**, con `git pull` en `~/buscador-vacantes` del Fedora y `systemctl --user restart buscador-asistente` cuando el bloque toca el asistente. El timer del radar toma el código en la siguiente corrida.
4. **Rollback.** `git revert` del bloque. Las tablas y columnas nuevas se ignoran sin daño. Para volver a publicar junior sin revertir, basta `alcance.junior.activo: true`.

## Open Questions

- ¿El dueño quiere que la política de datos mencione que la frase de `/buscar` se procesa con DeepSeek? Cambiar el texto obliga a subir `politica.version` y a que todos acepten de nuevo. Por eso, mientras no se decida, solo se avisa en la ayuda de `/buscar`.
- Los criterios exactos de «destacada» quedan con los valores por defecto del spec, y el dueño los ajusta en `config.yaml` tras ver una semana de publicaciones.
