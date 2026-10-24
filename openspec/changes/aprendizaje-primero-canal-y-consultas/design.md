# Design

## Context

Estado actual, verificado en el código el 2026-10-15:

- **Descartes.** `corrida._aplicar` solo suma el motivo en `resumen.descartes`. Una vacante rechazada no queda en `vistas` ni en otra tabla. Las rechazadas por la IA quedan en `clasificaciones`, pero solo con la huella, sin título ni enlace. Por eso hoy no se puede saber por qué no llegó una vacante concreta.
- **Nivel.** No hay ningún interruptor de nivel. «Sin experiencia», «primer empleo» y «recién egresado» están dentro de `filtros.nivel.junior` (`config.yaml`), así que no se pueden separar del nivel junior. El núcleo ya es solo de prácticas (`priorizar-practicas-aprendiz`), pero la cola larga tiene unas 45 consultas junior de un total de unas 75. El prompt del clasificador acepta junior, y `categoria_por_terminos` manda a su área lo que no es práctica.
- **Reglas que pueden perder aprendizaje** (hipótesis, `filtros.py`):
  - **H1.** `_anios_excesivos` mira cada frase de la descripción que contenga «experiencia». «Empresa con más de 20 años de experiencia» rechaza la vacante.
  - **H2.** `exclusion_seniority` se aplica al título antes que cualquier evidencia de práctica: «Practicante … Coordinador …» se rechaza.
  - **H3.** El paso 4 rechaza «práctica sin TI» con cualquier descripción. elempleo solo trae el fragmento `li.result-info-hover-li-description`, y Magneto y SPE recortan a `MAX_DESCRIPCION`.
  - **H4.** `evidencia_practica` no incluye «sena», «semillero» ni «programa de talento», aunque `nivel.practica` sí los incluye.
  - **H5.** `huella()` usa título y empresa, y `ya_vista` la compara durante `dias_vistas: 90`. Una empresa que vuelve a publicar «Aprendiz SENA Sistemas» un mes después se descarta como duplicada.
  - **H6.** Las dudosas sin respuesta de la IA vencen a las 24 h (`horas_vencimiento_pendiente`) y se pierden sin dejar rastro, salvo un `log.warning`.
  - **H7.** Computrabajo no trae descripción ni detalle: una oferta de otra ciudad sin modalidad en la tarjeta se rechaza como `presencial_fuera`. Es la política vigente; solo se mide.
- **IA.** `ClienteIA.chat_json` devuelve `realizada=False` por tope, saldo o falta de clave. El clasificador guarda la dudosa como pendiente. No hay incidente de IA: el reportero solo cubre fuentes, red y Telegram.
- **Reglas de experiencia.** `_anios_excesivos` solo reconoce cifras con «años» y «Experiencia:» en la misma línea. La regla 5 de `_por_titulo` acepta sin IA con TI en el título y un término de nivel en cualquier parte del texto, así que «mejores prácticas» en la descripción basta. `auxiliar` cuenta como nivel junior.
- **Fuera de este change.** El botón único, el selector y las consultas del asistente viven en `selector-y-consultas-asistente`. Las destacadas las reemplaza la fase 2 del plan de mejora.

## Goals / Non-Goals

**Goals:**
- Que ningún descarte de una vacante con evidencia de práctica sea invisible para el dueño.
- Corregir cada hipótesis H1–H6 que el corpus de vacantes perdidas confirme. Ninguna se corrige «a ciegas».
- Pausar el nivel junior con un solo interruptor, reversible y sin código muerto.
- Que al menos el 95 % de lo publicado sea práctica, aprendizaje o sin experiencia, y que ese porcentaje se mida en el resumen diario.
- Endurecer las reglas para que no se publiquen vacantes con experiencia, sin perder aprendices: lo que deja de aceptarse queda dudoso, no rechazado.

**Non-Goals:**
- Cambiar la política de ubicación: Cartagena presencial, o remoto o híbrido para el resto de Colombia.
- Pedir el detalle de Computrabajo o elempleo. Si el corpus muestra que H3 o H7 pierden muchas vacantes, va en otro change.
- El botón único, el selector y `/buscar` (`selector-y-consultas-asistente`) y las destacadas (fase 2).
- Reactivar el nivel junior: queda para cuando la fase 1 lleve dos semanas cumpliendo la métrica del 95 %.

