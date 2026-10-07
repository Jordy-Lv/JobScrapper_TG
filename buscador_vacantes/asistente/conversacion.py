"""Lógica del bot asistente, independiente de la librería de Telegram.

El adaptador (bot.py) traduce los updates a llamadas ``al_*`` y entrega una ``Salida``. Así cada
flujo (alta, toque ⚡, avisos, comandos) se prueba sin Telegram. El estado de la conversación
vive en la base (paso_alta y kv), de modo que un reinicio retoma donde iba cada usuario.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from buscador_vacantes.asistente import preguntas_tarjeta as pt
from buscador_vacantes.asistente import progreso, resumen_postulacion, tarjeta, vinculos
from buscador_vacantes.asistente import tarjeta_postulacion as tp
from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.cola import CON_RESPALDO, E, Evento
from buscador_vacantes.asistente.cv_lectura import (
    CVInvalido,
    Enfoque,
    Formacion,
    Idioma,
    PerfilExtraido,
    RequiereConfirmacion,
    leer_cv,
    validar_archivo,
)
from buscador_vacantes.asistente.enlaces import PREFIJO_VACANTE
from buscador_vacantes.asistente.ia import ClaveInvalida, CuotaAgotada, ErrorIA, Saturado
from buscador_vacantes.asistente.membresia import Comprobador, SinPermisos
from buscador_vacantes.asistente.nucleo import Camino, Nucleo, Paquete
from buscador_vacantes.asistente.respuestas import (
    Contexto,
    ErrorPegado,
    recordar,
    resolver,
    separar_preguntas,
)
from buscador_vacantes.asistente.tarjeta import Tarjeta
from buscador_vacantes.asistente.usuarios import EstadoUsuario, Usuario
from buscador_vacantes.estado import a_texto, de_texto

log = logging.getLogger(__name__)

MENSAJE_GUIA_PROXIMAMENTE = (
    "🎯 <b>Guía para tu entrevista</b>\n"
    "Muy pronto podrás generar una guía hecha a la medida de esta vacante: preguntas "
    "probables, cómo responderlas con tu experiencia y qué investigar de la empresa.\n\n"
    "🚧 Funcionalidad disponible próximamente."
)

Botones = list[list[tuple[str, str]]]  # (texto, "cb:…" o "url:…")


def derivar_del_cv(
    perfil: PerfilExtraido, locales: dict[str, str | None], cuestionario: dict[str, str]
) -> dict[str, str]:
    """Llena desde el CV lo que el cuestionario necesita, sin pisar lo que el usuario ya dio."""
    nuevo = dict(cuestionario)
    valores = dict(locales)
    valores["nombre"] = perfil.nombre
    valores["ciudad"] = perfil.ciudad
    if perfil.formacion and perfil.formacion[0].estado:
        en_curso = "curso" in perfil.formacion[0].estado.lower()
        valores["estudia_actualmente"] = "Sí" if en_curso else "No"
    for idioma in perfil.idiomas:
        if idioma.idioma.lower().startswith(("ingl", "engl")) and idioma.nivel:
            valores["ingles_nivel"] = idioma.nivel
    for campo, valor in valores.items():
        if valor and not nuevo.get(campo):
            nuevo[campo] = valor
    return nuevo


class Salida(Protocol):
    async def enviar(
        self, chat_id: int, texto: str, botones: Botones | None = None
    ) -> int | None: ...

    async def editar(
        self, chat_id: int, mensaje_id: int, texto: str, botones: Botones | None = None
    ) -> None: ...

    async def documento(self, chat_id: int, ruta: Path, texto: str | None = None) -> None: ...

    async def borrar(self, chat_id: int, mensaje_id: int) -> None: ...


class Bloqueado(Exception):
    """El usuario bloqueó al bot (Forbidden)."""


SECCIONES = ("formacion", "experiencia", "proyectos", "habilidades", "idiomas")
NOMBRE_SECCION = {
    "formacion": "Formación",
    "experiencia": "Experiencia",
    "proyectos": "Proyectos",
    "habilidades": "Habilidades",
    "idiomas": "Idiomas",
}


def cb(*partes: object) -> str:
    return "cb:" + ":".join(str(p) for p in partes)


@dataclass
class RespuestaToque:
    """Aviso del botón ⚡ del canal (answerCallbackQuery)."""

    texto: str
    url: str | None = None  # abre el bot con la vacante en lugar de postular
    alerta: bool = False  # ventana con botón Aceptar en lugar de un aviso fugaz


@dataclass
class Opciones:
    limite_mensajes_min: int = 30


class Conversacion:
    def __init__(
        self,
        nucleo: Nucleo,
        salida: Salida,
        comprobador: Comprobador,
        *,
        reloj_monotono: Callable[[], float] = time.monotonic,
        dormir=asyncio.sleep,
    ) -> None:
        self.n = nucleo
        self.s = salida
        self.comprobador = comprobador
        self.config = nucleo.config
        self.reloj = reloj_monotono
        self.dormir = dormir
        self._mensajes: dict[int, deque[float]] = defaultdict(deque)
        self._candados: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tareas: set[asyncio.Task] = set()
        self._borrados: set[asyncio.Task] = set()  # borrados programados; no se esperan
        self._toques_resumen: dict[int, deque[float]] = defaultdict(deque)
        self.intervalo_animacion = 2.5  # segundos entre cuadros del progreso
        self._etapas: dict[int, int] = {}  # postulación → etapa en curso del progreso
        self._animaciones: dict[int, asyncio.Task] = {}

    # --- utilidades ------------------------------------------------------------------

    def es_dueno(self, tid: int) -> bool:
        return tid == self.config.dueno_telegram_id

    def _permitir(self, tid: int) -> bool:
        ahora = self.reloj()
        cola = self._mensajes[tid]
        while cola and ahora - cola[0] > 60:
            cola.popleft()
        if len(cola) >= self.config.topes.mensajes_min:
            return False
        cola.append(ahora)
        return True

    def _esperando(self, usuario: Usuario) -> dict | None:
        valor = self.n.base.kv_obtener(f"esperando:{usuario.id}")
        return json.loads(valor) if valor else None

    def _esperar(self, usuario: Usuario, datos: dict | None) -> None:
        self.n.base.kv_guardar(f"esperando:{usuario.id}", json.dumps(datos) if datos else "")

    def _en_segundo_plano(self, coro) -> None:
        tarea = asyncio.create_task(coro)
        self._tareas.add(tarea)
        tarea.add_done_callback(self._tareas.discard)

    async def esperar_tareas(self) -> None:
        """Para pruebas y para el cierre limpio."""
        while self._tareas:
            await asyncio.gather(*list(self._tareas), return_exceptions=True)

    async def _enviar(self, usuario_o_tid, texto: str, botones: Botones | None = None):
        tid = usuario_o_tid if isinstance(usuario_o_tid, int) else usuario_o_tid.telegram_id
        try:
            return await self.s.enviar(tid, texto, botones)
        except Bloqueado:
            if usuario := self.n.usuarios.obtener(tid):
                self.n.usuarios.marcar_inactivo(usuario)
            return None

    # --- entrada: /start --------------------------------------------------------------

    async def al_iniciar(self, tid: int, nombre: str | None, payload: str | None) -> None:
        if not self._permitir(tid):
            return
        id_corto = payload[2:] if payload and payload.startswith("v_") else None
        usuario = self.n.usuarios.obtener(tid)
        ahora = self.n.ahora()
        if usuario is None:
            try:
                miembro = await self.comprobador.es_miembro_nuevo(tid)
            except SinPermisos:
                await self._enviar(tid, t.ALTAS_CERRADAS)
                return
            if not miembro:
                await self._enviar(tid, t.NO_MIEMBRO)
                return
            usuario = self.n.usuarios.crear(tid, nombre, ahora)
        else:
            usuario = await self.comprobador.comprobar(usuario, ahora)
        if usuario.estado == EstadoUsuario.SUSPENDIDO:
            await self._enviar(usuario, t.SUSPENDIDO)
            return
        self.n.usuarios.tocar_actividad(usuario, ahora)
        if self.n.usuarios.requiere_politica(usuario, self.config.politica.version):
            if id_corto:
                self.n.usuarios.fijar_vacante_pendiente(usuario, id_corto)
            await self._mostrar_politica(usuario)
            return
        if usuario.estado == EstadoUsuario.ALTA:
            if id_corto:
                self.n.usuarios.fijar_vacante_pendiente(usuario, id_corto)
            await self._continuar_alta(self.n.usuarios.obtener(tid))
            return
        if usuario.estado == EstadoUsuario.INACTIVO:
            with self.n.base.transaccion() as cx:
                cx.execute(
                    "UPDATE usuarios SET estado = 'activo', motivo_estado = NULL WHERE id = ?",
                    (usuario.id,),
                )
        if id_corto:
            await self.procesar_toque(usuario, id_corto)
        else:
            await self._enviar(usuario, t.AYUDA)

    async def _mostrar_politica(self, usuario: Usuario) -> None:
        await self._enviar(
            usuario,
            t.e(self.config.politica.texto),
            [[("✅ Acepto", cb("politica", "si")), ("No acepto", cb("politica", "no"))]],
        )

    # --- alta guiada ------------------------------------------------------------------

    async def _continuar_alta(self, usuario: Usuario) -> None:
        paso = usuario.paso_alta or "politica"
        if paso == "politica":
            await self._mostrar_politica(usuario)
        elif paso == "clave":
            self._esperar(usuario, {"tipo": "clave"})
            await self._enviar(
                usuario, t.PEDIR_CLAVE, [[("No tengo clave por ahora", cb("clave", "omitir"))]]
            )
        elif paso == "cv":
            await self._enviar(
                usuario,
                t.PEDIR_CV.format(max_mb=self.config.cv.max_mb),
                [[
                    ("✍️ Crearla desde cero", cb("cvopc", "cero")),
                    ("📎 Adjuntar mi CV", cb("cvopc", "adjuntar")),
                ]],
            )  # fmt: skip
        elif paso == "resumen":
            await self._mostrar_resumen(usuario)
        elif paso.startswith("revision:"):
            await self._mostrar_seccion(usuario, paso.split(":", 1)[1])
        elif paso == "enfoque":
            await self._mostrar_enfoque(usuario)
        elif paso.startswith("cuestionario:"):
            await self._reanudar_preguntas(
                usuario, list(range(len(t.CUESTIONARIO))), int(paso.split(":", 1)[1])
            )
        elif paso.startswith("faltantes:"):
            await self._reanudar_preguntas(
                usuario, self._faltantes(usuario), int(paso.split(":", 1)[1])
            )
        elif paso == "navegador":
            if self.n.tiene_navegador(usuario.id):  # ya lo vinculó: no se le pide otra vez
                await self._terminar_alta(usuario)
            else:
                await self._mostrar_navegador(usuario)

    async def _ir_a(self, usuario: Usuario, paso: str) -> None:
        self.n.usuarios.fijar_paso(usuario, paso)
        await self._continuar_alta(self.n.usuarios.por_id(usuario.id))

    async def _recibir_clave(self, usuario: Usuario, texto: str, mensaje_id: int | None) -> None:
        if mensaje_id is not None:
            try:
                await self.s.borrar(usuario.telegram_id, mensaje_id)
            except Exception:  # noqa: BLE001 - si no se puede borrar, se sigue igual
                log.warning("No se pudo borrar el mensaje con la clave")
        clave = texto.strip()
        try:
            valida = await self.n.cliente_ia(usuario.id).validar_clave(clave)
        except ErrorIA:
            await self._enviar(
                usuario,
                "No pude validar la clave ahora (Gemini no responde). "
                "Intenta de nuevo en unos minutos.",
            )
            return
        if not valida:
            await self._enviar(
                usuario,
                "❌ Esa clave no es válida. Revisa que la copiaste "
                "completa desde aistudio.google.com e inténtalo de nuevo.",
            )
            return
        retomar_cv = bool((self._esperando(usuario) or {}).get("retomar_cv"))
        self.n.guardar_clave_gemini(usuario.id, clave)
        self._esperar(usuario, None)
        await self._enviar(usuario, f"✅ Clave guardada (termina en …{t.e(clave[-4:])}).")
        if usuario.paso_alta == "clave":
            await self._ir_a(usuario, "cv")
        elif retomar_cv:
            ruta = self.n.usuarios.directorio(usuario) / "cv_original.pdf"
            if ruta.exists():
                await self._leer_cv(usuario, ruta.read_bytes(), permitir=False)

    async def al_documento(self, tid: int, contenido: bytes, nombre: str | None) -> None:
        usuario = self.n.usuarios.obtener(tid)
        if usuario is None or not self._permitir(tid):
            return
        if usuario.paso_alta != "cv" and not (self._esperando(usuario) or {}).get("tipo") == "cv":
            await self._enviar(usuario, "Si quieres reemplazar tu hoja de vida usa /perfil.")
            return
        try:
            validar_archivo(contenido, self.config.cv)
        except CVInvalido as exc:
            await self._enviar(usuario, f"❌ {t.e(exc)}")
            return
        ruta = self.n.usuarios.directorio(usuario) / "cv_original.pdf"
        ruta.write_bytes(contenido)
        with self.n.base.transaccion() as cx:
            cx.execute("UPDATE usuarios SET cv_archivo = ? WHERE id = ?", (str(ruta), usuario.id))
        await self._leer_cv(usuario, contenido, permitir=False)

    REINTENTOS_CV_S = (120, 300)  # Gemini saturado: se reintenta solo a los 2 y a los 7 min
    INTENTOS_CV = 3  # fallos seguidos que se reintentan antes de preguntarle al usuario
    PAUSA_INTENTOS_CV_S = 3
    ESPERA_CUOTA_CV_S = 1800  # al esperar que se restablezca la cuota, se prueba cada 30 min
    AVISOS_CUOTA_CV = 48  # hasta 24 h

    async def _leer_cv(
        self,
        usuario: Usuario,
        contenido: bytes,
        *,
        permitir: bool,
        reintento: int = 0,
        silencioso: bool = False,
    ) -> bool:
        """Lee el CV con la IA. Con ``silencioso`` no molesta si falla; devuelve si quedó resuelto."""
        clave = self.n.clave_gemini(usuario.id)
        if not clave:
            await self._enviar(
                usuario, "Como no tengo clave de Gemini, armemos tu perfil con unas preguntas."
            )
            await self._perfil_manual(usuario, 0)
            return True
        if reintento == 0 and not silencioso:
            await self._enviar(usuario, "📄 Leyendo tu hoja de vida…")
        try:
            lectura = await self._leer_cv_con_intentos(
                usuario, clave, contenido, permitir=permitir, intentos=1 if silencioso else None
            )
        except RequiereConfirmacion:
            await self._enviar(
                usuario,
                t.CV_ESCANEADO,
                [
                    [
                        ("Sí, enviarlo completo", cb("cv", "escaneado")),
                        ("Llenar a mano", cb("cv", "manual")),
                    ]
                ],
            )
            return True
        except CVInvalido as exc:
            await self._enviar(usuario, f"❌ {t.e(exc)}")
            return True
        except Saturado:
            if silencioso:
                return False
            if reintento < len(self.REINTENTOS_CV_S):
                espera = self.REINTENTOS_CV_S[reintento]
                if reintento == 0:
                    await self._enviar(
                        usuario,
                        "⏳ Los servidores de IA de Google están muy ocupados en este momento. "
                        f"Reintento solo en {espera // 60} minutos y te aviso; no tienes que "
                        "hacer nada.",
                        [[("Prefiero llenarlo a mano", cb("cv", "manual"))]],
                    )
                self._en_segundo_plano(
                    self._reintentar_cv(usuario.id, contenido, permitir, reintento + 1, espera)
                )
                return True
            await self._enviar(
                usuario,
                "Google sigue saturado. Armemos tu perfil con unas preguntas (podrás "
                "reemplazarlo luego enviando tu CV desde /perfil).",
            )
            await self._perfil_manual(usuario, 0)
            return True
        except ErrorIA as exc:
            if silencioso:
                return False
            await self._preguntar_fallo_cv(usuario, exc)
            return True
        self.n.guardar_perfil(usuario.id, lectura.perfil)
        datos = self.n.datos_usuario(usuario.id)
        locales = {c: getattr(lectura.locales, c) for c in ("correo", "telefono", "documento")}
        self.n.guardar_cuestionario(
            usuario.id, derivar_del_cv(lectura.perfil, locales, datos.cuestionario)
        )
        self._esperar(usuario, None)
        if usuario.estado == EstadoUsuario.ALTA:
            await self._ir_a(usuario, "resumen")
        else:
            await self._enviar(
                usuario, "✅ Perfil actualizado con tu nueva hoja de vida. Revísalo con /perfil."
            )
        return True

    async def _leer_cv_con_intentos(
        self, usuario: Usuario, clave: str, contenido: bytes, *, permitir: bool, intentos=None
    ):
        """Llama a la IA y reintenta los fallos pasajeros (red, error del proveedor) hasta 3 veces.

        La saturación, la cuota y la clave inválida no se reintentan aquí: no se arreglan en segundos.
        """
        intentos = intentos or self.INTENTOS_CV
        for numero in range(1, intentos + 1):
            try:
                return await leer_cv(
                    self.n.cliente_ia(usuario.id),
                    clave,
                    usuario.id,
                    contenido,
                    self.config.cv,
                    permitir_archivo_completo=permitir,
                )
            except (Saturado, CuotaAgotada, ClaveInvalida):
                raise
            except ErrorIA:
                if numero == intentos:
                    raise
                await self.dormir(self.PAUSA_INTENTOS_CV_S)

    @staticmethod
    def _causa_fallo_cv(exc: ErrorIA) -> str:
        if isinstance(exc, CuotaAgotada):
            return (
                "Lo más probable es que se llenó la cuota de tu clave de Gemini "
                "(el plan gratuito se agota por día y por minuto)."
            )
        if isinstance(exc, ClaveInvalida):
            return "Gemini rechazó tu clave: puede estar mal copiada, revocada o desactivada."
        if (exc.motivo or "").startswith("HTTP"):
            return (
                f"Gemini respondió con un error ({t.e(exc.motivo)}). Suele ser un fallo "
                "pasajero del servicio de Google."
            )
        return (
            "No logré conectarme con Gemini. Puede ser una caída momentánea de Google "
            "o un problema de red del servidor."
        )

    async def _preguntar_fallo_cv(self, usuario: Usuario, exc: ErrorIA) -> None:
        botones = [[("✍️ Llenarla a mano", cb("cv", "manual"))]]
        if isinstance(exc, CuotaAgotada):
            botones += [
                [("🔄 Seguir intentando", cb("cv", "reintentar"))],
                [("🔑 Cambiar API key", cb("cv", "clave"))],
                [("🔔 Avísame cuando se restablezca la cuota", cb("cv", "avisar"))],
            ]
        elif isinstance(exc, ClaveInvalida):
            botones += [[("🔑 Cambiar API key", cb("cv", "clave"))]]
        else:
            botones += [[("🔄 Seguir intentando", cb("cv", "reintentar"))]]
        intentos = (
            ""
            if isinstance(exc, (CuotaAgotada, ClaveInvalida))
            else f" tras {self.INTENTOS_CV} intentos"
        )
        await self._enviar(
            usuario,
            f"⚠️ No pude leer tu hoja de vida con la IA{intentos}.\n\n"
            f"{self._causa_fallo_cv(exc)}\n\n¿Qué prefieres hacer?",
            botones,
        )

    async def _esperar_cuota_cv(self, usuario_id: int, contenido: bytes) -> None:
        """Prueba cada 30 min (hasta 24 h) y retoma solo cuando la IA vuelve a responder."""
        for _ in range(self.AVISOS_CUOTA_CV):
            await self.dormir(self.ESPERA_CUOTA_CV_S)
            usuario = self.n.usuarios.por_id(usuario_id)
            # Si eligió otra cosa (a mano, otra clave), el aviso queda cancelado
            if usuario is None or (self._esperando(usuario) or {}).get("tipo") != "cuota_cv":
                return
            if await self._leer_cv(usuario, contenido, permitir=False, silencioso=True):
                return
        usuario = self.n.usuarios.por_id(usuario_id)
        if usuario is not None and (self._esperando(usuario) or {}).get("tipo") == "cuota_cv":
            self._esperar(usuario, None)
            await self._enviar(
                usuario,
                "La cuota de Gemini sigue sin restablecerse. Cuando quieras, envía tu CV de nuevo "
                "o usa /perfil.",
                [[("✍️ Llenarla a mano", cb("cv", "manual"))]],
            )

    async def _reintentar_cv(
        self, usuario_id: int, contenido: bytes, permitir: bool, reintento: int, espera: float
    ) -> None:
        await self.dormir(espera)
        usuario = self.n.usuarios.por_id(usuario_id)
        # Si mientras tanto eligió llenarlo a mano o ya tiene perfil, no se hace nada
        if usuario is None or (self._esperando(usuario) or {}).get("tipo") == "manual":
            return
        if usuario.estado == EstadoUsuario.ALTA and usuario.paso_alta != "cv":
            return
        await self._leer_cv(usuario, contenido, permitir=permitir, reintento=reintento)

    # Perfil sin IA: unas preguntas de texto
    PREGUNTAS_MANUAL = (
        ("nombre", "¿Cuál es tu nombre completo?"),
        ("programa", "¿Qué estudias o estudiaste? (programa y nivel, ej.: Tecnólogo en ADSO)"),
        ("institucion", "¿En qué institución?"),
        (
            "habilidades",
            "Escribe tus habilidades técnicas separadas por coma (ej.: Python, SQL, Excel)",
        ),
        ("ciudad", "¿En qué ciudad vives?"),
        ("correo", "¿Cuál es tu correo electrónico?"),
        ("telefono", "¿Cuál es tu número de celular?"),
    )

    async def _perfil_manual(self, usuario: Usuario, indice: int, respuesta: str | None = None):
        estado = self._esperando(usuario) or {"tipo": "manual", "indice": 0, "datos": {}}
        if respuesta is not None:
            clave, _ = self.PREGUNTAS_MANUAL[estado["indice"]]
            estado["datos"][clave] = respuesta.strip()
            indice = estado["indice"] + 1
        if indice < len(self.PREGUNTAS_MANUAL):
            estado.update({"tipo": "manual", "indice": indice})
            self._esperar(usuario, estado)
            await self._enviar(usuario, self.PREGUNTAS_MANUAL[indice][1])
            return
        d = estado["datos"]
        perfil = PerfilExtraido(
            es_cv=True,
            nombre=d.get("nombre"),
            ciudad=d.get("ciudad"),
            formacion=[
                Formacion(institucion=d.get("institucion", ""), programa=d.get("programa", ""))
            ],
            habilidades_tecnicas=[
                h.strip() for h in d.get("habilidades", "").split(",") if h.strip()
            ],
        )
        self.n.guardar_perfil(usuario.id, perfil)
        datos = self.n.datos_usuario(usuario.id)
        locales = {c: d.get(c) for c in ("correo", "telefono")}
        self.n.guardar_cuestionario(usuario.id, derivar_del_cv(perfil, locales, datos.cuestionario))
        self._esperar(usuario, None)
        await self._ir_a(usuario, "resumen")

    def _texto_seccion(self, perfil: PerfilExtraido, seccion: str) -> str:
        match seccion:
            case "formacion":
                items = [
                    f"{f.programa} — {f.institucion}" + (f" ({f.estado})" if f.estado else "")
                    for f in perfil.formacion
                ]
            case "experiencia":
                items = [f"{x.cargo} — {x.empresa}" for x in perfil.experiencia]
            case "proyectos":
                items = [
                    p.nombre + (f": {', '.join(p.tecnologias)}" if p.tecnologias else "")
                    for p in perfil.proyectos
                ]
            case "habilidades":
                items = (
                    [", ".join(perfil.habilidades_tecnicas)] if perfil.habilidades_tecnicas else []
                )
            case _:
                items = [f"{i.idioma} ({i.nivel})" if i.nivel else i.idioma for i in perfil.idiomas]
        return "\n".join(f"• {t.e(i)}" for i in items) or "<i>(vacío)</i>"

    async def _mostrar_seccion(self, usuario: Usuario, seccion: str) -> None:
        datos = self.n.datos_usuario(usuario.id)
        if datos is None:
            await self._ir_a(usuario, "cv")
            return
        await self._enviar(
            usuario,
            f"<b>Editar · {NOMBRE_SECCION[seccion]}</b>\n"
            + self._texto_seccion(datos.perfil, seccion),
            [
                [
                    ("✅ Correcto", cb("seccion", seccion, "ok")),
                    ("✏️ Corregir", cb("seccion", seccion, "corregir")),
                ]
            ],
        )

    def _aplicar_correccion(self, perfil: PerfilExtraido, seccion: str, texto: str) -> None:
        lineas = [x.strip(" •-") for x in texto.splitlines() if x.strip(" •-")]
        if seccion == "habilidades":
            perfil.habilidades_tecnicas = [
                h.strip() for h in texto.replace("\n", ",").split(",") if h.strip()
            ]
        elif seccion == "idiomas":
            perfil.idiomas = []
            for parte in texto.replace("\n", ",").split(","):
                palabras = parte.split()
                if palabras:
                    nivel = palabras[-1] if len(palabras) > 1 else None
                    idioma = " ".join(palabras[:-1]) if nivel else palabras[0]
                    perfil.idiomas.append(Idioma(idioma=idioma, nivel=nivel))
        elif seccion == "formacion":
            perfil.formacion = [
                Formacion(programa=p[0].strip(), institucion=(p[1].strip() if len(p) > 1 else ""))
                for p in (
                    linea.split("—") if "—" in linea else linea.split(" - ") for linea in lineas
                )
            ]
        elif seccion == "experiencia":
            from buscador_vacantes.asistente.cv_lectura import Experiencia

            perfil.experiencia = [
                Experiencia(cargo=p[0].strip(), empresa=(p[1].strip() if len(p) > 1 else ""))
                for p in (
                    linea.split("—") if "—" in linea else linea.split(" - ") for linea in lineas
                )
            ]
        elif seccion == "proyectos":
            from buscador_vacantes.asistente.cv_lectura import Proyecto

            perfil.proyectos = [Proyecto(nombre=linea) for linea in lineas]

    async def _mostrar_resumen(self, usuario: Usuario) -> None:
        """Un solo mensaje con todo lo que se sacó del CV: si está bien, no se pregunta nada."""
        datos = self.n.datos_usuario(usuario.id)
        if datos is None:
            await self._ir_a(usuario, "cv")
            return
        c, p = datos.cuestionario, datos.perfil
        contacto = [
            f"{etiqueta}: {t.e(c.get(campo) or valor or '—')}"
            for etiqueta, campo, valor in (
                ("Nombre", "nombre", p.nombre),
                ("Ciudad", "ciudad", p.ciudad),
                ("Correo", "correo", None),
                ("Celular", "telefono", None),
            )
        ]
        partes = ["<b>Paso 4 de 5 · Revisa tu información</b>", "\n".join(contacto)]
        for seccion in SECCIONES:
            partes.append(f"<b>{NOMBRE_SECCION[seccion]}</b>\n{self._texto_seccion(p, seccion)}")
        enfoque = p.enfoque
        partes.append(
            "<b>Enfoque</b>\n"
            f"• Roles: {t.e(', '.join(enfoque.roles) or '—')}\n"
            f"• Tecnologías a destacar: {t.e(', '.join(enfoque.tecnologias_destacar) or '—')}"
        )
        partes.append(
            "Lo que tu CV no dice (aspiración salarial, disponibilidad…) te lo preguntaré una "
            "sola vez, cuando un formulario lo pida."
        )
        botones = [
            [
                ("✅ Información correcta", cb("resumen", "ok")),
                ("✏️ Editar", cb("resumen", "editar")),
            ]
        ]
        await self._enviar(usuario, "\n\n".join(partes), botones)

    async def _mostrar_enfoque(self, usuario: Usuario) -> None:
        datos = self.n.datos_usuario(usuario.id)
        enfoque = datos.perfil.enfoque if datos else Enfoque()
        await self._enviar(
            usuario,
            t.PEDIR_ENFOQUE.format(
                roles=t.e(", ".join(enfoque.roles) or "—"),
                tecnologias=t.e(", ".join(enfoque.tecnologias_destacar) or "—"),
                objetivo=t.e(enfoque.objetivo or "—"),
            ),
            [[("✅ Correcto", cb("enfoque", "ok")), ("✏️ Cambiar", cb("enfoque", "cambiar"))]],
        )

    def _pregunta_y_opciones(self, usuario: Usuario, item) -> tuple[str, tuple[str, ...]]:
        """La modalidad se pregunta según la ciudad donde vive: lo presencial es en esa ciudad."""
        if item.clave != "modalidades":
            return item.pregunta, item.opciones
        datos = self.n.datos_usuario(usuario.id)
        ciudad = ""
        if datos:
            ciudad = (datos.cuestionario.get("ciudad") or datos.perfil.ciudad or "").strip()
        if not ciudad:
            return item.pregunta, item.opciones
        return (
            f"Vives en {ciudad}. ¿Qué modalidades aceptas?",
            (f"Presencial en {ciudad}", "Híbrido y remoto", "Cualquiera"),
        )

    def _faltantes(self, usuario: Usuario) -> list[int]:
        """Índices del cuestionario que el CV no respondió ni el usuario contestó todavía."""
        datos = self.n.datos_usuario(usuario.id)
        cuestionario = datos.cuestionario if datos else {}
        fila = self.n.base.cx.execute(
            "SELECT actualizar_cv_portal FROM usuarios WHERE id = ?", (usuario.id,)
        ).fetchone()
        faltan = []
        for indice, item in enumerate(t.CUESTIONARIO):
            if item.clave == "actualizar_cv_portal":
                if fila["actualizar_cv_portal"] is None:
                    faltan.append(indice)
            elif not cuestionario.get(item.clave) and item.clave not in cuestionario.get(
                "_omitidos", ""
            ):
                faltan.append(indice)
        return faltan

    def _guardar_respuesta_cuestionario(self, usuario: Usuario, indice: int, valor: str) -> None:
        item = t.CUESTIONARIO[indice]
        datos = self.n.datos_usuario(usuario.id)
        cuestionario = datos.cuestionario if datos else {}
        if item.clave == "actualizar_cv_portal":
            with self.n.base.transaccion() as cx:
                cx.execute(
                    "UPDATE usuarios SET actualizar_cv_portal = ? WHERE id = ?",
                    (1 if valor == "Sí" else 0, usuario.id),
                )
        if valor:
            cuestionario[item.clave] = valor
        elif item.opcional:  # omitida: no se vuelve a preguntar en el alta
            cuestionario.pop(item.clave, None)  # al corregir, omitir borra la respuesta anterior
            cuestionario["_omitidos"] = cuestionario.get("_omitidos", "") + f" {item.clave}"
        cuestionario.pop(f"sugerido_{item.clave}", None)
        self.n.guardar_cuestionario(usuario.id, cuestionario)

    # --- tarjeta de preguntas rápidas ---------------------------------------------------

    def _preguntas(self, usuario: Usuario) -> pt.Preguntas | None:
        return pt.Preguntas.de_texto(self.n.base.kv_obtener(f"preguntas:{usuario.id}"))

    def _guardar_preguntas(self, usuario: Usuario, estado: pt.Preguntas | None) -> None:
        self.n.base.kv_guardar(f"preguntas:{usuario.id}", estado.a_texto() if estado else "")

    async def _iniciar_preguntas(self, usuario: Usuario, indices: list[int]) -> None:
        """Abre una tarjeta nueva con el bloque de preguntas."""
        estado = pt.Preguntas(indices=indices, actual=indices[0])
        self._guardar_preguntas(usuario, estado)
        self._esperar(usuario, {"tipo": "cuestionario"})
        await self._pintar_preguntas(usuario, estado)

    async def _reanudar_preguntas(self, usuario: Usuario, indices: list[int], desde: int) -> None:
        """Repinta la tarjeta guardada según su fase; sin estado, abre el bloque."""
        estado = self._preguntas(usuario)
        if estado is not None:
            self._esperar(usuario, {"tipo": "cuestionario"})
            await self._pintar_preguntas(usuario, estado)
            return
        pendientes = [i for i in indices if i >= desde]
        if not pendientes:
            await self._ir_a(usuario, "navegador")
            return
        await self._iniciar_preguntas(usuario, pendientes)

    def _vista_preguntas(
        self, usuario: Usuario, estado: pt.Preguntas
    ) -> tuple[str, Botones | None]:
        datos = self.n.datos_usuario(usuario.id)
        respuestas = datos.cuestionario if datos else {}
        if estado.fase == pt.RESUMEN:
            return pt.texto_resumen(estado, respuestas), pt.botones_resumen(cb)
        if estado.fase == pt.LISTA:
            return pt.texto_lista(), pt.botones_lista(estado, cb)
        item = t.CUESTIONARIO[estado.actual]
        pregunta, opciones = self._pregunta_y_opciones(usuario, item)
        if estado.fase == pt.OTRO:
            return pt.texto_otro(estado, pregunta), pt.botones_otro(cb)
        sugerido = respuestas.get(f"sugerido_{item.clave}")
        if item.clave == "ciudad" and datos and datos.perfil.ciudad:
            sugerido = datos.perfil.ciudad
        botones = pt.botones_pregunta(
            estado,
            cb,
            opciones=opciones,
            por_fila=item.por_fila,
            otro=item.otro,
            sugerido=sugerido,
            opcional=item.opcional,
        )
        return pt.texto_pregunta(estado, pregunta), botones or None

    async def _pintar_preguntas(self, usuario: Usuario, estado: pt.Preguntas) -> None:
        """Edita la tarjeta; si el mensaje ya no existe envía una nueva con el mismo estado."""
        texto, botones = self._vista_preguntas(usuario, estado)
        if estado.mensaje_id:
            try:
                await self.s.editar(usuario.telegram_id, estado.mensaje_id, texto, botones)
                return
            except Exception:  # noqa: BLE001 - mensaje borrado o vencido: se envía uno nuevo
                log.info("No se pudo editar la tarjeta de preguntas de %s", usuario.id)
        estado.mensaje_id = await self._enviar(usuario, texto, botones)
        self._guardar_preguntas(usuario, estado)

    async def _borrar_texto_usuario(self, usuario: Usuario, mensaje_id: int | None) -> None:
        if mensaje_id is None:
            return
        try:
            await self.s.borrar(usuario.telegram_id, mensaje_id)
        except Exception:  # noqa: BLE001 - mejor esfuerzo: la respuesta ya quedó guardada
            log.info("No se pudo borrar la respuesta escrita de %s", usuario.id)

    async def _registrar_respuesta(
        self, usuario: Usuario, estado: pt.Preguntas, valor: str, mensaje_id: int | None = None
    ) -> None:
        """Guarda la respuesta, borra el texto escrito y avanza (siguiente pregunta o resumen)."""
        self._guardar_respuesta_cuestionario(usuario, estado.actual, valor)
        await self._borrar_texto_usuario(usuario, mensaje_id)
        estado.aviso = ""
        siguiente = None if estado.editando else estado.siguiente()
        if siguiente is None:
            estado.fase, estado.editando = pt.RESUMEN, False
        else:
            estado.actual, estado.fase = siguiente, pt.PREGUNTANDO
        self._guardar_preguntas(usuario, estado)
        await self._pintar_preguntas(usuario, estado)

    async def _texto_cuestionario(
        self, usuario: Usuario, texto: str, mensaje_id: int | None
    ) -> None:
        estado = self._preguntas(usuario)
        valor = texto.strip()
        if estado is None:  # sin tarjeta no hay a qué responder
            self._esperar(usuario, None)
            await self._borrar_texto_usuario(usuario, mensaje_id)
            return
        item = t.CUESTIONARIO[estado.actual]
        if valor and estado.fase == pt.PREGUNTANDO and not item.opciones:
            await self._registrar_respuesta(usuario, estado, valor, mensaje_id)
        elif valor and estado.fase == pt.OTRO:
            numero = re.sub(r"[\s$.,]", "", valor)
            if numero.isdigit():
                await self._registrar_respuesta(usuario, estado, numero, mensaje_id)
                return
            estado.aviso = pt.AVISO_NUMERO
            self._guardar_preguntas(usuario, estado)
            await self._borrar_texto_usuario(usuario, mensaje_id)
            await self._pintar_preguntas(usuario, estado)
        else:  # la tarjeta no espera texto: se borra sin guardarse
            await self._borrar_texto_usuario(usuario, mensaje_id)

    async def _toque_cuestionario(self, usuario: Usuario, args: list[str]) -> None:
        estado = self._preguntas(usuario)
        if estado is None:
            return
        accion = args[0]
        fase = estado.fase
        if accion == "ok" and fase == pt.RESUMEN:
            await self._confirmar_preguntas(usuario, estado)
            return
        if accion == "editar" and fase == pt.RESUMEN:
            estado.fase = pt.LISTA
        elif accion == "campo" and fase == pt.LISTA and int(args[1]) in estado.indices:
            estado.actual, estado.fase, estado.editando = int(args[1]), pt.PREGUNTANDO, True
            estado.aviso = ""
        elif accion == "volver" and fase == pt.OTRO:
            estado.fase, estado.aviso = pt.PREGUNTANDO, ""
        elif accion == "volver" and (
            fase == pt.LISTA or (fase == pt.PREGUNTANDO and estado.editando)
        ):
            estado.fase, estado.editando, estado.aviso = pt.RESUMEN, False, ""
        elif accion.isdigit() and fase == pt.PREGUNTANDO and int(accion) == estado.actual:
            await self._elegir_opcion(usuario, estado, args[1])
            return
        # cualquier otro toque es de una tarjeta vieja: no cambia nada y se repinta la vigente
        self._guardar_preguntas(usuario, estado)
        await self._pintar_preguntas(usuario, estado)

    async def _elegir_opcion(self, usuario: Usuario, estado: pt.Preguntas, eleccion: str) -> None:
        item = t.CUESTIONARIO[estado.actual]
        if eleccion == "otro" and item.otro:  # la respuesta llega como texto, dentro de la tarjeta
            estado.fase, estado.aviso = pt.OTRO, ""
            self._guardar_preguntas(usuario, estado)
            await self._pintar_preguntas(usuario, estado)
            return
        datos = self.n.datos_usuario(usuario.id)
        if eleccion == "omitir" and item.opcional:
            valor = ""
        elif eleccion == "sug":
            valor = (
                datos.cuestionario.get(f"sugerido_{item.clave}")
                or (datos.perfil.ciudad if item.clave == "ciudad" else "")
                or ""
            )
        else:
            opciones = item.valores or self._pregunta_y_opciones(usuario, item)[1]
            if not eleccion.isdigit() or int(eleccion) >= len(opciones):
                await self._pintar_preguntas(usuario, estado)
                return
            valor = opciones[int(eleccion)]
        await self._registrar_respuesta(usuario, estado, valor)

    async def _confirmar_preguntas(self, usuario: Usuario, estado: pt.Preguntas) -> None:
        self._guardar_preguntas(usuario, None)
        self._esperar(usuario, None)
        if estado.mensaje_id:
            try:
                await self.s.editar(usuario.telegram_id, estado.mensaje_id, pt.CIERRE, None)
            except Exception:  # noqa: BLE001 - la tarjeta ya no existe: no hay nada que cerrar
                log.info("No se pudo cerrar la tarjeta de preguntas de %s", usuario.id)
        if usuario.estado == EstadoUsuario.ALTA:
            await self._ir_a(usuario, "navegador")

    async def _mostrar_navegador(self, usuario: Usuario) -> None:
        tienda = (
            f" desde {self.config.extension.url_edge}" if self.config.extension.url_edge else ""
        )
        botones: Botones = [[("🔗 Vincular mi navegador", cb("vincular"))]]
        await self._enviar(usuario, t.NAVEGADOR.format(tienda=t.e(tienda)), botones)

    async def _terminar_alta(self, usuario: Usuario) -> None:
        self.n.usuarios.completar_alta(usuario)
        usuario = self.n.usuarios.por_id(usuario.id)
        datos = self.n.datos_usuario(usuario.id)
        if datos:
            ruta = await asyncio.to_thread(self.n.cv_base_de, usuario, datos)
            with self.n.base.transaccion() as cx:
                cx.execute(
                    "UPDATE usuarios SET cv_base_archivo = ? WHERE id = ?", (str(ruta), usuario.id)
                )
        if self._tarjeta(usuario) or self.n.tiene_navegador(usuario.id):
            await self._actualizar_tarjeta(usuario, self._alta_lista)
        if not usuario.vacante_pendiente:  # con vacante pendiente la postulación arranca sola
            enlace = self.n.enlace_grupo
            botones: Botones | None = [[("👥 Ir al grupo", f"url:{enlace}")]] if enlace else None
            await self._enviar(usuario, t.ALTA_LISTA, botones)
        else:
            pendiente = usuario.vacante_pendiente
            self.n.usuarios.fijar_vacante_pendiente(usuario, None)
            await self.procesar_toque(
                self.n.usuarios.por_id(usuario.id), pendiente, en_tarjeta=True
            )

    @staticmethod
    def _alta_lista(tj: Tarjeta) -> None:
        tj.navegador = tj.listo = True

    # --- tarjeta de conexión ----------------------------------------------------------

    def _tarjeta(self, usuario: Usuario) -> Tarjeta | None:
        return Tarjeta.de_texto(self.n.base.kv_obtener(f"tarjeta:{usuario.id}"))

    def _guardar_tarjeta(self, usuario: Usuario, tj: Tarjeta | None) -> None:
        self.n.base.kv_guardar(f"tarjeta:{usuario.id}", tj.a_texto() if tj else "")

    async def _actualizar_tarjeta(self, usuario: Usuario, cambiar: Callable[[Tarjeta], None]):
        """Aplica el cambio al estado de la tarjeta y la vuelve a pintar (la crea si no existe).

        Si hay una postulación en curso con su card, la conexión se pinta como bloque de esa card.
        """
        tj = self._tarjeta(usuario) or Tarjeta()
        if tj.pid is None and (pid := self._pid_en_curso(usuario)) is not None:
            tj = Tarjeta(
                mensaje_id=self._card(pid).mensaje_id, navegador=True, listo=True,
                cuentas=dict(tj.cuentas), pid=pid,
            )  # fmt: skip
        cambiar(tj)
        self._guardar_tarjeta(usuario, tj)
        await self._pintar_tarjeta(usuario, tj)

    async def _pintar_tarjeta(self, usuario: Usuario, tj: Tarjeta) -> None:
        """Con postulación, la tarjeta es el bloque de conexión de su card; si no, un mensaje."""
        if tj.pid is not None:
            await self._pintar_card(usuario, tj.pid, crear=True)
            return
        texto = tarjeta.texto(tj)
        botones = tarjeta.botones(tj, cb)
        if tj.mensaje_id:
            try:
                await self.s.editar(usuario.telegram_id, tj.mensaje_id, texto, botones)
                return
            except Exception:  # noqa: BLE001 - mensaje borrado: se envía uno nuevo
                log.info("No se pudo editar la tarjeta de %s", usuario.id)
        tj.mensaje_id = await self._enviar(usuario, texto, botones)
        self._guardar_tarjeta(usuario, tj)

    # --- card de la postulación -------------------------------------------------------

    def _card(self, pid: int) -> tp.Card | None:
        return tp.Card.de_texto(self.n.base.kv_obtener(f"card:{pid}"))

    def _guardar_card(self, pid: int, card: tp.Card | None) -> None:
        self.n.base.kv_guardar(f"card:{pid}", card.a_texto() if card else "")

    def _mensaje_de(self, pid: int) -> int | None:
        fila = self.n.base.cx.execute(
            "SELECT mensaje_id FROM postulaciones WHERE id = ?", (pid,)
        ).fetchone()
        return fila["mensaje_id"] if fila else None

    def _obtener_card(self, pid: int, *, crear: bool) -> tp.Card | None:
        """La card guardada; si no hay, una nueva sobre el mensaje que la postulación ya tenga
        (así una postulación en curso antes del cambio sigue en su mensaje). Sin mensaje y sin
        ``crear``, no hay card: por ejemplo una postulación automática que no avisa."""
        card = self._card(pid)
        if card is None:
            mensaje = self._mensaje_de(pid)
            if mensaje is None and not crear:
                return None
            card = tp.Card(mensaje_id=mensaje)
        return card

    def _pid_en_curso(self, usuario: Usuario) -> int | None:
        """Postulación en curso del usuario que ya tiene card (la más reciente)."""
        activos = (E.EN_COLA, E.ESPERANDO_NAVEGADOR, E.TOMADA, E.EN_CURSO, E.VERIFICACION,
                   E.ESPERANDO_USUARIO, E.ESPERANDO_SESION)  # fmt: skip
        filas = self.n.base.cx.execute(
            "SELECT id FROM postulaciones WHERE usuario_id = ? AND tipo = 'postular' "
            f"AND estado IN ({', '.join('?' for _ in activos)}) ORDER BY id DESC",
            (usuario.id, *activos),
        ).fetchall()
        return next((f["id"] for f in filas if self._card(f["id"]) is not None), None)

    def _datos_card(self, usuario: Usuario, pid: int, card: tp.Card, cuadro: int = 0) -> tp.Datos:
        fila = self.n.base.cx.execute(
            "SELECT p.plataforma, p.seguimiento, v.titulo, v.empresa, v.url FROM postulaciones p "
            "LEFT JOIN vacantes v ON v.id_corto = p.id_corto WHERE p.id = ?",
            (pid,),
        ).fetchone()
        d = tp.Datos(
            pid=pid, titulo=fila["titulo"], empresa=fila["empresa"],
            plataforma=fila["plataforma"], url=fila["url"], seguimiento=fila["seguimiento"],
            etapa=self._etapas.get(pid, 0), cuadro=cuadro,
        )  # fmt: skip
        tj = self._tarjeta(usuario)
        if tj is not None and tj.pid == pid and card.fase not in (tp.CONFIRMADA, tp.INCIERTA):
            d.conexion = tarjeta.lineas(tj)
            d.botones_conexion = tarjeta.botones(tj, cb) or []
        if card.fase == tp.PREGUNTA and card.pregunta:
            pendiente = next(
                (x for x in self.n.pendientes(usuario.id) if x["id"] == card.pregunta["id"]), None
            )
            if pendiente:
                d.pendiente = {
                    "id": pendiente["id"], "pregunta": pendiente["pregunta"],
                    "opciones": json.loads(pendiente["opciones_json"] or "[]"),
                }  # fmt: skip
        if card.fase in (tp.CONFIRMADA, tp.INCIERTA):
            p = self.n.cola.obtener(pid)
            if p is not None:
                d.resumen, _ = self._datos_resumen(p, confirmada=card.fase == tp.CONFIRMADA)
        return d

    async def _pintar_card(
        self, usuario: Usuario, pid: int, cuadro: int = 0, *, animacion: bool = False,
        crear: bool = False,
    ) -> None:  # fmt: skip
        """Edita la card de la postulación; si su mensaje ya no existe envía una nueva con el
        estado actual (salvo en la animación: un cuadro perdido lo atrapa el siguiente)."""
        card = self._obtener_card(pid, crear=crear)
        if card is None:
            return
        if card.fase == tp.PREGUNTA and self._datos_card(usuario, pid, card).pendiente is None:
            card.fase, card.pregunta = tp.EN_COLA, None  # la pregunta ya se respondió
        d = self._datos_card(usuario, pid, card, cuadro)
        texto, botones = tp.texto(card, d), tp.botones(card, d, cb)
        if card.mensaje_id:
            if animacion:
                await self.s.editar(usuario.telegram_id, card.mensaje_id, texto, botones)
                return
            try:
                await self.s.editar(usuario.telegram_id, card.mensaje_id, texto, botones)
                self._guardar_card(pid, card)
                self._anclar(pid, card.mensaje_id)
                return
            except Exception:  # noqa: BLE001 - mensaje borrado o vencido: se envía uno nuevo
                log.info("No se pudo editar la card de la postulación %s", pid)
        card.mensaje_id = await self._enviar(usuario, texto, botones)
        self._guardar_card(pid, card)
        self._anclar(pid, card.mensaje_id)

    def _anclar(self, pid: int, mensaje_id: int | None) -> None:
        if mensaje_id and mensaje_id != self._mensaje_de(pid):
            with self.n.base.transaccion() as cx:
                cx.execute(
                    "UPDATE postulaciones SET mensaje_id = ? WHERE id = ?", (mensaje_id, pid)
                )

    async def _poner_fase(
        self, usuario: Usuario, pid: int, fase: str, *, motivo: str | None = None,
        pregunta: dict | None = None,
    ) -> None:  # fmt: skip
        """Cambia la fase de la card (la crea si no existe) y la pinta."""
        card = self._obtener_card(pid, crear=True)
        card.fase, card.vista, card.motivo, card.pregunta = fase, tp.PRINCIPAL, motivo, pregunta
        self._guardar_card(pid, card)
        await self._pintar_card(usuario, pid, crear=True)

    async def _cerrar_card(
        self, usuario: Usuario, pid: int, fase: str, *, motivo: str | None = None
    ) -> None:
        """La postulación dejó de avanzar sola: se detiene el progreso, se suelta la conexión
        (su bloque ya no aplica) y la card pasa a la fase final o de espera."""
        await self._detener_progreso(pid)
        tj = self._tarjeta(usuario)
        if tj is not None and tj.pid == pid:
            self._guardar_tarjeta(usuario, None)
        await self._poner_fase(usuario, pid, fase, motivo=motivo)

    # --- toque de ⚡ ----------------------------------------------------------------

    async def procesar_toque(
        self, usuario: Usuario, id_corto: str, *, origen: str = "boton", en_tarjeta: bool = False
    ):
        """Encola la vacante. Devuelve el toque, o None si las postulaciones están en pausa."""
        async with self._candados[usuario.id]:
            if usuario.pausado:
                await self._enviar(
                    usuario, "Tus postulaciones están en pausa. Usa /pausa para reanudarlas."
                )
                return None
            toque = self.n.tocar(usuario, id_corto, origen=origen)
        if toque.camino == Camino.NO_DISPONIBLE:
            await self._enviar(usuario, "Esa vacante ya no está disponible en el asistente.")
            return toque
        pid = toque.postulacion.id
        if toque.camino == Camino.YA_EXISTE:
            if self._card(pid) is not None:  # la card sigue donde estaba: solo se repinta
                await self._pintar_card(usuario, pid)
            else:
                titulo = t.e(toque.vacante.titulo)
                estado = t.ESTADOS.get(toque.postulacion.estado, toque.postulacion.estado)
                await self._enviar(usuario, f"<b>{titulo}</b>\nYa la tienes: {estado}.")
            return toque
        # Un toque produce una sola card: la del alta (si la vacante venía pendiente), la que ya
        # tenía esta postulación (reintento) o una nueva
        card = self._card(pid) or tp.Card(mensaje_id=self._mensaje_de(pid))
        tj = self._tarjeta(usuario) if en_tarjeta else None
        if tj is not None and tj.pid is None:  # la vacante del alta sigue en la tarjeta
            tj.pid = pid
            card.mensaje_id = card.mensaje_id or tj.mensaje_id
            self._guardar_tarjeta(usuario, tj)
        if toque.camino == Camino.AUTOMATICA:
            card.fase, card.motivo = tp.EN_COLA, None
        else:
            card.fase, card.motivo = tp.RESPALDO, toque.motivo
        card.vista, card.pregunta = tp.PRINCIPAL, None
        self._guardar_card(pid, card)
        if toque.camino == Camino.RESPALDO and tj is not None:
            self._guardar_tarjeta(usuario, None)  # el bloque de conexión ya no aplica
        await self._pintar_card(usuario, pid, crear=True)
        if toque.camino == Camino.AUTOMATICA:
            self._en_segundo_plano(self._preparar(usuario, toque))
        else:
            self._en_segundo_plano(self._enviar_paquete(usuario, pid, toque.motivo))
        return toque

    async def al_toque_canal(self, tid: int, id_corto: str) -> RespuestaToque:
        """Botón ⚡ de un mensaje del canal: Telegram dice quién lo tocó y se postula ahí mismo.

        La respuesta es el aviso corto que ve el usuario sobre el canal. Si aún no terminó su
        registro, se le abre el bot con la vacante para que el alta continúe con ella.
        """
        registro = f"https://t.me/{self.config.bot_usuario}?start={PREFIJO_VACANTE}{id_corto}"
        if not self._permitir(tid):
            return RespuestaToque("Vas muy rápido; intenta de nuevo en un minuto.", alerta=True)
        usuario = self.n.usuarios.obtener(tid)
        if (
            usuario is None
            or usuario.estado == EstadoUsuario.ALTA
            or self.n.usuarios.requiere_politica(usuario, self.config.politica.version)
        ):
            return RespuestaToque("", url=registro)
        ahora = self.n.ahora()
        usuario = await self.comprobador.comprobar(usuario, ahora)
        if usuario.estado == EstadoUsuario.SUSPENDIDO:
            return RespuestaToque(t.SUSPENDIDO, alerta=True)
        self.n.usuarios.tocar_actividad(usuario, ahora)
        if usuario.estado == EstadoUsuario.INACTIVO:
            with self.n.base.transaccion() as cx:
                cx.execute(
                    "UPDATE usuarios SET estado = 'activo', motivo_estado = NULL WHERE id = ?",
                    (usuario.id,),
                )
        toque = await self.procesar_toque(usuario, id_corto, origen="canal")
        if toque is None:
            return RespuestaToque(
                "⏸️ Tus postulaciones están en pausa. Reanúdalas con /pausa en el bot.", alerta=True
            )
        titulo = (toque.vacante.titulo or "la vacante") if toque.vacante else "la vacante"
        if toque.camino == Camino.AUTOMATICA:
            return RespuestaToque(
                f"⚡ Postulando a {titulo[:120]}. Te aviso el resultado en el bot."
            )
        if toque.camino == Camino.YA_EXISTE:
            estado = t.ESTADOS.get(toque.postulacion.estado, toque.postulacion.estado)
            return RespuestaToque(f"Ya la tienes: {estado}.", alerta=True)
        if toque.camino == Camino.RESPALDO:
            return RespuestaToque(
                "📋 Esta no la puedo enviar sola: te mandé al bot el paquete para postularte.",
                alerta=True,
            )
        return RespuestaToque("Esa vacante ya no está disponible.", alerta=True)

    async def _preparar(self, usuario: Usuario, toque) -> None:
        try:
            afinidad, _, parcial = await self.n.preparar(
                usuario, toque.vacante, toque.postulacion.id
            )
        except Exception:  # noqa: BLE001 - la extensión lo genera si hace falta
            log.exception("No se pudo preparar la postulación %s", toque.postulacion.id)
            return
        if afinidad:
            texto = f"🎯 Afinidad {afinidad.porcentaje} %"
            if afinidad.faltan:
                texto += f" · te falta: {t.e(', '.join(afinidad.faltan[:5]))}"
            pid = toque.postulacion.id
            card = self._obtener_card(pid, crear=False)
            if card is None:
                await self._enviar(usuario, texto)
                return
            card.afinidad = texto
            self._guardar_card(pid, card)
            await self._pintar_card(usuario, pid)

    async def _enviar_paquete(self, usuario: Usuario, pid: int, motivo: str) -> None:
        p = self.n.cola.obtener(pid)
        vacante = self.n.indice.obtener(p.id_corto) if p and p.id_corto else None
        if vacante is None:
            return
        try:
            paquete = await self.n.armar_paquete(usuario, vacante, pid, motivo)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo armar el paquete %s", pid)
            await self._enviar(usuario, "No pude armar el paquete. Intenta de nuevo más tarde.")
            return
        await self._mostrar_paquete(usuario, pid, paquete)

    async def _mostrar_paquete(self, usuario: Usuario, pid: int, paquete: Paquete) -> None:
        v = paquete.vacante
        cabecera = f"📋 <b>{t.e(v.titulo)}</b> · {t.e(v.empresa)}"
        if paquete.afinidad:
            cabecera += f"\n🎯 Afinidad {paquete.afinidad.porcentaje} %"
            if paquete.afinidad.faltan:
                cabecera += f" · te falta: {t.e(', '.join(paquete.afinidad.faltan[:5]))}"
        if paquete.detalle_parcial:
            cabecera += "\n(No pude leer la vacante completa: la adaptación es parcial.)"
        await self._enviar(usuario, cabecera)
        await self.s.documento(usuario.telegram_id, paquete.cv, "Tu CV adaptado a esta vacante")
        await self._enviar(usuario, "✉️ <b>Mensaje de presentación</b>\n" + t.bloque(paquete.carta))
        lineas = []
        for r in paquete.respuestas:
            valor = t.bloque(r.texto) if not r.falta else "<i>responde tú</i>"
            lineas.append(f"<b>{t.e(r.pregunta.texto)}</b>\n{valor}")
        if lineas:
            await self._enviar(usuario, "💬 <b>Respuestas típicas</b>\n\n" + "\n\n".join(lineas))
        if paquete.contacto:
            await self._enviar(
                usuario,
                "👤 <b>Tus datos</b>\n"
                + "\n".join(f"{k}: {t.bloque(v)}" for k, v in paquete.contacto.items()),
            )
        # El cierre («Ya me postulé», «No me interesa», pegar preguntas) está en la card

    # --- texto libre ------------------------------------------------------------------

    async def al_texto(self, tid: int, texto: str, mensaje_id: int | None = None) -> None:
        usuario = self.n.usuarios.obtener(tid)
        if usuario is None:
            await self.al_iniciar(tid, None, None)
            return
        if not self._permitir(tid):
            return
        esperando = self._esperando(usuario) or {}
        tipo = esperando.get("tipo")
        if tipo == "clave" or (usuario.paso_alta == "clave"):
            await self._recibir_clave(usuario, texto, mensaje_id)
        elif tipo == "manual":
            await self._perfil_manual(usuario, 0, texto)
        elif tipo == "corregir":
            datos = self.n.datos_usuario(usuario.id)
            self._aplicar_correccion(datos.perfil, esperando["seccion"], texto)
            self.n.guardar_perfil(usuario.id, datos.perfil)
            self._esperar(usuario, None)
            await self._mostrar_seccion(usuario, esperando["seccion"])
        elif tipo == "enfoque":
            datos = self.n.datos_usuario(usuario.id)
            datos.perfil.enfoque = Enfoque(
                roles=[r.strip() for r in texto.split(",") if r.strip()][:5],
                tecnologias_destacar=datos.perfil.enfoque.tecnologias_destacar,
                objetivo=datos.perfil.enfoque.objetivo,
            )
            self.n.guardar_perfil(usuario.id, datos.perfil)
            self._esperar(usuario, None)
            await self._mostrar_enfoque(usuario)
        elif tipo == "cuestionario":
            await self._texto_cuestionario(usuario, texto, mensaje_id)
        elif tipo == "pendiente":
            await self._texto_pendiente(usuario, esperando["id"], texto.strip(), mensaje_id)
        elif tipo == "pegar":
            await self._responder_pegadas(usuario, esperando["pid"], texto)
        elif tipo == "editar":
            recordar(self.n.base, usuario.id, esperando["pregunta"], texto.strip(), self.n.ahora())
            self._esperar(usuario, None)
            await self._enviar(usuario, "✅ Guardada; la usaré la próxima vez.")
        elif usuario.estado == EstadoUsuario.ALTA:
            await self._continuar_alta(usuario)
        else:
            await self._enviar(usuario, t.AYUDA)

    async def _responder_pegadas(self, usuario: Usuario, pid: int, texto: str) -> None:
        try:
            preguntas = separar_preguntas(texto)
        except ErrorPegado as exc:
            await self._enviar(usuario, f"❌ {t.e(exc)}")
            return
        datos = self.n.datos_usuario(usuario.id)
        p = self.n.cola.obtener(pid)
        vacante = self.n.indice.obtener(p.id_corto) if p and p.id_corto else None
        clave = self.n.clave_gemini(usuario.id)
        ctx = Contexto(
            self.n.base,
            usuario.id,
            datos,
            self.n.ahora(),
            self.n.cliente_ia(usuario.id) if clave else None,
            clave,
            vacante.resumen if vacante else "",
        )
        self._esperar(usuario, None)
        for pregunta in preguntas:
            r = await resolver(pregunta, ctx)
            if r.falta:
                await self._enviar(
                    usuario,
                    f"<b>{t.e(pregunta.texto)}</b>\n<i>No tengo ese dato: respóndela tú.</i>",
                )
            else:
                await self._enviar(
                    usuario,
                    f"<b>{t.e(pregunta.texto)}</b>\n{t.bloque(r.texto)}\n<i>origen: {r.origen}</i>",
                    [[("✏️ Corregir y recordar", cb("editar", pid))]],
                )
                self.n.base.kv_guardar(f"ultima_pregunta:{usuario.id}", pregunta.texto)

    async def _texto_pendiente(
        self, usuario: Usuario, pendiente_id: int, texto: str, mensaje_id: int | None
    ) -> None:
        """Texto escrito mientras la card hace una pregunta: solo vale si ella espera texto."""
        pendiente = next(
            (p for p in self.n.pendientes(usuario.id) if p["id"] == pendiente_id), None
        )
        if pendiente is None:  # ya se respondió: no se espera nada
            self._esperar(usuario, None)
        if pendiente is None or not texto or json.loads(pendiente["opciones_json"] or "[]"):
            await self._borrar_texto_usuario(usuario, mensaje_id)  # fuera de turno: sin guardarse
            return
        await self._responder_pendiente(usuario, pendiente_id, texto, mensaje_id)

    async def _responder_pendiente(
        self, usuario: Usuario, pendiente_id: int, respuesta: str, mensaje_id: int | None = None
    ) -> None:
        """Guarda la respuesta y la card avanza a la siguiente pregunta o vuelve a la cola."""
        fila = next((p for p in self.n.pendientes(usuario.id) if p["id"] == pendiente_id), None)
        pid = fila["postulacion_id"] if fila else None
        reencolada = self.n.responder_pendiente(usuario.id, pendiente_id, respuesta)
        self._esperar(usuario, None)
        await self._borrar_texto_usuario(usuario, mensaje_id)
        restantes = self.n.pendientes(usuario.id)
        con_card = pid is not None and self._card(pid) is not None
        if con_card and not any(r["postulacion_id"] == pid for r in restantes):
            await self._poner_fase(usuario, pid, tp.EN_COLA)
        if restantes:
            await self._preguntar_pendiente(usuario, restantes[0])
        elif not con_card:  # pregunta sin postulación: no hay card donde decirlo
            if reencolada:
                await self._enviar(usuario, "✅ Gracias, lo recordaré. Sigo con tu postulación.")
            else:
                await self._enviar(usuario, "✅ Gracias, lo recordaré.")

    async def _preguntar_pendiente(self, usuario: Usuario, pendiente: dict) -> None:
        self._esperar(usuario, {"tipo": "pendiente", "id": pendiente["id"]})
        pid = pendiente.get("postulacion_id")
        if pid is None:  # sin postulación no hay card: se pregunta en un mensaje
            opciones = json.loads(pendiente["opciones_json"] or "[]")
            botones = [[(o, cb("pend", pendiente["id"], n))] for n, o in enumerate(opciones[:8])]
            texto = f"❓ Para tu postulación necesito un dato:\n<b>{t.e(pendiente['pregunta'])}</b>"
            if not opciones:
                texto += "\nEscríbeme la respuesta."
            await self._enviar(usuario, texto, botones or None)
            return
        cx = self.n.base.cx
        total, respondidas = cx.execute(
            "SELECT COUNT(*), COUNT(respondida_en) FROM pendientes_usuario "
            "WHERE postulacion_id = ?",
            (pid,),
        ).fetchone()
        avance = {"id": pendiente["id"], "n": respondidas + 1, "total": total}
        await self._poner_fase(usuario, pid, tp.PREGUNTA, pregunta=avance)

    # --- botones ------------------------------------------------------------------------

    async def al_boton(self, tid: int, data: str) -> str | None:
        usuario = self.n.usuarios.obtener(tid)
        if usuario is None or not data.startswith("cb:"):
            return None
        partes = data[3:].split(":")
        accion, args = partes[0], partes[1:]
        ahora = self.n.ahora()
        match accion:
            case "politica":
                if args[0] == "no":
                    self.n.usuarios.borrar(usuario, ahora)
                    await self._enviar(
                        tid,
                        "Entendido. Sin tu autorización no puedo ayudarte; no guardé tus datos.",
                    )
                    return None
                self.n.usuarios.aceptar_politica(usuario, self.config.politica.version, ahora)
                if usuario.estado == EstadoUsuario.ALTA:
                    await self._ir_a(usuario, "clave")
                else:
                    await self._enviar(usuario, "✅ Gracias por aceptar la nueva versión.")
                    if usuario.vacante_pendiente:
                        pendiente = usuario.vacante_pendiente
                        self.n.usuarios.fijar_vacante_pendiente(usuario, None)
                        await self.procesar_toque(usuario, pendiente)
            case "clave":
                if args[0] == "omitir":
                    self._esperar(usuario, None)
                    if usuario.paso_alta == "clave":
                        await self._ir_a(usuario, "cv")
                elif args[0] == "borrar":
                    self.n.guardar_clave_gemini(usuario.id, None)
                    await self._enviar(usuario, "🗑 Clave de Gemini borrada.")
            case "cvopc":
                if args[0] == "cero":
                    await self._enviar(usuario, t.CV_DESDE_CERO)
                else:
                    await self._enviar(usuario, t.CV_ADJUNTAR.format(max_mb=self.config.cv.max_mb))
            case "cv":
                ruta = Path(
                    self.n.base.cx.execute(
                        "SELECT cv_archivo FROM usuarios WHERE id = ?", (usuario.id,)
                    ).fetchone()[0]
                )
                if args[0] == "escaneado":
                    await self._leer_cv(usuario, ruta.read_bytes(), permitir=True)
                elif args[0] == "reintentar":
                    await self._leer_cv(usuario, ruta.read_bytes(), permitir=False)
                elif args[0] == "clave":
                    self._esperar(usuario, {"tipo": "clave", "retomar_cv": True})
                    await self._enviar(usuario, t.PEDIR_CLAVE)
                elif args[0] == "avisar":
                    self._esperar(usuario, {"tipo": "cuota_cv"})
                    await self._enviar(
                        usuario,
                        "🔔 Listo. Reviso cada 30 minutos y, apenas Gemini responda, leo tu hoja "
                        "de vida y te aviso. Si prefieres, puedes llenarla a mano cuando quieras.",
                        [[("✍️ Llenarla a mano", cb("cv", "manual"))]],
                    )
                    self._en_segundo_plano(self._esperar_cuota_cv(usuario.id, ruta.read_bytes()))
                else:
                    await self._perfil_manual(usuario, 0)
            case "seccion":
                seccion, decision = args
                if decision == "corregir":
                    self._esperar(usuario, {"tipo": "corregir", "seccion": seccion})
                    ayuda = (
                        "separadas por coma"
                        if seccion in ("habilidades", "idiomas")
                        else "una por línea, como «Cargo — Empresa» o «Programa — Institución»"
                    )
                    await self._enviar(
                        usuario,
                        f"Escríbeme tu {NOMBRE_SECCION[seccion].lower()} correcta ({ayuda}).",
                    )
                    return None
                siguiente = SECCIONES.index(seccion) + 1
                destino = (
                    f"revision:{SECCIONES[siguiente]}" if siguiente < len(SECCIONES) else "enfoque"
                )
                if usuario.estado == EstadoUsuario.ALTA:
                    await self._ir_a(usuario, destino)
                else:
                    await self._enviar(usuario, "✅ Guardado.")
            case "enfoque":
                if args[0] == "cambiar":
                    self._esperar(usuario, {"tipo": "enfoque"})
                    await self._enviar(
                        usuario,
                        "Escribe los roles que buscas separados por coma "
                        "(ej.: Desarrollo backend, Soporte TI).",
                    )
                elif usuario.estado == EstadoUsuario.ALTA:
                    await self._ir_a(usuario, "cuestionario:0")
            case "cuest":
                await self._toque_cuestionario(usuario, args)
            case "resumen":
                if args[0] == "ok":
                    await self._enviar(
                        usuario,
                        "Ahora unas preguntas rápidas que suelen pedir los formularios de las "
                        "vacantes y que tu CV no responde. Casi todas son con botones.",
                    )
                    await self._ir_a(usuario, "faltantes:0")
                else:
                    await self._ir_a(usuario, f"revision:{SECCIONES[0]}")
            case "vincular":
                await self._vincular(usuario)
            case "perfil":
                self._esperar(usuario, {"tipo": "cv"})
                await self._enviar(usuario, "Envíame tu nueva hoja de vida en PDF.")
            case "alta":
                await self._terminar_alta(usuario)
            case "pend":
                pendiente = next(
                    (p for p in self.n.pendientes(usuario.id) if p["id"] == int(args[0])), None
                )
                if pendiente:
                    opciones = json.loads(pendiente["opciones_json"] or "[]")
                    await self._responder_pendiente(
                        usuario, pendiente["id"], opciones[int(args[1])]
                    )
            case "pegar":
                self._esperar(usuario, {"tipo": "pegar", "pid": int(args[0])})
                await self._enviar(
                    usuario,
                    "Pega aquí las preguntas que te muestra el portal "
                    "(una por línea; las opciones con guion debajo).",
                )
            case "editar":
                pregunta = self.n.base.kv_obtener(f"ultima_pregunta:{usuario.id}")
                if pregunta:
                    self._esperar(usuario, {"tipo": "editar", "pregunta": pregunta})
                    await self._enviar(
                        usuario, f"Escribe tu respuesta para:\n<b>{t.e(pregunta)}</b>"
                    )
            case "cerrar":  # «Cerrar» de un mensaje efímero: borra de una vez todo el grupo
                filas = self.n.base.cx.execute(
                    "SELECT * FROM mensajes_efimeros WHERE usuario_id = ? AND clave = ?",
                    (usuario.id, ":".join(args)),
                ).fetchall()
                await self._borrar_filas(filas)
            case "res":
                return await self._ver_resumen(usuario, int(args[0]), args[1])
            case "rei":
                p = self.n.cola.obtener(int(args[0]))
                if p is None or p.usuario_id != usuario.id or not p.id_corto:
                    return None
                toque = await self.procesar_toque(usuario, p.id_corto)
                if toque is not None and toque.camino == Camino.AUTOMATICA:
                    return "🔁 Reintentando"
                return None
            case "seg":
                pid, seguimiento = int(args[0]), args[1]
                with self.n.base.transaccion() as cx:
                    hechas = cx.execute(
                        "UPDATE postulaciones SET seguimiento = ? WHERE id = ? AND usuario_id = ?",
                        (seguimiento, pid, usuario.id),
                    ).rowcount
                if hechas and self._card(pid) is not None:  # la card marca ✓ la opción elegida
                    await self._pintar_card(usuario, pid)
                return "Anotado ✅"
            case "guia":  # aún no existe: se avisa en un mensaje aparte que se borra solo
                p = self.n.cola.obtener(int(args[0]))
                if p is None or p.usuario_id != usuario.id:
                    return None
                clave = f"guia:{p.id}"
                async with self._candados[usuario.id]:
                    if self._vigente(usuario, clave, ahora) is not None:
                        return "👆 Ya te lo avisé arriba"
                    await self._enviar_efimero(usuario, [MENSAJE_GUIA_PROXIMAMENTE], clave)
            case "cuenta":
                plataforma, decision = args
                if decision == "si":
                    self.n.cuentas.confirmar(usuario.id, plataforma, ahora)
                    await self._actualizar_tarjeta(
                        usuario, lambda tj: tj.poner_cuenta(plataforma, tarjeta.CONFIRMADA)
                    )
                elif decision == "nueva":
                    # No se guarda el correo ajeno: se olvida la asociación y en el próximo
                    # latido se pide confirmar la cuenta abierta, mostrando su correo completo
                    self.n.cuentas.olvidar(usuario.id, plataforma)
                    await self._actualizar_tarjeta(
                        usuario, lambda tj: tj.poner_cuenta(plataforma, tarjeta.REVISANDO)
                    )
                else:
                    self.n.cuentas.olvidar(usuario.id, plataforma)
                    await self._actualizar_tarjeta(
                        usuario, lambda tj: tj.poner_cuenta(plataforma, tarjeta.PENDIENTE)
                    )
            case "nav":
                vinculos.revocar(self.n.base, usuario.id, int(args[0]))
                return "Navegador revocado"
            case "borrarme":
                self.n.usuarios.borrar(usuario, ahora)
                await self._enviar(
                    tid, "🗑 Borré todos tus datos. Si quieres volver, escribe /start."
                )
            case "pausa":
                nuevo = 0 if usuario.pausado else 1
                with self.n.base.transaccion() as cx:
                    cx.execute("UPDATE usuarios SET pausado = ? WHERE id = ?", (nuevo, usuario.id))
                return "Postulaciones en pausa" if nuevo else "Postulaciones reanudadas"
        return None

    async def _avisar_ya_vinculado(self, usuario: Usuario) -> bool:
        """Si el usuario ya tiene un navegador vinculado, lo avisa y evita generar otro código."""
        navegadores = vinculos.navegadores_de(self.n.base, usuario.id)
        if not navegadores:
            return False
        lineas = []
        for nav in navegadores:
            ultimo = (
                nav.ultimo_latido.astimezone().strftime("%d/%m %H:%M") if nav.ultimo_latido else "—"
            )
            lineas.append(f"• {t.e(nav.nombre or 'Navegador')} · último uso {ultimo}")
        await self._enviar(usuario, t.YA_VINCULADO.format(navegadores="\n".join(lineas)))
        return True

    async def _vincular(self, usuario: Usuario) -> None:
        if await self._avisar_ya_vinculado(usuario):
            return
        url_publica = self.config.api.url_publica
        if not url_publica:
            await self._enviar(
                usuario, "La vinculación aún no está disponible. Avisé al administrador."
            )
            return
        codigo = vinculos.crear_codigo(self.n.base, usuario.id, self.n.ahora())
        await self._enviar(
            usuario,
            "Abre este enlace <b>en el navegador donde instalaste la extensión</b>. "
            f"Si no se vincula solo, escribe en la extensión el código "
            f"<code>{vinculos.mostrar_codigo(codigo)}</code> (vence en 10 minutos).",
            [[("🔗 Vincular mi navegador", f"url:{url_publica}/api/v1/vincular/{codigo}")]],
        )

    # --- comandos ------------------------------------------------------------------

    async def al_comando(self, tid: int, comando: str, args: list[str]) -> None:
        usuario = self.n.usuarios.obtener(tid)
        if usuario is None:
            await self.al_iniciar(tid, None, None)
            return
        if not self._permitir(tid):
            return
        if usuario.estado == EstadoUsuario.SUSPENDIDO:
            await self._enviar(usuario, t.SUSPENDIDO)
            return
        if usuario.estado == EstadoUsuario.ALTA and comando not in ("borrarme", "ayuda"):
            await self._continuar_alta(usuario)
            return
        self.n.usuarios.tocar_actividad(usuario, self.n.ahora())
        dueno = self.es_dueno(tid)
        manejador = {
            "ayuda": self._c_ayuda,
            "help": self._c_ayuda,
            "estado": self._c_estado,
            "historial": self._c_historial,
            "detalle": self._c_detalle,
            "perfil": self._c_perfil,
            "cuestionario": self._c_cuestionario,
            "cv": self._c_cv,
            "clave": self._c_clave,
            "vincular": self._c_vincular,
            "navegadores": self._c_navegadores,
            "automatico": self._c_automatico,
            "pausa": self._c_pausa,
            "borrarme": self._c_borrarme,
        }.get(comando)
        if dueno:
            manejador = manejador or {
                "usuarios": self._a_usuarios,
                "suspender": self._a_suspender,
                "reactivar": self._a_reactivar,
                "stats": self._a_stats,
                "plataformas": self._a_plataformas,
            }.get(comando)
        if manejador is None:
            await self._enviar(
                usuario, "No conozco ese comando.\n\n" + t.AYUDA + (t.AYUDA_ADMIN if dueno else "")
            )
            return
        await manejador(usuario, args)

    async def _c_ayuda(self, usuario: Usuario, args) -> None:
        await self._enviar(
            usuario, t.AYUDA + (t.AYUDA_ADMIN if self.es_dueno(usuario.telegram_id) else "")
        )

    async def _c_estado(self, usuario: Usuario, args) -> None:
        ahora = self.n.ahora()
        caido = timedelta(minutes=self.config.extension.navegador_caido_min)
        lineas = ["<b>Tu estado</b>"]
        navegadores = vinculos.navegadores_de(self.n.base, usuario.id)
        if not navegadores:
            lineas.append("💻 Sin navegador vinculado (usa /vincular)")
        for nav in navegadores:
            en_linea = nav.ultimo_latido and ahora - nav.ultimo_latido <= caido
            lineas.append(
                f"💻 {t.e(nav.nombre or 'Navegador')}: "
                f"{'🟢 en línea' if en_linea else '⚪ desconectado'}"
            )
        for plataforma in self.config.plataformas:
            asociado = self.n.cuentas.asociado(usuario.id, plataforma)
            nombre = t.NOMBRES_PLATAFORMA.get(plataforma, plataforma)
            if asociado:
                correo, estado = asociado
                marca = "✅" if estado == "confirmada" else "❔ por confirmar"
                lineas.append(f"{marca} {nombre}: {t.e(correo)}")
            else:
                lineas.append(f"⚪ {nombre}: sin cuenta detectada")
        hoy = self.n.cola.postulaciones_hoy(usuario.id, ahora)
        lineas.append(f"📨 Hoy: {hoy} de {self.config.topes.usuario_dia} postulaciones")
        if usuario.pausado:
            lineas.append("⏸ Tus postulaciones están en pausa")
        await self._enviar(usuario, "\n".join(lineas))

    def _historial(self, usuario: Usuario) -> list[dict]:
        filas = self.n.base.cx.execute(
            "SELECT p.*, v.titulo, v.empresa, v.url FROM postulaciones p LEFT JOIN vacantes v "
            "ON v.id_corto = p.id_corto WHERE p.usuario_id = ? AND p.tipo = 'postular' "
            "ORDER BY p.creada DESC LIMIT 30",
            (usuario.id,),
        ).fetchall()
        return [dict(f) for f in filas]

    async def _c_historial(self, usuario: Usuario, args) -> None:
        historial = self._historial(usuario)
        if not historial:
            await self._enviar(
                usuario, "Aún no tienes postulaciones. Toca ⚡ Postularme en el grupo."
            )
            return
        lineas = ["<b>Tus postulaciones</b> (usa /detalle N)"]
        for n, p in enumerate(historial, 1):
            fecha = de_texto(p["creada"]).astimezone().strftime("%d/%m")
            seguimiento = f" · {p['seguimiento']}" if p["seguimiento"] else ""
            lineas.append(
                f"{n}. {t.e(p['titulo'] or 'Vacante')} · {fecha} · "
                f"{t.ESTADOS.get(p['estado'], p['estado'])}{seguimiento}"
            )
        await self._enviar(usuario, "\n".join(lineas))

    async def _c_detalle(self, usuario: Usuario, args) -> None:
        historial = self._historial(usuario)
        try:
            p = historial[int(args[0]) - 1]
        except (IndexError, ValueError):
            await self._enviar(usuario, "Usa /detalle N con el número de /historial.")
            return
        lineas = [
            f"<b>{t.e(p['titulo'])}</b> · {t.e(p['empresa'])}",
            t.ESTADOS.get(p["estado"], p["estado"]),
        ]
        if p["afinidad"] is not None:
            lineas.append(f"🎯 Afinidad {p['afinidad']} %")
        lineas.append("\n<b>Pasos</b>")
        for paso in self.n.base.cx.execute(
            "SELECT ts, paso, estado, detalle FROM postulacion_pasos WHERE postulacion_id = ? "
            "ORDER BY id",
            (p["id"],),
        ):
            hora = de_texto(paso["ts"]).astimezone().strftime("%d/%m %H:%M")
            detalle = f": {t.e(paso['detalle'])[:120]}" if paso["detalle"] else ""
            lineas.append(f"• {hora} {t.e(paso['estado'] or paso['paso'])}{detalle}")
        respuestas = self.n.base.cx.execute(
            "SELECT pregunta, respuesta, origen FROM respuestas WHERE postulacion_id = ?",
            (p["id"],),
        ).fetchall()
        if respuestas:
            lineas.append("\n<b>Preguntas y respuestas</b>")
            for r in respuestas:
                lineas.append(
                    f"• {t.e(r['pregunta'])}\n  → {t.e(r['respuesta'])} <i>({r['origen']})</i>"
                )
        await self._enviar(usuario, "\n".join(lineas)[:4000])
        if p["cv_archivo"] and Path(p["cv_archivo"]).is_file():
            await self.s.documento(usuario.telegram_id, Path(p["cv_archivo"]), "CV usado")

    async def _c_perfil(self, usuario: Usuario, args) -> None:
        datos = self.n.datos_usuario(usuario.id)
        if datos is None:
            await self._enviar(usuario, "Aún no tienes perfil.")
            return
        partes = [
            f"<b>{NOMBRE_SECCION[s]}</b>\n{self._texto_seccion(datos.perfil, s)}" for s in SECCIONES
        ]
        botones = [[(f"✏️ {NOMBRE_SECCION[s]}", cb("seccion", s, "corregir"))] for s in SECCIONES]
        botones.append([("📄 Reemplazar CV", cb("perfil", "cv"))])
        await self._enviar(usuario, "\n\n".join(partes), botones)

    async def _c_cuestionario(self, usuario: Usuario, args) -> None:
        await self._iniciar_preguntas(usuario, list(range(len(t.CUESTIONARIO))))

    async def _c_cv(self, usuario: Usuario, args) -> None:
        datos = self.n.datos_usuario(usuario.id)
        if datos is None:
            await self._enviar(usuario, "Aún no tienes perfil.")
            return
        ruta = await asyncio.to_thread(self.n.cv_base_de, usuario, datos)
        await self.s.documento(usuario.telegram_id, ruta, "Tu CV base (apto para ATS)")

    async def _c_clave(self, usuario: Usuario, args) -> None:
        fila = self.n.base.cx.execute(
            "SELECT gemini_ult4, gemini_valida FROM usuarios WHERE id = ?", (usuario.id,)
        ).fetchone()
        estado = (
            f"Tu clave termina en …{t.e(fila['gemini_ult4'])}"
            + (" (inválida)" if fila["gemini_valida"] == 0 else "")
            if fila["gemini_ult4"]
            else "No tienes clave de Gemini."
        )
        self._esperar(usuario, {"tipo": "clave"})
        await self._enviar(
            usuario,
            f"{estado}\nPega una clave nueva para reemplazarla.",
            [[("🗑 Borrar mi clave", cb("clave", "borrar"))]],
        )

    async def _c_vincular(self, usuario: Usuario, args) -> None:
        if await self._avisar_ya_vinculado(usuario):
            return
        await self._mostrar_navegador(usuario)

    async def _c_navegadores(self, usuario: Usuario, args) -> None:
        navegadores = vinculos.navegadores_de(self.n.base, usuario.id)
        if not navegadores:
            await self._enviar(usuario, "No tienes navegadores vinculados. Usa /vincular.")
            return
        botones = []
        lineas = ["<b>Tus navegadores</b>"]
        for nav in navegadores:
            ultimo = (
                nav.ultimo_latido.astimezone().strftime("%d/%m %H:%M") if nav.ultimo_latido else "—"
            )
            lineas.append(f"• {t.e(nav.nombre or 'Navegador')} · último uso {ultimo}")
            botones.append([(f"Revocar {nav.nombre or nav.id}", cb("nav", nav.id))])
        await self._enviar(usuario, "\n".join(lineas), botones)

    async def _c_automatico(self, usuario: Usuario, args) -> None:
        fila = self.n.base.cx.execute(
            "SELECT automatico_umbral FROM usuarios WHERE id = ?", (usuario.id,)
        ).fetchone()
        if args:
            try:
                umbral = max(0, min(100, int(args[0].rstrip("%"))))
            except ValueError:
                await self._enviar(
                    usuario, "Usa /automatico 70 (el porcentaje mínimo de afinidad)."
                )
                return
        elif fila["automatico_umbral"] is not None:
            umbral = None
        else:
            umbral = self.config.automatico_usuario.umbral_defecto
        with self.n.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET automatico_umbral = ? WHERE id = ?", (umbral, usuario.id)
            )
        if umbral is None:
            await self._enviar(usuario, "⏹ Modo automático desactivado.")
        else:
            await self._enviar(
                usuario,
                f"🤖 Modo automático activo: postularé solo a las "
                f"vacantes con afinidad de {umbral} % o más, dentro de tu "
                "tope diario. Desactívalo con /automatico.",
            )

    async def _c_pausa(self, usuario: Usuario, args) -> None:
        texto = await self.al_boton(usuario.telegram_id, cb("pausa"))
        await self._enviar(usuario, f"⏯ {texto}.")

    async def _c_borrarme(self, usuario: Usuario, args) -> None:
        await self._enviar(
            usuario,
            "⚠️ Esto borra <b>todos</b> tus datos: perfil, CV, clave, "
            "navegadores e historial. No se puede deshacer.\n\n"
            "Este chat no se borra: si también quieres limpiarlo, elimínalo desde Telegram.",
            [[("Sí, borrar todo", cb("borrarme"))]],
        )

    # --- administración --------------------------------------------------------------

    async def _a_usuarios(self, usuario: Usuario, args) -> None:
        self.n.usuarios.auditar(usuario.telegram_id, "listar_usuarios", None, self.n.ahora())
        lineas = ["<b>Usuarios</b>"]
        for u in self.n.usuarios.todos():
            actividad = (
                u.ultima_actividad.astimezone().strftime("%d/%m") if u.ultima_actividad else "—"
            )
            lineas.append(f"{u.id}. {t.e(u.nombre or '—')} · {u.estado} · {actividad}")
        await self._enviar(usuario, "\n".join(lineas)[:4000])

    async def _a_suspender(self, usuario: Usuario, args) -> None:
        objetivo = self.n.usuarios.por_id(int(args[0])) if args and args[0].isdigit() else None
        if objetivo is None:
            await self._enviar(usuario, "Usa /suspender ID (de /usuarios).")
            return
        self.n.usuarios.suspender(objetivo, usuario.telegram_id, self.n.ahora())
        await self._enviar(usuario, f"Usuario {objetivo.id} suspendido.")

    async def _a_reactivar(self, usuario: Usuario, args) -> None:
        objetivo = self.n.usuarios.por_id(int(args[0])) if args and args[0].isdigit() else None
        if objetivo is None:
            await self._enviar(usuario, "Usa /reactivar ID (de /usuarios).")
            return
        self.n.usuarios.reactivar(objetivo, usuario.telegram_id, self.n.ahora())
        await self._enviar(usuario, f"Usuario {objetivo.id} reactivado.")

    async def _a_stats(self, usuario: Usuario, args) -> None:
        cx = self.n.base.cx
        desde = a_texto(self.n.ahora() - timedelta(days=1))
        usuarios = cx.execute("SELECT estado, COUNT(*) n FROM usuarios GROUP BY estado").fetchall()
        estados = cx.execute(
            "SELECT estado, COUNT(*) n FROM postulaciones WHERE creada >= ? GROUP BY estado",
            (desde,),
        ).fetchall()
        sin_ia = cx.execute(
            "SELECT SUM(origen != 'ia'), COUNT(*) FROM respuestas r JOIN "
            "postulaciones p ON p.id = r.postulacion_id WHERE p.creada >= ?",
            (desde,),
        ).fetchone()
        banco = cx.execute(
            "SELECT COUNT(*) FROM banco_preguntas WHERE origen = 'ia' AND creada >= ?", (desde,)
        ).fetchone()[0]
        lineas = [
            "<b>Últimas 24 h</b>",
            "Usuarios: " + ", ".join(f"{f['estado']} {f['n']}" for f in usuarios),
            "Postulaciones: " + (", ".join(f"{f['estado']} {f['n']}" for f in estados) or "0"),
        ]
        if sin_ia and sin_ia[1]:
            lineas.append(f"Respuestas sin IA: {round(100 * (sin_ia[0] or 0) / sin_ia[1])} %")
        lineas.append(f"Preguntas nuevas en el banco: {banco}")
        await self._enviar(usuario, "\n".join(lineas))

    async def _a_plataformas(self, usuario: Usuario, args) -> None:
        if len(args) == 2 and args[0] in self.config.plataformas and args[1] in ("on", "off"):
            self.config.plataformas[args[0]].automatica = args[1] == "on"
            self.n.usuarios.auditar(
                usuario.telegram_id, "plataforma", args[0], self.n.ahora(), args[1]
            )
        lineas = ["<b>Plataformas</b> (hasta reiniciar; el valor fijo está en config.yaml)"]
        for nombre, ajustes in self.config.plataformas.items():
            lineas.append(f"• {nombre}: {'automática' if ajustes.automatica else 'solo paquete'}")
        await self._enviar(usuario, "\n".join(lineas))

    # --- avisos del núcleo ------------------------------------------------------------

    async def notificar(self, evento: Evento | dict) -> None:
        try:
            if isinstance(evento, Evento):
                await self._avisar_evento(evento)
            else:
                await self._avisar_dict(evento)
        except Exception:  # noqa: BLE001 - un aviso fallido no debe tumbar la API ni la cola
            log.exception("No se pudo enviar el aviso %s", evento)

    async def _avisar_dict(self, d: dict) -> None:
        usuario = self.n.usuarios.por_id(d["usuario_id"]) if "usuario_id" in d else None
        if usuario is None:
            return
        tipo = d["tipo"]
        nombre = t.NOMBRES_PLATAFORMA.get(d.get("plataforma", ""), d.get("plataforma", ""))
        if tipo == "navegador_vinculado":
            await self._actualizar_tarjeta(usuario, lambda tj: setattr(tj, "navegador", True))
            if usuario.estado == EstadoUsuario.ALTA:  # vincular era lo último del alta
                await self._terminar_alta(usuario)
        elif tipo == "cuenta_por_confirmar":
            await self._actualizar_tarjeta(
                usuario,
                lambda tj: tj.poner_cuenta(d["plataforma"], tarjeta.POR_CONFIRMAR, d["asociado"]),
            )
        elif tipo == "cuenta_distinta":
            await self._actualizar_tarjeta(
                usuario,
                lambda tj: tj.poner_cuenta(
                    d["plataforma"], tarjeta.DISTINTA, d["asociado"], d["encontrado"]
                ),
            )
        elif tipo == "cuenta_sin_correo":
            log.info("No se pudo leer el correo de %s para el usuario %s", nombre, usuario.id)
        elif tipo == "portal_listo":
            await self._actualizar_tarjeta(
                usuario,
                lambda tj: tj.poner_cuenta(d["plataforma"], tarjeta.CONFIRMADA, d.get("asociado")),
            )
        elif tipo == "portal_incompleto":
            await self._actualizar_tarjeta(
                usuario, lambda tj: tj.poner_cuenta(d["plataforma"], tarjeta.COMPLETANDO)
            )
        elif tipo == "verificacion":
            await self._poner_fase(usuario, d["postulacion_id"], tp.VERIFICACION)
        elif tipo == "preguntas_pendientes":
            pendientes = self.n.pendientes(usuario.id)
            if pendientes:
                await self._preguntar_pendiente(usuario, pendientes[0])
        elif tipo == "clave_invalida":
            await self._enviar(
                usuario,
                "⚠️ Tu clave de Gemini ya no funciona. Sigo sin IA; registra una nueva con /clave.",
            )
        elif tipo == "postulando":
            await self._iniciar_progreso(usuario, d["postulacion_id"])
        elif tipo == "paso":
            etapa = progreso.etapa_de_paso(d["paso"])
            pid = d["postulacion_id"]
            if pid not in self._animaciones:
                return
            card = self._card(pid)
            if card is not None and card.fase != tp.PROGRESO:  # p. ej. se resolvió la verificación
                await self._poner_fase(usuario, pid, tp.PROGRESO)
            if etapa is not None and etapa > self._etapas[pid]:
                self._etapas[pid] = etapa
                await self._pintar_progreso(usuario, pid, 0)

    async def _pintar_progreso(self, usuario: Usuario, pid: int, cuadro: int) -> None:
        """Un cuadro del progreso en la card; solo si la card está mostrando el progreso."""
        card = self._card(pid)
        if card is not None and card.fase == tp.PROGRESO:
            await self._pintar_card(usuario, pid, cuadro, animacion=True)

    async def _iniciar_progreso(self, usuario: Usuario, pid: int) -> None:
        """La card marca las etapas y gira mientras la extensión trabaja (se edita, no se envía)."""
        nueva = pid not in self._animaciones
        if nueva:
            self._etapas[pid] = 0
        try:
            card = self._obtener_card(pid, crear=False)
            if card is not None:  # sin card (automática que no avisa) no hay nada que mostrar
                await self._poner_fase(usuario, pid, tp.PROGRESO)
        except Exception:  # noqa: BLE001 - mensaje viejo o borrado: el aviso final lo reenvía
            log.info("No se pudo mostrar el progreso de %s", pid)
        if nueva:
            self._animaciones[pid] = asyncio.create_task(self._animar_progreso(usuario, pid))

    async def _animar_progreso(self, usuario: Usuario, pid: int) -> None:
        for cuadro in range(1, 600):
            await asyncio.sleep(self.intervalo_animacion)
            try:
                await self._pintar_progreso(usuario, pid, cuadro)
            except Exception:  # noqa: BLE001 - un cuadro perdido no importa
                log.debug("Cuadro de progreso perdido en %s", pid)

    async def _detener_progreso(self, pid: int) -> None:
        tarea = self._animaciones.pop(pid, None)
        self._etapas.pop(pid, None)
        if tarea is not None:
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)

    def _datos_resumen(self, p, *, confirmada: bool = True):
        """Datos de una postulación para el resumen: (datos, CV usado o None)."""
        vacante = self.n.indice.obtener(p.id_corto) if p.id_corto else None
        if vacante is None:
            return None, None
        cx = self.n.base.cx
        fila = cx.execute(
            "SELECT p.afinidad, p.cv_archivo, p.terminada_en, v.requisitos_json "
            "FROM postulaciones p LEFT JOIN vacantes v ON v.id_corto = p.id_corto "
            "WHERE p.id = ?",
            (p.id,),
        ).fetchone()
        pasos = cx.execute(
            "SELECT paso, detalle FROM postulacion_pasos WHERE postulacion_id = ? ORDER BY id",
            (p.id,),
        ).fetchall()
        respuestas = cx.execute(
            "SELECT pregunta, respuesta, origen FROM respuestas WHERE postulacion_id = ? "
            "ORDER BY id",
            (p.id,),
        ).fetchall()
        requisitos = None
        if fila["requisitos_json"]:
            requisitos = json.loads(fila["requisitos_json"]).get("requisitos")
        adjunto = next((x["detalle"] for x in reversed(pasos) if x["paso"] == "cv_adjunto"), None)
        datos = resumen_postulacion.DatosResumen(
            vacante=vacante, plataforma=p.plataforma,
            enviada_en=de_texto(fila["terminada_en"]) if fila["terminada_en"] else None,
            afinidad=fila["afinidad"], requisitos=requisitos,
            respuestas=[dict(r) for r in respuestas], pasos=[x["paso"] for x in pasos],
            cv_adjunto=adjunto, confirmada=confirmada,
        )  # fmt: skip
        usado = adjunto or ("cv_subir" in datos.pasos and "cv_verificar_fallo" not in datos.pasos)
        cv = Path(fila["cv_archivo"]) if usado and fila["cv_archivo"] else None
        return datos, cv if cv and cv.is_file() else None

    async def _enviar_resumen(self, usuario: Usuario, p, *, confirmada: bool = True) -> None:
        """La card pasa a «confirmada» (o «incierta»): título, empresa y una cita con el estado,
        con las vistas de respuestas y de qué trata, la oferta y el seguimiento. La hoja de vida
        que recibió el portal sigue yendo como documento aparte."""
        await self._cerrar_card(usuario, p.id, tp.CONFIRMADA if confirmada else tp.INCIERTA)
        _, cv = self._datos_resumen(p, confirmada=confirmada)
        if cv is not None:
            await self.s.documento(usuario.telegram_id, cv, "La hoja de vida que recibió el portal")

    # --- mensajes que se borran solos (botones del resumen) ----------------------------------

    def _espera_lectura(self, textos: list[str]) -> int:
        """Segundos que el mensaje se queda en pantalla: lo que toma leerlo, con tope."""
        c = self.config.mensajes_efimeros
        caracteres = sum(len(re.sub(r"<[^>]+>", "", x)) for x in textos)
        return int(min(c.lectura_max_s, max(c.lectura_min_s, caracteres / c.caracteres_por_s)))

    def _toque_resumen_permitido(self, tid: int) -> bool:
        ahora = self.reloj()
        cola = self._toques_resumen[tid]
        while cola and ahora - cola[0] > 60:
            cola.popleft()
        if len(cola) >= self.config.mensajes_efimeros.max_por_min:
            return False
        cola.append(ahora)
        return True

    def _vigente(self, usuario: Usuario, clave: str, ahora: datetime) -> datetime | None:
        """Cuándo se borra el mensaje de este botón, si todavía está en pantalla."""
        fila = self.n.base.cx.execute(
            "SELECT MAX(borrar_en) AS hasta FROM mensajes_efimeros "
            "WHERE usuario_id = ? AND clave = ? AND borrar_en > ?",
            (usuario.id, clave, a_texto(ahora)),
        ).fetchone()
        return de_texto(fila["hasta"]) if fila and fila["hasta"] else None

    async def _enviar_efimero(self, usuario: Usuario, textos: list[str], clave: str) -> int:
        """Envía los mensajes, anota cuándo borrarlos y programa el borrado."""
        espera = self._espera_lectura(textos)
        aviso = f"<i>🕒 Se borra solo en {espera} s</i>"
        textos = [*textos[:-1], f"{textos[-1]}\n\n{aviso}"]
        borrar_en = a_texto(self.n.ahora() + timedelta(seconds=espera))
        filas: list[int] = []
        for texto in textos:
            mensaje = await self._enviar(usuario, texto, [[("Cerrar", cb("cerrar", clave))]])
            if mensaje is None:
                continue
            with self.n.base.transaccion() as cx:
                fila = cx.execute(
                    "INSERT INTO mensajes_efimeros(usuario_id, chat_id, mensaje_id, clave, "
                    "borrar_en) VALUES (?, ?, ?, ?, ?)",
                    (usuario.id, usuario.telegram_id, mensaje, clave, borrar_en),
                )
                filas.append(fila.lastrowid)
        if filas:
            tarea = asyncio.create_task(self._borrar_luego(filas, espera))
            self._borrados.add(tarea)
            tarea.add_done_callback(self._borrados.discard)
        return espera

    async def _borrar_luego(self, filas: list[int], espera: float) -> None:
        await self.dormir(espera)
        marcas = ", ".join("?" for _ in filas)
        pendientes = self.n.base.cx.execute(
            f"SELECT * FROM mensajes_efimeros WHERE id IN ({marcas})", filas
        ).fetchall()
        await self._borrar_filas(pendientes)

    async def _borrar_filas(self, filas) -> int:
        borrados = 0
        for f in filas:
            try:
                await self.s.borrar(f["chat_id"], f["mensaje_id"])
                borrados += 1
            except Exception:  # noqa: BLE001 - el usuario ya lo borró o es muy viejo
                log.info("No se pudo borrar el mensaje %s", f["mensaje_id"])
            with self.n.base.transaccion() as cx:
                cx.execute("DELETE FROM mensajes_efimeros WHERE id = ?", (f["id"],))
        return borrados

    async def borrar_vencidos(self, ahora: datetime) -> int:
        """Borra lo que ya cumplió su tiempo: cubre los reinicios del servicio."""
        filas = self.n.base.cx.execute(
            "SELECT * FROM mensajes_efimeros WHERE borrar_en <= ?", (a_texto(ahora),)
        ).fetchall()
        return await self._borrar_filas(filas)

    async def _ver_resumen(self, usuario: Usuario, pid: int, parte: str) -> str | None:
        """Responde a «Respuestas» (r), «De qué trata» (d) y «Volver» (v). Con card, son vistas
        de la misma card; sin ella (tarjeta enviada antes del cambio) son mensajes efímeros.
        Devuelve el aviso corto que ve el usuario sobre el botón cuando no se envía nada."""
        p = self.n.cola.obtener(pid)
        if p is None or p.usuario_id != usuario.id or parte not in ("r", "d", "v"):
            return None
        card = self._card(pid)
        if card is not None:
            if card.fase not in (tp.CONFIRMADA, tp.INCIERTA):  # toque viejo: se repinta la vigente
                await self._pintar_card(usuario, pid)
                return None
            if parte != "v" and not self._toque_resumen_permitido(usuario.telegram_id):
                return "Vas muy rápido; intenta de nuevo en un minuto."
            card.vista = {"r": tp.RESPUESTAS, "d": tp.DE_QUE_TRATA, "v": tp.PRINCIPAL}[parte]
            self._guardar_card(pid, card)
            await self._pintar_card(usuario, pid)
            return None
        if parte == "v":
            return None
        clave = f"res:{pid}:{parte}"
        async with self._candados[usuario.id]:  # dos toques seguidos no envían dos veces
            ahora = self.n.ahora()
            hasta = self._vigente(usuario, clave, ahora)
            if hasta is not None:
                faltan = max(1, int((hasta - ahora).total_seconds()))
                return f"👆 Ya lo tienes arriba; se borra en {faltan} s"
            if not self._toque_resumen_permitido(usuario.telegram_id):
                return "Vas muy rápido; intenta de nuevo en un minuto."
            datos, _ = self._datos_resumen(p, confirmada=p.estado != E.INCIERTA)
            if datos is None:
                return None
            if parte == "r":
                textos = resumen_postulacion.respuestas(datos)
            else:
                textos = resumen_postulacion.de_que_trata(datos)
            if textos:
                await self._enviar_efimero(usuario, textos, clave)
        return None

    async def _avisar_evento(self, ev: Evento) -> None:
        usuario = self.n.usuarios.por_id(ev.usuario_id)
        if usuario is None:
            return
        p = self.n.cola.obtener(ev.postulacion_id)
        if p is None:
            return
        if p.tipo != "postular":
            if ev.estado == E.COMPLETADO:
                nombre = t.NOMBRES_PLATAFORMA.get(p.plataforma, p.plataforma)
                await self._enviar(usuario, f"✅ Tu perfil de {nombre} quedó completo.")
            return
        estado = t.ESTADOS.get(ev.estado, ev.estado)
        if ev.tipo == "navegador_desconectado":
            await self._cerrar_card(usuario, p.id, tp.ESPERANDO_NAVEGADOR)
            return
        if ev.tipo == "reencolada":
            return
        if ev.estado == E.ENVIADA:
            # La ficha de éxito de una postulación automática se puede silenciar por portal
            # (engranaje de la extensión); un toque ⚡ siempre avisa, porque el usuario lo espera
            if p.origen == "automatico" and p.plataforma:
                pref = self.n.preferencias.obtener(usuario.id, p.plataforma)
                if not pref.avisar:
                    return
            await self._enviar_resumen(usuario, p)
        elif ev.estado == E.ESPERANDO_SESION:
            await self._cerrar_card(usuario, p.id, tp.SESION)
        elif ev.estado == E.INCIERTA:
            # Igual se le cuenta qué se respondió y con qué hoja de vida, para que pueda revisar
            await self._enviar_resumen(usuario, p, confirmada=False)
        elif ev.estado == E.BLOQUEADA and (ev.detalle or "") in t.BLOQUEOS_PORTAL:
            await self._cerrar_card(usuario, p.id, tp.BLOQUEO, motivo=ev.detalle)
        elif ev.estado in CON_RESPALDO:
            motivo = ev.detalle if ev.tipo == "respaldo" else str(ev.estado)
            await self._cerrar_card(usuario, p.id, tp.RESPALDO, motivo=motivo)
            self._en_segundo_plano(self._enviar_paquete(usuario, p.id, motivo))
            if (
                ev.estado in (E.FORMULARIO_DESCONOCIDO, E.BLOQUEADA)
                and self.config.dueno_telegram_id
            ):
                await self._enviar(
                    self.config.dueno_telegram_id,
                    f"⚠️ Postulación {p.id} ({p.plataforma}): {estado}. Revisa la "
                    "evidencia en data/asistente/postulaciones/.",
                )
        else:
            await self._cerrar_card(usuario, p.id, tp.CERRADA, motivo=str(ev.estado))

    # --- tareas periódicas ----------------------------------------------------------------

    async def recordatorios(self, ahora: datetime) -> int:
        """Una sola vez, a los N días, para los paquetes de respaldo sin seguimiento."""
        limite = a_texto(ahora - timedelta(days=self.config.recordatorio_dias))
        filas = self.n.base.cx.execute(
            "SELECT p.id, p.usuario_id, v.titulo FROM postulaciones p LEFT JOIN vacantes v "
            "ON v.id_corto = p.id_corto WHERE p.estado = 'respaldo' AND p.seguimiento IS NULL "
            "AND p.recordado = 0 AND p.terminada_en < ?",
            (limite,),
        ).fetchall()
        for f in filas:
            usuario = self.n.usuarios.por_id(f["usuario_id"])
            with self.n.base.transaccion() as cx:
                cx.execute("UPDATE postulaciones SET recordado = 1 WHERE id = ?", (f["id"],))
            if usuario:
                await self._enviar(
                    usuario,
                    f"¿Te postulaste a <b>{t.e(f['titulo'])}</b>?",
                    [
                        [
                            ("✅ Sí", cb("seg", f["id"], "postulada")),
                            ("🙅 No", cb("seg", f["id"], "descartada")),
                        ]
                    ],
                )
        return len(filas)
