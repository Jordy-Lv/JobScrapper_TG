# Estado actual del radar (24/10/2026)

> Radiografía del módulo de scraping hecha leyendo el código de `main` (commit `139372f`). Responde los puntos 1 y 2 del [diagnóstico](diagnostico-2026-10-24.md). Las referencias son `ruta:línea`.

## 1. Flujo de una corrida

`deploy/buscador.timer` lanza una corrida cada 30 minutos (`*:00,30`, con hasta 2 minutos de azar). `radar/corrida.py:main` toma el lock y pone un límite de 25 minutos (`_limitar_tiempo`, `corrida.py:853`). Después, `Corrida.ejecutar` (`corrida.py:738`) hace estos pasos:

1. **Limpieza** (`Estado.limpiar`). Borra vistas de más de 90 días, intentos y corridas de más de 30, detalles de más de 15 y descartes de más de 14.
2. **Consulta de cada fuente** (`_consultar`, `corrida.py:275`).
   - Salta las fuentes en cooldown y las que no cumplieron su intervalo mínimo; hoy solo LinkedIn tiene intervalo.
   - El lote de palabras clave sale de la rotación (`radar/rotacion.py`).
   - Si una fuente falla, las demás siguen.
3. **Reglas** (`_evaluar` → `_aplicar`, `corrida.py:370-450`). Primero los rechazos; luego la deduplicación (`Estado.ya_vista`); luego la cola de detalle para LinkedIn sin modalidad. Lo demás queda **aceptado** o **dudoso**.
4. **Cola de detalle** (`_resolver_detalles_de`, `corrida.py:469`). Hasta 2 detalles de LinkedIn por corrida, y solo si LinkedIn corrió y no está bloqueado.
5. **Clasificación con IA** de las dudosas (`_clasificar`, `corrida.py:584`). Si falla, las aceptadas por reglas igual se publican.
6. **Guardarraíl de prácticas** (`_aplicar_guardarrail`, `corrida.py:608`). Una vacante en «Prácticas» sin evidencia de práctica pasa a su área.
7. **Publicación** (`_publicar`, `corrida.py:635` → `radar/publicacion.py`). Si Telegram rechaza un mensaje, sus vacantes quedan en `por_enviar` y se reintentan durante 24 h.
8. **Incidentes y healthcheck.** `salud.exito` se envía en **toda** corrida que no se cae, aunque haya publicado 0.

**No hay nada que corte la recolección por horario.** No hay horas de silencio, ni tope diario de mensajes, ni un presupuesto diario que se agote; la rotación es circular. Que no lleguen vacantes después de cierta hora no viene de ninguna regla escrita.

## 2. Fuentes

| Fuente | Peticiones por corrida | Filtro de fecha u orden | Precisión de la fecha | Observaciones |
|---|---|---|---|---|
| LinkedIn | 2 (consulta OR de 14 términos, 10 tarjetas por página) | `f_TPR`: tiempo desde la última consulta buena + 30 min, entre 2 h y 24 h; `sortBy=DD` | horas («Hace 9 horas») o día | Corre cada 120 min (180/240 tras un bloqueo). Sin modalidad en la tarjeta: necesita el detalle. `f_E=1,2` trae prácticas **y nivel de entrada**. |
| Computrabajo | 8 (2 del núcleo × 3 páginas + 2 de la cola larga) | `pubdate=3`; página 1 por relevancia | solo relativa («Ayer») | Sin descripción en el listado. |
| elempleo | 5 | `hace-1-semana` | solo relativa | Un 404 cuenta como «sin resultados», es decir, como éxito. |
| Magneto | 4 | `publish_date` descendente, solo página 1 | exacta | |
| GetOnBoard | 6 (2 del núcleo × 2 páginas + 2 de la cola larga) | página según `total_pages`, palabras propias de una sola palabra | exacta (epoch) | `seniorities: [no_experience, junior]` |
| SPE | 2 páginas de 50 | las más recientes | solo día | Publica con días de retraso. |

Entre todas son unas **1.100 peticiones al día**, desde una sola IP, con cadencia fija y encabezados mínimos (`fuentes/base.py:175-183`: solo User-Agent y Accept-Language, HTTP/1.1 y un cliente nuevo sin cookies en cada corrida).

**Bloqueos** (`fuentes/base.py:248-278`):

- Un 403, 429 o 999, o una página de desafío, deja la fuente fuera por 2 h, luego 6 h y luego 24 h.
- El contador solo se reinicia con una respuesta 2xx.
- El incidente se abre a las **2 corridas bloqueadas seguidas** (`radar/incidentes.py:190-201`): el primer cooldown no avisa.

