"""Núcleo del asistente: une índice, detalle, IA, CV, respuestas, cola y cuentas.

El bot y la API usan esta clase; los avisos al usuario salen por ``notificador`` (el bot).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from buscador_vacantes.asistente.afinidad import Afinidad, calcular_afinidad, obtener_requisitos
from buscador_vacantes.asistente.api import Campo, PaqueteDocumentos, ResultadoFormulario
from buscador_vacantes.asistente.campos import RESERVADO, DatosUsuario, es_guardable
from buscador_vacantes.asistente.cifrado import Cifrador, ClaveInvalida
from buscador_vacantes.asistente.cola import ESPERANDO, Cola, E, Evento, Postulacion, Tipo
from buscador_vacantes.asistente.cuentas_portal import CuentasPortal
from buscador_vacantes.asistente.cv_adaptado import adaptar, cv_base, redactar_carta
from buscador_vacantes.asistente.cv_lectura import PerfilExtraido
from buscador_vacantes.asistente.cv_pdf import (
    Contacto,
    generar_pdf,
    generar_pdf_carta,
    nombre_archivo,
)
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.destinos_linkedin import (
    clasificar,
    seguir_acortadores,
    usar,
    vigente,
)
from buscador_vacantes.asistente.detalle import Detalles, EstadoPagina
from buscador_vacantes.asistente.documentos import Documentos
from buscador_vacantes.asistente.espera import Causa, Entrada, NavegadorLatido, causa
from buscador_vacantes.asistente.esquemas_ats import LectorEsquemas, a_campos, familia_con_lector
from buscador_vacantes.asistente.ia import ClaveInvalida as ClaveIAInvalida
from buscador_vacantes.asistente.ia import (
    ClienteIA,
    CuotaAgotada,
    ErrorIA,
    Parte,
    TopeAlcanzado,
)
from buscador_vacantes.asistente.ia import datos as delimitar
from buscador_vacantes.asistente.pantalla import (
    INSTRUCCION_ENTENDER_PAGINA,
    INSTRUCCION_REPARAR_FLUJO,
    Consulta,
    ConsultaReparacion,
    DecisionPagina,
    Reparacion,
    texto_consulta,
    texto_reparacion,
)
from buscador_vacantes.asistente.preferencias import Preferencias
from buscador_vacantes.asistente.recetas import (
    aplicar_parches,
    barrera_de,
    clave_campo,
    host_de,
    parches_aplicables,
)
from buscador_vacantes.asistente.respuestas import (
    Contexto,
    Origen,
    Pregunta,
    Respuesta,
    aprendida,
    detectar_idioma,
    elegir_opcion,
    normalizar_pregunta,
    recordar,
    recortar_a_limite,
    redactar_formulario,
    resolver,
    revisar_formulario,
    tipo_archivo,
)
from buscador_vacantes.asistente.textos import MOTIVOS_SIN_ALERTA
from buscador_vacantes.asistente.usuarios import EstadoUsuario, Usuario, Usuarios
from buscador_vacantes.asistente.vacantes import Indice, VacanteIndexada
from buscador_vacantes.comun import config as cfg
from buscador_vacantes.comun.estado import a_texto, ahora_utc, de_texto
from buscador_vacantes.comun.fechas import ZONA

log = logging.getLogger(__name__)

CLAVE_VIGIA = "vigia_dia"  # día (en Bogotá) del último ensayo programado del vigía
PROVEEDOR_PROVISIONAL = "gemini"  # se elimina en la tarea 3.3 (proveedor por usuario)

RUTA_SELECTORES = cfg.RAIZ / "assets" / "asistente" / "selectores"


class Camino(StrEnum):
    AUTOMATICA = "automatica"
    RESPALDO = "respaldo"
    NO_DISPONIBLE = "no_disponible"
    YA_EXISTE = "ya_existe"
    EN_CUENTA = "en_cuenta"  # la cuenta regresiva corre: aún no se encoló nada
    ACEPTAR_RIESGO = "aceptar_riesgo"  # LinkedIn: falta que el usuario acepte el riesgo


# Nombre de archivo (prefijo) con que se entrega cada tipo de documento a la extensión
NOMBRES_DE_ARCHIVO = {"certificado_notas": "Notas", "carta": "Carta", "portafolio": "Portafolio"}


@dataclass
class Toque:
    """Resultado de tocar ⚡ Postularme."""

    camino: Camino
    vacante: VacanteIndexada | None = None
    postulacion: Postulacion | None = None
    motivo: str | None = None  # por qué no es automática


class Nucleo:
    def __init__(
        self,
        configuracion: cfg.Configuracion,
        base: BaseAsistente,
        indice: Indice,
        detalles: Detalles,
        ia: dict[str, ClienteIA],
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
        self.ia = ia  # un cliente por proveedor del catálogo, por id
        self.cifrador = cifrador
        self.archivos = archivos
        self.enlace_grupo: str | None = None  # lo fija servicio.construir_nucleo
        self.reloj = reloj
        self.cola = Cola(base, self.config)
        self.linkedin = self.cola.linkedin  # aceptación, interruptores, pausa y aperturas
        self.cuentas = CuentasPortal(base, cifrador)
        self.preferencias = Preferencias(base)
        self.usuarios = Usuarios(base, archivos)
        self.documentos = Documentos(base, cifrador, self.usuarios)
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

    def portales_abiertos(self, usuario_id: int) -> set[str]:
        """Plataformas con la sesión abierta y la cuenta confirmada según el último latido de
        los navegadores del usuario."""
        filas = self.base.cx.execute(
            "SELECT portales_json FROM navegadores WHERE usuario_id = ? AND revocado = 0",
            (usuario_id,),
        ).fetchall()
        abiertos: set[str] = set()
        for fila in filas:
            portales = json.loads(fila["portales_json"]) if fila["portales_json"] else {}
            for plataforma, portal in portales.items():
                if (
                    isinstance(portal, dict)
                    and portal.get("cuenta") == "ok"
                    and portal.get("estado") not in ("sin_sesion", "sin_permiso")
                ):
                    abiertos.add(plataforma)
        return abiertos

    def permiso_externo(self, usuario_id: int) -> bool:
        """Si algún navegador del usuario tiene concedido el permiso para las páginas externas
        (la plataforma `externa` de la extensión), según su último latido."""
        filas = self.base.cx.execute(
            "SELECT portales_json FROM navegadores WHERE usuario_id = ? AND revocado = 0",
            (usuario_id,),
        ).fetchall()
        for fila in filas:
            portales = json.loads(fila["portales_json"]) if fila["portales_json"] else {}
            externa = portales.get("externa")
            if isinstance(externa, dict) and externa.get("estado") not in (None, "sin_permiso"):
                return True
        return False

    # --- vacantes y selectores -----------------------------------------------------------

    def vacante(self, id_corto: str) -> dict[str, Any] | None:
        v = self.indice.obtener(id_corto)
        return None if v is None else {"url": v.url, "titulo": v.titulo, "empresa": v.empresa}

    def cargar_selectores(self) -> int:
        """Carga assets/asistente/selectores/<plataforma>.json a la base (arranque o comando)."""
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
        if not fila:
            return None
        version, contenido = fila["version"], json.loads(fila["contenido_json"])
        parches = parches_aplicables(self.base, plataforma)
        if parches:  # los candidatos y firmes van antepuestos; la versión cambia para que la
            contenido = aplicar_parches(contenido, parches)  # extensión vuelva a bajarlos
            version = f"{version}+p{max(p['id'] for p in parches)}"
        return version, contenido

    def espera(self, pid: int) -> Causa | None:
        """Por qué una postulación en cola todavía no sale hacia la extensión (None si nada)."""
        p = self.cola.obtener(pid)
        if p is None or p.plataforma is None or p.estado not in ESPERANDO:
            return None
        ahora = self.ahora()
        filas = self.base.cx.execute(
            "SELECT id, version, ultimo_latido, portales_json FROM navegadores "
            "WHERE usuario_id = ? AND revocado = 0",
            (p.usuario_id,),
        ).fetchall()
        navegadores = [
            NavegadorLatido(
                f["id"], de_texto(f["ultimo_latido"]), f["version"],
                json.loads(f["portales_json"]) if f["portales_json"] else {},
            )
            for f in filas
        ]  # fmt: skip
        ajustes = self.config.plataformas.get(p.plataforma)
        encendida = bool(ajustes and ajustes.automatica and self.selectores(p.plataforma))
        return causa(Entrada(
            plataforma=p.plataforma, navegadores=navegadores, ahora=ahora,
            version_minima=self.config.extension.version_minima,
            navegador_caido=timedelta(minutes=self.config.extension.navegador_caido_min),
            plataforma_encendida=encendida, restriccion=self.cola.restriccion(p, ahora),
        ))  # fmt: skip

    # --- toque de ⚡ ------------------------------------------------------------------

    def camino_automatico(self, usuario_id: int, vacante: VacanteIndexada) -> str | None:
        """None si se puede postular sola; si no, el motivo del respaldo."""
        if barrera := barrera_de(self.base, host_de(vacante.url)):
            return barrera  # el host exige cuenta u OAuth: al respaldo sin abrir la página
        if vacante.plataforma is None:
            return "plataforma_no_soportada"
        ajustes = self.config.plataformas.get(vacante.plataforma)
        if ajustes is None or not ajustes.automatica:
            return "plataforma_no_automatica"
        if not self.tiene_navegador(usuario_id):
            return "sin_navegador"
        if vacante.plataforma == "linkedin":
            return self._camino_linkedin(usuario_id, vacante)
        return None

    def _camino_linkedin(self, usuario_id: int, vacante: VacanteIndexada) -> str | None:
        """Lo que se sabe de una vacante de LinkedIn al tocar ⚡: la aceptación del riesgo, los
        interruptores y, si otro usuario ya resolvió el destino, su clasificación. Lo demás
        (sencilla o externa, cerrada) se descubre al abrir la página con la sesión del usuario."""
        ajustes = self.config.linkedin
        if not self.linkedin.acepto(usuario_id, ajustes.riesgo_version):
            return "linkedin_sin_aceptar"
        estado = self.linkedin.estado(usuario_id)
        if not (estado.sencilla or estado.externas):
            return "linkedin_apagado"
        guardado = vigente(self.base, vacante.id_corto, self.ahora(), ajustes.destino_dias)
        if guardado is None:
            return None
        clasificado = clasificar(
            guardado["destino"], ajustes, self.config.medicion_linkedin, self.base
        )
        if clasificado.motivo:
            return clasificado.motivo
        if not estado.externas:
            return "linkedin_apagado"
        if not self.permiso_externo(usuario_id):
            return "sin_permiso_externo"
        return None

    def aceptar_riesgo_linkedin(
        self, usuario: Usuario, id_corto: str, *, origen: str = "boton"
    ) -> Toque:
        """«Acepto y postular»: guarda la aceptación (versión y fecha) y sigue con el toque."""
        self.linkedin.aceptar(usuario.id, self.config.linkedin.riesgo_version, self.ahora())
        return self.tocar(usuario, id_corto, origen=origen)

    def solo_paquete_linkedin(
        self, usuario: Usuario, id_corto: str, *, origen: str = "boton"
    ) -> Toque:
        """«Solo paquete»: la vacante va al respaldo sin abrir nada; la próxima vez se vuelve a
        ofrecer la aceptación."""
        ahora = self.ahora()
        vacante = self.indice.resolver(id_corto, ahora)
        if vacante is None:
            return Toque(Camino.NO_DISPONIBLE)
        if existente := self.cola.de_usuario(usuario.id, id_corto):
            return Toque(Camino.YA_EXISTE, vacante, existente)
        postulacion, _ = self.cola.encolar(
            usuario.id, id_corto, vacante.plataforma, ahora, origen=origen
        )
        motivo = "linkedin_sin_aceptar"
        self.cola.a_respaldo(postulacion.id, ahora, motivo, (E.EN_COLA,))
        return Toque(Camino.RESPALDO, vacante, self.cola.obtener(postulacion.id), motivo)

    def pausar_linkedin(self, usuario_id: int) -> datetime:
        """Un aviso de seguridad de LinkedIn detiene sus postulaciones `pausa_seguridad_h` horas."""
        hasta = self.ahora() + timedelta(hours=self.config.linkedin.pausa_seguridad_h)
        self.linkedin.pausar(usuario_id, hasta)
        return hasta

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
            if (motivo == existente.motivo == "linkedin_sin_aceptar"
                    and existente.estado == E.RESPALDO):  # «Solo paquete»: se vuelve a ofrecer
                return Toque(Camino.ACEPTAR_RIESGO, vacante, existente, motivo)
            return Toque(Camino.YA_EXISTE, vacante, existente)
        if motivo == "linkedin_sin_aceptar":  # nada se abre ni se encola hasta que elija
            return Toque(Camino.ACEPTAR_RIESGO, vacante, motivo=motivo)
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

    def proveedor_de(self, usuario_id: int) -> str:
        # Provisional hasta 3.1/3.3: la base solo guarda claves de Gemini, sin proveedor elegido
        return PROVEEDOR_PROVISIONAL

    def cliente_ia(self, usuario_id: int) -> ClienteIA:
        return self.ia[self.proveedor_de(usuario_id)]

    def nivel_de(self, postulacion: Postulacion) -> str:
        """El nivel de IA con que corre la postulación: el copiado al encolar, o el menor al que
        bajó la cuota del usuario hoy."""
        return self.preferencias.nivel_efectivo(
            postulacion.usuario_id, postulacion.nivel_ia, self.ahora()
        )

    def en_ensayo(self, postulacion: Postulacion) -> bool:
        """Si la postulación se ensaya (llena todo y se detiene antes de enviar): el usuario lo
        pidió o su plataforma está en ensayo. «Enviar de verdad» la exime."""
        if postulacion.tipo == Tipo.VIGIA:
            return True  # el vigía nunca envía
        if postulacion.forzar_real or postulacion.tipo != Tipo.POSTULAR:
            return False
        if self.preferencias.ensayo_usuario(postulacion.usuario_id):
            return True
        plataformas = self.preferencias.plataformas_en_ensayo(self.config.ensayo.plataformas)
        return postulacion.plataforma in plataformas

    async def _ia(self, usuario_id: int) -> tuple[ClienteIA | None, str | None]:
        clave = self.clave_gemini(usuario_id)
        return (self.cliente_ia(usuario_id), clave) if clave else (None, None)

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
        except ClaveIAInvalida:
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

    # --- esquema anticipado --------------------------------------------------------------

    @staticmethod
    def esquema_de(vacante: VacanteIndexada | None) -> list[Pregunta]:
        """Las preguntas del formulario que un lector leyó de la vacante antes de abrir la
        página; los campos mal formados se ignoran."""
        preguntas = []
        for crudo in (vacante.esquema if vacante else None) or []:
            try:
                c = Campo.model_validate(crudo)
            except ValidationError:
                continue
            preguntas.append(
                Pregunta(c.texto, c.tipo, c.opciones, c.obligatoria, c.nombre, c.maximo, c.ayuda,
                         c.autocomplete, c.accept, c.idioma, c.busqueda)
            )  # fmt: skip
        return preguntas

    async def anticipar_esquema(
        self, postulacion: Postulacion, vacante: VacanteIndexada | None
    ) -> bool:
        """Resuelve de una vez, con el redactor, todo el formulario que la vacante ya trae leído.
        True si quedó resuelto; False si falta algo del usuario (su pregunta queda en la card, o
        la revisión de lo redactado) y la postulación sigue esperando. Sin esquema, True."""
        preguntas = self.esquema_de(vacante)
        if not preguntas:
            return True
        resultado = await self.resolver_formulario(postulacion, preguntas)
        return not (resultado.faltan or resultado.revisar)

    def destino_guardado(self, postulacion: Postulacion) -> dict[str, str] | None:
        """El destino ya resuelto de la vacante de LinkedIn de esta postulación (con menos de
        `destino_dias`), o None si hay que abrir LinkedIn para descubrirlo."""
        if postulacion.plataforma != "linkedin" or not postulacion.id_corto:
            return None
        return vigente(
            self.base, postulacion.id_corto, self.ahora(), self.config.linkedin.destino_dias
        )

    def requiere_anticipo(self, postulacion: Postulacion, vacante: VacanteIndexada | None) -> bool:
        """Si conviene retener la postulación mientras se resuelve el formulario de antemano:
        la vacante trae su esquema o es de LinkedIn con un destino guardado."""
        return bool(self.esquema_de(vacante)) or self.destino_guardado(postulacion) is not None

    async def anticipar_destino(self, postulacion: Postulacion, vacante: VacanteIndexada) -> str:
        """Resuelve de antemano lo que se sabe de la vacante: `resuelto` (puede salir a la cola),
        `faltan` (queda una pregunta en la card) o `cerrada` (pasó al respaldo). Con un destino
        guardado de LinkedIn confirma antes que la vacante siga abierta (sin saltarse el
        cooldown de la fuente) y lee el formulario del destino si su familia tiene lector."""
        guardado = self.destino_guardado(postulacion)
        if guardado is None:
            return "resuelto" if await self.anticipar_esquema(postulacion, vacante) else "faltan"
        ahora = self.ahora()
        detalle = await self.detalles.obtener(vacante, ahora)
        if detalle.estado == EstadoPagina.CERRADA:
            self.cola.cerrar_vacante(postulacion.id, ahora, (E.ESPERANDO_USUARIO,))
            return "cerrada"
        usar(self.base, postulacion.id_corto, ahora)
        if familia_con_lector(guardado["familia"]) and not await self.preparar_esquema(
            postulacion, guardado["familia"], guardado["destino"]
        ):
            return "faltan"
        return "resuelto"

    async def resolver_redireccion(self, url: str) -> str:
        """La URL final tras seguir los acortadores conocidos (`asistente.linkedin.acortadores`).
        Solo se pide la página de un acortador de la lista, con la pausa por dominio de siempre."""

        async def ubicacion(actual: str) -> str | None:
            await self.detalles.ritmo.esperar_turno(host_de(actual))
            try:
                respuesta = await self.detalles.cliente.get(actual, follow_redirects=False)
            except httpx.HTTPError as exc:
                log.info("Acortador %s no responde: %s", host_de(actual), type(exc).__name__)
                return None
            return respuesta.headers.get("location") if respuesta.is_redirect else None

        return await seguir_acortadores(url, self.config.linkedin, ubicacion)

    async def preparar_esquema(self, postulacion: Postulacion, familia: str, url: str) -> bool:
        """Lee el formulario del destino de una familia con lector, lo guarda como esquema de la
        vacante y lo resuelve de una vez. False si falta un dato del usuario (su pregunta queda
        en la card). Sin esquema (familia sin lector o lectura fallida) devuelve True: el motor
        lee la página."""
        if not postulacion.id_corto:
            return True
        lector = LectorEsquemas(self.detalles.cliente, self.detalles.ritmo)
        preguntas = await lector.leer(familia, url)
        self.indice.guardar_esquema(
            postulacion.id_corto, a_campos(preguntas) if preguntas else None
        )
        if not preguntas:
            return True
        return await self.anticipar_esquema(postulacion, self.indice.obtener(postulacion.id_corto))

    def esquema_resuelto(self, postulacion: Postulacion) -> dict[str, str]:
        """Lo ya respondido del formulario anticipado, por la clave del campo (la misma de la
        firma de una pantalla), para que la extensión no consulte por esos campos."""
        vacante = self.indice.obtener(postulacion.id_corto) if postulacion.id_corto else None
        respuestas = {
            f["pregunta_norm"]: f["respuesta"]
            for f in self.base.cx.execute(
                "SELECT pregunta_norm, respuesta FROM respuestas WHERE postulacion_id = ? "
                "AND respuesta IS NOT NULL",
                (postulacion.id,),
            )
        }
        resuelto = {}
        for p in self.esquema_de(vacante):
            norma = normalizar_pregunta(p.texto)
            # Lo redactado o resuelto, o lo que el usuario contestó en la card después
            valor = respuestas.get(norma) or aprendida(self.base, postulacion.usuario_id, norma)
            if p.tipo != "archivo" and valor and valor != RESERVADO:
                resuelto[clave_campo(p.nombre, p.texto)] = valor
        return resuelto

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
        nivel = self.nivel_de(postulacion)
        preset = getattr(self.config.niveles_ia, nivel)
        ctx = Contexto(
            self.base, usuario.id, datos, self.ahora(), cliente, clave,
            vacante.resumen if vacante else "",
            postulacion.plataforma, detectar_idioma(preguntas),
            requisitos_en_redactor=preset.requisitos_en_redactor,
            ejemplos_estilo=preset.ejemplos_estilo,
            doble_redaccion=preset.doble_redaccion,
            revisor_final=preset.revisor_final,
            requisitos=self._requisitos_de(postulacion) if preset.requisitos_en_redactor else [],
            nivel=nivel, clasificar_preguntas=preset.clasificar_preguntas,
        )  # fmt: skip
        resultado = ResultadoFormulario()
        previas = self._redacciones_previas(postulacion.id)
        estados: dict[str, str] = {}  # pregunta normalizada → estado de la redacción reutilizada
        resueltas: list[Respuesta] = []
        por_redactar: list[Pregunta] = []
        # Fase 1: datos, opciones y redacciones ya hechas para esta postulación, sin redactar
        for pregunta in preguntas:
            if pregunta.tipo == "archivo":
                continue  # el CV lo adjunta la extensión
            try:
                respuesta = await resolver(pregunta, ctx)
            except ClaveIAInvalida:
                self.marcar_clave_invalida(usuario.id)
                ctx.cliente, ctx.clave = None, None
                respuesta = await resolver(pregunta, ctx)
            if respuesta.redactar:
                norma = normalizar_pregunta(pregunta.texto)
                previa = previas.get(norma)
                reutilizada = self._reutilizar(pregunta, previa) if previa else None
                if reutilizada is None:
                    por_redactar.append(pregunta)
                    continue
                estados[norma] = previa["estado"]
                respuesta = reutilizada
            resueltas.append(respuesta)
        # Fase 2: una sola llamada para todas las preguntas abiertas que faltan
        resueltas += await self._redactar(por_redactar, ctx)
        if ctx.revisadas:
            with self.base.transaccion() as cx:
                self.cola.paso(cx, postulacion.id, "respuestas_revisadas", self.ahora(),
                               detalle=str(ctx.revisadas))  # fmt: skip
        for respuesta in resueltas:
            if respuesta.falta:
                if respuesta.pregunta.obligatoria:
                    resultado.faltan.append(respuesta)
            else:
                resultado.respuestas.append(respuesta)
        orden = {id(p): i for i, p in enumerate(preguntas)}
        resultado.respuestas.sort(key=lambda r: orden[id(r.pregunta)])
        revisar = not resultado.faltan and self._toca_revisar(postulacion, resultado, estados)
        self._guardar_respuestas(postulacion.id, resultado.respuestas, estados, revisar=revisar)
        if resultado.faltan:
            self._crear_pendientes(usuario.id, postulacion.id, resultado.faltan)
            await self.notificar({"tipo": "preguntas_pendientes", "usuario_id": usuario.id,
                                  "postulacion_id": postulacion.id})  # fmt: skip
            return resultado
        if revisar:
            resultado.revisar = True
            await self.notificar({"tipo": "revision_respuestas", "usuario_id": usuario.id,
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

    async def arbitrar_pantalla(
        self, postulacion: Postulacion, consulta: Consulta
    ) -> DecisionPagina | None:
        """Árbitro de las pantallas que las reglas no entienden (tarea `entender_pagina`, con la
        clave del usuario). None: sin clave o la IA falló, y la pantalla va a respaldo."""
        cliente, clave = await self._ia(postulacion.usuario_id)
        if cliente is None:
            return None
        try:
            return await cliente.generar(
                "entender_pagina", clave, postulacion.usuario_id, INSTRUCCION_ENTENDER_PAGINA,
                [Parte(delimitar("pantalla", texto_consulta(consulta)))], DecisionPagina,
                nivel=self.nivel_de(postulacion),
            )  # fmt: skip
        except ClaveIAInvalida:
            self.marcar_clave_invalida(postulacion.usuario_id)
        except ErrorIA:
            pass
        return None

    async def reparar_pantalla(
        self, postulacion: Postulacion, consulta: ConsultaReparacion
    ) -> Reparacion | None:
        """Corrección de un paso que falló antes del envío (tarea `reparar_flujo`). Usa la clave
        del usuario; si no tiene clave o cuota y `autorreparacion.clave_duenio` está encendido,
        la del dueño, que paga solo esta tarea (su entrada no lleva datos personales) y queda
        registrada a su nombre. None: sin IA disponible o la IA falló."""
        candidatos = [postulacion.usuario_id]
        if self.config.autorreparacion.clave_duenio:
            duenio = self.usuarios.obtener(self.config.dueno_telegram_id)
            if duenio is not None and duenio.id != postulacion.usuario_id:
                candidatos.append(duenio.id)
        partes = [Parte(delimitar("pantalla", texto_reparacion(consulta)))]
        for usuario_id in candidatos:
            # La clave del dueño paga una reparación con el nivel normal: el nivel del usuario no
            # decide cuánto gasta el dueño
            nivel = self.nivel_de(postulacion) if usuario_id == postulacion.usuario_id else "normal"
            cliente, clave = await self._ia(usuario_id)
            if cliente is None:
                continue
            try:
                return await cliente.generar(
                    "reparar_flujo", clave, usuario_id, INSTRUCCION_REPARAR_FLUJO, partes,
                    Reparacion, nivel=nivel,
                )  # fmt: skip
            except ClaveIAInvalida:
                self.marcar_clave_invalida(usuario_id)
            except (CuotaAgotada, TopeAlcanzado):
                continue
            except ErrorIA:
                return None
        return None

    async def documentos_pantalla(
        self, postulacion: Postulacion, preguntas: list[Pregunta]
    ) -> PaqueteDocumentos:
        """Los documentos, además del CV, que piden los campos de archivo de la pantalla.

        Cada campo recibe el documento del usuario cuyo tipo corresponde a su etiqueta. La carta
        sin documento guardado se redacta para esta vacante: la obligatoria siempre, la opcional
        solo en los niveles con `carta_opcional` (Máximo). Un campo opcional sin documento queda
        vacío; uno obligatorio sin documento se le pide al usuario en su card (pendiente de tipo
        «documento») y la postulación espera.
        """
        paquete = PaqueteDocumentos()
        usuario = self.usuarios.por_id(postulacion.usuario_id)
        datos = self.datos_usuario(postulacion.usuario_id)
        if usuario is None or datos is None:
            return paquete
        nivel = self.nivel_de(postulacion)
        carta_opcional = getattr(self.config.niveles_ia, nivel).carta_opcional
        contacto = self.contacto(datos)
        for pregunta in preguntas:
            tipo = tipo_archivo(pregunta) if pregunta.tipo == "archivo" else "cv"
            if tipo == "cv" or tipo in paquete.documentos:
                continue
            guardado = self.documentos.por_tipo(usuario.id, tipo)
            if guardado is not None:  # el del usuario manda sobre cualquier redacción
                nombre = nombre_archivo(contacto.nombre, NOMBRES_DE_ARCHIVO[tipo])
                paquete.documentos[tipo] = (nombre, self.documentos.leer(guardado))
            elif tipo == "carta" and (pregunta.obligatoria or carta_opcional):
                carta = await self._carta_para(postulacion, usuario, datos, contacto, nivel)
                if carta is not None:
                    paquete.documentos[tipo] = carta
                elif pregunta.obligatoria:
                    paquete.faltan.append(pregunta)
            elif pregunta.obligatoria:
                paquete.faltan.append(pregunta)
        if paquete.faltan:
            self._crear_pendientes_documento(usuario.id, postulacion.id, paquete.faltan)
            await self.notificar({"tipo": "preguntas_pendientes", "usuario_id": usuario.id,
                                  "postulacion_id": postulacion.id})  # fmt: skip
        return paquete

    async def _carta_para(
        self, postulacion: Postulacion, usuario: Usuario, datos: DatosUsuario,
        contacto: Contacto, nivel: str,
    ) -> tuple[str, bytes] | None:  # fmt: skip
        """La carta de presentación redactada para la vacante de la postulación, en PDF."""
        vacante = self.indice.obtener(postulacion.id_corto) if postulacion.id_corto else None
        if vacante is None:
            return None
        nombre = nombre_archivo(contacto.nombre, "Carta")
        archivo = self._carpeta_postulacion(usuario, postulacion.id) / nombre
        if not archivo.is_file():  # una por postulación: otra pantalla con el campo la reutiliza
            cliente, clave = await self._ia(usuario.id)
            try:
                texto = await redactar_carta(
                    datos, cv_base(datos.perfil), vacante.titulo or "la vacante", vacante.resumen,
                    self.config.carta_max_caracteres, cliente=cliente, clave=clave,
                    usuario_id=usuario.id, nivel=nivel,
                )  # fmt: skip
            except ClaveIAInvalida:
                self.marcar_clave_invalida(usuario.id)
                texto = await redactar_carta(
                    datos, cv_base(datos.perfil), vacante.titulo or "la vacante", vacante.resumen,
                    self.config.carta_max_caracteres, cliente=None, clave=None,
                    usuario_id=usuario.id,
                )  # fmt: skip
            archivo.write_bytes(generar_pdf_carta(texto, contacto, vacante.titulo))
        return nombre, archivo.read_bytes()

    def _crear_pendientes_documento(
        self, usuario_id: int, pid: int, faltan: list[Pregunta]
    ) -> None:
        """Una pregunta pendiente por documento obligatorio que no hay (tipo «documento», con el
        tipo de documento en `campo`); no se repite una que ya espera respuesta."""
        with self.base.transaccion() as cx:
            for pregunta in faltan:
                norma = normalizar_pregunta(pregunta.texto)
                ya = cx.execute(
                    "SELECT 1 FROM pendientes_usuario WHERE postulacion_id = ? "
                    "AND pregunta_norm = ? AND respondida_en IS NULL",
                    (pid, norma),
                ).fetchone()
                if ya:
                    continue
                cx.execute(
                    "INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, "
                    "pregunta_norm, opciones_json, campo, tipo, creada) "
                    "VALUES (?, ?, ?, ?, '[]', ?, 'documento', ?)",
                    (usuario_id, pid, pregunta.texto, norma, tipo_archivo(pregunta),
                     a_texto(self.ahora())),
                )  # fmt: skip

    def documento_recibido(self, usuario_id: int, pendiente_id: int) -> bool:
        """El usuario guardó el documento que pedía una pendiente: se da por respondida y, si no
        quedan más en esa postulación, vuelve a la cola. True si se reencoló."""
        fila = self.base.cx.execute(
            "SELECT postulacion_id FROM pendientes_usuario WHERE id = ? AND usuario_id = ? "
            "AND tipo = 'documento' AND respondida_en IS NULL",
            (pendiente_id, usuario_id),
        ).fetchone()
        if fila is None:
            return False
        pid = fila["postulacion_id"]
        ahora = self.ahora()
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE pendientes_usuario SET respondida_en = ?, respuesta = 'documento' "
                "WHERE id = ?",
                (a_texto(ahora), pendiente_id),
            )
        restantes = self.base.cx.execute(
            "SELECT COUNT(*) FROM pendientes_usuario WHERE postulacion_id = ? "
            "AND respondida_en IS NULL",
            (pid,),
        ).fetchone()[0]
        return restantes == 0 and self.cola.reanudar(pid, ahora, (E.ESPERANDO_USUARIO,))

    def documento_a_respaldo(self, usuario_id: int, pendiente_id: int) -> int | None:
        """El usuario prefiere dejar la vacante en el respaldo en vez de enviar el documento:
        la postulación termina con el motivo `documento_faltante` y sus preguntas se cierran.
        Devuelve el id de la postulación, o None si ya no aplica."""
        fila = self.base.cx.execute(
            "SELECT postulacion_id FROM pendientes_usuario WHERE id = ? AND usuario_id = ? "
            "AND tipo = 'documento' AND respondida_en IS NULL",
            (pendiente_id, usuario_id),
        ).fetchone()
        if fila is None or fila["postulacion_id"] is None:
            return None
        pid = fila["postulacion_id"]
        ahora = self.ahora()
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE pendientes_usuario SET respondida_en = ? WHERE postulacion_id = ? "
                "AND respondida_en IS NULL",
                (a_texto(ahora), pid),
            )
        if not self.cola.a_respaldo(pid, ahora, "documento_faltante", (E.ESPERANDO_USUARIO,)):
            return None
        return pid

    # --- vigía ------------------------------------------------------------------------------

    def vacante_para_vigia(
        self, usuario_id: int, plataforma: str, ahora: datetime
    ) -> VacanteIndexada | None:
        """Una vacante reciente y abierta de la plataforma que el usuario no tiene en la cola."""
        desde = ahora - timedelta(days=self.config.vigia.dias_recientes)
        fila = self.base.cx.execute(
            "SELECT id_corto FROM vacantes WHERE plataforma = ? AND enviada_en >= ? "
            "AND COALESCE(estado_pagina, 'ok') NOT IN ('cerrada', 'bloqueada') "
            "AND id_corto NOT IN (SELECT id_corto FROM postulaciones "
            "WHERE usuario_id = ? AND id_corto IS NOT NULL) "
            "ORDER BY enviada_en DESC LIMIT 1",
            (plataforma, a_texto(desde), usuario_id),
        ).fetchone()
        return self.indice.obtener(fila["id_corto"]) if fila else None

    def programar_vigia(self, ahora: datetime) -> list[Postulacion]:
        """Una vez al día, a la hora del vigía, encola en el navegador del dueño un ensayo por
        plataforma automática. Si el servicio estaba apagado a esa hora, sale dentro de la
        ventana configurada y no después (fuera de las horas de uso)."""
        vigia = self.config.vigia
        dueno = self.usuarios.obtener(self.config.dueno_telegram_id) if vigia.activo else None
        if dueno is None or not self.tiene_navegador(dueno.id):
            return []
        local = ahora.astimezone(ZONA)
        hora = time.fromisoformat(vigia.hora)
        inicio = datetime.combine(local.date(), hora, tzinfo=ZONA)
        if not inicio <= local < inicio + timedelta(hours=vigia.ventana_h):
            return []
        if self.base.kv_obtener(CLAVE_VIGIA) == local.date().isoformat():
            return []
        self.base.kv_guardar(CLAVE_VIGIA, local.date().isoformat())
        creadas = []
        for plataforma, ajustes in self.config.plataformas.items():
            if not ajustes.automatica or not self.selectores(plataforma):
                continue
            vacante = self.vacante_para_vigia(dueno.id, plataforma, ahora)
            if vacante is None:
                continue
            if p := self.cola.encolar_vigia(dueno.id, vacante.id_corto, plataforma, ahora):
                creadas.append(p)
        return creadas

    def cerrar_vigia(self, p: Postulacion, estado: E, motivo: str | None) -> str:
        """Qué pasó con el ensayo del vigía: `ok`, `reparado` (falló y el bucle lo reparó),
        `fallo` (la plataforma cambió y nadie la reparó: queda en ensayo para todos hasta
        `/plataformas <p> real`), `bloqueada` o `omitida` (la vacante cerró, falta la sesión,
        el sitio exige cuenta… nada que le falle a la plataforma)."""
        if estado == E.ENSAYADA:
            reparo = self.base.cx.execute(
                "SELECT 1 FROM postulacion_pasos WHERE postulacion_id = ? "
                "AND paso IN ('reparacion', 'respaldo_generico')",
                (p.id,),
            ).fetchone()
            return "reparado" if reparo else "ok"
        if estado == E.BLOQUEADA and motivo not in MOTIVOS_SIN_ALERTA:
            return "bloqueada"
        if estado in (E.FORMULARIO_DESCONOCIDO, E.FALLIDA) and motivo not in MOTIVOS_SIN_ALERTA:
            if p.plataforma:
                self.preferencias.poner_en_ensayo(p.plataforma, "vigia", self.ahora())
            return "fallo"
        return "omitida"

    # --- modo ensayo ------------------------------------------------------------------------

    def datos_ensayo(self, pid: int) -> dict:
        """Lo que la card de un ensayo muestra: las respuestas que se habrían enviado, dónde se
        trabaría (el último paso `ensayo_trabado`) y si la plataforma está en ensayo."""
        cx = self.base.cx
        trabado = cx.execute(
            "SELECT detalle FROM postulacion_pasos WHERE postulacion_id = ? "
            "AND paso = 'ensayo_trabado' ORDER BY id DESC LIMIT 1",
            (pid,),
        ).fetchone()
        respuestas = cx.execute(
            "SELECT id, pregunta, respuesta, origen FROM respuestas WHERE postulacion_id = ? "
            "ORDER BY id",
            (pid,),
        ).fetchall()
        p = self.cola.obtener(pid)
        en_plataforma = bool(
            p and p.plataforma
            in self.preferencias.plataformas_en_ensayo(self.config.ensayo.plataformas)
        )
        return {
            "trabado": trabado["detalle"] if trabado else None,
            "respuestas": [dict(r) for r in respuestas],
            "en_plataforma": en_plataforma,
        }

    def enviar_de_verdad(self, usuario_id: int, pid: int) -> bool:
        """«Enviar de verdad» en la card de un ensayo: vuelve a la cola, ya sin ensayo."""
        p = self.cola.obtener(pid)
        return bool(
            p and p.usuario_id == usuario_id and self.cola.enviar_de_verdad(pid, self.ahora())
        )

    def ensayo_a_respaldo(self, usuario_id: int, pid: int) -> bool:
        """«Paquete de respaldo» en la card de un ensayo: termina con `plataforma_en_ensayo`."""
        p = self.cola.obtener(pid)
        desde = (E.ENSAYADA, E.FORMULARIO_DESCONOCIDO, E.BLOQUEADA, E.FALLIDA)
        return bool(
            p and p.usuario_id == usuario_id
            and self.cola.a_respaldo(pid, self.ahora(), "plataforma_en_ensayo", desde)
        )

    def cv_base_de(self, usuario: Usuario, datos: DatosUsuario) -> Path:
        contacto = self.contacto(datos)
        archivo = self.usuarios.directorio(usuario) / nombre_archivo(contacto.nombre)
        archivo.write_bytes(generar_pdf(cv_base(datos.perfil), contacto))
        return archivo

    async def _redactar(self, preguntas: list[Pregunta], ctx: Contexto) -> list[Respuesta]:
        """Redacta las preguntas abiertas en una llamada. Sin IA, o si falla, cada una se le
        pregunta al usuario tal cual (pendiente de formulario)."""
        try:
            redactadas = await redactar_formulario(preguntas, ctx)
        except ClaveIAInvalida:
            self.marcar_clave_invalida(ctx.usuario_id)
            redactadas = None
        if redactadas is None:
            return [Respuesta(p, falta=True) for p in preguntas]
        if ctx.revisor_final:
            try:
                ctx.revisadas += await revisar_formulario(preguntas, redactadas, ctx)
            except ClaveIAInvalida:
                self.marcar_clave_invalida(ctx.usuario_id)
        resultado = []
        for i, pregunta in enumerate(preguntas):
            r = redactadas.get(i)
            if r is None:
                resultado.append(Respuesta(pregunta, falta=True))
                continue
            # Un dato ya respondido (o reservado) no se vuelve a pedir: si la IA aún lo pide,
            # la pregunta del portal pasa al usuario para escribirla
            nuevos = [
                d for d in r.faltan
                if aprendida(self.base, ctx.usuario_id, normalizar_pregunta(d.pregunta)) is None
            ]  # fmt: skip
            if nuevos and pregunta.obligatoria:
                resultado.append(Respuesta(pregunta, falta=True, datos=nuevos))
            elif nuevos:
                resultado.append(Respuesta(pregunta, falta=True))
            elif r.opcion is not None:  # pregunta con opciones: la IA eligió una válida
                resultado.append(Respuesta(pregunta, opcion=r.opcion, origen=Origen.IA))
            elif r.valor and not pregunta.opciones:
                resultado.append(Respuesta(pregunta, valor=r.valor, origen=Origen.IA))
            else:
                resultado.append(Respuesta(pregunta, falta=True))
        return resultado

    def _requisitos_de(self, postulacion: Postulacion) -> list[str]:
        """Lo que pide la vacante, ya extraído (en `preparar`), para el redactor de Máximo."""
        if not postulacion.id_corto:
            return []
        fila = self.base.cx.execute(
            "SELECT requisitos_json FROM vacantes WHERE id_corto = ?", (postulacion.id_corto,)
        ).fetchone()
        if not fila or not fila["requisitos_json"]:
            return []
        try:
            requisitos = json.loads(fila["requisitos_json"]).get("requisitos") or {}
        except ValueError:
            return []
        return [f"{r} (obligatorio)" for r in requisitos.get("obligatorios", [])] + [
            f"{r} (deseable)" for r in requisitos.get("deseables", [])
        ]

    @staticmethod
    def _reutilizar(pregunta: Pregunta, previa: dict) -> Respuesta | None:
        """La respuesta guardada en una pasada anterior; None si ya no sirve (por ejemplo, la
        opción elegida ya no está entre las del portal)."""
        origen = Origen(previa["origen"])
        if pregunta.opciones:
            indice = elegir_opcion(previa["respuesta"], pregunta.opciones)
            return None if indice is None else Respuesta(pregunta, opcion=indice, origen=origen)
        valor = recortar_a_limite(previa["respuesta"], pregunta.maximo)
        return Respuesta(pregunta, valor=valor, origen=origen)

    def _redacciones_previas(self, pid: int) -> dict[str, dict]:
        """Redacciones de esta postulación que se reutilizan en una pasada nueva del formulario:
        las de la IA y las que el usuario corrigió o aprobó."""
        filas = self.base.cx.execute(
            "SELECT pregunta_norm, respuesta, origen, estado FROM respuestas "
            "WHERE postulacion_id = ? AND respuesta IS NOT NULL "
            "AND (origen IN ('ia', 'usuario') OR estado = 'aprobada')",
            (pid,),
        ).fetchall()
        return {f["pregunta_norm"]: dict(f) for f in filas if f["origen"] in set(Origen)}

    def _toca_revisar(
        self, postulacion: Postulacion, resultado: ResultadoFormulario, estados: dict[str, str]
    ) -> bool:
        """Revisión encendida en el portal y hay redacciones de la IA sin aprobar."""
        if not postulacion.plataforma:
            return False
        pref = self.preferencias.obtener(postulacion.usuario_id, postulacion.plataforma)
        if not pref.revisar_respuestas:
            return False
        return any(
            r.origen == Origen.IA
            and estados.get(normalizar_pregunta(r.pregunta.texto)) != "aprobada"
            for r in resultado.respuestas
        )

    def _guardar_respuestas(
        self, pid: int, respuestas: list[Respuesta], estados: dict[str, str], *, revisar: bool
    ) -> None:
        """Una fila por pregunta: se actualiza sin borrar las redacciones de otras pasadas."""
        with self.base.transaccion() as cx:
            for r in respuestas:
                norma = normalizar_pregunta(r.pregunta.texto)
                estado = estados.get(norma, "enviada")
                if revisar and r.origen == Origen.IA and estado != "aprobada":
                    estado = "propuesta"
                elif not revisar and estado == "propuesta":
                    estado = "enviada"  # la revisión se apagó mientras esperaba
                cx.execute(
                    "INSERT INTO respuestas(postulacion_id, campo, pregunta, respuesta, origen, "
                    "pregunta_norm, estado) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(postulacion_id, pregunta_norm) DO UPDATE SET "
                    "campo = excluded.campo, pregunta = excluded.pregunta, "
                    "respuesta = excluded.respuesta, origen = excluded.origen, "
                    "estado = excluded.estado",
                    (pid, r.campo, r.pregunta.texto, r.texto, r.origen, norma, estado),
                )

    def _crear_pendientes(self, usuario_id: int, pid: int, faltan: list[Respuesta]) -> None:
        """Una pregunta del portal (tipo formulario) o, si el redactor pidió datos, una por
        dato con sus sugerencias (tipo dato). No se repite una pregunta ya pendiente."""
        filas = []
        for r in faltan:
            if r.datos:
                filas += [(d.pregunta, d.sugerencias, None, "dato") for d in r.datos]
            else:
                filas.append((r.pregunta.texto, r.pregunta.opciones, r.campo, "formulario"))
        with self.base.transaccion() as cx:
            for pregunta, opciones, campo, tipo in filas:
                norma = normalizar_pregunta(pregunta)
                ya = cx.execute(
                    "SELECT 1 FROM pendientes_usuario WHERE postulacion_id = ? "
                    "AND pregunta_norm = ? AND respondida_en IS NULL",
                    (pid, norma),
                ).fetchone()
                if ya:
                    continue
                cx.execute(
                    "INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, "
                    "pregunta_norm, opciones_json, campo, tipo, creada) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (usuario_id, pid, pregunta, norma, json.dumps(opciones, ensure_ascii=False),
                     campo, tipo, a_texto(self.ahora())),
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

        En un pendiente de dato se guarda el dato corto (o RESERVADO, «Prefiero no decirlo»):
        la siguiente pasada del formulario lo usa para redactar. Devuelve True si la
        postulación se reencoló.
        """
        ahora = self.ahora()
        fila = self.base.cx.execute(
            "SELECT * FROM pendientes_usuario WHERE id = ? AND usuario_id = ?",
            (pendiente_id, usuario_id),
        ).fetchone()
        if not fila or fila["respondida_en"]:
            return False
        recordar(self.base, usuario_id, fila["pregunta"], respuesta, ahora)
        if es_guardable(fila["campo"]) and respuesta != RESERVADO:
            # Un dato del perfil (salario, disponibilidad…) sirve para cualquier redacción
            datos = self.datos_usuario(usuario_id)
            if datos is not None:
                datos.cuestionario[fila["campo"]] = respuesta
                self.guardar_cuestionario(usuario_id, datos.cuestionario)
        # La misma pregunta pendiente en otras postulaciones queda respondida con este dato
        afectadas = {
            f["postulacion_id"]
            for f in self.base.cx.execute(
                "SELECT postulacion_id FROM pendientes_usuario WHERE pregunta_norm = ? "
                "AND usuario_id = ? AND respondida_en IS NULL AND postulacion_id IS NOT NULL",
                (fila["pregunta_norm"], usuario_id),
            )
        }
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE pendientes_usuario SET respondida_en = ?, respuesta = ? "
                "WHERE pregunta_norm = ? AND usuario_id = ? AND respondida_en IS NULL",
                (a_texto(ahora), respuesta, fila["pregunta_norm"], usuario_id),
            )
        reencolada = False
        for pid in afectadas:
            restantes = self.base.cx.execute(
                "SELECT COUNT(*) FROM pendientes_usuario WHERE postulacion_id = ? "
                "AND respondida_en IS NULL",
                (pid,),
            ).fetchone()[0]
            if restantes == 0 and self.cola.reanudar(pid, ahora, (E.ESPERANDO_USUARIO,)):
                reencolada |= pid == fila["postulacion_id"]
        return reencolada

    # --- revisión antes de enviar --------------------------------------------------------

    def respuestas_en_revision(self, pid: int) -> list[dict]:
        """Redacciones de la IA que el usuario revisa antes del envío, en el orden del form."""
        filas = self.base.cx.execute(
            "SELECT id, pregunta, respuesta, origen, estado FROM respuestas "
            "WHERE postulacion_id = ? AND estado IN ('propuesta', 'aprobada') "
            "AND origen IN ('ia', 'usuario') ORDER BY id",
            (pid,),
        ).fetchall()
        return [dict(f) for f in filas]

    def corregir_respuesta(self, usuario_id: int, respuesta_id: int, texto: str) -> int | None:
        """El texto del usuario reemplaza la redacción tal cual. Devuelve la postulación."""
        fila = self.base.cx.execute(
            "SELECT r.postulacion_id FROM respuestas r JOIN postulaciones p "
            "ON p.id = r.postulacion_id WHERE r.id = ? AND p.usuario_id = ?",
            (respuesta_id, usuario_id),
        ).fetchone()
        if fila is None or not texto.strip():
            return None
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE respuestas SET respuesta = ?, origen = 'usuario', estado = 'aprobada' "
                "WHERE id = ?",
                (texto.strip(), respuesta_id),
            )
        return fila["postulacion_id"]

    def aprobar_respuestas(self, usuario_id: int, pid: int) -> bool:
        """«✅ Enviar»: todo lo propuesto queda aprobado y la postulación vuelve a la cola; la
        pasada siguiente lo reutiliza sin llamar a la IA. True si se reencoló."""
        p = self.cola.obtener(pid)
        if p is None or p.usuario_id != usuario_id:
            return False
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE respuestas SET estado = 'aprobada' "
                "WHERE postulacion_id = ? AND estado = 'propuesta'",
                (pid,),
            )
        return self.cola.reanudar(pid, self.ahora(), (E.ESPERANDO_USUARIO,))

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
