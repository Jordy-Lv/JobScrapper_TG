# Proposal

## Why

La raíz del repositorio acumula 21 módulos Python sueltos junto a la configuración, la
documentación y los archivos de referencia de Hermes. Eso dificulta ver en GitHub qué es
código, qué es configuración y qué es documentación. Ahora que el buscador está en
producción y estable, es buen momento para ordenarlo sin cambiar lo que hace.

## What Changes

- Los 21 módulos de la raíz y el subpaquete `fuentes/` pasan a un paquete
  `buscador_vacantes/`. El flujo y la CLI que hoy viven en `buscador.py` pasan a
  `buscador_vacantes/corrida.py`.
- En la raíz queda solo un `buscador.py` delgado como punto de entrada, así que
  `uv run buscador.py ...` y las unidades systemd del PC Fedora siguen iguales.
- `buscador-vacantes-spec.md` y `referencia_hermes/` pasan a `docs/`.
- Se actualizan los imports, los tests, la raíz de rutas de `config.py` (sigue
  resolviendo `config.yaml`, `.env`, `data/`, `logs/` y `assets/` en la raíz del repo),
  `README.md`, `CLAUDE.md`, `openspec/config.yaml` y la exclusión de ruff en
  `pyproject.toml`.
- Sin cambios de comportamiento: mismas opciones de CLI, mismos mensajes, mismo
  estado SQLite y mismas rutas de datos.

Raíz resultante:

```
buscador.py  buscador_vacantes/  tests/  deploy/  assets/  docs/  openspec/
config.yaml  pyproject.toml  uv.lock  README.md  CLAUDE.md  .env.example
```

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

Ninguna. Es un refactor de estructura sin cambios de comportamiento observable, por lo
que el change declara `skip_specs: true`.

## Impact

- **Código:** todos los módulos de la raíz y `fuentes/` (solo cambian de ubicación y de
  imports) y `config.RAIZ`.
- **Tests:** imports y un `monkeypatch` por texto (`"simulacion.FALLAS_IA"`).
- **Documentación:** `README.md` (árbol de módulos, ejemplo de `migrar`), `CLAUDE.md`,
  `openspec/config.yaml`.
- **Producción (PC Fedora):** hace falta un `git pull` entre corridas. Las unidades
  systemd, el `.env`, `data/` y `logs/` no se tocan.
- **Logs:** los nombres de logger de los módulos que usan `__name__` llevarán el
  prefijo `buscador_vacantes.` (p. ej. `buscador_vacantes.clasificador`). Ningún
  componente lee esos nombres.
- **Change en curso `crear-buscador-vacantes`:** sus artefactos citan las rutas antiguas
  como registro histórico y no se reescriben. Sus tareas pendientes (11.x) no dependen
  de la estructura.
