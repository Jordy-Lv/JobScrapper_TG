"""Diccionario de tecnologías con sinónimos (assets/tecnologias.yaml)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from buscador_vacantes.config import RAIZ
from buscador_vacantes.normalizar import normalizar_texto

RUTA = RAIZ / "assets" / "tecnologias.yaml"

# Términos que en texto libre dan falsos positivos (S.A.S., "go", "r", "ia" en palabras…).
# Cuentan si el usuario los declara en su perfil, pero no se buscan en descripciones.
AMBIGUOS = {
    "c", "r", "go", "ia", "ai", "ml", "ts", "py", "vb", "sas", "lan", "wan", "shell",
    "node", "nest", "spring", "rails", "elastic", "kali", "mongo", "apache", "spark",
    "lambda", "agil", "hardware", "testing", "qa", "java se", "redes", "android", "ios",
}  # fmt: skip


class Diccionario:
    def __init__(self, datos: dict[str, dict[str, list[str]]]) -> None:
        self.canonicas: dict[str, str] = {}  # término normalizado → nombre canónico
        self.categorias: dict[str, str] = {}  # nombre canónico → categoría
        for categoria, tecnologias in datos.items():
            for canonica, sinonimos in tecnologias.items():
                self.categorias[canonica] = categoria
                for termino in [canonica, *(sinonimos or [])]:
                    self.canonicas[normalizar_texto(str(termino))] = canonica
        buscables = sorted(
            (t for t in self.canonicas if t not in AMBIGUOS and len(t) > 1),
            key=len,
            reverse=True,
        )
        self._patron = re.compile(
            r"(?<![\w+#])(" + "|".join(re.escape(t) for t in buscables) + r")(?![\w+#])"
        )

    def canonica(self, termino: str) -> str | None:
        return self.canonicas.get(normalizar_texto(termino))

    def son_sinonimos(self, a: str, b: str) -> bool:
        ca, cb = self.canonica(a), self.canonica(b)
        return ca is not None and ca == cb

    def buscar(self, texto: str) -> list[str]:
        """Tecnologías canónicas mencionadas en un texto, en orden de aparición, sin repetir."""
        vistas: dict[str, None] = {}
        for m in self._patron.finditer(normalizar_texto(texto)):
            vistas.setdefault(self.canonicas[m.group(1)], None)
        return list(vistas)


@lru_cache(maxsize=1)
def diccionario(ruta: Path = RUTA) -> Diccionario:
    return Diccionario(yaml.safe_load(ruta.read_text(encoding="utf-8")))
