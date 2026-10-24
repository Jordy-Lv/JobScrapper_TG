# Fase 3: recuperación y limpieza de la última semana

| | |
|---|---|
| **Dificultad** | 🟡 media (comando nuevo, estado y pruebas) + 👤 (copia de seguridad, revisión en el chat de prueba y ejecución en el Fedora) |
| **Change de OpenSpec** | `recuperar-vacantes-semana` (nuevo) |
| **Atiende** | punto 3 del diagnóstico: borrar los descartes y recuperar las vacantes de una semana o menos |
| **Depende de** | [fase 1](fase-1-aprendizaje-primero.md): hay que reevaluar con las reglas nuevas, o se recupera el mismo spam. Mejor si la [fase 2](fase-2-visibilidad-y-fechas.md) ya está, para que las recuperadas salgan con el formato nuevo. |

## Objetivo

Rescatar las vacantes de aprendizaje y sin experiencia de **los últimos 7 días que nunca se publicaron**: las descartadas por reglas viejas, las vencidas esperando a la IA y las sembradas sin enviar. Se publican una sola vez, marcadas como recuperadas. Después se limpian los registros que ya no sirven.

**Fuera del alcance** (decisión del dueño): no se reenvían las vacantes que ya salieron al grupo.

## Lo que se puede recuperar

| Origen | Qué guarda | Cuánto dura | Limitación |
|---|---|---|---|
| `descartes` | título, empresa, URL, ubicación, modalidad, etapa y motivo | 14 días | Sin fecha de publicación, salario ni descripción. Existe desde el despliegue del commit `139372f`. |
| `vistas` sembradas (`enviada_en` y `prueba_en` nulos) | título, empresa, URL, categoría, ubicación y modalidad | 90 días | Sin fecha de publicación (`publicada` nunca se llenó). |
| `pendientes`, `pendientes_detalle`, `por_enviar` | la vacante completa (`vacante_json`) | 24–48 h | Solo lo muy reciente. |
| Lo que nunca quedó registrado | — | — | Solo se recupera **volviendo a buscarlo** en los portales (el barrido profundo). |

Como `descartes` y las vistas sembradas no guardan la fecha de publicación, la antigüedad se estima con `primera_vez` o `ultima_vez`. En las que pasan los filtros se pide el detalle para leer la fecha real y la descripción, y las de más de 7 días se cortan.

## Tareas

### 1. Copia de seguridad (👤)

```bash
sqlite3 data/vacantes.db ".backup 'data/vacantes-antes-recuperar-$(date +%F).db'"
```

### 2. Comando `buscador.py recuperar` (🟡)

```text
uv run buscador.py recuperar --dias 7 [--dry-run | --chat-prueba] [--origen descartes,sembradas,pendientes] [--tope 40]
```

1. **Reúne los candidatos** de los orígenes elegidos, con 7 días o menos (`ultima_vez` / `primera_vez`) y sin `enviada_en` en `vistas`.
2. **Reconstruye** cada `Vacante`. Si la fuente lo permite, pide el detalle para tener la descripción y la fecha, con el presupuesto de detalle de la fuente y respetando los cooldowns.
3. **Reevalúa** con las reglas de la fase 1, el guardarraíl, el alcance (junior pausado) y la IA para las dudosas. El prompt nuevo invalida la caché vieja de `clasificaciones`, así que no se repiten los rechazos anteriores.
4. **Publica** las que pasan, con el encabezado «♻️ <b>N vacantes recuperadas de la última semana</b>», ordenadas por fecha y como máximo `--tope` por ejecución (1 s entre mensajes, como `publicacion.py`).
5. **Marca** cada vacante recuperada para no enviarla dos veces: columna `recuperada_en` en `vistas` (migración de esquema). `enviada_en` se llena como en un envío normal, para que el asistente la indexe.
6. **`--dry-run`** solo imprime cuántas hay por origen, cuántas pasan y por qué se descartan las demás. Ni escribe ni envía.

### 3. Barrido profundo, una sola vez (🟡)

Es para lo que nunca quedó registrado, por ejemplo si `descartes` no estaba desplegada.

```text
uv run buscador.py --barrido-profundo --dias 7 [--dry-run | --chat-prueba] [--fuente X]
```

- Ventanas de 7 días donde la fuente lo permite: Computrabajo `pubdate=7`, LinkedIn `f_TPR=r604800`, elempleo `hace-1-semana` (ya lo usa).
- **Solo el núcleo de aprendizaje**, con más páginas (3 a 5).
- Ignora las vistas **sembradas**, pero respeta las enviadas.
- Presupuesto propio y pausas más largas (de 10 a 20 s), para no gatillar bloqueos.
- Pensado para correrlo una vez de madrugada, fuera de la cadencia de 30 minutos (el lock ya lo impide).

### 4. Limpieza (🟢, después de recuperar)

- Borrar de `descartes` las filas ya procesadas por `recuperar`, recuperadas o no.
- Borrar las **vistas sembradas** de más de 7 días que nunca se enviaron (`enviada_en IS NULL AND prueba_en IS NULL`). Así una vacante vigente que vuelva a aparecer en un portal se reevalúa en vez de quedar bloqueada 90 días.
- Comando: `uv run buscador.py limpiar --descartes-procesados --sembradas-antes 7`, con `--dry-run` que muestra los conteos.
- `estado.dias_descartes` sigue en 14 para la auditoría diaria de la fase 1.

### 5. Ejecución (👤)

1. `recuperar --dry-run` y `--barrido-profundo --dry-run`: revisar los conteos.
2. `recuperar --chat-prueba`: el dueño revisa el mensaje «♻️».
3. `recuperar` hacia el grupo real.
4. `limpiar`.

## Criterios de aceptación

- [ ] `recuperar --dry-run` lista los candidatos por origen y el veredicto de cada uno, sin escribir nada; se prueba en `tests/radar`.
- [ ] Ninguna vacante se publica dos veces: una prueba corre `recuperar` dos veces seguidas y la segunda no envía nada.
- [ ] Ninguna recuperada tiene más de 7 días según la fecha de publicación, o según `primera_vez` si el portal no da fecha.
- [ ] Las recuperadas cumplen el alcance de la fase 1: ninguna junior ni con 1 año o más de experiencia.
- [ ] Después de `limpiar` no quedan vistas sembradas de más de 7 días sin enviar, ni descartes procesados.
- [ ] La copia de seguridad existe antes de la primera ejecución real.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Se vuelve a publicar spam. | Reevaluación obligatoria con las reglas de la fase 1, primero al chat de prueba, y tope por ejecución. |
| Vacantes ya cerradas en el portal. | El detalle detecta 404 y 410 (`pendientes_detalle` ya lo hace) y esas se descartan. |
| El barrido profundo dispara bloqueos. | Una sola vez, solo el núcleo, pausas largas, de madrugada, respetando cooldowns. |
| Pasaron más de 7 días antes de ejecutar la fase. | Solo queda el barrido profundo: los portales siguen mostrando las vigentes. |

## Sesión recomendada

**Sesión nueva** (necesita el contexto de `estado.py` y `corrida.py`, no el de las reglas). Mensaje listo para pegar:

> Ejecuta la fase 3 de `docs/radar/plan-mejora-scraping/fase-3-recuperacion-y-limpieza.md`: crea con `/opsx:propose` el change `recuperar-vacantes-semana` (comandos `recuperar`, `--barrido-profundo` y `limpiar`, con `--dry-run` y `--chat-prueba`) y aplícalo. Las tareas 1 y 5 son del dueño.
