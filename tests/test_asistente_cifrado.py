import pytest

pytest.importorskip("cryptography", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import cifrado  # noqa: E402
from buscador_vacantes.asistente.cifrado import Cifrador, ClaveInvalida  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.corrida import main  # noqa: E402

AHORA = "2026-10-04T15:00:00+00:00"


@pytest.fixture
def base(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "asistente.db")
    yield base
    base.cerrar()


def test_ida_y_vuelta():
    c = Cifrador(cifrado.generar_clave())
    token = c.cifrar("AIzaSy-clave-secreta")
    assert "AIzaSy" not in token
    assert c.descifrar(token) == "AIzaSy-clave-secreta"


@pytest.mark.parametrize("clave", [None, "", "no-es-una-clave"])
def test_clave_maestra_ausente_o_invalida(clave):
    with pytest.raises(ClaveInvalida):
        Cifrador(clave)


def test_clave_equivocada_se_detecta_al_comprobar(base):
    original = Cifrador(cifrado.generar_clave())
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO usuarios(telegram_id, directorio, creado, gemini_clave) "
            "VALUES (1, 'u', ?, ?)",
            (AHORA, original.cifrar("clave")),
        )
    original.comprobar(base)
    with pytest.raises(ClaveInvalida, match="no es la clave"):
        Cifrador(cifrado.generar_clave()).comprobar(base)


def test_rotacion_sin_perdida(base):
    actual, nueva = cifrado.generar_clave(), cifrado.generar_clave()
    c = Cifrador(actual)
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO usuarios(telegram_id, directorio, creado, gemini_clave) "
            "VALUES (1, 'u', ?, ?)",
            (AHORA, c.cifrar("gemini-1")),
        )
        cx.execute(
            "INSERT INTO cuentas_portal(usuario_id, plataforma, correo_cifrado, correo_hash) "
            "VALUES (1, 'computrabajo', ?, ?)",
            (c.cifrar("ana@gmail.com"), cifrado.huella("ana@gmail.com")),
        )
    assert cifrado.rotar(base, actual, nueva) == 2
    n = Cifrador(nueva)
    fila = base.cx.execute("SELECT gemini_clave FROM usuarios").fetchone()
    assert n.descifrar(fila[0]) == "gemini-1"
    fila = base.cx.execute("SELECT correo_cifrado FROM cuentas_portal").fetchone()
    assert n.descifrar(fila[0]) == "ana@gmail.com"
    with pytest.raises(ClaveInvalida):
        c.descifrar(fila[0])


def test_rotacion_con_clave_actual_equivocada_no_cambia_nada(base):
    c = Cifrador(cifrado.generar_clave())
    token = c.cifrar("gemini-1")
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO usuarios(telegram_id, directorio, creado, gemini_clave) "
            "VALUES (1, 'u', ?, ?)",
            (AHORA, token),
        )
    with pytest.raises(ClaveInvalida):
        cifrado.rotar(base, cifrado.generar_clave(), cifrado.generar_clave())
    assert base.cx.execute("SELECT gemini_clave FROM usuarios").fetchone()[0] == token


def test_huella_normaliza():
    assert cifrado.huella(" Ana@Gmail.com ") == cifrado.huella("ana@gmail.com")


def test_cli_generar_clave(capsys):
    assert main(["asistente", "generar-clave"]) == 0
    clave = capsys.readouterr().out.strip()
    Cifrador(clave)  # es una clave válida
