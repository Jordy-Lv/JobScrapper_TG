"""Tarjeta de conexión: un solo mensaje que va desde «Navegador vinculado» hasta la postulación.

Reúne lo que antes eran avisos sueltos (navegador vinculado, sesión iniciada, cuenta asociada,
alta lista). Si el alta termina con una vacante pendiente, sus líneas pasan a ser el bloque
«Conexión» de la card de esa postulación (``tarjeta_postulacion.py``). Son funciones puras; la
conversación guarda el estado y edita el mensaje.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from buscador_vacantes.asistente import textos as t

PENDIENTE = "pendiente"  # sin sesión, o la cuenta propuesta no era la suya
REVISANDO = "revisando"  # «es mi cuenta nueva»: en el próximo latido se pide confirmar
POR_CONFIRMAR = "por_confirmar"
CONFIRMADA = "confirmada"
COMPLETANDO = "completando"  # el portal tiene el perfil incompleto y se está llenando
DISTINTA = "distinta"  # la sesión abierta es de otra cuenta


@dataclass
class Tarjeta:
    mensaje_id: int | None = None
    navegador: bool = False
    listo: bool = False  # el alta terminó
    cuentas: dict[str, dict] = field(default_factory=dict)  # plataforma → {estado, correo, otro}
    pid: int | None = None  # postulación que se muestra dentro de la tarjeta

    def a_texto(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)

    @classmethod
    def de_texto(cls, valor: str | None) -> Tarjeta | None:
        return cls(**json.loads(valor)) if valor else None

    def poner_cuenta(self, plataforma: str, estado: str, correo: str | None = None,
                     otro: str | None = None) -> None:  # fmt: skip
        anterior = self.cuentas.get(plataforma, {})
        self.cuentas[plataforma] = {
            "estado": estado,
            "correo": correo if correo is not None else anterior.get("correo"),
            "otro": otro,
        }


def _linea_cuenta(nombre: str, cuenta: dict) -> str:
    correo = t.e(cuenta.get("correo"))
    match cuenta["estado"]:
        case "por_confirmar":
            return f"❓ <b>{nombre}</b>: sesión iniciada con <b>{correo}</b>. ¿Es tu cuenta?"
        case "confirmada":
            return f"✓ {nombre} · {correo}" if correo else f"✓ {nombre}"
        case "revisando":
            return f"· {nombre}: revisando la cuenta abierta en tu navegador…"
        case "completando":
            return f"🛠 {nombre}: completando tu perfil con tus datos y tu CV"
        case "distinta":
            return (
                f"⚠️ <b>{nombre}</b>: la cuenta abierta ({t.e(cuenta.get('otro'))}) no es la "
                f"tuya ({correo}). No postularé con ella."
            )
        case _:
            return f"· {nombre}: inicia sesión con tu cuenta en ese navegador"


def _cuentas(tarjeta: Tarjeta, solo: str | None, excepto: str | None) -> dict[str, dict]:
    """Las cuentas que se muestran: la de `solo` (pendiente si aún no hay), las distintas de
    `excepto` o todas."""
    if solo is not None:
        return {solo: tarjeta.cuentas.get(solo, {"estado": PENDIENTE})}
    return {p: c for p, c in tarjeta.cuentas.items() if p != excepto}


def lineas(tarjeta: Tarjeta, solo: str | None = None, excepto: str | None = None) -> list[str]:
    """Las líneas del bloque «Conexión»: navegador y una por portal.

    `solo=p` deja solo la línea del portal `p` (la card de una vacante de `p`); `excepto=p`,
    las de los demás portales (el mensaje aparte mientras hay una card de `p` abierta)."""
    salida = ["🔗 <b>Conexión con tus portales</b>"]
    if tarjeta.navegador:
        salida.append("✓ Navegador vinculado")
    cuentas = _cuentas(tarjeta, solo, excepto)
    if cuentas:
        for plataforma, cuenta in cuentas.items():
            salida.append(_linea_cuenta(t.NOMBRES_PLATAFORMA.get(plataforma, plataforma), cuenta))
    elif tarjeta.navegador and excepto is None:
        salida.append("· Inicia sesión en Computrabajo, Magneto y elempleo en ese navegador.")
    return salida


def texto(tarjeta: Tarjeta, solo: str | None = None, excepto: str | None = None) -> str:
    """La tarjeta de conexión sola (sin postulación)."""
    return "\n".join(lineas(tarjeta, solo, excepto))


def botones(
    tarjeta: Tarjeta, cb: Callable[..., str], solo: str | None = None, excepto: str | None = None
) -> list[list[tuple[str, str]]] | None:
    """Confirmar / Cancelar de cada cuenta por confirmar y los de la cuenta distinta, con el
    mismo filtro que `lineas`."""
    filas = []
    for plataforma, cuenta in _cuentas(tarjeta, solo, excepto).items():
        nombre = t.NOMBRES_PLATAFORMA.get(plataforma, plataforma)
        if cuenta["estado"] == POR_CONFIRMAR:
            filas.append([
                (f"Confirmar {nombre}", cb("cuenta", plataforma, "si")),
                ("Cancelar", cb("cuenta", plataforma, "no")),
            ])  # fmt: skip
        elif cuenta["estado"] == DISTINTA:
            filas.append([
                ("Es mi cuenta nueva", cb("cuenta", plataforma, "nueva")),
                ("No es mía", cb("cuenta", plataforma, "no")),
            ])  # fmt: skip
    return filas or None
