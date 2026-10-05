from datetime import datetime, timedelta
from html.parser import HTMLParser

from buscador_vacantes.fechas import ZONA
from buscador_vacantes.formato import LIMITE_TELEGRAM, componer, encabezado, ficha, longitud
from buscador_vacantes.modelo import Categoria, Vacante

AHORA = datetime(2026, 10, 3, 23, 30, tzinfo=ZONA)


def vac(
    i=1,
    titulo="Practicante de Proyectos de TI",
    categoria=Categoria.PRACTICAS,
    dias=2,
    salario=None,
    empresa="Redeban",
    ubicacion="Bogotá",
    modalidad="Híbrido",
    fuente="linkedin",
):
    return Vacante(
        fuente=fuente, id_fuente=str(i), titulo=titulo, empresa=empresa,
        url=f"https://www.linkedin.com/jobs/view/{i}?a=1&b=2", keyword="kw",
        ubicacion=ubicacion, modalidad=modalidad, salario=salario,
        publicada=AHORA - timedelta(days=dias) if dias is not None else None,
        categoria=categoria,
    )  # fmt: skip


class Verificador(HTMLParser):
    """Comprueba que el HTML esté balanceado y solo use etiquetas de Telegram."""

    PERMITIDAS = {"b", "a"}

    def __init__(self):
        super().__init__()
        self.pila = []

    def handle_starttag(self, tag, attrs):
        assert tag in self.PERMITIDAS, tag
        self.pila.append(tag)

    def handle_endtag(self, tag):
        assert self.pila.pop() == tag


def html_valido(texto):
    verificador = Verificador()
    verificador.feed(texto)
    verificador.close()
    assert verificador.pila == []


def test_ficha_sin_salario_tiene_3_lineas():
    texto = ficha(vac(), AHORA)
    assert texto.split("\n") == [
        '<b><a href="https://www.linkedin.com/jobs/view/1?a=1&amp;b=2">'
        "Practicante de Proyectos de TI</a></b>",
        "🏢 Redeban · 📍 Bogotá (Híbrido)",
        "🔎 LinkedIn · 🕒 hace 2 días",
    ]
    assert "💰" not in texto


def test_ficha_con_salario():
    texto = ficha(vac(salario="1 SMMLV + auxilio", fuente="computrabajo", dias=0), AHORA)
    lineas = texto.split("\n")
    assert len(lineas) == 4
    assert lineas[2] == "💰 1 SMMLV + auxilio"
    assert lineas[3] == "🔎 Computrabajo · 🕒 hoy"


def test_ficha_sin_fecha_ni_empresa():
    texto = ficha(vac(dias=None, empresa="", modalidad=None), AHORA)
    assert texto.split("\n")[1:] == ["📍 Bogotá", "🔎 LinkedIn"]


def test_modalidad_no_se_repite():
    texto = ficha(vac(ubicacion="Remoto (cualquier país)", modalidad="Remoto"), AHORA)
    assert "📍 Remoto (cualquier país)" in texto
    assert "(Remoto)" not in texto


def test_encabezado_singular_y_plural():
    assert encabezado(1) == "🔔 <b>1 vacante nueva</b>"
    assert encabezado(3) == "🔔 <b>3 vacantes nuevas</b>"


def test_escape_de_caracteres():
    vacante = vac(titulo="Practicante QA & Testing <remoto>", empresa="A&B <SAS>")
    [mensaje] = componer([vacante], AHORA)
    assert "Practicante QA &amp; Testing &lt;remoto&gt;" in mensaje.texto
    assert "A&amp;B &lt;SAS&gt;" in mensaje.texto
    html_valido(mensaje.texto)


def test_orden_de_categorias_y_recientes_primero():
    vacantes = [
        vac(1, "Analista Jr CloudOps", Categoria.INFRAESTRUCTURA, dias=5),
        vac(2, "Aprendiz SENA Desarrollo", Categoria.PRACTICAS, dias=3),
        vac(3, "Practicante de Datos", Categoria.PRACTICAS, dias=0),
        vac(4, "Desarrollador Junior", Categoria.DESARROLLO, dias=1),
    ]
    [mensaje] = componer(vacantes, AHORA)
    texto = mensaje.texto
    assert texto.startswith("🔔 <b>4 vacantes nuevas</b>\n\n🎓 <b>PRÁCTICAS Y APRENDIZAJE</b>")
    posiciones = [texto.index(t) for t in (
        "Practicante de Datos", "Aprendiz SENA Desarrollo", "DESARROLLO JUNIOR",
        "Desarrollador Junior", "INFRAESTRUCTURA / DEVOPS / CLOUD JUNIOR", "Analista Jr CloudOps",
    )]  # fmt: skip
    assert posiciones == sorted(posiciones)
    assert "QA / TESTING" not in texto  # categorías vacías no se muestran
    assert mensaje.claves == ["linkedin:3", "linkedin:2", "linkedin:4", "linkedin:1"]


