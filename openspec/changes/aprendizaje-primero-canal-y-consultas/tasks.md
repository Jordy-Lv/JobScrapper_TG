# Tasks

## 1. Auditoría de descartes y diagnóstico (🟡)

- [ ] 1.1 Migrar `comun/estado.py` a la siguiente versión de esquema:
  - tabla `descartes` según design §5;
  - tabla `lotes_canal` según design §2;
  - columnas `publicada`, `destacada` y `area` en `vistas`;
  - limpieza de `descartes` con `estado.dias_descartes` (14) en `Estado.limpiar`, y de `lotes_canal` con `dias_vistas`.

  Agregar `dias_descartes` a `config.Estado`. Verificar en `tests/comun/test_estado.py` que una base del esquema anterior con datos migra sin perder filas, que una base nueva nace en el esquema nuevo y que la limpieza borra un descarte de 15 días.
- [ ] 1.2 Agregar `Estado.registrar_descarte(vacante, huella, etapa, motivo, detalle, momento)`, con upsert por clave que sube `veces` y `ultima_vez`. Llamarlo desde `corrida._aplicar` (etapa `reglas`), desde `_clasificar` con las rechazadas por la IA y su motivo (etapa `ia`), desde `_aplicar_guardarrail` (etapa `guardarrail`) y desde las vencidas del clasificador y de la cola de detalle (etapa `vencida`). Nada se escribe en dry-run, seed ni modo prueba. Verificar en `tests/radar/test_buscador.py` que una corrida con una vacante de cada caso deja un registro por etapa, y que la misma vacante en dos corridas deja `veces = 2`.
- [ ] 1.3 Implementar `buscador.py diagnosticar <url | título>` (design §5): búsqueda por URL normalizada, clave o título en `vistas`, `por_enviar`, `pendientes`, `pendientes_detalle` y `descartes`. Sin coincidencias, mostrar el resumen de `intentos` de los últimos 3 días de la fuente que corresponde al dominio. El comando abre la base en solo lectura. Verificar con pruebas en `tests/radar/test_punto_entrada.py` para «publicada», «descartada por reglas», «pendiente de IA» y «nunca vista».
- [ ] 1.4 Agregar `diagnosticar --evaluar --titulo … [--empresa --ubicacion --modalidad --descripcion --fuente] [--con-ia]`: veredicto, motivo, categoría, guardarraíl y alcance. Con `--con-ia` se usa un `Estado` en memoria, sin escribir en la caché. Verificar con una prueba que evalúa «Aprendiz SENA Tecnólogo ADSO» y con una prueba con respx de `--con-ia` que no toca `clasificaciones`.
- [ ] 1.5 Documentar `diagnosticar` en `README.md` (sección de operación), con dos ejemplos. Verificar que los ejemplos corren tal como están escritos contra una copia de `data/vacantes.db`.

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

## 3. Nivel junior pausado (🟡)

- [ ] 3.1 Agregar `alcance.junior.activo` (por defecto `false`) a `config.py` y `palabras_clave.junior` como grupo propio. Mover a `palabras_clave.junior` las consultas junior de `cola_larga`: las que tienen «junior», «jr», «entry level» o ningún término de práctica. Dejar en la cola larga solo las de práctica por rol. Agregar al núcleo los términos del spec «El núcleo cubre la jerga del aprendizaje» y quitarlos de la cola larga. Verificar con pruebas en `tests/comun/test_config.py`: sin repetidos entre grupos, toda palabra del núcleo y de la cola larga tiene un término de práctica, y «contrato de aprendizaje» está en el núcleo.
- [ ] 3.2 Excluir el grupo `junior` de `grupos_cola` y `calcular_lote` con el nivel pausado, conservando su posición en `rotacion`. Usar `seniorities: [no_experience]` en GetOnBoard con el nivel pausado. Verificar en `tests/radar/test_fechas_rotacion.py` que ninguna consulta del lote es `junior` con el nivel pausado y que al activarlo retoma la posición guardada.
- [ ] 3.3 Ajustar los presupuestos para que el núcleo cubra el 75 % en las fuentes sin filtro de nivel (por ejemplo, Magneto `reservado_nucleo: 3`), sin subir ningún presupuesto total. Actualizar la prueba de `test_config.py` que hoy exige el 50 %. Verificar con `uv run buscador.py --dry-run --fuente computrabajo` que hace 6 requests del núcleo y 2 de la cola larga, ninguno junior.
- [ ] 3.4 Agregar `corrida._aplicar_alcance` después del guardarraíl: con el nivel pausado, todo lo que no sea `PRACTICAS` se descarta con el motivo `nivel_pausado` y se registra en `descartes` (etapa `nivel`). Verificar con los escenarios de «Nivel junior configurable y pausado por defecto» y «El guardarraíl respeta el nivel pausado» en `test_buscador.py`.
- [ ] 3.5 Agregar el marcador `{alcance}` a `clasificador.prompt_sistema` y `clasificador.textos_alcance.{practicas, junior}` en `config.yaml`, con un texto para solo prácticas y otro para prácticas y junior. `version_prompt` se calcula sobre el prompt ya resuelto. Verificar en `test_clasificador.py` que los dos alcances dan versiones distintas, que con el nivel pausado el prompt no menciona junior y que la configuración falla si falta el marcador.
- [ ] 3.6 Actualizar `README.md` y los comentarios de `config.yaml`: el canal publica solo prácticas y aprendizaje, y se explica cómo encender junior. Verificar que lo documentado coincide con `config.yaml`.

