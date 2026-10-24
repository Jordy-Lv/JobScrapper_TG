# Tasks

## 1. Auditoría de descartes y diagnóstico (🟡)

- [x] 1.1 Migrar `comun/estado.py` a la siguiente versión de esquema:
  - tabla `descartes` según design §5;
  - tabla `lotes_canal` según design §2;
  - columnas `publicada`, `destacada` y `area` en `vistas`;
  - limpieza de `descartes` con `estado.dias_descartes` (14) en `Estado.limpiar`, y de `lotes_canal` con `dias_vistas`.

  Agregar `dias_descartes` a `config.Estado`. Verificar en `tests/comun/test_estado.py` que una base del esquema anterior con datos migra sin perder filas, que una base nueva nace en el esquema nuevo y que la limpieza borra un descarte de 15 días.
- [x] 1.2 Agregar `Estado.registrar_descarte(vacante, huella, etapa, motivo, detalle, momento)`, con upsert por clave que sube `veces` y `ultima_vez`. Llamarlo desde `corrida._aplicar` (etapa `reglas`), desde `_clasificar` con las rechazadas por la IA y su motivo (etapa `ia`), desde `_aplicar_guardarrail` (etapa `guardarrail`) y desde las vencidas del clasificador y de la cola de detalle (etapa `vencida`). Nada se escribe en dry-run, seed ni modo prueba. Verificar en `tests/radar/test_buscador.py` que una corrida con una vacante de cada caso deja un registro por etapa, y que la misma vacante en dos corridas deja `veces = 2`.
- [x] 1.3 Implementar `buscador.py diagnosticar <url | título>` (design §5): búsqueda por URL normalizada, clave o título en `vistas`, `por_enviar`, `pendientes`, `pendientes_detalle` y `descartes`. Sin coincidencias, mostrar el resumen de `intentos` de los últimos 3 días de la fuente que corresponde al dominio. El comando abre la base en solo lectura. Verificar con pruebas en `tests/radar/test_punto_entrada.py` para «publicada», «descartada por reglas», «pendiente de IA» y «nunca vista».
- [x] 1.4 Agregar `diagnosticar --evaluar --titulo … [--empresa --ubicacion --modalidad --descripcion --fuente] [--con-ia]`: veredicto, motivo, categoría y guardarraíl (el alcance se agrega en 3.4, cuando exista `alcance.junior`). Con `--con-ia` se usa un `Estado` en memoria, sin escribir en la caché. Verificar con una prueba que evalúa «Aprendiz SENA Tecnólogo ADSO» y con una prueba con respx de `--con-ia` que no toca `clasificaciones`.
- [x] 1.5 Documentar `diagnosticar` en `README.md` (sección de operación), con dos ejemplos. Verificar que los ejemplos corren tal como están escritos contra una copia de `data/vacantes.db`.

## 2. Corpus de aprendizaje perdido y corrección de reglas (🔴)

> Tarea pesada: recomendar sesión nueva antes de empezarla y al terminarla.

