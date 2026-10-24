# Proposal

> **Ajuste del 2026-10-24** (fase 1 del [plan de mejora del scraping](../../../docs/radar/plan-mejora-scraping/README.md)). Se sacaron de este change el botón único, el selector y `/buscar` (ahora en `selector-y-consultas-asistente`) y las vacantes destacadas (las reemplaza la fase 2, `visibilidad-area-y-fecha`). El alcance pasa de «solo prácticas» a **prácticas + sin experiencia**, y se agrega un bloque de endurecimiento de reglas. El nombre del change se conserva por los enlaces existentes.

## Why

La prioridad del grupo «JOBS - PRÁCTICAS/APRENDIZ» es que **al menos el 95 %** de lo publicado sea práctica, pasantía, aprendiz, contrato de aprendizaje SENA, trainee o **sin experiencia** de TI, y encontrar **todas** las de ese tipo. Hoy pasan cuatro cosas:

- **Se pierden vacantes.** El dueño encuentra a mano vacantes de aprendizaje que el bot no publicó, y no hay forma de saber por qué: las vacantes rechazadas no quedan registradas en ninguna parte.
- **El nivel junior gasta presupuesto.** Más de la mitad de la cola larga de búsqueda son consultas junior que no son la prioridad actual.
- **Se publican vacantes con experiencia.** Reglas demasiado laxas aceptan, por ejemplo, «Desarrollador Java» porque la descripción dice «mejores prácticas», o no ven «dos años» escrito en letra.
- **«Sin experiencia» depende de junior.** Hoy esos términos viven en `filtros.nivel.junior`: apagar junior los apagaría.

## What Changes

**1. Aprendizaje y sin experiencia primero; junior listo pero apagado**
- Nuevo interruptor `alcance.junior` en `config.yaml`, **apagado por defecto**. Mientras está apagado:
  - no se buscan las palabras clave junior (pasan a su propio grupo);
  - el código descarta las vacantes aceptadas cuyo nivel no sea práctica ni sin experiencia, con el motivo `nivel_pausado`;
  - el prompt del clasificador describe prácticas, aprendizaje y sin experiencia (0 años).

  Al encenderlo vuelve todo el comportamiento junior, sin tocar código. **BREAKING**: el canal deja de publicar vacantes junior.
- **«Sin experiencia» como nivel propio**, en `filtros.nivel.sin_experiencia`, con prioridad igual a la de las prácticas.
- **Auditoría de descartes:** cada vacante rechazada (por reglas, por la IA, por el guardarraíl o por el nivel pausado) queda en una tabla `descartes` con su motivo, por 14 días.
- **Diagnóstico de vacantes:** nuevo comando `buscador.py diagnosticar <url | título>`. Le dice al dueño si la vacante se buscó, si llegó, qué regla o qué respuesta de la IA la rechazó y por qué.
- **Revisión exhaustiva de las reglas**, con un corpus de vacantes de aprendizaje reales que el bot perdió. Hipótesis encontradas leyendo el código, que se confirman o descartan con ese corpus:
  - los años de la empresa («más de 20 años de experiencia en el sector») se cuentan como experiencia exigida;
  - una práctica con un término de seniority en el título se rechaza sin pasar por la IA;
  - «práctica sin TI» se rechaza mirando solo un fragmento corto de la descripción (elempleo y Magneto);
  - «SENA», «semillero» y «programa de talento» no cuentan como evidencia de práctica para el guardarraíl;
  - la republicación de la misma vacante por la misma empresa (nueva cohorte de aprendices) se descarta como duplicada durante 90 días;
  - las dudosas se pierden si DeepSeek falla 24 h seguidas.
- **Endurecimiento de reglas (E1–E6)**, para que no se publiquen vacantes con experiencia:
  - la regla 5 solo acepta sin IA si el nivel está en el título o hay evidencia fuerte en la descripción;
  - «auxiliar» deja de contar como junior y se ignoran frases como «mejores prácticas»;
  - se detectan los años en letra, en meses y en la línea siguiente a «Experiencia:»;
  - con junior apagado, 1 año de experiencia ya se rechaza (se aceptan hasta 6 meses y la experiencia «deseable»);
  - cada vacante conserva su área (también las prácticas) y su nivel.
