"""Punto de entrada del buscador de vacantes: `uv run buscador.py ...` (ver README.md)."""

import sys

from buscador_vacantes.radar.corrida import main

if __name__ == "__main__":
    sys.exit(main())
