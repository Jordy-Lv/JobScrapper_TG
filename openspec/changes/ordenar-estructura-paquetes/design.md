## Context

Ver proposal.md. Hallazgos medidos sobre el árbol unificado (rama del asistente + `main`): `asistente/` ya es un paquete (~40 módulos; `conversacion.py` de 2.342 líneas queda para la fase 3); en `buscador_vacantes/` hay 25 módulos planos y `fuentes/` (7). El asistente importa de los planos: `config` (13 veces), `estado` (`a_texto`, `de_texto`, `ahora_utc`), `normalizar` (6), `fechas` y `registro`. No importa `ia_cliente`, `formato`, `salud`, `incidentes`, `notificador_telegram`, `lock`, `reportero` ni `publicacion`. Hay cadenas de parcheo a rutas viejas en `tests/test_simulacion.py` y `tests/test_asistente_servicio.py`. `buscador.py` solo importa `corrida.main`; las unidades systemd lo invocan por nombre de archivo.

## Goals / Non-Goals

**Goals:**
- Tres paquetes con dependencias en un solo sentido, sin cambiar comportamiento.
- Historial de git conservado.

**Non-Goals:**
- Dividir `conversacion.py` (fase 3), mover assets/docs (fase 2), perfiles en `data/control.db` (fase 4).
- Cambiar nombres de funciones o clases, `config.yaml` o esquemas de BD.

## Decisions

- **Reparto propuesto** (a confirmar con el dueño):
  - `comun/`: `config`, `estado`, `modelo`, `normalizar`, `fechas`, `registro`, `lock`.
  - `radar/`: `corrida`, `clasificador`, `filtros`, `resumen`, `rotacion`, `publicacion`, `reportero`, `incidentes`, `salud`, `formato`, `simulacion`, `migrar_historial`, `ia_cliente`, `notificador_telegram`, `fuentes/`.
  - `asistente/`: sin cambios de contenido. Su cliente de IA propio (`asistente/ia/`) no se fusiona con `ia_cliente`.
  - Dudosos: `ia_cliente` y `notificador_telegram` (hoy solo los usa el radar; irían a `comun/` si el asistente los reutiliza luego).
- **Movimiento en commits separados:** primero solo `git mv` (ese commit puede dejar la suite en rojo), luego los imports; se verifica con `git log --follow`. Alternativa descartada: scripts de reescritura sin `git mv`.
- **Imports absolutos** (`buscador_vacantes.radar.corrida`), sin reexportar módulos viejos desde la raíz, para que los errores de ruta salten en la suite y no se oculten con alias.
- **`buscador.py`**: mismo contrato externo (argumentos, salida); solo cambia la línea de import de `main` si la ruta cambia.
- **Prueba de arquitectura** que recorre los imports con `ast` y falla si se viola la dirección `comun` ← `asistente` ← `radar`. Decisión del dueño (2026-10-14): `radar` puede importar de `asistente` (hoy lo hacen `corrida`, `formato`, `publicacion` y `resumen`); el desacoplamiento total queda fuera de esta fase, como cambio propio si se necesita.
- **Planes de changes abiertos:** reemplazo de rutas solo en markdown mediante una tabla antiguo→nuevo; no se tocan sus tareas ya marcadas ni su código.

## Risks / Trade-offs

- Trabajo sin confirmar en `linkedin-detalle-vacantes` y otros changes: hacerlo cuando estén confirmados, o rebasar tras el movimiento.
- Las cadenas de parcheo y `sys.modules[...]` en pruebas no las detecta un buscador de imports: grep por `"buscador_vacantes.` y suite completa.
- Rutas de módulos guardadas en datos: se verifica que los esquemas SQLite no tengan ninguna.
- Entorno del Fedora (`uv run --frozen`): probar `buscador.py`, `resumen` y `asistente servicio` antes de desplegar.
- Si la fase 0 no está desplegada, el movimiento genera conflictos con la rama del asistente.
