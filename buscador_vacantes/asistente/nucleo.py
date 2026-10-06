"""Núcleo del asistente: une índice, detalle, IA, CV, respuestas, cola y cuentas.

El bot y la API usan esta clase; los avisos al usuario salen por ``notificador`` (el bot).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.afinidad import Afinidad, calcular_afinidad, obtener_requisitos
from buscador_vacantes.asistente.api import ResultadoFormulario
from buscador_vacantes.asistente.campos import CAMPOS, DatosUsuario
from buscador_vacantes.asistente.cifrado import Cifrador, ClaveInvalida
from buscador_vacantes.asistente.cola import Cola, E, Evento, Postulacion, Tipo
from buscador_vacantes.asistente.cuentas_portal import CuentasPortal
from buscador_vacantes.asistente.cv_adaptado import adaptar, cv_base, redactar_carta
from buscador_vacantes.asistente.cv_lectura import PerfilExtraido
from buscador_vacantes.asistente.cv_pdf import Contacto, generar_pdf, nombre_archivo
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.detalle import Detalles, EstadoPagina
from buscador_vacantes.asistente.gemini import ClaveGeminiInvalida, ClienteGemini
from buscador_vacantes.asistente.preferencias import Preferencias
from buscador_vacantes.asistente.respuestas import (
    Contexto,
    Pregunta,
    Respuesta,
    normalizar_pregunta,
    recordar,
    resolver,
)
from buscador_vacantes.asistente.usuarios import EstadoUsuario, Usuario, Usuarios
from buscador_vacantes.asistente.vacantes import Indice, VacanteIndexada
from buscador_vacantes.estado import a_texto, ahora_utc

log = logging.getLogger(__name__)

RUTA_SELECTORES = cfg.RAIZ / "assets" / "selectores"


class Camino(StrEnum):
    AUTOMATICA = "automatica"
    RESPALDO = "respaldo"
    NO_DISPONIBLE = "no_disponible"
    YA_EXISTE = "ya_existe"


@dataclass
class Toque:
    """Resultado de tocar ⚡ Postularme."""

    camino: Camino
    vacante: VacanteIndexada | None = None
    postulacion: Postulacion | None = None
    motivo: str | None = None  # por qué no es automática


@dataclass
class Paquete:
    """Respaldo para postular a mano: todo listo para copiar."""

    vacante: VacanteIndexada
    motivo: str
    afinidad: Afinidad | None
    cv: Path
    carta: str
    respuestas: list[Respuesta] = field(default_factory=list)
    contacto: dict[str, str] = field(default_factory=dict)
    detalle_parcial: bool = False


class Nucleo:
    def __init__(
        self,
        configuracion: cfg.Configuracion,
        base: BaseAsistente,
        indice: Indice,
        detalles: Detalles,
        gemini: ClienteGemini,
        cifrador: Cifrador,
        archivos: Path,
        *,
        reloj: Callable[[], datetime] = ahora_utc,
    ) -> None:
        assert configuracion.asistente is not None
        self.configuracion = configuracion
        self.config = configuracion.asistente
        self.base = base
        self.indice = indice
        self.detalles = detalles
        self.gemini = gemini
        self.cifrador = cifrador
        self.archivos = archivos
        self.enlace_grupo: str | None = None  # lo fija servicio.construir_nucleo
        self.reloj = reloj
        self.cola = Cola(base, self.config)
        self.cuentas = CuentasPortal(base, cifrador)
        self.preferencias = Preferencias(base)
        self.usuarios = Usuarios(base, archivos)
        self.notificador: Callable[[Evento | dict], Awaitable[None]] | None = None

    def ahora(self) -> datetime:
        return self.reloj()

    async def notificar(self, evento: Evento | dict) -> None:
        if self.notificador is not None:
            await self.notificador(evento)
        else:
            log.info("Evento sin notificador: %s", evento)

    # --- datos del usuario ---------------------------------------------------------------

    def datos_usuario(self, usuario_id: int) -> DatosUsuario | None:
        fila = self.base.cx.execute(
            "SELECT perfil_json, cuestionario_json FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if not fila or not fila["perfil_json"]:
            return None
        perfil = PerfilExtraido.model_validate_json(fila["perfil_json"])
        cuestionario = json.loads(fila["cuestionario_json"] or "{}")
        return DatosUsuario(perfil, cuestionario)

    def guardar_perfil(self, usuario_id: int, perfil: PerfilExtraido) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET perfil_json = ? WHERE id = ?",
                (perfil.model_dump_json(), usuario_id),
            )

    def guardar_cuestionario(self, usuario_id: int, cuestionario: dict[str, str]) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET cuestionario_json = ? WHERE id = ?",
                (json.dumps(cuestionario, ensure_ascii=False), usuario_id),
            )

    def clave_gemini(self, usuario_id: int) -> str | None:
        fila = self.base.cx.execute(
            "SELECT gemini_clave, gemini_valida FROM usuarios WHERE id = ?", (usuario_id,)
        ).fetchone()
        if not fila or not fila["gemini_clave"] or fila["gemini_valida"] == 0:
            return None
        try:
            return self.cifrador.descifrar(fila["gemini_clave"])
        except ClaveInvalida:
            return None

    def guardar_clave_gemini(self, usuario_id: int, clave: str | None) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET gemini_clave = ?, gemini_ult4 = ?, gemini_valida = ? "
                "WHERE id = ?",
                (
                    self.cifrador.cifrar(clave) if clave else None,
                    clave[-4:] if clave else None,
                    1 if clave else None,
                    usuario_id,
                ),
            )

    def marcar_clave_invalida(self, usuario_id: int) -> None:
        with self.base.transaccion() as cx:
            cx.execute("UPDATE usuarios SET gemini_valida = 0 WHERE id = ?", (usuario_id,))

    def contacto(self, datos: DatosUsuario) -> Contacto:
        c = datos.cuestionario
        return Contacto(
            nombre=c.get("nombre") or datos.perfil.nombre or "Candidato",
            ciudad=c.get("ciudad") or datos.perfil.ciudad,
            correo=c.get("correo"),
            telefono=c.get("telefono"),
            enlaces=tuple(e.url for e in datos.perfil.enlaces[:2]),
        )

    def tiene_navegador(self, usuario_id: int) -> bool:
        return bool(
            self.base.cx.execute(
                "SELECT 1 FROM navegadores WHERE usuario_id = ? AND revocado = 0", (usuario_id,)
            ).fetchone()
        )

    # --- vacantes y selectores -----------------------------------------------------------

    def vacante(self, id_corto: str) -> dict[str, Any] | None:
        v = self.indice.obtener(id_corto)
        return None if v is None else {"url": v.url, "titulo": v.titulo, "empresa": v.empresa}

    def cargar_selectores(self) -> int:
        """Carga assets/selectores/<plataforma>.json a la base (al arrancar o con el comando)."""
        cargados = 0
        if not RUTA_SELECTORES.is_dir():
            return 0
        with self.base.transaccion() as cx:
            for archivo in sorted(RUTA_SELECTORES.glob("*.json")):
                contenido = json.loads(archivo.read_text(encoding="utf-8"))
                cx.execute(
                    "INSERT INTO selectores(plataforma, version, contenido_json, cargado_en) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(plataforma) DO UPDATE SET "
                    "version = excluded.version, contenido_json = excluded.contenido_json, "
                    "cargado_en = excluded.cargado_en",
                    (archivo.stem, str(contenido.get("version", "1")),
                     json.dumps(contenido, ensure_ascii=False), a_texto(self.ahora())),
                )  # fmt: skip
                cargados += 1
        return cargados

    def selectores(self, plataforma: str) -> tuple[str, dict] | None:
        fila = self.base.cx.execute(
            "SELECT version, contenido_json FROM selectores WHERE plataforma = ?", (plataforma,)
        ).fetchone()
        return (fila["version"], json.loads(fila["contenido_json"])) if fila else None

    # --- toque de ⚡ ------------------------------------------------------------------

    def camino_automatico(self, usuario_id: int, vacante: VacanteIndexada) -> str | None:
        """None si se puede postular sola; si no, el motivo del respaldo."""
        if vacante.plataforma is None:
            return "plataforma_no_soportada"
        ajustes = self.config.plataformas.get(vacante.plataforma)
        if ajustes is None or not ajustes.automatica:
            return "plataforma_no_automatica"
        if not self.tiene_navegador(usuario_id):
            return "sin_navegador"
        return None

    def tocar(self, usuario: Usuario, id_corto: str, *, origen: str = "boton") -> Toque:
        ahora = self.ahora()
        vacante = self.indice.resolver(id_corto, ahora)
        if vacante is None:
            return Toque(Camino.NO_DISPONIBLE)
        motivo = self.camino_automatico(usuario.id, vacante)
        if existente := self.cola.de_usuario(usuario.id, id_corto):
            # Un nuevo toque reintenta lo que el portal no llegó a recibir (por ejemplo, tras
            # verificar el correo que el portal pedía); lo demás muestra su estado
            if motivo is None and self.cola.reintentar(existente.id, ahora):
                return Toque(Camino.AUTOMATICA, vacante, self.cola.obtener(existente.id))
            return Toque(Camino.YA_EXISTE, vacante, existente)
        if motivo is None:
            postulacion, _ = self.cola.encolar(
                usuario.id, id_corto, vacante.plataforma, ahora, origen=origen
            )
            return Toque(Camino.AUTOMATICA, vacante, postulacion)
        postulacion, _ = self.cola.encolar(usuario.id, id_corto, vacante.plataforma, ahora,
                                           origen=origen)  # fmt: skip
        self.cola.a_respaldo(postulacion.id, ahora, motivo, (E.EN_COLA,))
        return Toque(Camino.RESPALDO, vacante, self.cola.obtener(postulacion.id), motivo)

    # --- preparación (detalle, afinidad, CV adaptado) -------------------------------------

    def _carpeta_postulacion(self, usuario: Usuario, pid: int) -> Path:
        carpeta = self.usuarios.directorio(usuario) / "postulaciones" / str(pid)
        carpeta.mkdir(parents=True, exist_ok=True)
        os.chmod(carpeta, 0o700)
        return carpeta

    async def _ia(self, usuario_id: int) -> tuple[ClienteGemini | None, str | None]:
        clave = self.clave_gemini(usuario_id)
        return (self.gemini, clave) if clave else (None, None)

    async def preparar(
        self, usuario: Usuario, vacante: VacanteIndexada, pid: int
    ) -> tuple[Afinidad | None, Path, bool]:
        """Detalle, afinidad y CV adaptado de esta vacante. Devuelve (afinidad, cv, parcial)."""
        datos = self.datos_usuario(usuario.id)
        if datos is None:
            raise RuntimeError("el usuario no tiene perfil")
        detalle = await self.detalles.obtener(vacante, self.ahora())
        parcial = detalle.estado != EstadoPagina.OK
        cliente, clave = await self._ia(usuario.id)
        try:
            requisitos = await obtener_requisitos(
                self.base, vacante.id_corto, vacante.resumen, cliente=cliente, clave=clave,
                usuario_id=usuario.id,
            )  # fmt: skip
            afinidad = calcular_afinidad(requisitos, datos.perfil)
            cv = await adaptar(datos, requisitos, vacante.resumen, cliente=cliente, clave=clave,
                               usuario_id=usuario.id)  # fmt: skip
        except ClaveGeminiInvalida:
            self.marcar_clave_invalida(usuario.id)
            await self.notificar({"tipo": "clave_invalida", "usuario_id": usuario.id})
            afinidad, cv = None, cv_base(datos.perfil)
        contacto = self.contacto(datos)
        archivo = self._carpeta_postulacion(usuario, pid) / nombre_archivo(contacto.nombre)
        archivo.write_bytes(generar_pdf(cv, contacto))
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE postulaciones SET cv_archivo = ?, afinidad = ? WHERE id = ?",
                (str(archivo), afinidad.porcentaje if afinidad else None, pid),
            )
        return afinidad, archivo, parcial

    # --- formulario (lo pide la extensión) ----------------------------------------------

    async def resolver_formulario(
        self, postulacion: Postulacion, preguntas: list[Pregunta]
    ) -> ResultadoFormulario:
        usuario = self.usuarios.por_id(postulacion.usuario_id)
        datos = self.datos_usuario(postulacion.usuario_id)
        if usuario is None or datos is None:
            return ResultadoFormulario(faltan=[Respuesta(p, falta=True) for p in preguntas])
        vacante = self.indice.obtener(postulacion.id_corto) if postulacion.id_corto else None
        cliente, clave = await self._ia(usuario.id)
        ctx = Contexto(self.base, usuario.id, datos, self.ahora(), cliente, clave,
                       vacante.resumen if vacante else "")  # fmt: skip
        resultado = ResultadoFormulario()
        for pregunta in preguntas:
            if pregunta.tipo == "archivo":
                continue  # el CV lo adjunta la extensión
            try:
                respuesta = await resolver(pregunta, ctx)
            except ClaveGeminiInvalida:
                self.marcar_clave_invalida(usuario.id)
                ctx.cliente, ctx.clave = None, None
                respuesta = await resolver(pregunta, ctx)
            if respuesta.falta:
                if pregunta.obligatoria:
                    resultado.faltan.append(respuesta)
            else:
                resultado.respuestas.append(respuesta)
        self._guardar_respuestas(postulacion.id, resultado.respuestas)
        if resultado.faltan:
            self._crear_pendientes(usuario.id, postulacion.id, resultado.faltan)
            await self.notificar({"tipo": "preguntas_pendientes", "usuario_id": usuario.id,
                                  "postulacion_id": postulacion.id})  # fmt: skip
            return resultado
        if postulacion.tipo == Tipo.POSTULAR:
            fila = self.base.cx.execute(
                "SELECT cv_archivo FROM postulaciones WHERE id = ?", (postulacion.id,)
            ).fetchone()
            if fila and fila["cv_archivo"] and Path(fila["cv_archivo"]).is_file():
                resultado.cv = Path(fila["cv_archivo"])
            elif vacante is not None:
                _, resultado.cv, _ = await self.preparar(usuario, vacante, postulacion.id)
        else:
            resultado.cv = self.cv_base_de(usuario, datos)
        return resultado

    def cv_base_de(self, usuario: Usuario, datos: DatosUsuario) -> Path:
        contacto = self.contacto(datos)
        archivo = self.usuarios.directorio(usuario) / nombre_archivo(contacto.nombre)
        archivo.write_bytes(generar_pdf(cv_base(datos.perfil), contacto))
        return archivo

    def _guardar_respuestas(self, pid: int, respuestas: list[Respuesta]) -> None:
        with self.base.transaccion() as cx:
            cx.execute("DELETE FROM respuestas WHERE postulacion_id = ?", (pid,))
            for r in respuestas:
                cx.execute(
                    "INSERT INTO respuestas(postulacion_id, campo, pregunta, respuesta, origen) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pid, r.campo, r.pregunta.texto, r.texto, r.origen),
                )

    def _crear_pendientes(self, usuario_id: int, pid: int, faltan: list[Respuesta]) -> None:
        with self.base.transaccion() as cx:
            for r in faltan:
                norma = normalizar_pregunta(r.pregunta.texto)
                ya = cx.execute(
                    "SELECT 1 FROM pendientes_usuario WHERE postulacion_id = ? "
                    "AND pregunta_norm = ? AND respondida_en IS NULL",
                    (pid, norma),
                ).fetchone()
                if ya:
                    continue
                cx.execute(
                    "INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, "
                    "pregunta_norm, opciones_json, campo, creada) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (usuario_id, pid, r.pregunta.texto, norma,
                     json.dumps(r.pregunta.opciones, ensure_ascii=False), r.campo,
                     a_texto(self.ahora())),
                )  # fmt: skip

    def pendientes(self, usuario_id: int) -> list[dict]:
        filas = self.base.cx.execute(
            "SELECT * FROM pendientes_usuario WHERE usuario_id = ? AND respondida_en IS NULL "
            "ORDER BY id",
            (usuario_id,),
        ).fetchall()
        return [dict(f) for f in filas]

    def responder_pendiente(self, usuario_id: int, pendiente_id: int, respuesta: str) -> bool:
        """Guarda la respuesta como aprendida; si ya no quedan, la postulación vuelve a la cola.

        Devuelve True si la postulación se reencoló.
        """
        ahora = self.ahora()
        fila = self.base.cx.execute(
            "SELECT * FROM pendientes_usuario WHERE id = ? AND usuario_id = ?",
            (pendiente_id, usuario_id),
        ).fetchone()
        if not fila or fila["respondida_en"]:
            return False
        recordar(self.base, usuario_id, fila["pregunta"], respuesta, ahora)
        if fila["campo"] in CAMPOS:
            # Un dato del perfil (salario, disponibilidad…) sirve para cualquier redacción
            datos = self.datos_usuario(usuario_id)
            if datos is not None:
                datos.cuestionario[fila["campo"]] = respuesta
                self.guardar_cuestionario(usuario_id, datos.cuestionario)
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE pendientes_usuario SET respondida_en = ?, respuesta = ? "
                "WHERE pregunta_norm = ? AND usuario_id = ? AND respondida_en IS NULL",
                (a_texto(ahora), respuesta, fila["pregunta_norm"], usuario_id),
            )
        restantes = self.base.cx.execute(
            "SELECT COUNT(*) FROM pendientes_usuario WHERE postulacion_id = ? "
            "AND respondida_en IS NULL",
            (fila["postulacion_id"],),
        ).fetchone()[0]
        if restantes == 0 and fila["postulacion_id"]:
            return self.cola.reanudar(fila["postulacion_id"], ahora, (E.ESPERANDO_USUARIO,))
        return False

    # --- paquete de respaldo -------------------------------------------------------------

    async def armar_paquete(self, usuario: Usuario, vacante: VacanteIndexada, pid: int,
                            motivo: str) -> Paquete:  # fmt: skip
        datos = self.datos_usuario(usuario.id)
        if datos is None:
            raise RuntimeError("el usuario no tiene perfil")
        afinidad, cv, parcial = await self.preparar(usuario, vacante, pid)
        cliente, clave = await self._ia(usuario.id)
        carta = await redactar_carta(
            datos, cv_base(datos.perfil), vacante.titulo or "la vacante", vacante.resumen,
            self.config.carta_max_caracteres, cliente=cliente, clave=clave, usuario_id=usuario.id,
        )  # fmt: skip
        tipicas = self.config.preguntas_tipicas.get(
            vacante.fuente, self.config.preguntas_tipicas.get("otras", [])
        )
        ctx = Contexto(self.base, usuario.id, datos, self.ahora(), cliente, clave,
                       vacante.resumen)  # fmt: skip
        respuestas = [await resolver(Pregunta(t), ctx) for t in tipicas]
        self._guardar_respuestas(pid, [r for r in respuestas if not r.falta])
        c = self.contacto(datos)
        pares = (
            ("Nombre", c.nombre), ("Correo", c.correo), ("Teléfono", c.telefono),
            ("Ciudad", c.ciudad),
        )  # fmt: skip
        contacto = {k: v for k, v in pares if v}
        return Paquete(vacante, motivo, afinidad, cv, carta, respuestas, contacto, parcial)

    # --- modo automático por usuario -------------------------------------------------------

    async def encolar_automaticos(self) -> list[Postulacion]:
        """Encola, para cada usuario con modo automático, las vacantes nuevas que superan su
        umbral. Se llama después de indexar."""
        ahora = self.ahora()
        nuevas = []
        usuarios = self.base.cx.execute(
            "SELECT id FROM usuarios WHERE estado = 'activo' AND pausado = 0 "
            "AND automatico_umbral IS NOT NULL"
        ).fetchall()
        vacantes = self.base.cx.execute(
            "SELECT id_corto FROM vacantes WHERE plataforma IS NOT NULL AND indexada_en >= ?",
            (self.base.kv_obtener("automatico_hasta") or a_texto(ahora),),
        ).fetchall()
        for u in usuarios:
            usuario = self.usuarios.por_id(u["id"])
            datos = self.datos_usuario(u["id"])
            if usuario is None or datos is None or usuario.estado != EstadoUsuario.ACTIVO:
                continue
            fila = self.base.cx.execute(
                "SELECT automatico_umbral FROM usuarios WHERE id = ?", (u["id"],)
            ).fetchone()
            for v in vacantes:
                vacante = self.indice.obtener(v["id_corto"])
                if vacante is None or self.cola.de_usuario(u["id"], v["id_corto"]):
                    continue
                if self.camino_automatico(u["id"], vacante) is not None:
                    continue
                pref = (
                    self.preferencias.obtener(u["id"], vacante.plataforma)
                    if vacante.plataforma
                    else None
                )
                if pref is not None and not pref.automatico:
                    continue  # el usuario apagó la postulación sola en ese portal
                requisitos = await obtener_requisitos(self.base, vacante.id_corto,
                                                      vacante.resumen)  # fmt: skip
                afinidad = calcular_afinidad(requisitos, datos.perfil)
                porcentaje = afinidad.porcentaje if afinidad else None
                umbral_propio = pref.umbral if pref else None
                umbral = umbral_propio if umbral_propio is not None else fila["automatico_umbral"]
                if self.cola.debe_encolar_automatico(
                    umbral, porcentaje, vacante.plataforma, u["id"], ahora
                ):
                    p, creada = self.cola.encolar(u["id"], vacante.id_corto, vacante.plataforma,
                                                  ahora, origen="automatico",
                                                  afinidad=porcentaje)  # fmt: skip
                    if creada:
                        nuevas.append(p)
        self.base.kv_guardar("automatico_hasta", a_texto(ahora))
        return nuevas
