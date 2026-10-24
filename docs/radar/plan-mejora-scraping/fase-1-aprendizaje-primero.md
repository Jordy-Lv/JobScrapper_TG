# Fase 1: aprendizaje y sin experiencia primero

| | |
|---|---|
| **Dificultad** | 🔴 pesada: toca reglas, prompt, palabras clave y presupuestos, y depende de un corpus de casos reales |
| **Change de OpenSpec** | `aprendizaje-primero-canal-y-consultas`, ajustado con `/opsx:update` |
| **Atiende** | puntos 2 (DeepSeek y reglas) y 3b (prioridad del 95 % a aprendices y sin experiencia) |
| **Depende de** | [fase 0](fase-0-diagnostico-del-silencio.md) (descartar antes un arreglo urgente) |

## Objetivo

Que al menos el **95 %** de lo publicado sea práctica, pasantía, aprendiz, contrato de aprendizaje (SENA), trainee o **sin experiencia**, de cualquier área de TI. Y que el dueño pueda saber, vacante por vacante, por qué se publicó o se descartó.

## Ajuste del change existente (primera tarea, 🟢)

Con `/opsx:update aprendizaje-primero-canal-y-consultas`:

1. **Sacar los bloques 6 y 7** (botón único, selector y `/buscar` del asistente) a un change nuevo, `selector-y-consultas-asistente`, con sus specs `selector-vacantes-asistente` y `consultas-vacantes-asistente`. Ese change queda propuesto para después de este plan.
2. **Sacar el bloque 5 (destacadas).** Lo reemplaza la [fase 2](fase-2-visibilidad-y-fechas.md), con otros criterios: área foco en lugar de «práctica + TI + Cartagena + 3 días».
3. **Ampliar el alcance** de «solo prácticas» a **prácticas + sin experiencia**, con junior (1–2 años) apagado. Ver «Niveles» abajo.
4. **Agregar el endurecimiento de reglas** (bloque nuevo, abajo).
5. Mantener los bloques 1 (`diagnosticar`), 2 (corpus H1–H7), 3 (nivel junior pausado), 4 (DeepSeek verificable) y 8 (verificación en producción).

## Niveles

| Nivel | Ejemplos | Con la fase 1 |
|---|---|---|
| **Prácticas y aprendizaje** | aprendiz, aprendiz SENA, contrato de aprendizaje, etapa productiva, practicante, pasante, trainee, intern, semillero, programa de talento | ✅ se publica |
| **Sin experiencia** | «sin experiencia», «no requiere experiencia», «primer empleo», «recién egresado», «nivel de entrada» **con 0 años** exigidos | ✅ se publica |
| **Junior** | junior, jr, entry level, 1–2 años | ⏸ apagado (`alcance.junior.activo: false`), descartado con el motivo `nivel_pausado` |
| Semi senior o más | senior, ssr, lead, 2 años o más | ❌ se descarta, como hoy |

Hoy «sin experiencia» y «primer empleo» están dentro de `filtros.nivel.junior` (`config.yaml:353`). Se separan en un grupo propio, `filtros.nivel.sin_experiencia`, que cuenta como alcance prioritario. Así, apagar junior no las apaga a ellas.

## Bloques de trabajo

### Bloque 1: auditoría y diagnóstico (🟡, del change)

- Ya están hechas la 1.1 y la 1.2: la tabla `descartes` y el registro por etapa.
- Falta la 1.3–1.5: el comando `buscador.py diagnosticar <url | título>` y `diagnosticar --evaluar … [--con-ia]`, documentados en el `README.md`. Es la herramienta con la que el dueño pregunta «¿por qué no llegó esta vacante?».

### Bloque 2: corpus de aprendizaje perdido y corrección de reglas (🔴, del change)

- 👤 El dueño reúne de 15 a 30 enlaces de vacantes de aprendizaje que encontró a mano.
- Se diagnostican y se arma `tests/fixtures/casos_aprendizaje_perdidos.yaml`.
- Se corrigen las hipótesis H1–H6 (descritas en el `design.md` del change):
  - H1: los años de la empresa no cuentan como experiencia;
  - H2: una práctica con un término de seniority queda dudosa;
  - H3: «práctica sin TI» solo se decide con la descripción completa;
  - H4: «SENA», «semillero» y otros términos cuentan como evidencia;
  - H5: la cohorte nueva no es un duplicado;
  - H6: las prácticas dudosas esperan 72 h a la IA.

### Bloque 3: nivel junior pausado y búsqueda de aprendizaje (🟡, del change, ampliado)

- `alcance.junior.activo: false` en `config.py` y `config.yaml`. Las consultas junior pasan a `palabras_clave.junior`, que no se busca mientras el nivel esté pausado.
- El presupuesto liberado va al núcleo de aprendizaje: «contrato de aprendizaje», «etapa productiva», aprendiz o practicante por rol (desarrollo, soporte, redes, datos, bases de datos, QA).
- **Nuevo:** agregar al núcleo o a la cola larga consultas de **sin experiencia** de TI: «desarrollador sin experiencia», «soporte TI sin experiencia», «primer empleo sistemas».
- GetOnBoard pasa a `seniorities: [no_experience]`.
- **Nuevo:** LinkedIn pasa a `f_E=1`, solo prácticas. El nivel de entrada (`2`) trae sobre todo profesionales. Se mide con los datos de `descartes` antes de decidir.
- `corrida._aplicar_alcance` descarta, con el motivo `nivel_pausado`, todo lo que no sea prácticas ni sin experiencia.
- El prompt del clasificador recibe un marcador `{alcance}`: «prácticas, aprendizaje y sin experiencia (0 años)» mientras junior está pausado.

