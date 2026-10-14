# 0001. Paquetes `comun`, `radar` y `asistente`

- **Estado:** aceptada
- **Fecha:** 2026-10-14
- **Cambio de OpenSpec:** `ordenar-estructura-paquetes`

## Contexto

El proyecto empezó como el buscador de vacantes (el radar) y después sumó el asistente de
postulación en la misma base de código. Los módulos del radar vivían planos en
`buscador_vacantes/`, junto al subpaquete `asistente/`, y las pruebas estaban todas en
`tests/`. No se veía qué parte dependía de cuál: el asistente importaba `config`, `estado`,
`normalizar`, `fechas` y `registro` sin que nada marcara que eran compartidos.

## Decisión

El código se organiza en tres paquetes dentro de `buscador_vacantes/`, y las pruebas siguen la
misma forma en `tests/`:

| Paquete | Contenido |
|---|---|
| `comun/` | Infraestructura compartida: `config`, `estado`, `modelo`, `normalizar`, `fechas`, `registro`, `lock`. |
| `radar/` | Buscador y publicación: `corrida`, `filtros`, `clasificador`, `ia_cliente`, `notificador_telegram`, `formato`, `publicacion`, `reportero`, `resumen`, `incidentes`, `salud`, `rotacion`, `detalle`, `simulacion`, `migrar_historial` y `fuentes/`. |
| `asistente/` | Bot, API para la extensión, CV adaptado, cola de postulaciones y proveedores de IA del usuario. |

Las dependencias van en un solo sentido: **`comun` ← `asistente` ← `radar`**.

- `comun` no importa de `radar` ni de `asistente`.
- `asistente` no importa de `radar`.
- `radar` sí puede importar de `asistente` y de `comun`, porque es el radar quien pone el botón
  ⚡ y el enlace del asistente en cada vacante (`formato`, `publicacion`), quien arranca el
  subcomando `asistente` (`corrida`) y quien reporta sus métricas en el resumen diario
  (`resumen`).

Una prueba de arquitectura (`tests/comun/test_arquitectura.py`) recorre los imports con `ast`
y falla si se viola esta dirección.

`buscador.py` se mantiene igual y es el único punto de entrada, de modo que las unidades de
systemd no cambian.

## Alternativas descartadas

- **Desacoplamiento total (el radar no importa del asistente):** exigía mover `enlaces.py` a
  `comun/` y separar `resumen` y `corrida` de la base del asistente. Es un refactor real sobre el
  código que publica en el canal, sin beneficio mientras ambos viven en el mismo repositorio y
  servidor. Si algún día se separan en dos programas, la prueba de arquitectura indica qué falta.
- **Reexportar los módulos viejos desde la raíz para no tocar imports:** habría ocultado rutas
  rotas en lugar de hacerlas saltar en la suite.
- **Mover `ia_cliente` y `notificador_telegram` a `comun/`:** hoy solo los usa el radar (el
  asistente tiene su propio cliente de IA multiproveedor en `asistente/ia/`). Pasarán a `comun/`
  cuando el asistente los reutilice.

## Consecuencias

- Cada módulo declara por carpeta a qué parte del sistema pertenece, y las dependencias
  prohibidas se detectan automáticamente.
- Los nombres de los módulos en los registros ahora incluyen el paquete (por ejemplo
  `buscador_vacantes.radar.incidentes`).
- `RAIZ` (en `comun/config.py`) depende de la profundidad de la carpeta: si `config.py` se vuelve
  a mover, hay que ajustarla.
- Los módulos de pruebas con el mismo nombre en paquetes distintos (por ejemplo
  `test_detalle.py`) conviven gracias a los `__init__.py` de `tests/`.
- La división de `asistente/conversacion.py` (unas 2.300 líneas) queda para la fase 3.
