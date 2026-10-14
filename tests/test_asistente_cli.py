import json
import zipfile

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.cli import empaquetar_extension


def test_paquete_de_la_extension_para_la_tienda(tmp_path):
    salida = empaquetar_extension(cfg.RAIZ / "extension", tmp_path)
    version = json.loads((cfg.RAIZ / "extension" / "manifest.json").read_text("utf-8"))["version"]
    assert salida.name == f"asistente-postulacion-{version}.zip"
    with zipfile.ZipFile(salida) as z:
        nombres = z.namelist()
        assert "manifest.json" in nombres  # en la raíz, como pide la tienda
        assert {"servicio.js", "motor.js", "popup.html", "iconos/128.png"} <= set(nombres)
        assert all(not n.startswith(".") and "\\" not in n for n in nombres)
    # Dos empaquetados seguidos dan el mismo archivo
    primero = salida.read_bytes()
    assert empaquetar_extension(cfg.RAIZ / "extension", tmp_path).read_bytes() == primero