### Bloque nuevo: endurecimiento de reglas (🟡)

Son las causas, encontradas en el código, de que hoy se publiquen vacantes con experiencia:

| # | Cambio | Dónde | Prueba |
|---|---|---|---|
| E1 | La regla 5 solo acepta sin IA si la palabra de nivel está **en el título**, o si hay evidencia fuerte en la descripción (`evidencia_practica_descripcion` o «sin experiencia»). Si no, la vacante queda dudosa. | `filtros.py:_por_titulo` (regla 5) | «Desarrollador Java» con «mejores prácticas» en la descripción → dudosa, no aceptada. |
| E2 | Quitar `auxiliar` del nivel junior; queda solo como disparador de dudosa. | `config.yaml` `filtros.nivel.junior` | «Auxiliar de sistemas» con 2 años en la descripción → rechazada. |
| E3 | Agregar a `frases_ignoradas`: «mejores prácticas», «prácticas de desarrollo», «prácticas ágiles», «equipo junior». | `config.yaml` | La frase sola ya no da nivel. |
| E4 | Detectar los años escritos en letra («dos años»), en meses («24 meses», «18 meses» ≥ 12) y «Experiencia:» seguido de salto de línea con el número en la línea siguiente. | `filtros.py:_anios_excesivos` | Una prueba por variante. |
| E5 | Con junior apagado, el umbral de experiencia baja a **1 año**; se aceptan meses (≤ 6) y la experiencia «deseable» u «opcional». En un rango cuenta el mínimo: «1 a 3 años» se rechaza. | `config.yaml` `anios_experiencia_excluidos_desde`, condicionado al alcance | «Aprendiz… 6 meses de experiencia deseable» pasa; «1 año de experiencia» se rechaza. |
| E6 | **Conservar el área de las prácticas.** Además de la categoría, se guarda el área detectada (por ejemplo, «Aprendiz de desarrollo» → categoría `practicas`, área `desarrollo`). | `filtros.py`, `modelo.py`, `vistas.area` | La usa la [fase 2](fase-2-visibilidad-y-fechas.md). |

Cada cambio se valida contra `tests/fixtures/casos_reales_2026-10.yaml` y contra el corpus del bloque 2, para no perder aprendices al endurecer.

### Bloque 4: DeepSeek verificable (🟡, del change)

- `buscador.py ia --verificar`: saldo y aciertos contra `tests/fixtures/clasificador_oro.yaml`, unas 25 dudosas etiquetadas. **Ampliar el conjunto** con casos de «sin experiencia» y de junior pausado.
- Incidente `ia:clasificador`: saldo bajo, tope alcanzado, 2 corridas seguidas sin respuesta válida o una dudosa vencida.
- Métricas de la IA en el resumen diario.
- **Nuevo:** el resumen diario muestra el **porcentaje de lo publicado por nivel** (prácticas / sin experiencia / otro). Es la métrica de esta fase.

### Bloque 8: verificación en producción (👤, del change)

- Despliegue en el Fedora.
- 3 días de observación.
- Comparación con la semana anterior usando `descartes`.

## Criterios de aceptación

- [ ] El change queda ajustado: los bloques 6 y 7 en `selector-y-consultas-asistente`, el bloque 5 fuera, y el alcance «prácticas + sin experiencia» en el design y los specs.
- [ ] `uv run buscador.py --dry-run` no hace ninguna consulta del grupo `junior`.
- [ ] Ninguna vacante publicada en 3 días de producción es junior o pide 1 año o más; se comprueba con `vistas` y `descartes`.
- [ ] El resumen diario muestra que al menos el 95 % de lo publicado es prácticas o sin experiencia.
- [ ] `ia --verificar` acierta al menos el 90 % con la clave real.
- [ ] Cada vacante del corpus del dueño tiene una causa explicada por `diagnosticar`, y las corregibles pasan las pruebas.
- [ ] `uv run pytest`, `uv run ruff check` y `uv run ruff format --check` en verde.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Al endurecer la regla 5 se pierden aprendices (falsos negativos). | Todo pasa por el corpus del bloque 2. Lo que deja de aceptarse queda **dudoso** (va a la IA), no rechazado. |
| Más dudosas implica más gasto en DeepSeek. | Tope de 300 llamadas al día, lotes de 30 y caché; las métricas del bloque 4 lo vigilan. |
| Con `f_E=1`, LinkedIn trae muy poco. | Se mide primero con `descartes`. Si cae la cobertura, se vuelve a `1,2` y se deja que filtren la regla y la IA. |
| Cambiar el prompt invalida la caché `clasificaciones`. | Es lo esperado. El primer día habrá más llamadas. |

## Sesión recomendada

**Sesión nueva** (🔴). Mensaje listo para pegar:

> Ejecuta la fase 1 de `docs/radar/plan-mejora-scraping/fase-1-aprendizaje-primero.md`. Primero ajusta con `/opsx:update` el change `aprendizaje-primero-canal-y-consultas` (sacar los bloques 6–7 a `selector-y-consultas-asistente`, quitar el bloque 5, alcance prácticas + sin experiencia, bloque de endurecimiento E1–E6). Luego sigue con `/opsx:apply` desde la tarea 1.3.
