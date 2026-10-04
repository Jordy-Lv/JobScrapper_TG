import subprocess
import sys

from buscador_vacantes.config import RAIZ


def test_punto_entrada_de_la_raiz_muestra_la_ayuda():
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "buscador.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "usage: buscador.py" in resultado.stdout
    assert "--dry-run" in resultado.stdout


def test_raiz_es_la_del_repositorio():
    assert (RAIZ / "config.yaml").is_file()
    assert (RAIZ / "buscador.py").is_file()