## 4. DeepSeek verificable (🟡)

- [ ] 4.1 Agregar `clasificador.horas_vencimiento_practicas` (72): una pendiente con evidencia de práctica en el título vence a las 72 h y las demás a las 24 h, como antes. Al vencer, queda en `descartes` con la etapa `vencida`. Verificar con los escenarios de «Las prácticas dudosas esperan más a la IA» en `test_clasificador.py`.
- [ ] 4.2 Crear `tests/fixtures/clasificador_oro.yaml` con unas 25 dudosas etiquetadas (design §7) e implementar `buscador.py ia --verificar`:
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
- [ ] 4.5 Agregar al resumen diario las métricas de la IA, los descartes por etapa con sus tres motivos principales, las destacadas enviadas y los datos de prácticas perdidas que recibe la IA del resumen (spec `resumen-diario`). Actualizar `resumen.prompt_sistema` para que use esos datos. Verificar con los tres escenarios del spec en `test_resumen.py`.

## 5. Vacantes destacadas y formato compacto (🟡)

- [ ] 5.1 Agregar `publicacion.destacadas` a `config.py` y a `config.yaml` (design §8). Implementar `Filtros.es_destacada(vacante, ahora)`, que devuelve los criterios cumplidos, exponiendo la regla de ciudad base o remoto de `_geografia` como un método público. Verificar con los tres escenarios de «Vacantes destacadas» en `test_filtros.py`.
- [ ] 5.2 En `formato.py`: `ficha_completa` con la línea de insignias, `ficha_compacta` en dos líneas sin salario, el bloque «⭐ DESTACADAS» al inicio, el encabezado con el conteo de destacadas y el título del bloque repetido al partir el mensaje. Verificar con los escenarios de «Bloque de destacadas al inicio», «Formato compacto para las demás vacantes», «Las destacadas se cuentan en el encabezado» y «El corte de mensajes respeta el bloque de destacadas» en `test_formato.py`, cuidando que ningún mensaje pase de 4.096 unidades.
- [ ] 5.3 Guardar en `vistas` las columnas `publicada`, `destacada` y `area` al registrar una vacante enviada. Verificar el escenario «Vacante destacada enviada» en `test_publicacion.py`.
- [ ] 5.4 👤 Revisar en el chat de prueba (`--chat-prueba`) una corrida con destacadas y vacantes normales. Verificar que el dueño aprueba el formato o deja anotados los ajustes en `config.yaml` o en `formato.py` antes del despliegue.

## 6. Botón único y selector de vacantes (🟡)

- [ ] 6.1 Hacer que `NotificadorBotAPI.enviar_mensaje` acepte botones `url:`. En `publicacion.py`, reemplazar los botones por vacante por un solo botón URL `t.me/<bot>?start=l_<id_lote>`, con el texto del spec, y guardar el lote en `lotes_canal` solo al confirmarse el envío. Sin asistente activo, no hay botón. Verificar con los escenarios de «Un solo botón de postulación por mensaje del canal» y de «Lote de cada mensaje publicado» en `test_publicacion.py` y `test_notificador.py`.
- [ ] 6.2 Agregar `Indice.resolver_lote(id_lote, ahora)` en `asistente/vacantes.py`: lee `lotes_canal` en solo lectura, indexa las claves que falten y devuelve las vacantes en orden, o `None` si el lote venció. Verificar con pruebas en `tests/asistente/test_datos.py` o en un archivo nuevo `test_vacantes.py`.
- [ ] 6.3 Crear `asistente/selector.py`, con lógica pura: páginas de 6, texto numerado, ⭐ y ✅, y botones `sel:`, `selpag:` y `selx`. Su estado vive en `kv`. Verificar con pruebas unitarias del escenario «Lote de nueve vacantes» y de las marcas ⭐ y ✅.
- [ ] 6.4 Conectar el selector en la conversación:
  - `al_iniciar` reconoce `l_<id>`, guarda el lote pendiente durante el alta y lo muestra al terminarla;
  - `sel:` llama a `procesar_toque(..., origen="selector")`;
  - `pv:` y `v_` siguen funcionando.

  Si `dividir-conversacion-asistente` ya se aplicó, usar su registro `@boton`. Verificar con los escenarios de «El botón abre el bot en privado con el lote del mensaje», «Elegir una vacante sigue el flujo de postulación existente», «El lote sobrevive al registro» y «Compatibilidad con los botones ya publicados» en `tests/asistente/test_bot.py`.
