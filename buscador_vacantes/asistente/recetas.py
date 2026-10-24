"""Lo que el asistente aprende de cada postulación: recetas por dominio, dominios barrera y
parches candidatos de los flujos declarados.

Todo se guarda sin valores del usuario ni datos de contacto: una receta lleva solo qué campo del
catálogo (o «redactar») va en cada campo del sitio, el botón usado y la señal de éxito; un parche,
un selector que calculó la extensión sobre un elemento real. Las recetas se comparten entre
usuarios. Los parches son datos que la extensión interpreta, nunca código.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.comun.estado import a_texto
from buscador_vacantes.comun.normalizar import normalizar_texto

UMBRAL_FIRMA = 0.8  # una receta aplica si comparte al menos el 80 % de las claves de la pantalla
FALLOS_PARA_APAGAR = 2  # fallos seguidos que desactivan una receta
SENALES = ("texto", "url", "desaparicion")  # señales de éxito explícitas del motor
MOTIVOS_BARRERA = ("ats_con_cuenta", "oauth", "mensajeria")  # el dominio exige cuenta o mensajería
MAX_SELECTOR = 500  # caracteres del selector guardado
MAX_CLAVE = 120

# Dominio → familia de ATS: una receta de un host sirve a los demás de su familia
FAMILIAS = {
    "greenhouse.io": "greenhouse",
    "ashbyhq.com": "ashby",
    "myworkdayjobs.com": "workday",
    "lever.co": "lever",
    "smartrecruiters.com": "smartrecruiters",
    "workable.com": "workable",
    "pandape.com": "pandape",
    "typeform.com": "typeform",
}
_CAMPO_VALIDO = re.compile(r"^(?:redactar|[a-z_]+(?::[a-z0-9 _]{1,40})?)$")
_SEGMENTO_VARIABLE = re.compile(r"^(?:\d+|[0-9a-f]{8,}(?:-[0-9a-f]{4,})*|[A-Za-z0-9_-]{20,})$")


# --- claves, hosts y rutas --------------------------------------------------------------------


def clave_campo(nombre: str | None, texto: str) -> str:
    """La clave de un campo en la firma de su pantalla: su `name`/`id` o su etiqueta normalizada."""
    clave = normalizar_texto(nombre) or re.sub(r"[^a-z0-9]+", " ", normalizar_texto(texto))
    return clave.strip()[:MAX_CLAVE]


def host_de(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host.removeprefix("www.")


def ruta_patron(url: str | None) -> str:
    """La ruta de la página con lo variable (números e identificadores) reemplazado por `*`."""
    partes = [s for s in urlparse(url or "").path.split("/") if s]
    return "/" + "/".join("*" if _SEGMENTO_VARIABLE.match(s) else s.lower() for s in partes)


def familia_de_host(host: str, plataforma: str | None = None) -> str:
    """La familia de ATS del host; mientras no se conozca, la plataforma (o el host mismo)."""
    for dominio, familia in FAMILIAS.items():
        if host == dominio or host.endswith("." + dominio):
            return familia
    return plataforma or host


def similitud(a: set[str], b: set[str]) -> float:
    """Fracción de claves que comparten dos firmas; dos pantallas sin campos son la misma."""
    if not a and not b:
        return 1.0
    return len(a & b) / max(len(a), len(b))


# --- receta ------------------------------------------------------------------------------------


class BotonReceta(BaseModel):
    texto: str = Field("", max_length=200)
    clase: str | None = Field(None, max_length=20)
    selector: Any | None = None  # lo calcula la extensión; nunca la IA

    @field_validator("selector", mode="before")
    @classmethod
    def _selector_chico(cls, valor: Any) -> Any:
        if valor is None:
            return None
        try:
            return valor if len(json.dumps(valor, ensure_ascii=False)) <= MAX_SELECTOR else None
        except (TypeError, ValueError):
            return None


class PantallaReceta(BaseModel):
    firma: list[str] = Field(default_factory=list, max_length=100)
    mapeo: dict[str, str] = Field(default_factory=dict)  # clave del campo → campo | «redactar»
    boton: BotonReceta | None = None

    @field_validator("mapeo", mode="before")
    @classmethod
    def _solo_campos_del_catalogo(cls, valor: Any) -> Any:
        """Lo que no parece un nombre de campo del catálogo se descarta: nunca un valor."""
        if not isinstance(valor, dict):
            return {}
        return {
            str(k)[:MAX_CLAVE]: v
            for k, v in valor.items()
            if isinstance(v, str) and _CAMPO_VALIDO.match(v)
        }


class Receta(BaseModel):
    pantallas: list[PantallaReceta] = Field(default_factory=list, max_length=60)
    senal: Literal["texto", "url", "desaparicion"] | None = None

    @field_validator("senal", mode="before")
    @classmethod
    def _senal_conocida(cls, valor: Any) -> Any:
        return valor if valor in SENALES else None


class Trazas:
    """Las pantallas de cada postulación en curso, para armar su receta al enviarse. Vive en
    memoria: si el servicio se reinicia a mitad de una postulación, esa no deja receta."""

    MAX_POSTULACIONES = 200

    def __init__(self) -> None:
        self._por_postulacion: dict[int, dict[str, Any]] = {}
        self._ultimas: dict[int, str] = {}  # la última página vista, aunque no se anote

    def agregar(self, pid: int, numero: int, url: str, pantalla: PantallaReceta) -> None:
        traza = self._por_postulacion.setdefault(pid, {"url": url, "pantallas": {}, "senal": None})
        if len(self._por_postulacion) > self.MAX_POSTULACIONES:
            self._por_postulacion.pop(next(iter(self._por_postulacion)))
        traza["pantallas"][numero] = pantalla  # la vuelta de corrección reemplaza a la pantalla

    def visitar(self, pid: int, url: str) -> None:
        if url:
            self._ultimas[pid] = url
            if len(self._ultimas) > self.MAX_POSTULACIONES:
                self._ultimas.pop(next(iter(self._ultimas)))

    def ultima_url(self, pid: int) -> str | None:
        return self._ultimas.get(pid)

    def senal(self, pid: int, senal: str | None) -> None:
        if pid in self._por_postulacion and senal in SENALES:
            self._por_postulacion[pid]["senal"] = senal

    def sacar(self, pid: int) -> tuple[str, Receta] | None:
        """(url de la primera pantalla, receta) y olvida la traza."""
        traza = self._por_postulacion.pop(pid, None)
        if not traza or not traza["pantallas"]:
            return None
        pantallas = [traza["pantallas"][n] for n in sorted(traza["pantallas"])]
        return traza["url"], Receta(pantallas=pantallas, senal=traza["senal"])

    def olvidar(self, pid: int) -> None:
        self._por_postulacion.pop(pid, None)
        self._ultimas.pop(pid, None)


def guardar_receta(
    base: BaseAsistente,
    *,
    host: str,
    ruta: str,
    familia: str,
    receta: Receta,
    origen: Literal["real", "ensayo"],
    ahora: datetime,
    enviada: bool = False,
) -> int | None:
    """Crea o refuerza la receta del sitio. Solo con `enviada` y una señal de éxito explícita;
    el ensayo (que no envía) guarda las suyas con `origen: ensayo`. Devuelve su id o None."""
    if not receta.pantallas or not host:
        return None
    if origen == "real" and not (enviada and receta.senal):
        return None
    if origen == "ensayo":
        receta = receta.model_copy(update={"senal": None})
    firma = sorted(set(receta.pantallas[0].firma))
    contenido = receta.model_dump_json()
    with base.transaccion() as cx:
        filas = cx.execute(
            "SELECT id, firma, origen FROM recetas WHERE host = ? AND ruta_patron = ?",
            (host, ruta),
        ).fetchall()
        for f in filas:
            if similitud(set(json.loads(f["firma"])), set(firma)) >= UMBRAL_FIRMA:
                nuevo_origen = "real" if origen == "real" else f["origen"]
                cx.execute(
                    "UPDATE recetas SET receta_json = ?, familia = ?, exitos = exitos + 1, "
                    "fallos_seguidos = 0, activa = 1, origen = ?, actualizada = ? WHERE id = ?",
                    (contenido, familia, nuevo_origen, a_texto(ahora), f["id"]),
                )
                return f["id"]
        cur = cx.execute(
            "INSERT INTO recetas(host, ruta_patron, familia, firma, receta_json, exitos, "
            "fallos_seguidos, activa, origen, actualizada) VALUES (?, ?, ?, ?, ?, 1, 0, 1, ?, ?)",
            (host, ruta, familia, json.dumps(firma), contenido, origen, a_texto(ahora)),
        )
        return cur.lastrowid


def receta_para(
    base: BaseAsistente, host: str, familia: str | None, ruta: str | None = None
) -> dict[str, Any] | None:
    """La receta activa del host o, si no hay, la mejor de su familia. Una receta de ensayo sirve
    para el mapeo y los botones, pero se entrega sin señal de éxito."""
    fila = base.cx.execute(
        "SELECT * FROM recetas WHERE activa = 1 AND host = ? "
        "ORDER BY ruta_patron = ? DESC, exitos DESC, actualizada DESC LIMIT 1",
        (host, ruta or ""),
    ).fetchone()
    alcance = "host"
    if fila is None and familia:
        fila = base.cx.execute(
            "SELECT * FROM recetas WHERE activa = 1 AND familia = ? AND host != ? "
            "ORDER BY exitos DESC, actualizada DESC LIMIT 1",
            (familia, host),
        ).fetchone()
        alcance = "familia"
    if fila is None:
        return None
    receta = Receta.model_validate_json(fila["receta_json"])
    if fila["origen"] == "ensayo":
        receta.senal = None
    return {"id": fila["id"], "alcance": alcance, "origen": fila["origen"],
            **receta.model_dump()}  # fmt: skip


def registrar_resultado_receta(base: BaseAsistente, receta_id: int, ok: bool) -> bool:
    """Un éxito la refuerza; un fallo suma uno seguido y a los 2 la desactiva. True si se acaba
    de desactivar (el dueño debe saberlo)."""
    with base.transaccion() as cx:
        if ok:
            cx.execute(
                "UPDATE recetas SET exitos = exitos + 1, fallos_seguidos = 0 WHERE id = ?",
                (receta_id,),
            )
            return False
        cx.execute(
            "UPDATE recetas SET fallos_seguidos = fallos_seguidos + 1 WHERE id = ?", (receta_id,)
        )
        fila = cx.execute(
            "SELECT fallos_seguidos, activa FROM recetas WHERE id = ?", (receta_id,)
        ).fetchone()
        if fila and fila["activa"] and fila["fallos_seguidos"] >= FALLOS_PARA_APAGAR:
            cx.execute("UPDATE recetas SET activa = 0 WHERE id = ?", (receta_id,))
            return True
    return False


# --- dominios barrera -------------------------------------------------------------------------


def marcar_barrera(base: BaseAsistente, host: str, motivo: str, ahora: datetime) -> bool:
    """Recuerda que el host exige cuenta, OAuth o mensajería. True si es nuevo."""
    if not host or motivo not in MOTIVOS_BARRERA:
        return False
    with base.transaccion() as cx:
        cur = cx.execute(
            "INSERT OR IGNORE INTO dominios_barrera(host, motivo, creado) VALUES (?, ?, ?)",
            (host, motivo, a_texto(ahora)),
        )
        return cur.rowcount > 0


def barrera_de(base: BaseAsistente, host: str) -> str | None:
    """El motivo por el que el host es barrera (las vacantes de ahí van al respaldo sin abrir
    la página), o None."""
    if not host:
        return None
    fila = base.cx.execute("SELECT motivo FROM dominios_barrera WHERE host = ?", (host,)).fetchone()
    return fila["motivo"] if fila else None


def quitar_barrera(base: BaseAsistente, host: str) -> bool:
    with base.transaccion() as cx:
        return cx.execute("DELETE FROM dominios_barrera WHERE host = ?", (host,)).rowcount > 0


def barreras(base: BaseAsistente) -> list[dict[str, str]]:
    filas = base.cx.execute("SELECT host, motivo FROM dominios_barrera ORDER BY host").fetchall()
    return [dict(f) for f in filas]


# --- parches candidatos de los flujos declarados ----------------------------------------------


def proponer_parche(
    base: BaseAsistente, plataforma: str, paso: str, selector: Any, ahora: datetime,
    postulacion_id: int | None = None,
) -> int | None:  # fmt: skip
    """Guarda como candidato el selector que reemplazó al del paso declarado que falló. None si
    el selector es inválido o ya estaba guardado (en cualquier estado)."""
    try:
        contenido = json.dumps(selector, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return None
    if not plataforma or not paso or not selector or len(contenido) > MAX_SELECTOR:
        return None
    with base.transaccion() as cx:
        ya = cx.execute(
            "SELECT 1 FROM parches_flujo WHERE plataforma = ? AND paso = ? AND selector_json = ?",
            (plataforma, paso, contenido),
        ).fetchone()
        if ya:
            return None
        cur = cx.execute(
            "INSERT INTO parches_flujo(plataforma, paso, selector_json, estado, exitos, "
            "postulacion_id, creado, actualizado) VALUES (?, ?, ?, 'candidato', 0, ?, ?, ?)",
            (plataforma, paso, contenido, postulacion_id, a_texto(ahora), a_texto(ahora)),
        )
        return cur.lastrowid


def parches_aplicables(base: BaseAsistente, plataforma: str) -> list[dict[str, Any]]:
    """Los parches que se anteponen a los selectores de la plataforma (candidatos y firmes), del
    más reciente al más viejo."""
    filas = base.cx.execute(
        "SELECT id, paso, selector_json, estado FROM parches_flujo "
        "WHERE plataforma = ? AND estado IN ('candidato', 'firme') ORDER BY id DESC",
        (plataforma,),
    ).fetchall()
    return [
        {"id": f["id"], "paso": f["paso"], "estado": f["estado"],
         "selector": json.loads(f["selector_json"])}
        for f in filas
    ]  # fmt: skip


def aplicar_parches(contenido: dict[str, Any], parches: list[dict[str, Any]]) -> dict[str, Any]:
    """Los selectores de la plataforma con cada parche antepuesto a la lista del paso que
    reemplaza. No toca el original ni agrega pasos."""
    parchado = copy.deepcopy(contenido)
    for parche in sorted(parches, key=lambda p: p["id"]):  # el más reciente queda primero
        for paso in parchado.get("postular", []):
            lista = paso.get("selector")
            if paso.get("nombre") == parche["paso"] and isinstance(lista, list):
                if parche["selector"] not in lista:
                    lista.insert(0, parche["selector"])
    return parchado


def resultado_parches(base: BaseAsistente, ids: list[int], ok: bool, ahora: datetime) -> list[dict]:
    """El resultado de una postulación que llevaba estos parches: un candidato pasa a firme con
    un éxito y se descarta con un fallo. Devuelve los que cambiaron de estado."""
    cambios = []
    if not ids:
        return cambios
    with base.transaccion() as cx:
        for pid in ids:
            fila = cx.execute(
                "SELECT id, plataforma, paso, estado FROM parches_flujo WHERE id = ?", (pid,)
            ).fetchone()
            if fila is None or fila["estado"] not in ("candidato", "firme"):
                continue
            if ok:
                cx.execute(
                    "UPDATE parches_flujo SET exitos = exitos + 1, estado = 'firme', "
                    "actualizado = ? WHERE id = ?",
                    (a_texto(ahora), pid),
                )
                if fila["estado"] == "candidato":
                    cambios.append({"id": pid, "plataforma": fila["plataforma"],
                                    "paso": fila["paso"], "estado": "firme"})  # fmt: skip
            elif fila["estado"] == "candidato":
                cx.execute(
                    "UPDATE parches_flujo SET estado = 'descartado', actualizado = ? WHERE id = ?",
                    (a_texto(ahora), pid),
                )
                cambios.append({"id": pid, "plataforma": fila["plataforma"],
                                "paso": fila["paso"], "estado": "descartado"})  # fmt: skip
    return cambios