- [ ] 2.1 👤 Desplegar el bloque 1 en el Fedora y dejar correr al menos 24 h. Mientras tanto, el dueño reúne de 15 a 30 enlaces de vacantes de aprendizaje, contrato de aprendizaje, prácticas o pasantías de TI que encontró a mano y que no llegaron al canal. Verificar que hay una lista con enlace, fuente y fecha de cada una.
- [ ] 2.2 Pasar cada enlace por `buscador.py diagnosticar` en el servidor y clasificar la causa en una tabla: no buscada, buscada pero fuera de las páginas leídas, regla y motivo, IA, vencida o duplicada. Guardar la tabla en `docs/radar/diagnostico-aprendizaje-perdido.md`, con la proporción por causa y qué hipótesis (H1–H7 del design) confirma cada caso. Verificar que cada enlace de 2.1 tiene una causa asignada.
- [ ] 2.3 Crear `tests/fixtures/casos_aprendizaje_perdidos.yaml` con los casos de 2.2, más un caso sintético por cada hipótesis H1–H6, y el test que lo recorre en `tests/radar/test_casos_reales.py`. Marcar con `xfail` los casos que fallan hoy. Verificar que `uv run pytest tests/radar/test_casos_reales.py` corre y que los `xfail` coinciden con las causas de 2.2.
- [ ] 2.4 H1: agregar `filtros.frases_trayectoria` y excluir de `_anios_excesivos` las frases de trayectoria de la empresa y de duración del contrato. Verificar con los escenarios de «Los años de la empresa no cuentan como experiencia exigida» en `test_filtros.py`, sin regresión en `test_casos_reales.py`.
- [ ] 2.5 H2: un término de seniority en un título con evidencia de práctica deja la vacante como dudosa. Verificar con el escenario «Práctica en un área de coordinación» y con que «Desarrollador Senior» se siga rechazando.
- [ ] 2.6 H3: agregar `filtros.min_caracteres_descripcion_completa` (400). El rechazo «práctica sin TI» solo se aplica con la descripción completa. Verificar con los escenarios de «"Práctica sin TI" solo con la descripción completa» y actualizar los casos del fixture `casos_reales_2026-10.yaml` que dependían del rechazo con descripción corta.
- [ ] 2.7 H4: ampliar `filtros.nivel.evidencia_practica` en `config.yaml` («sena», «semillero», «programa de talento», «práctica universitaria», «estudiante en práctica», «en formación»). Verificar con el escenario «Título con SENA sin "aprendiz"» y con que «Ingeniero IBM Sterling B2B» siga sin evidencia.
- [ ] 2.8 H5: agregar `estado.republicar_tras_dias` (30). `Estado.ya_vista` compara la huella solo con las vistas enviadas dentro de esa ventana, y la clave sin límite. Verificar en `test_estado.py` los escenarios «Nueva cohorte de aprendices» y «Copia en otra fuente», y que con 0 queda el comportamiento anterior.
- [ ] 2.9 Corregir lo que 2.2 haya mostrado fuera de H1–H6, y quitar los `xfail` de 2.3. Si una causa exige otro change (por ejemplo, el detalle de Computrabajo por H7), anotarla en el documento de 2.2 en lugar de implementarla aquí. Verificar que `uv run pytest` pasa completo sin `xfail` en el corpus y que `uv run ruff check` y `uv run ruff format --check` no reportan nada.

## 3. Alcance de prácticas y sin experiencia, con junior pausado (🟡)

- [ ] 3.1 Agregar `alcance.junior.activo` (por defecto `false`) a `config.py` y `palabras_clave.junior` como grupo propio. Mover a `palabras_clave.junior` las consultas junior de `cola_larga`: las que tienen «junior», «jr», «entry level» o ningún término de práctica. Dejar en la cola larga solo las de práctica por rol. Agregar al núcleo los términos del spec «El núcleo cubre la jerga del aprendizaje» y quitarlos de la cola larga. Agregar consultas de **sin experiencia** de TI al núcleo o a la cola larga («desarrollador sin experiencia», «soporte TI sin experiencia», «primer empleo sistemas»). En `config.yaml`, separar «sin experiencia», «primer empleo», «recién egresado», «recién graduado» y «nivel de entrada» de `filtros.nivel.junior` en un grupo propio, `filtros.nivel.sin_experiencia`. Verificar con pruebas en `tests/comun/test_config.py`: sin repetidos entre grupos, toda palabra del núcleo y de la cola larga tiene un término de práctica o de sin experiencia, «contrato de aprendizaje» está en el núcleo y ningún término está a la vez en `junior` y en `sin_experiencia`.
- [ ] 3.2 Excluir el grupo `junior` de `grupos_cola` y `calcular_lote` con el nivel pausado, conservando su posición en `rotacion`. Usar `seniorities: [no_experience]` en GetOnBoard con el nivel pausado. Medir con los datos de `descartes` cuántas vacantes de LinkedIn con `f_E=2` llegan a ser prácticas o sin experiencia y, si son pocas, cambiar `linkedin.opciones.f_E` a `"1"` (solo prácticas); si cae la cobertura, volver a `"1,2"` y dejar que filtren la regla y la IA. Verificar en `tests/radar/test_fechas_rotacion.py` que ninguna consulta del lote es `junior` con el nivel pausado y que al activarlo retoma la posición guardada, y en `test_linkedin.py` que `f_E` sigue la configuración.
- [ ] 3.3 Ajustar los presupuestos para que el núcleo cubra el 75 % en las fuentes sin filtro de nivel (por ejemplo, Magneto `reservado_nucleo: 3`), sin subir ningún presupuesto total. Actualizar la prueba de `test_config.py` que hoy exige el 50 %. Verificar con `uv run buscador.py --dry-run --fuente computrabajo` que hace 6 requests del núcleo y 2 de la cola larga, ninguno junior.
- [ ] 3.4 Agregar `Vacante.nivel` (`practica`, `sin_experiencia`, `junior`, `otro`), calculado por `Filtros.nivel_de` según el design §4: una vacante con términos de `sin_experiencia` y sin años exigidos cuenta como `sin_experiencia` aunque también diga «junior». Hacer que `categoria_por_terminos` publique en `PRACTICAS` las de nivel `practica` y `sin_experiencia`. Agregar `corrida._aplicar_alcance` después del guardarraíl: con el nivel pausado, todo lo que no sea `practica` ni `sin_experiencia` se descarta con el motivo `nivel_pausado` y se registra en `descartes` (etapa `nivel`). Mostrar el alcance (nivel y decisión de `_aplicar_alcance`) en `diagnosticar --evaluar`. Verificar con los escenarios de «Nivel junior configurable y pausado por defecto», «Sin experiencia dentro del alcance» y «El guardarraíl respeta el nivel pausado» en `test_buscador.py` y `test_filtros.py`.
- [ ] 3.5 Agregar el marcador `{alcance}` a `clasificador.prompt_sistema` y `clasificador.textos_alcance.{practicas, junior}` en `config.yaml`, con un texto para «prácticas, aprendizaje y sin experiencia (0 años)» y otro que además incluye junior. `version_prompt` se calcula sobre el prompt ya resuelto. Verificar en `test_clasificador.py` que los dos alcances dan versiones distintas, que con el nivel pausado el prompt menciona «sin experiencia» y no menciona junior, y que la configuración falla si falta el marcador.
- [ ] 3.6 Actualizar `README.md` y los comentarios de `config.yaml`: el canal publica solo prácticas, aprendizaje y sin experiencia, y se explica cómo encender junior. Verificar que lo documentado coincide con `config.yaml`.

