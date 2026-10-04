# Tasks

## 1. Paquete `buscador_vacantes/`

- [x] 1.1 Crear `buscador_vacantes/__init__.py` y mover con `git mv` los módulos de la raíz (config, estado, filtros, clasificador, ia_cliente, formato, publicacion, notificador_telegram, incidentes, reportero, resumen, simulacion, salud, migrar_historial, modelo, normalizar, fechas, rotacion, registro, lock) y `fuentes/` a `buscador_vacantes/`, y `buscador.py` a `buscador_vacantes/corrida.py`. Verificar con `git status`, que muestra solo renombrados (R), y con que en la raíz no queda ningún `.py`.
- [x] 1.2 Reescribir los imports del paquete a la forma absoluta `buscador_vacantes.*` (D3) y cambiar `RAIZ` a `Path(__file__).resolve().parent.parent` (D4). Verificar con `grep -rnE "^(from|import) (config|estado|filtros|clasificador|ia_cliente|formato|publicacion|notificador_telegram|incidentes|reportero|resumen|simulacion|salud|migrar_historial|modelo|normalizar|fechas|rotacion|registro|lock|fuentes|buscador)\b" buscador_vacantes tests`, que no devuelve nada.
- [x] 1.3 Crear el envoltorio `buscador.py` en la raíz (importa `main` de `buscador_vacantes.corrida` y hace `sys.exit(main())`) y agregar un test que ejecute `buscador.py --help` como subproceso y compruebe que sale con código 0. Verificar con que `uv run buscador.py --help` muestra las mismas opciones que antes.
- [x] 1.4 Actualizar los tests: imports, `import buscador` → `from buscador_vacantes import corrida as buscador`, y el parche por texto `"simulacion.FALLAS_IA"` → `"buscador_vacantes.simulacion.FALLAS_IA"`. Verificar con `uv run pytest` (332 pasan y 2 se saltan, más el test nuevo de 1.3), `uv run ruff check .` y `uv run ruff format --check .` limpios.
- [x] 1.5 Actualizar en `README.md` el árbol de módulos (rutas bajo `buscador_vacantes/`, `corrida.py` como CLI y flujo, cómo agregar una fuente en `buscador_vacantes/fuentes/` y registrarla en `FUENTES` de `corrida.py`). Verificar releyendo que cada ruta citada existe (`ls`).

## 2. Documentación a `docs/`

- [x] 2.1 Mover con `git mv` `buscador-vacantes-spec.md` a `docs/` y `referencia_hermes/` a `docs/referencia_hermes/`. En `pyproject.toml`, cambiar la exclusión de ruff `referencia_hermes` por `docs`. Verificar con `uv run ruff check .` limpio.
- [x] 2.2 Actualizar las referencias en `CLAUDE.md`, `openspec/config.yaml` y `README.md` (ejemplo `migrar --archivo docs/referencia_hermes/historial_vacantes.json`). Verificar con `grep -rn "buscador-vacantes-spec\|referencia_hermes" --exclude-dir=.venv --exclude-dir=.git --exclude-dir=changes .`, que solo devuelve rutas con `docs/`.

## 3. Verificación y despliegue

- [x] 3.1 En la Mac, ejecutar `uv run buscador.py --dry-run --fuente getonboard`, `uv run buscador.py --dry-run resumen` y `uv run buscador.py --simular-incidente linkedin:bloqueo --dry-run`. Verificar que terminan sin error, que leen `config.yaml` y `.env` de la raíz y que no aparece ningún `data/` ni `logs/` dentro de `buscador_vacantes/`.
- [x] 3.2 Hacer commit y push a `main` (mensajes en español, sin atribución a IA). Verificar con `git status` limpio y `git log origin/main -1`.
- [x] 3.3 En el PC Fedora: `systemctl --user stop buscador.timer` → `git pull` → `uv sync --frozen` → `uv run buscador.py --dry-run` → `systemctl --user start buscador.timer`, sin tocar las unidades systemd ni el `.env`. Verificar con `systemctl --user list-timers` (timer activo), la siguiente corrida sin errores en `journalctl --user -u buscador` y healthchecks en verde.
