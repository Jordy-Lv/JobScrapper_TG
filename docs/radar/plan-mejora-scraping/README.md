# Plan de mejora del módulo de scraping (radar)

> Fecha: 24 de octubre de 2026 · Origen: [diagnóstico del dueño](diagnostico-2026-10-24.md) · Alcance: solo el **radar** (búsqueda, filtrado y publicación). El asistente de postulación queda fuera de este plan.

## Objetivo

Que el grupo «JOBS - PRÁCTICAS/APRENDIZ» reciba **todas** las vacantes de aprendizaje, contrato de aprendizaje, prácticas, pasantías, trainee y sin experiencia de TI, y que nunca vuelva a pasar un día en silencio sin saber por qué. Se resaltan las de bases de datos, programación, infraestructura y QA, con la fecha de publicación exacta.

## Decisiones del dueño (24/10/2026)

| Tema | Decisión |
|---|---|
| Vacantes junior (1–2 años) | **Se apagan** con el interruptor `alcance.junior`. Prioridad absoluta: aprendizaje, prácticas, trainee y **sin experiencia**. Se pueden volver a encender sin tocar código. |
| Recuperación de la última semana | **Solo las nunca publicadas** (descartadas, vencidas o sembradas). Se reevalúan con las reglas nuevas y salen primero al chat de prueba. Las ya publicadas no se reenvían. |
| Change abierto `aprendizaje-primero-canal-y-consultas` | Se **separa**: sus bloques de scraping (1–4) son la fase 1. El bloque 5 se reemplaza por la fase 2. Los bloques 6–7 (selector y `/buscar` del asistente) pasan a un change aparte, `selector-y-consultas-asistente`, para después. |

*Propuesta, pendiente de decisión:* volver a evaluar el nivel junior cuando la fase 1 lleve dos semanas cumpliendo la métrica del 95 %.

## Mapa del diagnóstico a las fases