## 4. DeepSeek verificable (🟡)

- [ ] 4.1 Agregar `clasificador.horas_vencimiento_practicas` (72): una pendiente con evidencia de práctica en el título vence a las 72 h y las demás a las 24 h, como antes. Al vencer, queda en `descartes` con la etapa `vencida`. Verificar con los escenarios de «Las prácticas dudosas esperan más a la IA» en `test_clasificador.py`.
- [ ] 4.2 Crear `tests/fixtures/clasificador_oro.yaml` con unas 25 dudosas etiquetadas (design §7), incluidos casos de «sin experiencia» y de junior con el nivel pausado e implementar `buscador.py ia --verificar`:
  - saldo;
  - una llamada con el propósito `verificacion` y su tope diario;
  - el porcentaje de aciertos y la lista de errores;
  - sin escribir en `clasificaciones`.

  Verificar con una prueba con respx que una respuesta con 2 errores imprime «23/25» y los dos casos, y que la caché no cambia.
- [ ] 4.3 👤 Ejecutar `buscador.py ia --verificar` en el Fedora con la clave real. Verificar que el saldo y la llamada responden y que hay al menos un 90 % de aciertos. Si no, ajustar el prompt de 3.5 y repetir antes de seguir.
- [ ] 4.4 Agregar el incidente `ia:clasificador` en `incidentes.py`:
  - apertura por saldo bajo, tope alcanzado, `incidentes.corridas_ia_fallida` (2) corridas seguidas sin respuesta válida o una dudosa vencida;
  - cierre con la primera respuesta válida y saldo suficiente;
  - aviso al chat de administración.

  Agregar un ejemplo a `simulacion.py`. Verificar con los escenarios de los dos requisitos de `incidentes-reportero` en `test_incidentes.py` y con `uv run buscador.py --simular-incidente ia:clasificador --chat-prueba`.
- [ ] 4.5 Agregar al resumen diario las métricas de la IA, los descartes por etapa con sus tres motivos principales, el porcentaje de lo publicado por nivel (prácticas, sin experiencia y otro) y los datos de prácticas perdidas que recibe la IA del resumen (spec `resumen-diario`). Actualizar `resumen.prompt_sistema` para que use esos datos. Verificar con los tres escenarios del spec en `test_resumen.py`.

## 5. Endurecimiento de reglas (🟡)