- **Búsqueda:**
  - «contrato de aprendizaje», «etapa productiva» y las variantes por rol (aprendiz o practicante de desarrollo, soporte, redes, datos) pasan al núcleo;
  - se agregan consultas de TI sin experiencia («soporte TI sin experiencia», «primer empleo sistemas»);
  - el presupuesto que liberan las consultas junior va al núcleo de aprendizaje;
  - GetOnBoard pide solo `no_experience`, y LinkedIn pasa a `f_E=1` si los datos de `descartes` lo respaldan.
- **DeepSeek verificable:**
  - comando `buscador.py ia --verificar`: comprueba la clave y el saldo, y mide los aciertos contra un conjunto de casos etiquetados, con casos de sin experiencia y de junior pausado;
  - nuevo incidente `ia:clasificador`, por saldo bajo, corridas seguidas sin respuesta válida o dudosas vencidas;
  - métricas de la IA y **porcentaje de lo publicado por nivel** en el resumen diario;
  - una dudosa con evidencia fuerte de práctica de TI no se descarta solo porque la IA no respondió.

**Fuera de este change** (decisión del 2026-10-24):
- botón único, selector y consultas del asistente → `selector-y-consultas-asistente`, propuesto para después del plan;
- vacantes destacadas y formato compacto → fase 2 (`visibilidad-area-y-fecha`), con otros criterios (área foco);
- cambiar la política de ubicación, pedir el detalle de Computrabajo o elempleo, alertas personalizadas, fuentes nuevas y la extensión del navegador.

## Capabilities

### New Capabilities

- `auditoria-descartes`: el registro de cada vacante rechazada con su motivo y el comando de diagnóstico.

### Modified Capabilities

Estas capacidades todavía no están en `openspec/specs/`: nacen al archivar `crear-buscador-vacantes` y se amplían en otros changes abiertos. Por eso sus deltas solo usan `ADDED`, igual que en `linkedin-detalle-vacantes`.

- `filtrado-vacantes`: alcance de prácticas y sin experiencia con junior pausado y configurable, nivel `sin_experiencia` propio, endurecimiento de reglas (E1–E5), área y nivel de cada vacante aceptada, y correcciones H1–H4 y H6.
- `busqueda-fuentes`: el grupo junior solo se busca con el nivel activo, el núcleo de aprendizaje crece, hay consultas de sin experiencia y los filtros de nivel nativos siguen el alcance.
- `deduplicacion-estado`: se guardan el área y el nivel de cada vacante enviada y se permite republicar a una empresa que vuelve a publicar la misma vacante.
- `incidentes-reportero`: incidente `ia:clasificador`.
- `resumen-diario`: métricas de la IA, descartes por etapa y porcentaje de lo publicado por nivel.

## Impact

- **Radar:**
  - `buscador_vacantes/radar/filtros.py`: reglas de experiencia, seniority en prácticas, «práctica sin TI» con descripción completa, nivel y área.
  - `clasificador.py`: prompt armado por alcance y política ante una IA caída.
  - `corrida.py`: registro de descartes y nivel pausado.
  - `incidentes.py` y `resumen.py`.
  - Comandos nuevos en `buscador.py`: `diagnosticar` e `ia --verificar`.
- **Común:**
  - `comun/config.py`: `alcance`, `palabras_clave.junior`, `filtros.nivel.sin_experiencia` y `estado.republicar_tras_dias`.
  - `comun/modelo.py`: `Vacante.area` y `Vacante.nivel`.
  - `comun/estado.py`: tablas `descartes` y `lotes_canal`, y columnas de `vistas` (migración ya hecha en la tarea 1.1; el bloque 5 agrega `nivel`).
- **Configuración:** `palabras_clave`, `alcance`, `filtros` (`nivel`, `frases_ignoradas`, `frases_trayectoria`, umbrales de experiencia), `linkedin.opciones.f_E`, `clasificador`, `estado`.
- **Pruebas:** `tests/radar/test_filtros.py`, `test_casos_reales.py` (más un corpus nuevo de aprendizaje), `test_clasificador.py`, `test_incidentes.py`, `test_resumen.py`, `test_punto_entrada.py` y `tests/comun/test_config.py`.
- **Producción (Fedora):**
  - `git pull`; el timer del radar toma el código en la siguiente corrida.
  - Las migraciones de `vacantes.db` son aditivas.
  - Al cambiar el prompt cambia su versión y la caché de clasificaciones se renueva sola.
  - El canal deja de recibir vacantes junior desde la primera corrida.
- **Costo de IA:** el clasificador deja de gastar en vacantes junior; las reglas más estrictas mandan algunas vacantes más a la IA (tope de 300 llamadas al día).