| # | Pedido del diagnóstico | Dónde se atiende |
|---|---|---|
| 1 | La última vacante llegó a las 8:33: revisar el scraping y las mejoras | [Estado actual](estado-actual.md) (hipótesis) · [Fase 0](fase-0-diagnostico-del-silencio.md) (confirmarlo en el servidor) · [Fase 4](fase-4-observabilidad.md) (que no vuelva a pasar a ciegas) |
| 2 | ¿DeepSeek decide qué se aprueba? ¿Cuáles son las reglas? | [Estado actual §3 y §4](estado-actual.md#3-reglas-de-filtrado-en-orden) · [Fase 1](fase-1-aprendizaje-primero.md) (DeepSeek verificable) |
| 3 | Borrar descartes y recuperar vacantes de menos de una semana | [Fase 3](fase-3-recuperacion-y-limpieza.md) |
| 3b | Prioridad del 95 % a aprendices y sin experiencia | [Fase 1](fase-1-aprendizaje-primero.md) |
| 4 | Recomendaciones de un experto en scraping | [Estado actual §7](estado-actual.md#7-debilidades-del-módulo-de-scraping) · [Fase 4](fase-4-observabilidad.md) · [Fase 5](fase-5-recoleccion-robusta.md) |
| 5 | Más visibilidad para bases de datos, programación, infraestructura y QA | [Fase 2](fase-2-visibilidad-y-fechas.md) |
| 6 | Fecha de publicación más específica | [Fase 2](fase-2-visibilidad-y-fechas.md) |

## Fases

| Fase | Nombre | Dificultad | Change de OpenSpec | Depende de |
|---|---|---|---|---|
| 0 | [Diagnóstico del silencio del 24/10](fase-0-diagnostico-del-silencio.md) | 👤 + 🟢 | ninguno (solo documentación) | — |
| 1 | [Aprendizaje y sin experiencia primero](fase-1-aprendizaje-primero.md) | 🔴 | `aprendizaje-primero-canal-y-consultas` (ajustado con `/opsx:update`) | 0 |
| 2 | [Visibilidad por área y fecha transparente](fase-2-visibilidad-y-fechas.md) | 🟡 | `visibilidad-area-y-fecha` (nuevo) | puede ir en paralelo con la 1 |
| 3 | [Recuperación y limpieza de la última semana](fase-3-recuperacion-y-limpieza.md) | 🟡 | `recuperar-vacantes-semana` (nuevo) | 1 (y mejor tras la 2) |
| 4 | [Observabilidad](fase-4-observabilidad.md) | 🟡 | `observabilidad-scraping` (nuevo) | 0 |
| 5 | [Recolección robusta y eficiente](fase-5-recoleccion-robusta.md) | 🔴 | `recoleccion-robusta` (nuevo; se puede partir en 5a, 5b y 5c) | 4 |

```
Fase 0 ──► Fase 1 ──► Fase 3
   │          └─(paralelo)─ Fase 2
   └──► Fase 4 ──► Fase 5
```

**Orden recomendado:** 0 → 1 → 2 → 3 → 4 → 5. Si la fase 0 confirma una falla operativa (bloqueo de una fuente, Telegram rechazando mensajes o DeepSeek sin saldo), la parte de la fase 4 que la cubre se adelanta como arreglo urgente, antes de la fase 1.

**Ventana sugerida:** la fase 3 recupera vacantes de 7 días como máximo. Si la fase 1 tarda más de una semana, las vacantes del 17 al 24 de octubre ya no se recuperan por la base. En ese caso solo queda el barrido profundo de la fase 3, que lee lo que los portales aún muestran.

## Métricas de éxito del plan

| Métrica | Hoy | Meta | Cómo se mide |
|---|---|---|---|
| Vacantes publicadas que son de práctica, aprendizaje, trainee o sin experiencia | sin medir (junior activo por diseño) | ≥ 95 % | resumen diario (fase 1) |
| Horas seguidas sin publicar en horario laboral sin una alerta | sin límite (el 24/10, desde las 8:33) | ≤ 4 h con alerta automática | incidente de sequía (fase 4) |
| Vacantes de aprendizaje que el dueño encuentra a mano y el bot no publicó | desconocido | 0 sin causa explicada por `diagnosticar` | corpus de la fase 1 |
| Tarjetas con fecha de publicación explícita, o con aviso de «sin fecha» | solo «hoy / ayer / hace N días» | 100 % | pruebas de `formato.py` (fase 2) |
| Vacantes de las 4 áreas foco con etiqueta visible | 0 % | 100 % | pruebas de `formato.py` (fase 2) |
| Peticiones diarias a los portales | ~1.100 desde una IP, a ritmo fijo | menos peticiones con la misma o mejor cobertura | tabla `intentos` (fase 5) |

## Cómo se ejecuta cada fase

1. Abrir una **sesión nueva** por fase. Todas menos la 0 son 🟡 o 🔴 y cargan contexto propio.
2. Crear el change con `/opsx:propose <nombre>`, o ajustarlo con `/opsx:update` en la fase 1, usando como base el documento de la fase.
3. Implementar con `/opsx:apply`, marcando `[x]` en `tasks.md` y dejando las pruebas en verde: `uv run pytest`, `uv run ruff check` y `uv run ruff format --check`.
4. Las tareas 👤 (despliegue en el Fedora, revisión en el chat de prueba) las hace el dueño. No se simulan.
5. Archivar con `/opsx:archive` cuando la verificación en producción esté cumplida.

## Documentos

- [diagnostico-2026-10-24.md](diagnostico-2026-10-24.md): el pedido original del dueño.
- [estado-actual.md](estado-actual.md): cómo funciona hoy el radar, qué decide DeepSeek, hipótesis del silencio y debilidades.
- Fases: [0](fase-0-diagnostico-del-silencio.md) · [1](fase-1-aprendizaje-primero.md) · [2](fase-2-visibilidad-y-fechas.md) · [3](fase-3-recuperacion-y-limpieza.md) · [4](fase-4-observabilidad.md) · [5](fase-5-recoleccion-robusta.md)
