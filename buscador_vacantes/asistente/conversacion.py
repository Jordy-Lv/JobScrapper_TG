"""Lógica del bot asistente, independiente de la librería de Telegram.

El adaptador (bot.py) traduce los updates a llamadas ``al_*`` y entrega una ``Salida``. Así cada
flujo (alta, toque ⚡, avisos, comandos) se prueba sin Telegram. El estado de la conversación
vive en la base (paso_alta y kv), de modo que un reinicio retoma donde iba cada usuario.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from buscador_vacantes.asistente import resumen_postulacion, vinculos
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
from buscador_vacantes.asistente.gemini import ErrorIA, Saturado
from buscador_vacantes.asistente.membresia import Comprobador, SinPermisos
from buscador_vacantes.asistente.nucleo import Camino, Nucleo, Paquete
from buscador_vacantes.asistente.respuestas import (
    Contexto,
    ErrorPegado,
    recordar,
    resolver,
    separar_preguntas,
)
from buscador_vacantes.asistente.usuarios import EstadoUsuario, Usuario
from buscador_vacantes.estado import a_texto, de_texto

log = logging.getLogger(__name__)

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
            await self._enviar(usuario, t.PEDIR_CV.format(max_mb=self.config.cv.max_mb))
        elif paso == "resumen":
            await self._mostrar_resumen(usuario)
        elif paso.startswith("revision:"):
            await self._mostrar_seccion(usuario, paso.split(":", 1)[1])
        elif paso == "enfoque":
            await self._mostrar_enfoque(usuario)
        elif paso.startswith("cuestionario:"):
            await self._preguntar_cuestionario(usuario, int(paso.split(":", 1)[1]))
        elif paso.startswith("faltantes:"):
            await self._preguntar_faltante(usuario, int(paso.split(":", 1)[1]))
        elif paso == "navegador":
            await self._mostrar_navegador(usuario, al_terminar_alta=True)

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
            valida = await self.n.gemini.validar_clave(clave)
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
        self.n.guardar_clave_gemini(usuario.id, clave)
        self._esperar(usuario, None)
        await self._enviar(usuario, f"✅ Clave guardada (termina en …{t.e(clave[-4:])}).")
        if usuario.paso_alta == "clave":
            await self._ir_a(usuario, "cv")

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

    async def _leer_cv(
        self, usuario: Usuario, contenido: bytes, *, permitir: bool, reintento: int = 0
    ) -> None:
        clave = self.n.clave_gemini(usuario.id)
        if not clave:
            await self._enviar(
                usuario, "Como no tengo clave de Gemini, armemos tu perfil con unas preguntas."
            )
            await self._perfil_manual(usuario, 0)
            return
        if reintento == 0:
            await self._enviar(usuario, "📄 Leyendo tu hoja de vida…")
        try:
            lectura = await leer_cv(
                self.n.gemini,
                clave,
                usuario.id,
                contenido,
                self.config.cv,
                permitir_archivo_completo=permitir,
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
            return
        except CVInvalido as exc:
            await self._enviar(usuario, f"❌ {t.e(exc)}")
            return
        except Saturado:
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
                return
            await self._enviar(
                usuario,
                "Google sigue saturado. Armemos tu perfil con unas preguntas (podrás "
                "reemplazarlo luego enviando tu CV desde /perfil).",
            )
            await self._perfil_manual(usuario, 0)
            return
        except ErrorIA as exc:
            await self._enviar(
                usuario,
                f"No pude leerla con la IA ({t.e(exc)}). Armemos tu perfil con unas preguntas.",
            )
            await self._perfil_manual(usuario, 0)
            return
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

    async def _preguntar_cuestionario(
        self, usuario: Usuario, indice: int, *, restantes: int | None = None, modo: str = "todo"
    ) -> None:
        if indice >= len(t.CUESTIONARIO):
            await self._ir_a(usuario, "navegador")
            return
        item = t.CUESTIONARIO[indice]
        datos = self.n.datos_usuario(usuario.id)
        sugerido = datos.cuestionario.get(f"sugerido_{item.clave}") if datos else None
        if item.clave == "ciudad" and datos and datos.perfil.ciudad:
            sugerido = datos.perfil.ciudad
        botones: Botones = []
        if item.opciones:
            botones = [
                [(o, cb("cuest", indice, n)) for n, o in enumerate(item.opciones[i : i + 4], i)]
                for i in range(0, len(item.opciones), 4)
            ]
        if sugerido:
            botones.append([(f"Usar {sugerido}", cb("cuest", indice, "sug"))])
        if item.opcional:
            botones.append([("Omitir", cb("cuest", indice, "omitir"))])
        self._esperar(usuario, {"tipo": "cuestionario", "indice": indice, "modo": modo})
        progreso = f"<b>Pregunta {indice + 1} de {len(t.CUESTIONARIO)}</b>\n"
        if restantes is not None:
            progreso = f"<b>Faltan {restantes}</b>\n" if restantes > 1 else "<b>Última</b>\n"
        if usuario.estado != EstadoUsuario.ALTA:
            progreso = ""
        await self._enviar(usuario, progreso + t.e(item.pregunta), botones or None)

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

    async def _preguntar_faltante(self, usuario: Usuario, desde: int) -> None:
        pendientes = [i for i in self._faltantes(usuario) if i >= desde]
        if not pendientes:
            await self._ir_a(usuario, "navegador")
            return
        await self._preguntar_cuestionario(
            usuario, pendientes[0], restantes=len(pendientes), modo="faltantes"
        )

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
            cuestionario["_omitidos"] = cuestionario.get("_omitidos", "") + f" {item.clave}"
        cuestionario.pop(f"sugerido_{item.clave}", None)
        self.n.guardar_cuestionario(usuario.id, cuestionario)

    async def _siguiente_cuestionario(self, usuario: Usuario, indice: int) -> None:
        modo = (self._esperando(usuario) or {}).get("modo")
        if usuario.estado == EstadoUsuario.ALTA and modo == "faltantes":
            await self._ir_a(usuario, f"faltantes:{indice + 1}")
        elif usuario.estado == EstadoUsuario.ALTA:
            await self._ir_a(usuario, f"cuestionario:{indice + 1}")
        elif indice + 1 < len(t.CUESTIONARIO) and (self._esperando(usuario) or {}).get("todo"):
            await self._preguntar_cuestionario(usuario, indice + 1)
            self._esperar(usuario, {"tipo": "cuestionario", "indice": indice + 1, "todo": True})
        else:
            self._esperar(usuario, None)
            await self._enviar(usuario, "✅ Guardado.")

    async def _mostrar_navegador(self, usuario: Usuario, *, al_terminar_alta: bool) -> None:
        tienda = (
            f" desde {self.config.extension.url_edge}" if self.config.extension.url_edge else ""
        )
        botones: Botones = [[("🔗 Vincular mi navegador", cb("vincular"))]]
        if al_terminar_alta:
            botones.append([("Lo haré después", cb("alta", "fin"))])
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
        await self._enviar(usuario, t.ALTA_LISTA)
        if usuario.vacante_pendiente:
            pendiente = usuario.vacante_pendiente
            self.n.usuarios.fijar_vacante_pendiente(usuario, None)
            await self.procesar_toque(self.n.usuarios.por_id(usuario.id), pendiente)

    # --- toque de ⚡ ----------------------------------------------------------------

    async def procesar_toque(self, usuario: Usuario, id_corto: str, *, origen: str = "boton"):
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
        titulo = t.e(toque.vacante.titulo)
        if toque.camino == Camino.YA_EXISTE:
            estado = t.ESTADOS.get(toque.postulacion.estado, toque.postulacion.estado)
            await self._enviar(usuario, f"<b>{titulo}</b>\nYa la tienes: {estado}.")
            return toque
        if toque.camino == Camino.AUTOMATICA:
            mensaje = await self._enviar(
                usuario, f"<b>{titulo}</b>\n⏳ En cola. Te aviso el resultado."
            )
            if mensaje:
                with self.n.base.transaccion() as cx:
                    cx.execute(
                        "UPDATE postulaciones SET mensaje_id = ? WHERE id = ?",
                        (mensaje, toque.postulacion.id),
                    )
            self._en_segundo_plano(self._preparar(usuario, toque))
            return toque
        await self._enviar(
            usuario,
            f"<b>{titulo}</b>\n📋 No puedo postularla sola: "
            f"{t.e(t.MOTIVOS_RESPALDO.get(toque.motivo, toque.motivo))}. "
            "Preparo tu paquete para que lo hagas en un minuto…",
        )
        self._en_segundo_plano(self._enviar_paquete(usuario, toque.postulacion.id, toque.motivo))
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
            await self._enviar(usuario, texto)

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
        await self._enviar(
            usuario,
            "Cuando termines, cuéntame:",
            [
                [("🔗 Abrir vacante", f"url:{v.url}")],
                [("💬 Responder preguntas del formulario", cb("pegar", pid))],
                [
                    ("✅ Ya me postulé", cb("seg", pid, "postulada")),
                    ("🙅 No me interesa", cb("seg", pid, "descartada")),
                ],
            ],
        )

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
            indice = esperando["indice"]
            self._guardar_respuesta_cuestionario(usuario, indice, texto.strip())
            await self._siguiente_cuestionario(usuario, indice)
        elif tipo == "pendiente":
            await self._responder_pendiente(usuario, esperando["id"], texto.strip())
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
            self.n.gemini if clave else None,
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

    async def _responder_pendiente(self, usuario: Usuario, pendiente_id: int, respuesta: str):
        reencolada = self.n.responder_pendiente(usuario.id, pendiente_id, respuesta)
        self._esperar(usuario, None)
        restantes = self.n.pendientes(usuario.id)
        if restantes:
            await self._preguntar_pendiente(usuario, restantes[0])
        elif reencolada:
            await self._enviar(usuario, "✅ Gracias, lo recordaré. Sigo con tu postulación.")
        else:
            await self._enviar(usuario, "✅ Gracias, lo recordaré.")

    async def _preguntar_pendiente(self, usuario: Usuario, pendiente: dict) -> None:
        opciones = json.loads(pendiente["opciones_json"] or "[]")
        botones = [[(o, cb("pend", pendiente["id"], n))] for n, o in enumerate(opciones[:8])]
        self._esperar(usuario, {"tipo": "pendiente", "id": pendiente["id"]})
        texto = f"❓ Para tu postulación necesito un dato:\n<b>{t.e(pendiente['pregunta'])}</b>"
        if not opciones:
            texto += "\nEscríbeme la respuesta."
        await self._enviar(usuario, texto, botones or None)

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
            case "cv":
                ruta = Path(
                    self.n.base.cx.execute(
                        "SELECT cv_archivo FROM usuarios WHERE id = ?", (usuario.id,)
                    ).fetchone()[0]
                )
                if args[0] == "escaneado":
                    await self._leer_cv(usuario, ruta.read_bytes(), permitir=True)
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
                indice, eleccion = int(args[0]), args[1]
                item = t.CUESTIONARIO[indice]
                if eleccion == "omitir":
                    valor = ""
                elif eleccion == "sug":
                    datos = self.n.datos_usuario(usuario.id)
                    valor = (
                        datos.cuestionario.get(f"sugerido_{item.clave}")
                        or (datos.perfil.ciudad if item.clave == "ciudad" else "")
                        or ""
                    )
                else:
                    valor = item.opciones[int(eleccion)]
                self._guardar_respuesta_cuestionario(usuario, indice, valor)
                await self._siguiente_cuestionario(usuario, indice)
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
                    cx.execute(
                        "UPDATE postulaciones SET seguimiento = ? WHERE id = ? AND usuario_id = ?",
                        (seguimiento, pid, usuario.id),
                    )
                return "Anotado ✅"
            case "cuenta":
                plataforma, decision = args
                if decision == "si":
                    self.n.cuentas.confirmar(usuario.id, plataforma, ahora)
                    await self._enviar(
                        usuario,
                        f"✅ {t.NOMBRES_PLATAFORMA.get(plataforma, plataforma)}"
                        " quedó asociada a tu perfil.",
                    )
                elif decision == "nueva":
                    # No se guarda el correo ajeno: se olvida la asociación y en el próximo
                    # latido se pide confirmar la cuenta abierta, mostrando su correo completo
                    self.n.cuentas.olvidar(usuario.id, plataforma)
                    await self._enviar(
                        usuario,
                        "Listo: en unos segundos te pido confirmar la "
                        "cuenta abierta en tu navegador.",
                    )
                else:
                    self.n.cuentas.olvidar(usuario.id, plataforma)
                    await self._enviar(
                        usuario,
                        "Entendido: no postularé con esa cuenta. Inicia "
                        "sesión con la tuya en ese navegador.",
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

    async def _vincular(self, usuario: Usuario) -> None:
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
        if usuario.estado == EstadoUsuario.ALTA:
            await self._enviar(
                usuario,
                "Cuando termines (o si prefieres hacerlo después):",
                [[("Terminar", cb("alta", "fin"))]],
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
        self._esperar(usuario, {"tipo": "cuestionario", "indice": 0, "todo": True})
        await self._preguntar_cuestionario(usuario, 0)
        self._esperar(usuario, {"tipo": "cuestionario", "indice": 0, "todo": True})

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
        await self._mostrar_navegador(usuario, al_terminar_alta=False)

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
            "navegadores e historial. No se puede deshacer.",
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
            await self._enviar(
                usuario,
                "✅ Navegador vinculado. Ahora inicia sesión en "
                "Computrabajo y Magneto en ese navegador.",
            )
        elif tipo == "cuenta_por_confirmar":
            await self._enviar(
                usuario,
                f"🔓 Sesión iniciada en {nombre} mediante la extensión.\n"
                f"Cuenta: <b>{t.e(d['asociado'])}</b>\n\n"
                "¿La confirmas para postular con ella?",
                [
                    [
                        ("✅ Confirmar", cb("cuenta", d["plataforma"], "si")),
                        ("Cancelar", cb("cuenta", d["plataforma"], "no")),
                    ]
                ],
            )
        elif tipo == "cuenta_distinta":
            await self._enviar(
                usuario,
                f"⚠️ La cuenta de {nombre} abierta en tu navegador ({t.e(d['encontrado'])}) no es "
                f"la tuya ({t.e(d['asociado'])}). No postularé con ella.",
                [
                    [
                        ("Es mi cuenta nueva, usarla", cb("cuenta", d["plataforma"], "nueva")),
                        ("No es mía", cb("cuenta", d["plataforma"], "no")),
                    ]
                ],
            )
        elif tipo == "cuenta_sin_correo":
            log.info("No se pudo leer el correo de %s para el usuario %s", nombre, usuario.id)
        elif tipo == "portal_listo":
            await self._enviar(usuario, f"✅ {nombre} listo · cuenta: {t.e(d.get('asociado'))}")
        elif tipo == "portal_incompleto":
            await self._enviar(
                usuario,
                f"🛠 Tu perfil de {nombre} está incompleto: lo completo con tus datos y tu CV.",
            )
        elif tipo == "verificacion":
            await self._enviar(
                usuario,
                "🧩 El portal pide una verificación. Complétala en la "
                "pestaña que abrí en tu navegador y sigo solo.",
            )
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
            await self._editar_progreso(usuario, d["postulacion_id"], "🚀 Postulando…")

    async def _editar_progreso(self, usuario: Usuario, pid: int, estado: str) -> None:
        fila = self.n.base.cx.execute(
            "SELECT p.mensaje_id, v.titulo FROM postulaciones p LEFT JOIN vacantes v "
            "ON v.id_corto = p.id_corto WHERE p.id = ?",
            (pid,),
        ).fetchone()
        if fila and fila["mensaje_id"]:
            try:
                await self.s.editar(
                    usuario.telegram_id,
                    fila["mensaje_id"],
                    f"<b>{t.e(fila['titulo'])}</b>\n{estado}",
                )
                return
            except Exception:  # noqa: BLE001 - mensaje viejo o borrado: se envía uno nuevo
                pass
        await self._enviar(usuario, f"<b>{t.e(fila['titulo'] if fila else '')}</b>\n{estado}")

    async def _enviar_resumen(self, usuario: Usuario, p, *, confirmada: bool = True) -> None:
        """Resumen detallado de una postulación confirmada: la vacante, la hoja de vida que
        recibió el portal y cada pregunta con su respuesta y su origen."""
        vacante = self.n.indice.obtener(p.id_corto) if p.id_corto else None
        if vacante is None:
            return
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
        for texto in resumen_postulacion.mensajes(datos):
            await self._enviar(usuario, texto)
        usado = adjunto or ("cv_subir" in datos.pasos and "cv_verificar_fallo" not in datos.pasos)
        if usado and fila["cv_archivo"] and Path(fila["cv_archivo"]).is_file():
            await self.s.documento(usuario.telegram_id, Path(fila["cv_archivo"]),
                                   "La hoja de vida que recibió el portal")  # fmt: skip

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
            await self._editar_progreso(usuario, p.id, "💻 Se enviará cuando abras tu navegador.")
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
            await self._editar_progreso(
                usuario, p.id, "✅ <b>Postulación enviada y confirmada.</b> Te dejo el resumen."
            )
            await self._enviar_resumen(usuario, p)
            await self._enviar(
                usuario,
                "¿Cómo te fue? Márcalo cuando sepas:",
                [
                    [
                        ("🗣 Entrevista", cb("seg", p.id, "entrevista")),
                        ("❌ Rechazada", cb("seg", p.id, "rechazada")),
                        ("🎉 Oferta", cb("seg", p.id, "oferta")),
                    ]
                ],
            )
        elif ev.estado == E.ESPERANDO_SESION:
            nombre = t.NOMBRES_PLATAFORMA.get(p.plataforma, p.plataforma)
            await self._editar_progreso(
                usuario,
                p.id,
                f"🔑 Inicia sesión en {nombre} en tu navegador y continúo solo. Si no tienes "
                f"cuenta, créala aquí: {t.URL_REGISTRO.get(p.plataforma, '')}",
            )
        elif ev.estado == E.INCIERTA:
            await self._editar_progreso(
                usuario, p.id, estado + ". Revisa «Mis postulaciones» en el portal."
            )
            # Igual se le cuenta qué se respondió y con qué hoja de vida, para que pueda revisar
            await self._enviar_resumen(usuario, p, confirmada=False)
        elif ev.estado == E.BLOQUEADA and (ev.detalle or "") in t.BLOQUEOS_PORTAL:
            nombre = t.NOMBRES_PLATAFORMA.get(p.plataforma, p.plataforma or "el portal")
            await self._editar_progreso(
                usuario, p.id, f"🔒 {t.e(nombre)} pide una acción en tu cuenta antes de postular."
            )
            await self._enviar(
                usuario,
                "🔒 "
                + t.e(t.BLOQUEOS_PORTAL[ev.detalle].format(portal=nombre))
                + "\n\nCuando lo resuelvas, toca <b>🔁 Reintentar</b> (o ⚡ en la vacante) y la "
                "envío de nuevo. No envié nada todavía.",
                [[("🔁 Reintentar", cb("rei", p.id))]],
            )
        elif ev.estado in CON_RESPALDO:
            await self._editar_progreso(usuario, p.id, estado)
            motivo = ev.detalle if ev.tipo == "respaldo" else str(ev.estado)
            await self._enviar(
                usuario,
                "📋 Te preparo el paquete para que la envíes a mano: "
                f"{t.e(t.MOTIVOS_RESPALDO.get(motivo, motivo))}.",
            )
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
            await self._editar_progreso(usuario, p.id, estado)

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