## 3. Reglas de filtrado, en orden

`Filtros.evaluar` (`radar/filtros.py:334-442`) trabaja sobre el título y la descripción en minúsculas, sin tildes y sin las `frases_ignoradas` («buenas prácticas», «redes sociales», etc.).

| # | Regla | Resultado | Notas |
|---|---|---|---|
| 0 | Lista negra de empresas y palabras | rechaza | Las listas están vacías hoy. |
| 1a | Palabra de seniority **en el título** (senior, sr, lead, líder, gerente, jefe, arquitecto, coordinador, especialista…) | rechaza | Una práctica con «coordinación» en el título se pierde (hipótesis H2). |
| 1b | Años de experiencia ≥ 2 (`anios_experiencia_excluidos_desde: 2`, `_anios_excesivos`, `filtros.py:145`) | rechaza | Solo ve dígitos seguidos de «años» o «years». En un rango toma el mínimo («1 a 3 años» pasa). No ve «dos años», «24 meses» ni «Experiencia:» seguido de salto de línea. |
| 2 | Publicada hace más de 15 días | rechaza | |
| 3 | Geografía: presencial solo en Cartagena, Turbaco o Mamonal; fuera de ahí, remota o híbrida; remota de Colombia o LATAM | rechaza, o marca para confirmar modalidad | |
| 4 | Práctica en el título, con descripción y sin nada de TI | rechaza | Con fragmentos cortos de descripción puede equivocarse (H3). |
| 5 | **TI en el título y una palabra de nivel en el título o en la descripción**, sin área no TI en el título | **acepta sin IA** | Aquí se cuelan vacantes con experiencia: «estudiante», «auxiliar» o «junior» en cualquier parte de la descripción bastan («mejores prácticas» no está en las frases ignoradas). |
| 6 | Nada de TI, sin disparadores ni práctica en el título | rechaza | |
| 7 | Todo lo demás | **dudosa → DeepSeek** | |

**Categoría** (`categoria_por_terminos`, `filtros.py:173`): si hay práctica en el título, la categoría es «Prácticas». Si no, es la primera área que coincide, en este orden: QA, ciberseguridad, datos, bases de datos, desarrollo, infraestructura, soporte; si ninguna coincide, «otros TI». **Una práctica pierde su área**: «Aprendiz de desarrollo» queda solo como «Prácticas».

**Nivel aceptado hoy:** prácticas **y junior**.

- `nivel.junior` incluye junior, jr, entry level, sin experiencia, recién egresado, primer empleo y **auxiliar**.
- Unas 45 de las ~75 consultas de la cola larga son junior.
- Todavía no existe un interruptor para apagar junior.

Por eso llegan vacantes que piden experiencia.

## 4. Qué decide DeepSeek

- **Solo decide las dudosas**: la regla 7, más las aceptadas que tienen la modalidad por confirmar o son remotas sin país. **Lo que acepta la regla 5 nunca pasa por la IA.** En esas, el que aprueba es el código, no DeepSeek.
- **Lotes y llamada:** hasta 30 vacantes por llamada, temperatura 0, respuesta JSON. Se envía título, empresa, ubicación, modalidad, salario y la descripción cortada a 1.500 caracteres (`radar/clasificador.py:196-222`).
- **Prompt** (`config.yaml:899`):
  - Acepta TI en nivel de práctica, aprendiz, trainee, **junior o de entrada con hasta 1 año** de experiencia.
  - Rechaza lo que no es TI, lo senior y lo que pide 2 años o más.
  - «Prácticas» solo con evidencia explícita en el texto.
- **Caché:** tabla `clasificaciones`, por huella (título + empresa) y versión del prompt. Si el prompt cambia, la caché se invalida.
- **Topes** (`radar/ia_cliente.py:146-150`): 300 llamadas al día. Si el saldo baja de 1 USD o no hay clave, no se llama.
- **Si falla** (tope, saldo, error o JSON inválido): la dudosa espera en `pendientes` y se reintenta en cada corrida. **A las 24 h vence y se descarta** (`horas_vencimiento_pendiente`).
- **Guardarraíl:** después de la IA, una vacante en «Prácticas» sin evidencia en el título (ni evidencia fuerte en la descripción) pasa a su área. Nunca rechaza junior.

## 5. Deduplicación y retención