Causas, halladas en el código, de que hoy se publiquen vacantes con experiencia. Cada cambio se valida contra `tests/fixtures/casos_reales_2026-10.yaml` y contra el corpus del bloque 2, para no perder aprendices al endurecer. Lo que deja de aceptarse queda **dudoso** (va a la IA), no rechazado, salvo el rechazo por años de experiencia exigidos.

- [ ] 5.1 E1: la regla 5 de `Filtros._por_titulo` acepta sin IA solo si la palabra de nivel está en el título o hay evidencia fuerte en la descripción (`evidencia_practica_descripcion` o «sin experiencia»). Si no, la vacante queda dudosa. Verificar con el escenario «Nivel solo en la descripción» en `test_filtros.py` («Desarrollador Java» con «mejores prácticas» en la descripción queda dudosa) y sin regresión en `test_casos_reales.py`.
- [ ] 5.2 E2 y E3 en `config.yaml`: quitar `auxiliar` de `filtros.nivel.junior` (queda solo como disparador de dudosa) y agregar a `frases_ignoradas` «mejores prácticas», «prácticas de desarrollo», «prácticas ágiles» y «equipo junior». Verificar con los escenarios «Auxiliar sin práctica» (con 2 años en la descripción se rechaza) y «Frases que no son nivel».
- [ ] 5.3 E4: `Filtros._anios_excesivos` detecta los años escritos en letra («dos años»), en meses (≥ 12) y «Experiencia:» seguido de un salto de línea con el número en la línea siguiente. Verificar con una prueba por variante en `test_filtros.py`.
- [ ] 5.4 E5: con `alcance.junior.activo: false`, el umbral de experiencia excluida baja a 1 año (`anios_experiencia_excluidos_desde` condicionado al alcance). Se aceptan hasta 6 meses y la experiencia «deseable» u «opcional; en un rango cuenta el mínimo («1 a 3 años» se rechaza). Verificar con los escenarios «Experiencia deseable» (6 meses pasa) y «Un año exigido» (se rechaza), y que con el nivel activo el umbral anterior no cambia.
- [ ] 5.5 E6: conservar el área de las prácticas y el nivel. Agregar `Vacante.area`, calculada con `categoria_por_area` también para las prácticas («Aprendiz de desarrollo» → categoría `practicas`, área `desarrollo`), y el `nivel` de 3.4. Guardar `area` y `nivel` en `vistas` al registrar una vacante enviada (columna `nivel` nueva, migración aditiva) y exponer el área por `vistas.area`. Verificar con los escenarios «Área de una práctica» y «Nivel de una vacante» en `test_filtros.py` y `test_publicacion.py`.
- [ ] 5.6 Verificar el bloque completo: `uv run pytest tests/radar/test_filtros.py tests/radar/test_casos_reales.py` en verde, con el corpus del bloque 2 sin `xfail` y ningún aprendiz del corpus que pase de publicable a rechazado.

## 6. Verificación integrada en producción

- [ ] 6.1 👤 Desplegar en el Fedora (`git pull`) y revisar el canal, el bot y el resumen diario durante 3 días. Verificar que:
  - no llegan vacantes junior ni que pidan 1 año o más de experiencia, comprobado con `vistas` y `descartes`;
  - al menos el 95 % de lo publicado es práctica o sin experiencia, según el resumen diario;
  - el resumen muestra los descartes por etapa, las métricas de DeepSeek y el porcentaje por nivel.
- [ ] 6.2 Con los datos de 3 días de `descartes`, comparar las vacantes de prácticas enviadas por día frente a la semana anterior al change, y revisar los 20 descartes más frecuentes con evidencia de práctica en el título. Entregar el resultado al dueño y anotar en `docs/radar/diagnostico-aprendizaje-perdido.md` los ajustes que queden pendientes.

## Workflow follow-up

- Archivar este change después de `crear-buscador-vacantes`, `filtro-vacantes-limpias` y `linkedin-detalle-vacantes`: sus deltas usan `ADDED` sobre capacidades que nacen al archivarlos.
- Los bloques de botón único, selector y `/buscar` (antes 6 y 7) viven ahora en `selector-y-consultas-asistente`, y las vacantes destacadas (antes bloque 5) las reemplaza la fase 2 del plan de mejora (`visibilidad-area-y-fecha`).