def test_sin_vacantes_no_hay_mensajes():
    assert componer([], AHORA) == []


def test_40_vacantes_se_dividen_sin_cortar_fichas():
    vacantes = [
        vac(i, f"Practicante de Desarrollo de Software número {i} con título largo",
            Categoria.PRACTICAS if i < 25 else Categoria.SOPORTE, dias=i % 10,
            salario="1 SMMLV + auxilio de transporte", empresa=f"Empresa Grande {i} S.A.S.",
            ubicacion="Bogotá, D.C., Colombia")
        for i in range(40)
    ]  # fmt: skip
    mensajes = componer(vacantes, AHORA)
    assert len(mensajes) >= 2
    claves = [c for m in mensajes for c in m.claves]
    assert sorted(claves) == sorted(v.clave for v in vacantes)
    for numero, mensaje in enumerate(mensajes):
        assert longitud(mensaje.texto) <= LIMITE_TELEGRAM
        html_valido(mensaje.texto)
        # Cada ficha completa: tantas aperturas de enlace como vacantes en el mensaje
        assert mensaje.texto.count("<a href=") == len(mensaje.claves)
        if numero:
            # Los mensajes que continúan empiezan con el título de su categoría
            assert mensaje.texto.startswith(("🎓 <b>PRÁCTICAS", "🛠 <b>SOPORTE"))
    assert mensajes[0].texto.startswith("🔔 <b>40 vacantes nuevas</b>")
    assert not mensajes[1].texto.startswith("🔔")


def test_longitud_cuenta_emojis_como_dos():
    assert longitud("🔔") == 2
    assert longitud("abc") == 3


# --- Enlace ⚡ Postularme del asistente ---

from buscador_vacantes.asistente.enlaces import bot_para_enlaces, enlace, id_corto  # noqa: E402
from buscador_vacantes.config import cargar_configuracion  # noqa: E402


def test_id_corto_estable_y_de_12_caracteres():
    assert id_corto("linkedin:1") == id_corto("linkedin:1")
    assert id_corto("linkedin:1") != id_corto("linkedin:2")
    assert len(id_corto("computrabajo:ABC")) == 12
    assert id_corto("x").isalnum() and id_corto("x").islower()


def test_enlace_cabe_en_el_parametro_start():
    url = enlace("PostuladorBot", "computrabajo:" + "F" * 32)
    parametro = url.split("start=")[1]
    assert len(parametro) <= 64
    assert parametro.startswith("v_")


def test_ficha_sin_bot_queda_identica():
    assert ficha(vac(), AHORA) == ficha(vac(), AHORA, None)
    assert "Postularme" not in ficha(vac(), AHORA)


def test_ficha_con_bot_termina_en_el_enlace():
    texto = ficha(vac(), AHORA, "PostuladorBot")
    ultima = texto.split("\n")[-1]
    destino = enlace("PostuladorBot", vac().clave)
    assert ultima == f'⚡ <a href="{destino}">Postularme</a>'
    html_valido(texto)


def test_componer_con_enlace_respeta_el_limite():
    vacantes = [
        vac(i, f"Practicante de Desarrollo de Software número {i} con título largo",
            dias=i % 10, salario="1 SMMLV + auxilio de transporte",
            empresa=f"Empresa Grande {i} S.A.S.", ubicacion="Bogotá, D.C., Colombia")
        for i in range(40)
    ]  # fmt: skip
    mensajes = componer(vacantes, AHORA, bot_asistente="PostuladorBot")
    for mensaje in mensajes:
        assert longitud(mensaje.texto) <= LIMITE_TELEGRAM
        html_valido(mensaje.texto)
        assert mensaje.texto.count("Postularme</a>") == len(mensaje.claves)
    assert sum(len(m.claves) for m in mensajes) == 40


def test_bot_para_enlaces_segun_configuracion():
    config = cargar_configuracion()
    assert bot_para_enlaces(config) is None  # desactivado por defecto
    config.asistente.activo = True
    config.asistente.bot_usuario = "PostuladorBot"
    assert bot_para_enlaces(config) is None  # falta enlace_canal
    config.asistente.enlace_canal = True
    assert bot_para_enlaces(config) == "PostuladorBot"
