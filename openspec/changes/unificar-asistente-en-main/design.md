## Context

Ver proposal.md para la motivación. Medido con `git merge-tree` y un merge de prueba en un worktree aparte: base común `45be74f`; `main` aporta 5 commits (filtro de vacantes limpias, LinkedIn peticiones eficientes, modalidad) y la rama del asistente 77. Archivos que ambas ramas tocaron: `config.yaml` (+163/-… vs +252/-…), `corrida.py` (108 vs 38 líneas), `resumen.py` (28 vs 117), `config.py`, `deploy/INSTALAR.md`, `README.md` y pruebas. Git fusiona solos `config.yaml`, `corrida.py`, `resumen.py`, `config.py` e `INSTALAR.md`; los 4 conflictos son de texto en `README.md` y 3 archivos de pruebas, todos adiciones de ambos lados. La carpeta de trabajo actual tiene cambios sin confirmar en la rama `linkedin-detalle-vacantes`, por lo que el merge no se hace allí.

## Goals / Non-Goals

**Goals:**
- `main` contiene todo el trabajo del asistente y del radar, con la suite en verde.
- Producción desplegada con `TELEGRAM_CHAT_ADMIN` configurada.

**Non-Goals:**
- Mover carpetas o dividir módulos (fases 1-4 del plan).
- Adaptar los changes pendientes (`linkedin-detalle-vacantes`, etc.) a la rama unificada.

## Decisions

- **Merge, no rebase:** 77 commits ya publicados en `origin`; reescribirlos obliga a force-push. Alternativa descartada: rebase sobre `main`.
- **Rama de integración en worktree propio:** el merge se prepara en un worktree separado partiendo de `asistente-postulacion-telegram` (con `main` mezclada), así no se toca el árbol sucio de `linkedin-detalle-vacantes`. Solo después de confirmar se avanza `main` (fast-forward al commit del merge) y se hace push.
- **README:** se toma íntegro el de la rama del asistente (decisión del dueño). **Pruebas:** se conservan ambos lados, y unificando imports en `test_buscador.py` (`chat_admin`, `a_texto`).
- **Verificación de producción de solo lectura:** comprobar por SSH solo la presencia de la clave (sin valor) en el `.env`.
- **Despliegue tras confirmación:** `git pull` en el Fedora y reinicio de los servicios por el procedimiento de `deploy/INSTALAR.md`.

## Risks / Trade-offs

- Falta `TELEGRAM_CHAT_ADMIN` hoy en el `.env` del Fedora → avisos/resumen sin destino de administración. Mitigación: añadirla antes del `git pull`; el dueño aporta el chat id.
- Fusión automática de `config.yaml`/`corrida.py` sin conflicto textual pero con posible conflicto semántico → la suite y la comparación con la corrida en modo prueba lo detectan.
- Migraciones del asistente sobre las bases SQLite de producción → respaldar `data/` antes del despliegue.
- Los changes pendientes quedan temporalmente desfasados respecto de `main`.