## Decisions

**1–3. Botón único, lote del canal y selector.** Movidas a `selector-y-consultas-asistente`. La migración de `lotes_canal` ya está hecha por la tarea 1.1 de este change.

**4. `alcance.junior.activo` se aplica en un solo punto, después del guardarraíl.**
- **Niveles.** Cada vacante tiene un `nivel` (`practica`, `sin_experiencia`, `junior`, `otro`) que calcula `Filtros.nivel_de(vacante)`:
  - `practica`: términos de `filtros.nivel.practica` en el título;
  - `sin_experiencia`: términos del nuevo grupo `filtros.nivel.sin_experiencia` y **ningún año de experiencia exigido**; gana sobre `junior` cuando ambos aparecen («Desarrollador Junior (sin experiencia)»);
  - `junior`: términos de `filtros.nivel.junior` (junior, jr, entry level);
  - `otro`: el resto.
- `filtros.nivel.sin_experiencia` se separa de `filtros.nivel.junior` para que apagar junior no apague «sin experiencia». `categoria_por_terminos` publica las de nivel `practica` y `sin_experiencia` en `Categoria.PRACTICAS`; su área sale de `categoria_por_area` (E6).
- `corrida` gana `_aplicar_alcance(aceptadas)`. Va después de `_aplicar_guardarrail` y antes de publicar. Con el nivel pausado, descarta con `nivel_pausado` todo lo que no tenga nivel `practica` ni `sin_experiencia`.
- `Filtros.evaluar` no cambia. Así, encender junior no toca las reglas, y la prueba de casos reales sigue evaluando categorías.
- **Búsqueda.** `palabras_clave.junior` es un grupo de la cola larga con su propia posición en `rotacion`. Se excluye en `grupos_cola` y `calcular_lote` cuando el nivel está pausado. Al reactivarlo, retoma donde iba.
- **GetOnBoard.** `seniorities` pasa a `[no_experience]` con el nivel pausado.
- **LinkedIn.** Hoy `f_E=1,2`. El nivel de entrada (`2`) trae sobre todo profesionales, pero en LinkedIn muchos aprendices SENA se publican como «nivel de entrada». Se decide con datos: con `descartes` se mide cuántas vacantes con `f_E=2` llegan a ser prácticas o sin experiencia; si son pocas, pasa a `f_E=1`, y si cae la cobertura, se vuelve a `1,2` y filtran la regla y la IA.
- **Prompt.** `clasificador.prompt_sistema` gana un marcador `{alcance}` que se reemplaza por `clasificador.textos_alcance.practicas` («prácticas, aprendizaje y sin experiencia (0 años)») o por `practicas + junior`. `version_prompt` se calcula sobre el texto ya resuelto, así que cambiar el alcance renueva la caché sin código extra.
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
- **Resumen.** `resumen.py` agrega `ia_uso` por motivo para `proposito='clasificador'`. Las prácticas rechazadas por la IA salen de `descartes` (etapa `ia`) con evidencia en el título. El porcentaje de lo publicado por nivel sale de la columna `nivel` de `vistas` (últimas 24 h): es la métrica de esta fase, con meta de al menos 95 % entre `practica` y `sin_experiencia`.

**8. Endurecimiento de reglas (E1–E6).** Cada cambio tiene su prueba y se valida contra `casos_reales_2026-10.yaml` y el corpus de aprendizaje, para no perder aprendices. Lo que deja de aceptarse queda dudoso (va a la IA), salvo el rechazo por años exigidos.
- **E1.** La regla 5 de `Filtros._por_titulo` acepta sin IA solo si el término de nivel está en el título, o si la descripción trae `evidencia_practica_descripcion` o «sin experiencia». Si no, dudosa.
- **E2.** `auxiliar` sale de `filtros.nivel.junior` y queda solo como disparador de dudosa.
- **E3.** `frases_ignoradas` gana «mejores prácticas», «prácticas de desarrollo», «prácticas ágiles» y «equipo junior».
- **E4.** `_anios_excesivos` detecta los años en letra («dos años»), en meses (≥ 12) y «Experiencia:» con el número en la línea siguiente. Convive con H1: primero se quitan las frases de trayectoria y después se buscan los años.
- **E5.** Con junior apagado, el umbral baja a 1 año: `anios_experiencia_excluidos_desde` se lee del alcance. Se aceptan meses (≤ 6) y la experiencia «deseable» u «opcional». En un rango cuenta el mínimo.
- **E6.** `Vacante.area` y `Vacante.nivel` se calculan para todas las aceptadas, también las prácticas, y se guardan en `vistas` (`area` ya existe desde 1.1; `nivel` es una columna aditiva nueva). La fase 2 usa el área.
- Se descartó mover estas reglas a la IA: son deterministas, baratas y verificables con fixtures.