- `Estado.ya_vista` (`comun/estado.py:341`) compara la **clave** (fuente + id) **o la huella** (título + empresa normalizados) con las `vistas` de los últimos **90 días**.
  - Una empresa que repite «Aprendiz SENA» para una cohorte nueva queda bloqueada 90 días (H5).
  - Las filas sembradas con `--seed` también bloquean, aunque nunca se publicaron.
- `vistas` guarda título, empresa, URL, categoría, ubicación y modalidad. Las columnas `publicada`, `destacada` y `area` existen, pero **nunca se llenan**.
- `descartes` existe desde el commit `139372f` (tareas 1.1 y 1.2 del change abierto) y guarda etapa, motivo y detalle por 14 días. Solo tiene datos desde que ese commit se desplegó en el Fedora.

## 6. Hipótesis del silencio del 24/10 (después de las 8:33)

El 24 de octubre de 2026 fue **sábado**. Sin los datos del servidor, las causas posibles son, de más a menos probable:

| # | Hipótesis | Señal que la confirma |
|---|---|---|
| 1 | **Fin de semana + saturación.** Se publica poco y los mismos 14 términos del núcleo se repiten cada 30 min; lo nuevo se agota temprano y el resto cae en duplicadas o en `presencial_fuera`. | `corridas`: `crudas` alto, `duplicadas` casi igual a `crudas`, `enviadas = 0`. |
| 2 | **Cooldown en cadena** de Computrabajo, elempleo o Magneto (2 h → 6 h → 24 h) sin aviso en el primer bloqueo. | `fuentes_estado.cooldown_hasta` en el futuro; `[bloqueo]` o `[captcha]` en el log. |
| 3 | **Cuello de botella del detalle de LinkedIn:** como máximo unos 24 detalles al día, que se cortan del todo tras un 429. | `pendientes_detalle` creciendo; `ritmo:linkedin` en `kv`. |
| 4 | **Telegram rechazando en bucle** (mensaje inválido, 429 de más de 30 s, bot fuera del grupo). El healthcheck sigue en verde. | `Telegram rechazó` en el log; `por_enviar` creciendo; incidente `telegram:fallo_envio`. |
| 5 | **DeepSeek sin saldo** (menos de 1 USD) o con respuestas inválidas: las dudosas vencen a las 24 h. | `ia_uso.motivo`; `kv.ia_saldo`. |
| 6 | Corridas que no ocurren (equipo suspendido, red caída, `uv` fallando, `config.local.yaml`). | `corridas` sin filas después de las `13:33Z`. |

La [fase 0](fase-0-diagnostico-del-silencio.md) tiene las consultas exactas para confirmar cuál fue.

## 7. Debilidades del módulo de scraping

Vistas con ojos de arquitecto de RPA, de más a menos grave:

1. **No hay una verificación de punta a punta.** Nada avisa «0 publicadas en N horas mientras las fuentes sí traen ítems». El healthcheck da éxito aunque Telegram rechace todo, y los incidentes de volumen miden ítems crudos, no publicaciones.
2. **El primer bloqueo no avisa.** El incidente solo se abre a la segunda corrida bloqueada.
3. **Algunos fallos se clasifican mal.**
   - El muro de login de LinkedIn (responde 200) cuenta como `cambio_html`, sin backoff.
   - El 404 de elempleo cuenta como éxito.
   - Los desafíos se detectan con 5 subcadenas.
4. **La huella delata al bot.** User-Agent de Chrome sin los encabezados que lo acompañan, HTTP/1.1, sin cookies, una sola IP, cadencia exacta de :00 y :30, y el mismo ritmo para todas las fuentes sin importar cuánto rinden.
5. **Se repite lo mismo en lugar de buscar lo fresco.**
   - Computrabajo ordena la página 1 por relevancia; GetOnBoard no tiene orden ni filtro de fecha; Magneto solo lee la página 1.
   - Ninguna fuente deja de paginar cuando todo lo que ve ya es viejo.
6. **LinkedIn rinde poco:** 20 tarjetas cada 2 h, y el detalle depende del intervalo de LinkedIn.
7. **La deduplicación es demasiado amplia:** 90 días por título y empresa, sin tener en cuenta la ciudad ni la cohorte.
8. **Queda poca evidencia para investigar:** de cada petición solo se guarda el estado, el número de ítems y el tipo de error, nunca el HTML de la respuesta que falló.
9. **Las reglas y la IA no están alineadas con la prioridad.** Junior está activo, la regla 5 acepta con evidencia débil y no hay métrica de qué porcentaje de lo publicado es de aprendizaje.
10. **El runbook está desactualizado:** `deploy/INSTALAR.md` todavía describe los ritmos viejos de LinkedIn y consultas por día UTC.
