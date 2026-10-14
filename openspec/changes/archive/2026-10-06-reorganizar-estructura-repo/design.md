# Design

## Context

Ver proposal.md (Why). Estado actual que condiciona el enfoque:

- `pyproject.toml` declara `[tool.uv] package = false` y pytest usa `pythonpath = ["."]`.
  El código se importa como módulos sueltos de la raíz (`import config as cfg`,
  `from modelo import Vacante`, `from fuentes.base import ...`).
- Producción (PC Fedora) ejecuta `uv run --frozen buscador.py [resumen]` con
  `WorkingDirectory=%h/buscador-vacantes`, desde `deploy/buscador.service` y
  `deploy/buscador-resumen.service`.
- `config.RAIZ = Path(__file__).resolve().parent` es la base de `config.yaml`, `.env`,
  `data/`, `logs/` y `assets/`. Lo usan `buscador.py` y los tests.
- `tests/test_simulacion.py` parchea `"simulacion.FALLAS_IA"` por texto, y
  `tests/test_buscador.py` hace `import buscador` y lee `buscador.cfg.RAIZ`.
- Nada lee los nombres de logger; solo aparecen en las líneas de log
  (`%(name)s`).

## Goals / Non-Goals

**Goals:**
- Raíz con un solo `.py` (el punto de entrada) y el resto del código en un paquete.
- Mantener intacta la historia de git de cada archivo (`git mv`).
- Despliegue en Fedora con solo `git pull`, sin tocar unidades systemd ni `.env`.

**Non-Goals:**
- Partir `corrida.py` (unas 670 líneas) en módulos más pequeños, renombrar funciones o
  cambiar cualquier lógica.
- Convertir el proyecto en paquete instalable (`package = true`, `[project.scripts]`)
  o pasar a la estructura `src/`.
- Reescribir las rutas citadas en los artefactos del change `crear-buscador-vacantes`.

## Decisions

**D1. Paquete plano `buscador_vacantes/` en la raíz, sin `src/`.**
Con `package = false` y `pythonpath = ["."]`, un paquete en la raíz se importa tal cual
desde `uv run buscador.py` (la raíz queda en `sys.path[0]`) y desde pytest.
*Alternativa:* `src/buscador_vacantes/` con `package = true`. Obliga a instalar el
proyecto en el venv y a cambiar `uv.lock` y el despliegue a cambio de nada que este
proyecto necesite.

**D2. `buscador.py` de la raíz queda como envoltorio de 3 líneas; el contenido actual
pasa a `buscador_vacantes/corrida.py`.**
Mantiene idénticos `uv run buscador.py ...`, `deploy/*.service`, `deploy/prueba/*.conf`,
`README.md` y `deploy/INSTALAR.md`. El nombre `corrida.py` evita tener dos
`buscador.py` (raíz y paquete) y describe lo que contiene (clase `Corrida`, `main`).
El `git mv` se hace sobre el archivo original para conservar su historia; el envoltorio
nuevo se crea después.
*Alternativa:* `uv run python -m buscador_vacantes`. Obliga a editar las unidades
systemd en producción y toda la documentación de comandos.

**D3. Imports absolutos `from buscador_vacantes.x import ...`.**
Se leen igual en el paquete y en los tests, y ruff/isort los clasifica como de primera
parte sin configuración extra. `import config as cfg` pasa a
`from buscador_vacantes import config as cfg` para no tocar el resto del código que usa
`cfg.`. En los tests, `import buscador` pasa a
`from buscador_vacantes import corrida as buscador` por la misma razón.
*Alternativa:* imports relativos (`from .modelo import`). Son válidos, pero los tests
seguirían necesitando la forma absoluta y quedarían dos estilos.

**D4. `RAIZ = Path(__file__).resolve().parent.parent`.**
`config.py` baja un nivel, así que RAIZ sube uno. Todo lo que cuelga de RAIZ
(`config.yaml`, `.env`, `data/`, `logs/`, `assets/`) sigue apuntando a la raíz del repo.
`publicacion.publicar(raiz=Path("."))` no cambia: quien la llama ya pasa `cfg.RAIZ`.

**D5. Nombres de logger: se aceptan con prefijo.**
Los módulos con `logging.getLogger(__name__)` pasan a registrar
`buscador_vacantes.<módulo>`. `buscador.py` (ahora `corrida.py`) usa el nombre literal
`"buscador"` y `fuentes/base.py` usa `f"fuentes.{nombre}"`, y ambos se conservan.
Cambiar `__name__` por literales en 9 módulos para ahorrar un prefijo cosmético no
compensa.

**D6. Documentación de referencia a `docs/`.**
`buscador-vacantes-spec.md` → `docs/buscador-vacantes-spec.md` y
`referencia_hermes/` → `docs/referencia_hermes/`. En `pyproject.toml`, la exclusión de
ruff `referencia_hermes` pasa a `docs`.

## Risks / Trade-offs

- [Que un `git pull` en Fedora coincida con una corrida en marcha y esta importe un
  módulo ya movido] → Parar `buscador.timer` antes del pull, verificar con `--dry-run`
  y reactivarlo (tarea del grupo 3).
- [Que quede algún import o parche por texto olvidado y solo falle en una ruta poco
  usada] → Los 332 tests cubren todos los módulos. Además, `grep` de los nombres de
  módulo antiguos tras el cambio, y `--dry-run` real y `--simular-incidente` en la Mac.
- [Que `RAIZ` apunte mal y la corrida cree un `data/` vacío dentro del paquete, como si
  no hubiera estado] → Tests de `config` que leen `RAIZ / "config.yaml"`. Además, en
  Fedora se comprueba que el dry-run no envía duplicados, señal de que usa
  `data/vacantes.db` existente.
- [Que `__pycache__` de la raíz quede con módulos viejos importables] → Están en
  `.gitignore`. En Fedora el envoltorio importa explícitamente desde `buscador_vacantes`,
  así que no se resuelve por error contra un `.pyc` suelto de la raíz.

## Migration Plan

1. Mac: implementar, `uv run pytest`, `uv run ruff check .`, `--dry-run`. Commit y push.
2. Fedora: `systemctl --user stop buscador.timer` → `git pull` → `uv sync --frozen` →
   `uv run buscador.py --dry-run` → `systemctl --user start buscador.timer`. Revisar la
   siguiente corrida con `journalctl --user -u buscador`.
3. **Rollback:** `git checkout <commit anterior>` en `~/buscador-vacantes` y reiniciar el
   timer. No hay migración de datos que deshacer.