**9. Consultas del asistente.** Movidas a `selector-y-consultas-asistente`.

**10. Orden de implementación.**
1. Auditoría y diagnóstico.
2. Corpus y reglas (H1–H6).
3. Alcance de prácticas y sin experiencia.
4. DeepSeek.
5. Endurecimiento (E1–E6).
6. Verificación en producción.

La auditoría va primero porque las correcciones de reglas dependen de sus datos. El endurecimiento va después del corpus, que es la red de seguridad contra los falsos negativos. Cada bloque se despliega por separado.

## Risks / Trade-offs

- **[Pausar junior reduce el volumen del canal]** → Es lo que pidió el dueño. Lo pausado queda en `descartes` y se mide en el resumen. Reactivarlo es cambiar un `false` por un `true`.
- **[Más prácticas a la IA (H2, H3) → más costo]** → Son pocas: solo títulos con evidencia de práctica. El tope `presupuesto_dia.clasificador: 300` sobra, y dejar de clasificar junior libera llamadas.
- **[Al endurecer las reglas se pierden aprendices (falsos negativos)]** → Todo pasa por el corpus del bloque 2. Lo que deja de aceptarse queda dudoso (va a la IA), no rechazado.
- **[Con `f_E=1`, LinkedIn trae muy poco]** → Se mide primero con `descartes`. Si cae la cobertura, se vuelve a `1,2`.
- **[Cambiar el prompt invalida la caché de clasificaciones]** → Es lo esperado. El primer día habrá más llamadas, dentro del tope de 300.
- **[La republicación (H5) puede repetir una vacante que sigue abierta]** → Solo pasa con otra clave de la fuente y tras 30 días. Es configurable, y con `republicar_tras_dias: 0` se apaga.
- **[`descartes` hace crecer `vacantes.db`]** → Hay upsert por clave y una retención de 14 días. Se vigila en el resumen con el número de filas.

## Migration Plan

1. **Esquemas.**
   - `vacantes.db` pasa a la siguiente versión de esquema, con las tablas `descartes` y `lotes_canal` y las columnas `publicada`, `destacada` y `area` en `vistas` (tarea 1.1, hecha), y la columna `nivel` en `vistas` (bloque 5).
   - La migración es aditiva.
2. **Configuración.**
   - Mover las consultas junior de `cola_larga` a `palabras_clave.junior`.
   - Separar `filtros.nivel.sin_experiencia` de `filtros.nivel.junior`.
   - Agregar `alcance.junior.activo: false`, `estado.dias_descartes`, `estado.republicar_tras_dias`, `clasificador.horas_vencimiento_practicas`, `clasificador.textos_alcance`, `filtros.frases_trayectoria` y `filtros.min_caracteres_descripcion_completa`.
3. **Despliegue por bloques**, con `git pull` en `~/buscador-vacantes` del Fedora. El timer del radar toma el código en la siguiente corrida.
4. **Rollback.** `git revert` del bloque. Las tablas y columnas nuevas se ignoran sin daño. Para volver a publicar junior sin revertir, basta `alcance.junior.activo: true`.

## Open Questions

- ¿Qué pasa con `lotes_canal` y la columna `destacada`, ya migradas en 1.1 pero sin uso en este change? Se conservan: son aditivas, las usa `selector-y-consultas-asistente` y la fase 2 puede reutilizar `destacada` con su propio criterio.
- ¿Se vuelve a evaluar el nivel junior? Propuesta pendiente del dueño: tras dos semanas cumpliendo la métrica del 95 %.
