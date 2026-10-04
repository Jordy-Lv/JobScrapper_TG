from datetime import datetime, timedelta

import pytest

from buscador_vacantes.config import RAIZ, cargar_configuracion
from buscador_vacantes.estado import Estado
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.modelo import Categoria, Vacante
from buscador_vacantes.normalizar import huella
from buscador_vacantes.notificador_telegram import ResultadoEnvio
from buscador_vacantes.publicacion import publicar

AHORA = datetime(2026, 10, 3, 7, 0, tzinfo=ZONA)
CHAT = "-100123"


class NotificadorFalso:
    def __init__(self, fallar_mensajes=(), fallar_foto=False):
        self.fallar_mensajes = set(fallar_mensajes)
        self.fallar_foto = fallar_foto
        self.envios = []

    def enviar_mensaje(self, chat_id, texto):
        numero = sum(1 for tipo, *_ in self.envios if tipo == "mensaje")
        self.envios.append(("mensaje", chat_id, texto))
        if numero in self.fallar_mensajes:
            return ResultadoEnvio(False, codigo=400, error="Bad Request: can't parse entities")
        return ResultadoEnvio(True, message_id=numero)

    def enviar_foto(self, chat_id, ruta):
        self.envios.append(("foto", chat_id, ruta))
        return ResultadoEnvio(not self.fallar_foto, error="foto" if self.fallar_foto else None)

    def cerrar(self):
        pass


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


@pytest.fixture
def banner():
    return cargar_configuracion().banner


def candidatas(n, largo=False):
    salida = []
    for i in range(n):
        titulo = f"Practicante de Sistemas {i}" + (
            " con un título bastante largo" * 3 if largo else ""
        )
        vacante = Vacante(
            fuente="linkedin", id_fuente=str(i), titulo=titulo, empresa=f"Empresa {i}",
            url=f"https://co.linkedin.com/jobs/view/{i}", keyword="kw", ubicacion="Bogotá",
            salario="1 SMMLV + auxilio de transporte", categoria=Categoria.PRACTICAS,
            publicada=AHORA - timedelta(days=1),
        )  # fmt: skip
        salida.append((vacante, huella(vacante.titulo, vacante.empresa, vacante.clave)))
    return salida


def publicar_con(notificador, estado, banner, lista, ahora=AHORA, **kwargs):
    return publicar(lista, notificador, estado, banner, CHAT, ahora, raiz=RAIZ,
                    dormir=lambda s: None, **kwargs)  # fmt: skip


def tipos(notificador):
    return [envio[0] for envio in notificador.envios]


def test_sin_vacantes_no_envia_nada_ni_banner(estado, banner):
    notificador = NotificadorFalso()
    resultado = publicar_con(notificador, estado, banner, [])
    assert notificador.envios == [] and resultado.mensajes_enviados == 0


def test_primer_envio_del_dia_lleva_banner(estado, banner):
    notificador = NotificadorFalso()
    resultado = publicar_con(notificador, estado, banner, candidatas(2))
    assert tipos(notificador) == ["foto", "mensaje"]
    assert notificador.envios[0][2] == RAIZ / "assets" / "encabezado_vacantes.jpg"
    assert resultado.banner_enviado
    assert estado.kv_obtener("ultimo_banner") == "2026-10-03"
    assert estado.contar_vistas(enviadas=True) == 2


def test_segundo_envio_del_dia_sin_banner(estado, banner):
    publicar_con(NotificadorFalso(), estado, banner, candidatas(1))
    notificador = NotificadorFalso()
    nuevas = candidatas(3)[1:]
    publicar_con(notificador, estado, banner, nuevas, AHORA + timedelta(hours=5))
    assert tipos(notificador) == ["mensaje"]
    # Al día siguiente vuelve el banner
    notificador = NotificadorFalso()
    publicar_con(notificador, estado, banner, candidatas(1), AHORA + timedelta(days=1))
    assert tipos(notificador) == ["foto", "mensaje"]


@pytest.mark.parametrize(("modo", "fotos"), [("nunca", 0), ("siempre", 2)])
def test_modos_nunca_y_siempre(estado, banner, modo, fotos):
    banner = banner.model_copy(update={"modo": modo})
    notificador = NotificadorFalso()
    publicar_con(notificador, estado, banner, candidatas(1))
    publicar_con(notificador, estado, banner, candidatas(2)[1:])
    assert tipos(notificador).count("foto") == fotos


def test_fallo_del_banner_no_impide_vacantes(estado, banner):
    notificador = NotificadorFalso(fallar_foto=True)
    resultado = publicar_con(notificador, estado, banner, candidatas(2))
    assert resultado.mensajes_enviados == 1
    assert estado.kv_obtener("ultimo_banner") is None
    assert len(resultado.enviadas) == 2
    # Un banner fallido no es un rechazo de vacantes (no abre fallo_envio)
    assert resultado.rechazos == [] and resultado.error_banner == "foto"


def test_rechazo_parcial_de_telegram(estado, banner):
    lista = candidatas(45, largo=True)
    notificador = NotificadorFalso(fallar_mensajes={1})
    resultado = publicar_con(
        notificador, estado, banner.model_copy(update={"modo": "nunca"}), lista
    )
    mensajes = [e for e in notificador.envios if e[0] == "mensaje"]
    assert len(mensajes) >= 3
    assert len(resultado.rechazos) == 1
    rechazadas = resultado.rechazos[0].claves
    assert rechazadas and set(rechazadas) == set(resultado.no_enviadas)
    # Las de los mensajes confirmados quedan enviadas; las del rechazado, no
    assert estado.contar_vistas(enviadas=True) == 45 - len(rechazadas)
    for clave in rechazadas:
        vacante, h = next((v, h) for v, h in lista if v.clave == clave)
        assert not estado.ya_vista(clave, h)
    # Y quedan en la cola para reintentarse en la siguiente corrida
    assert {v.clave for v, _, _ in estado.obtener_por_enviar()} == set(rechazadas)


def test_reintento_exitoso_vacia_la_cola(estado, banner):
    lista = candidatas(1)
    publicar_con(NotificadorFalso(fallar_mensajes={0}), estado, banner, lista)
    assert len(estado.obtener_por_enviar()) == 1
    publicar_con(NotificadorFalso(), estado, banner, lista)
    assert estado.obtener_por_enviar() == []
    assert estado.contar_vistas(enviadas=True) == 1


def test_chat_de_prueba_no_marca_enviadas_al_canal(estado, banner):
    notificador = NotificadorFalso()
    publicar_con(notificador, estado, banner, candidatas(2), prueba=True)
    assert estado.contar_vistas(enviadas=True) == 0
    assert estado.kv_obtener("ultimo_banner") is None
    assert estado.kv_obtener("ultimo_banner_prueba") == "2026-10-03"
    vacante, h = candidatas(1)[0]
    assert estado.ya_vista(vacante.clave, h, prueba=True)
    assert not estado.ya_vista(vacante.clave, h)