- [ ] 6.5 Actualizar `asistente/textos.py` (`AYUDA`) y `docs/asistente/guia-usuario.md` con el botón único y el selector. Verificar que la guía describe el flujo tal como lo muestran las pruebas de 6.4.

## 7. Consultas desde el bot asistente (🔴)

> Tarea pesada: recomendar sesión nueva antes de empezarla y al terminarla.

- [ ] 7.1 Migrar `asistente.db` al esquema 3: columnas `ubicacion`, `modalidad`, `publicada`, `destacada` y `area` en `vacantes`. `Indice.indexar` las copia de `vistas`. Verificar en `tests/asistente/test_datos.py` la migración desde el esquema 2 y que una vacante indexada trae los datos nuevos.
- [ ] 7.2 Crear `asistente/consultas.py`, con lógica pura:
  - el dataclass `ConsultaVacantes`;
  - la validación pydantic con la lista cerrada de campos y valores;
  - la consulta SQL parametrizada sobre `vacantes`, ordenada con las destacadas primero y luego por fecha;
  - el alcance de los datos: solo el canal real, dentro de la retención y sin descartadas.

  Verificar con pruebas de cada filtro, de su combinación y de los escenarios «Vacante descartada» y «Sin resultados».
- [ ] 7.3 Implementar la tarjeta de filtros y los resultados en la conversación:
  - `/buscar` y el botón «🔎 Buscar vacantes»;
  - la tarjeta editable con el contador;
  - «Limpiar filtros» y el junior pausado;
  - los resultados con el selector de 6.3, en el modo `consulta`.

  Verificar con los escenarios de «Punto de entrada de las consultas», «Tarjeta de filtros con botones», «Nivel junior pausado en las consultas» y «Resultados paginados con postulación» en `test_bot.py`.
- [ ] 7.4 Implementar `/buscar <frase>`:
  - limpieza de la frase (200 caracteres, sin correos, teléfonos ni documentos);
  - llamada a DeepSeek con el cliente HTTP del radar y un prompt corto en `asistente.consultas.prompt_sistema`;
  - validación de la respuesta;
  - topes `ia_usuario_dia` (5) e `ia_servidor_dia` (200) contados en `asistente.db`;
  - búsqueda literal en el título y la empresa cuando no hay IA, con aviso.

  Verificar con respx los escenarios de «Búsqueda con las palabras del usuario», «Búsqueda por texto cuando la IA no está disponible» y «La frase del usuario no lleva datos personales a la IA».
- [ ] 7.5 Agregar `/buscar` a `AYUDA` y a `docs/asistente/guia-usuario.md`, con un aviso breve de que la frase se procesa con DeepSeek y sin datos personales. Verificar que la guía y `textos.py` coinciden.

## 8. Verificación integrada en producción

- [ ] 8.1 👤 Desplegar en el Fedora (`git pull`, reinicio de `buscador-asistente`) y revisar el canal, el bot y el resumen diario durante 3 días. Verificar que:
  - no llegan vacantes junior;
  - los mensajes tienen un solo botón y el selector funciona desde el móvil;
  - las destacadas aparecen al inicio;
  - `/buscar` responde con y sin IA;
  - el resumen muestra los descartes por etapa y las métricas de DeepSeek.
- [ ] 8.2 Con los datos de 3 días de `descartes`, comparar las vacantes de prácticas enviadas por día frente a la semana anterior al change, y revisar los 20 descartes más frecuentes con evidencia de práctica en el título. Entregar el resultado al dueño y anotar en `docs/radar/diagnostico-aprendizaje-perdido.md` los ajustes que queden pendientes.

## Workflow follow-up

- Archivar este change después de `crear-buscador-vacantes`, `filtro-vacantes-limpias` y `linkedin-detalle-vacantes`: sus deltas usan `ADDED` sobre capacidades que nacen al archivarlos.
- Si `dividir-conversacion-asistente` se aplica antes del bloque 6, actualizar las rutas de las tareas 6.4 y 7.3 al paquete nuevo.
