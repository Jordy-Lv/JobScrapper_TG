"""API v1 para la extensión de navegador (FastAPI). Se publica con Tailscale Funnel.

Todo vive bajo /api/v1/; cualquier otra ruta responde 404. Cada navegador se autentica con su
token (Authorization: Bearer); el servidor solo guarda su hash.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from buscador_vacantes.asistente import pantalla, recetas, reglas_motor, vinculos
from buscador_vacantes.asistente.cola import Cola, E, Evento, Postulacion, Tipo
from buscador_vacantes.asistente.cuentas_portal import CuentasPortal, EstadoCuenta
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.espera import version_tupla
from buscador_vacantes.asistente.preferencias import Preferencias
from buscador_vacantes.asistente.respuestas import Pregunta, Respuesta
from buscador_vacantes.comun import config as cfg
from buscador_vacantes.comun.estado import a_texto

log = logging.getLogger(__name__)

PREFIJO = "/api/v1"
MAX_CUERPO = 512 * 1024
MAX_HTML_EVIDENCIA = 300 * 1024
LIMITE_POR_MINUTO = 120
LIMITE_VINCULAR_POR_MINUTO = 20
LIMITE_PING_POR_MINUTO = 60
VERSION_CON_ENSAYO = (1, 2, 0)  # la primera extensión que se detiene antes de enviar
VIGENCIA_CV = timedelta(minutes=10)
LATIDO_FORMULARIO_S = 30  # latido del navegador mientras el servidor resuelve un formulario


# --- contrato con el resto del asistente --------------------------------------------------


@dataclass
class ResultadoFormulario:
    respuestas: list[Respuesta] = field(default_factory=list)
    faltan: list[Respuesta] = field(default_factory=list)
    cv: Path | None = None  # PDF a adjuntar o subir al perfil del portal
    revisar: bool = False  # el usuario revisa lo redactado antes del envío


@dataclass
class PaqueteDocumentos:
    """Lo que piden los campos de archivo de una pantalla, además del CV."""

    documentos: dict[str, tuple[str, bytes]] = field(default_factory=dict)  # tipo → (nombre, PDF)
    faltan: list[Pregunta] = field(default_factory=list)  # obligatorios sin documento


class Nucleo(Protocol):
    base: BaseAsistente
    cola: Cola
    cuentas: CuentasPortal
    preferencias: Preferencias
    config: cfg.Asistente
    archivos: Path

    def ahora(self) -> datetime: ...

    def vacante(self, id_corto: str) -> dict[str, Any] | None: ...

    def selectores(self, plataforma: str) -> tuple[str, dict] | None: ...

    async def resolver_formulario(
        self, postulacion: Postulacion, preguntas: list[Pregunta]
    ) -> ResultadoFormulario: ...

    async def arbitrar_pantalla(
        self, postulacion: Postulacion, consulta: pantalla.Consulta
    ) -> pantalla.DecisionPagina | None:
        """Árbitro de las pantallas que las reglas no entienden; None: sin IA o falló."""
        ...

    async def reparar_pantalla(
        self, postulacion: Postulacion, consulta: pantalla.ConsultaReparacion
    ) -> pantalla.Reparacion | None:
        """Corrección de un paso fallido antes del envío; None: sin IA o falló."""
        ...

    async def documentos_pantalla(
        self, postulacion: Postulacion, preguntas: list[Pregunta]
    ) -> PaqueteDocumentos:
        """Documentos (certificado de notas, carta…) que piden los campos de archivo, además del
        CV. Si falta uno obligatorio, deja la pregunta pendiente en la card del usuario."""
        ...

    def en_ensayo(self, postulacion: Postulacion) -> bool:
        """True si la postulación debe detenerse antes de enviar (modo ensayo)."""
        ...

    def esquema_resuelto(self, postulacion: Postulacion) -> dict[str, str]:
        """Respuestas del formulario anticipado por clave de campo; vacío si no hay esquema."""
        ...

    async def notificar(self, evento: Evento | dict) -> None: ...


# --- cuerpos ------------------------------------------------------------------------------


class Vincular(BaseModel):
    codigo: str = Field(max_length=20)
    nombre: str | None = Field(None, max_length=60)
    version: str | None = Field(None, max_length=20)


class Portal(BaseModel):
    estado: str = Field(pattern="^(sin_sesion|incompleto|listo)$")
    correo: str | None = Field(None, max_length=254)
    pagina_correo: str | None = Field(None, max_length=300)  # ruta donde se leyó el correo
    motivo: str | None = Field(None, max_length=40)  # por qué se marcó sin sesión


class Latido(BaseModel):
    version: str = Field(max_length=20)
    portales: dict[str, Portal] = Field(default_factory=dict)
    pausado: bool | None = None  # extensión en pausa; las versiones viejas no lo mandan


class PreferenciasPortalCuerpo(BaseModel):
    automatico: bool = True
    umbral: int | None = Field(None, ge=0, le=100)
    avisar: bool = True
    revisar_respuestas: bool = False


class NivelIACuerpo(BaseModel):
    nivel: Literal["ahorro", "normal", "maximo"]


class Campo(BaseModel):
    texto: str = Field(max_length=1000)
    tipo: str = Field("texto", max_length=20)
    opciones: list[str] = Field(default_factory=list, max_length=100)
    obligatoria: bool = True
    nombre: str | None = Field(None, max_length=200)
    maximo: int | None = Field(None, ge=1, le=100000)  # maxlength del campo, si lo tiene
    # Del esquema ampliado de la extensión 1.2 (la 1.1.x no los manda)
    ayuda: str | None = Field(None, max_length=500)
    autocomplete: str | None = Field(None, max_length=100)
    accept: str | None = Field(None, max_length=200)
    idioma: str | None = Field(None, max_length=10)
    busqueda: bool = False  # lista demasiado larga para leerla: se escribe el valor y se elige


class Formulario(BaseModel):
    campos: list[Campo] = Field(max_length=80)


class Pantalla(BaseModel):
    """Una pantalla del bucle genérico. Nunca trae valores de campos."""

    numero: int = Field(1, ge=1, le=1000)
    clase: str = Field(max_length=20)
    motivo: str | None = Field(None, max_length=60)
    idioma: str | None = Field(None, max_length=10)
    url: str = Field("", max_length=2000)
    campos: list[Campo] = Field(default_factory=list, max_length=80)
    botones: list[pantalla.Boton] = Field(default_factory=list, max_length=300)
    sugerido: pantalla.Sugerido | None = None
    firma: list[str] = Field(default_factory=list, max_length=100)
    resumen: pantalla.Resumen = Field(default_factory=pantalla.Resumen)
    exito: pantalla.Exito | None = None
    correccion: bool = False  # vuelta única tras un error de validación


class Reparar(Pantalla):
    """La pantalla donde falló un paso, con el paso y su motivo. Nunca trae valores de campos."""

    paso: str = Field(max_length=60)
    fallo: str = Field("", max_length=500)


class Paso(BaseModel):
    paso: str = Field(max_length=60)
    detalle: str | None = Field(None, max_length=2000)


class Verificacion(BaseModel):
    estado: str = Field(pattern="^(pendiente|resuelta)$")


class Parche(BaseModel):
    """El selector que reemplazó al de un paso declarado que falló. Solo datos."""

    paso: str = Field(max_length=60)
    selector: Any = None


class Resultado(BaseModel):
    parche: Parche | None = None
    estado: str
    motivo: str | None = Field(None, max_length=500)
    html: str | None = None  # evidencia, con los valores de los campos borrados
    confirmacion: str | None = Field(None, max_length=500)


# --- utilidades ---------------------------------------------------------------------------


def campos_obligatorios(selectores: tuple[str, dict] | None) -> set[str]:
    """Campos que el portal no marca como obligatorios pero que no se envían vacíos.

    Los declara `campos_obligatorios` en los selectores (por ejemplo, la nota de presentación de
    elempleo): si la IA no puede responderlos, se le preguntan al usuario por la card.
    """
    return set(selectores[1].get("campos_obligatorios", [])) if selectores else set()


_VALOR = re.compile(r"""\s(value|data-value)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_TEXTAREA = re.compile(r"(<textarea[^>]*>).*?(</textarea>)", re.IGNORECASE | re.DOTALL)


def sin_valores(documento: str) -> str:
    """Defensa adicional: quita valores de campos y el contenido de los textarea."""
    documento = _VALOR.sub("", documento)
    return _TEXTAREA.sub(r"\1\2", documento)


class Limitador:
    def __init__(self, por_minuto: int, reloj: Callable[[], float] = time.monotonic) -> None:
        self.por_minuto = por_minuto
        self.reloj = reloj
        self.registros: dict[str, deque[float]] = defaultdict(deque)

    def permitir(self, clave: str) -> bool:
        ahora = self.reloj()
        cola = self.registros[clave]
        while cola and ahora - cola[0] > 60:
            cola.popleft()
        if len(cola) >= self.por_minuto:
            return False
        cola.append(ahora)
        return True


PAGINA_VINCULO = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vincular navegador · Asistente de postulación</title>
<style>
:root{{--fondo:#eef2f7;--tarjeta:#fff;--texto:#1f2937;--titulo:#0f2a43;--suave:#4b5563;
--caja:#f1f4f8;--borde:#dde3ea;--ok:#2fb36d;--error:#d92d20;--azul:#3a8fd1;--azul-h:#2f7fbd}}
@media(prefers-color-scheme:dark){{:root{{--fondo:#0e1520;--tarjeta:#172231;--texto:#e5e9f0;
--titulo:#f3f6fa;--suave:#a4afbe;--caja:#1d2b3d;--borde:#2a3a4f}}}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
padding:24px 16px;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;
color:var(--texto);background:radial-gradient(circle at 50% 0,var(--tarjeta),var(--fondo) 70%)}}
main{{width:100%;max-width:440px;background:var(--tarjeta);border-radius:24px;
padding:36px 32px 32px;text-align:center;box-shadow:0 18px 50px rgba(15,42,67,.14)}}
.icono{{width:72px;height:72px;margin:0 auto 22px;border-radius:50%;display:none;
align-items:center;justify-content:center;color:#fff}}
.icono svg{{width:36px;height:36px}}
.icono.ok{{background:var(--ok);box-shadow:0 0 0 10px rgba(47,179,109,.16)}}
.icono.fallo{{background:var(--error);box-shadow:0 0 0 10px rgba(217,45,32,.14)}}
.icono.espera{{background:none;color:var(--azul)}}
.icono.espera svg{{width:56px;height:56px;animation:giro 1s linear infinite}}
@keyframes giro{{to{{transform:rotate(360deg)}}}}
body:not([data-vinculado]) .icono.espera,body[data-vinculado=si] .icono.ok,
body[data-vinculado=no] .icono.fallo{{display:flex}}
h1{{display:none;margin:0 0 10px;font-size:1.5rem;line-height:1.25;color:var(--titulo)}}
body:not([data-vinculado]) h1.espera,body[data-vinculado=si] h1.ok,
body[data-vinculado=no] h1.fallo{{display:block}}
#estado{{margin:0 auto 24px;max-width:320px;font-size:1.05rem;line-height:1.5;color:var(--suave)}}
#estado.error{{color:var(--error)}}
.telegram{{display:none;align-items:center;justify-content:center;gap:10px;width:100%;
padding:15px 20px;border-radius:999px;background:var(--azul);color:#fff;font-weight:600;
font-size:1.05rem;text-decoration:none;transition:background .15s}}
.telegram:hover,.telegram:focus-visible{{background:var(--azul-h)}}
.telegram svg{{width:22px;height:22px}}
body[data-vinculado=si] .telegram{{display:flex}}
.codigo{{margin-top:24px;padding:18px 16px;border-radius:16px;background:var(--caja)}}
body[data-vinculado=si] .codigo{{display:none}}
.codigo p{{margin:0 0 12px;font-weight:600;color:var(--titulo)}}
.caja{{display:inline-flex;align-items:stretch;border:1px solid var(--borde);border-radius:10px;
overflow:hidden;background:var(--tarjeta)}}
.caja code{{padding:10px 16px;font:600 1.15rem ui-monospace,SFMono-Regular,Consolas,monospace;
letter-spacing:.08em;color:var(--titulo)}}
.caja button{{border:0;border-left:1px solid var(--borde);background:var(--caja);color:var(--suave);
padding:0 12px;cursor:pointer}}
.caja button:hover,.caja button:focus-visible{{color:var(--titulo)}}
.caja button svg{{width:20px;height:20px;display:block}}
.codigo small{{display:block;margin-top:12px;color:var(--suave)}}
</style></head>
<body><main>
<div id="asistente-vinculo" data-codigo="{codigo}" data-api="{api}"></div>
<div class="icono espera" aria-hidden="true"><svg viewBox="0 0 50 50" fill="none"
stroke="currentColor" stroke-width="5" stroke-linecap="round"><circle cx="25" cy="25" r="20"
opacity=".2"/><path d="M45 25a20 20 0 0 0-20-20"/></svg></div>
<div class="icono ok" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"
stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path
d="M5 12.5l4.5 4.5L19 7.5"/></svg></div>
<div class="icono fallo" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"
stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/>
</svg></div>
<h1 class="espera">Vinculando tu navegador…</h1>
<h1 class="ok">¡Navegador vinculado con éxito!</h1>
<h1 class="fallo">No se pudo vincular</h1>
<p id="estado" role="status">Si tienes la extensión del asistente instalada, este navegador se
vincula solo en unos segundos.</p>
{boton_telegram}
<div class="codigo"><p>¿No se sincronizó automáticamente?</p>
<div class="caja"><code id="codigo-visible">{visible}</code><button type="button" id="copiar"
title="Copiar código" aria-label="Copiar código"><svg viewBox="0 0 24 24" fill="none"
stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect
x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg></button>
</div><small>Escríbelo en la extensión · vence en 10 minutos</small></div>
</main>
<script>document.getElementById("copiar").addEventListener("click",function(){{
var t=document.getElementById("codigo-visible").textContent;
if(navigator.clipboard)navigator.clipboard.writeText(t).then(function(){{
document.getElementById("copiar").title="¡Copiado!"}}).catch(function(){{}})}})</script>
</body></html>"""

BOTON_TELEGRAM = """<a class="telegram" href="{enlace}"><svg viewBox="0 0 24 24" fill="none"
stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
aria-hidden="true"><path d="M22 2 11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>
 Volver a Telegram</a>"""

PAGINA_PRIVACIDAD = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Política de privacidad · Asistente de postulación</title>
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;
color:#1f2937;line-height:1.55}h1{color:#1f3a5f;font-size:1.5rem}h2{color:#1f3a5f;
font-size:1.1rem;margin-top:1.8em}</style></head>
<body><h1>Política de privacidad de la extensión «Asistente de postulación»</h1>
<p>Última actualización: 15 de octubre de 2026.</p>
<p>La extensión es parte de un asistente privado para los miembros del canal de Telegram
«JOBS - PRÁCTICAS/APRENDIZ». Postula a vacantes de Computrabajo y Magneto (y de elempleo, si el
usuario activa su permiso) desde el navegador del propio usuario, con su sesión, cuando el
usuario lo pide desde el bot de Telegram.</p>
<h2>Qué datos usa la extensión</h2>
<ul>
<li><b>Token del navegador</b>: un código aleatorio que se guarda en el navegador para
identificarlo ante el servidor del asistente. El servidor solo guarda su huella (hash).</li>
<li><b>Estado de los portales</b>: si hay una sesión iniciada en cada portal activo y el
correo de esa cuenta, para no postular con la cuenta de otra persona.</li>
<li><b>Preguntas de los formularios de postulación</b>: su texto y opciones se envían al
servidor para obtener las respuestas del perfil del usuario.</li>
<li><b>Registro de cada paso</b> y, si algo falla, el HTML del formulario <b>con los valores
escritos borrados</b>, para corregir el asistente.</li>
</ul>
<h2>Qué datos NO usa</h2>
<ul>
<li>No lee ni envía contraseñas, cookies, ni el almacenamiento de los portales.</li>
<li>No lee el historial de navegación ni ninguna página fuera de los portales de empleo
activados y el servidor del asistente.</li>
<li>No toma capturas de pantalla ni graba lo que el usuario hace.</li>
<li>No descarga ni ejecuta código remoto: solo recibe datos (selectores y respuestas).</li>
<li>No vende ni comparte datos con terceros, ni muestra publicidad.</li>
</ul>
<h2>Dónde se guardan</h2>
<p>En el servidor privado del asistente (un equipo del administrador), en una base de datos
local. Los correos de las cuentas de los portales y las claves de IA se guardan cifrados. El
servidor nunca recibe contraseñas ni sesiones de los portales.</p>
<h2>Cuánto tiempo</h2>
<p>El registro de las postulaciones se conserva 90 días y la evidencia de errores 30 días.
Una cuenta sin uso durante 12 meses se elimina.</p>
<h2>Tus derechos</h2>
<p>Puedes ver tus datos con <code>/perfil</code> e <code>/historial</code> en el bot, revocar
un navegador con <code>/navegadores</code> y borrar todos tus datos en cualquier momento con
<code>/borrarme</code>. Al desinstalar la extensión se borra todo lo que guardó en el
navegador.</p>
<h2>Contacto</h2>
<p>Escribe al administrador del canal por Telegram o al bot del asistente.</p>
</body></html>"""


# --- aplicación -----------------------------------------------------------------------------


def crear_app(nucleo: Nucleo) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    limite = Limitador(LIMITE_POR_MINUTO)
    limite_vincular = Limitador(LIMITE_VINCULAR_POR_MINUTO)
    limite_ping = Limitador(LIMITE_PING_POR_MINUTO)
    # token → (archivo o PDF en memoria, nombre, vencimiento)
    descargas_cv: dict[str, tuple[Path | bytes, str, datetime]] = {}
    trazas = recetas.Trazas()

    @app.middleware("http")
    async def tamano_maximo(request: Request, siguiente):
        largo = request.headers.get("content-length")
        if largo and int(largo) > MAX_CUERPO:
            return JSONResponse({"detail": "cuerpo demasiado grande"}, status_code=413)
        return await siguiente(request)

    def navegador_actual(authorization: str = Header("")) -> vinculos.Navegador:
        token = authorization.removeprefix("Bearer ").strip()
        navegador = vinculos.autenticar(nucleo.base, token) if token else None
        if navegador is None:
            raise HTTPException(401, "token inválido o revocado")
        if not limite.permitir(f"t{navegador.id}"):
            raise HTTPException(429, "demasiadas peticiones")
        return navegador

    def latir(nav: vinculos.Navegador) -> None:
        with nucleo.base.transaccion() as cx:
            cx.execute(
                "UPDATE navegadores SET ultimo_latido = ? WHERE id = ?",
                (a_texto(nucleo.ahora()), nav.id),
            )

    def postulacion_de(pid: int, nav: vinculos.Navegador) -> Postulacion:
        p = nucleo.cola.obtener(pid)
        if p is None or p.usuario_id != nav.usuario_id:
            raise HTTPException(404, "postulación no encontrada")
        # Mientras ejecuta una postulación la extensión no manda latidos (el latido es el que
        # la ejecuta): cada llamada de la postulación cuenta como señal de vida, así un paso
        # largo (la IA, el CV adaptado) no la deja como "navegador cerrado"
        latir(nav)
        return p

    async def resolver_con_latido(p: Postulacion, nav: vinculos.Navegador, preguntas):
        """Resuelve el formulario sin dejar que la espera cuente como navegador caído: la
        llamada puede durar más que `navegador_caido_min` (la IA con reintentos, el CV).
        Registra cuánto tardó, para saber si ahí está el cuello de botella."""
        return await con_latido(
            p, nav, nucleo.resolver_formulario(p, preguntas), "formulario_resuelto"
        )

    async def con_latido(p: Postulacion, nav: vinculos.Navegador, corrutina, paso: str):
        inicio = time.perf_counter()
        tarea = asyncio.ensure_future(corrutina)
        try:
            while True:
                terminadas, _ = await asyncio.wait({tarea}, timeout=LATIDO_FORMULARIO_S)
                if terminadas:
                    break
                latir(nav)
        finally:
            if not tarea.done():
                tarea.cancel()
        latir(nav)
        resultado = tarea.result()
        nucleo.cola.registrar_paso(
            p.id, nav.id, paso, f"{time.perf_counter() - inicio:.1f} s", nucleo.ahora()
        )
        anotar_nivel_bajado(p, nav)
        return resultado

    def nivel_de(p: Postulacion) -> str:
        return nucleo.preferencias.nivel_efectivo(p.usuario_id, p.nivel_ia, nucleo.ahora())

    def anotar_nivel_bajado(p: Postulacion, nav: vinculos.Navegador) -> None:
        """Si la cuota del usuario bajó el nivel de esta postulación (en esta llamada o antes),
        queda el paso `nivel_bajado` con «de>a»; la card del resumen lo cuenta."""
        origen, actual = nucleo.preferencias.nivel_guardado(p.nivel_ia), nivel_de(p)
        if origen == actual:
            return
        detalle = f"{origen}>{actual}"
        ya = nucleo.base.cx.execute(
            "SELECT 1 FROM postulacion_pasos WHERE postulacion_id = ? AND paso = 'nivel_bajado' "
            "AND detalle = ?",
            (p.id, detalle),
        ).fetchone()
        if ya is None:
            nucleo.cola.registrar_paso(p.id, nav.id, "nivel_bajado", detalle, nucleo.ahora())

    def postulacion_en_curso(pid: int, nav: vinculos.Navegador) -> Postulacion:
        p = postulacion_de(pid, nav)
        if p.navegador_id != nav.id or p.estado != E.EN_CURSO:
            raise HTTPException(409, "la postulación no está en curso en este navegador")
        return p

    def receta_de(p: Postulacion, campos: list[Campo]) -> recetas.PantallaReceta | None:
        """La pantalla de la receta que llevó el trabajo y que coincide con estos campos."""
        fila = nucleo.base.cx.execute(
            "SELECT receta_id FROM postulaciones WHERE id = ?", (p.id,)
        ).fetchone()
        claves = {recetas.clave_campo(c.nombre, c.texto) for c in campos if c.tipo != "archivo"}
        return recetas.pantalla_de_receta(nucleo.base, fila["receta_id"] if fila else None, claves)

    def preguntas_de(
        p: Postulacion,
        campos: list[Campo],
        idioma: str | None = None,
        receta: recetas.PantallaReceta | None = None,
    ) -> list[Pregunta]:
        """`idioma` es el de la página (lo que informa la pantalla) para los campos que no
        traen el suyo. `receta` dice qué dato del catálogo va en cada campo que ya conoce."""
        forzadas = campos_obligatorios(nucleo.selectores(p.plataforma))
        mapeo = receta.mapeo if receta else {}
        return [
            Pregunta(c.texto, c.tipo, c.opciones, c.obligatoria or c.nombre in forzadas,
                     c.nombre, c.maximo, c.ayuda, c.autocomplete, c.accept, c.idioma or idioma,
                     c.busqueda, mapeo.get(recetas.clave_campo(c.nombre, c.texto)))
            for c in campos
        ]  # fmt: skip

    def peticion_de(p: Postulacion, cuerpo: Pantalla) -> pantalla.Peticion:
        receta = receta_de(p, cuerpo.campos)
        return pantalla.Peticion(
            cuerpo.clase, cuerpo.motivo, cuerpo.idioma, cuerpo.url,
            preguntas_de(p, cuerpo.campos, cuerpo.idioma, receta), cuerpo.botones,
            cuerpo.sugerido, cuerpo.resumen, cuerpo.exito, cuerpo.correccion,
            receta.boton if receta else None,
        )  # fmt: skip

    def anotar_pantalla(pid: int, cuerpo: Pantalla, decision: pantalla.Decision) -> None:
        """Lo que pasó en la pantalla, sin valores, para la receta del sitio si se envía."""
        accion = decision.accion or {}
        trazas.visitar(pid, cuerpo.url)
        if accion.get("tipo") == "exito" and cuerpo.exito:
            trazas.senal(pid, cuerpo.exito.senal)
        elif accion.get("tipo") in ("avanzar", "enviar"):
            boton = next((b for b in cuerpo.botones if b.indice == accion.get("indice")), None)
            firma = sorted({recetas.clave_campo(c.nombre, c.texto) for c in cuerpo.campos
                            if c.tipo != "archivo"})  # fmt: skip
            trazas.agregar(pid, cuerpo.numero, cuerpo.url, recetas.PantallaReceta(
                firma=firma, mapeo=decision.mapeo,
                boton=recetas.BotonReceta(texto=boton.texto, clase=boton.clase,
                                          selector=boton.selector) if boton else None,
            ))  # fmt: skip

    def respuesta_reparacion(motivo: str, diagnostico: str = "") -> dict[str, Any]:
        return {"acciones": [], "diagnostico": diagnostico,
                "accion": {"tipo": "respaldo", "motivo": motivo}}  # fmt: skip

    def publicar_cv(cv: Path | None) -> str | None:
        """Enlace de un solo uso (10 min) para que la extensión baje el CV."""
        if cv is None:
            return None
        return publicar(cv, cv.name)

    def publicar(contenido: Path | bytes, nombre: str) -> str:
        """Lo mismo para cualquier PDF; los documentos del usuario viajan descifrados desde la
        memoria, nunca se escriben en claro en el disco."""
        token = secrets.token_urlsafe(24)
        descargas_cv[token] = (contenido, nombre, nucleo.ahora() + VIGENCIA_CV)
        return f"{PREFIJO}/cv/{token}"

    # --- ping ---

    @app.get(PREFIJO + "/ping")
    async def ping(request: Request):
        # Público y sin base de datos: la extensión lo cronometra para mostrar la latencia.
        # No usa navegador_actual, así que no cuenta como latido ni revela nada del servidor
        ip = request.client.host if request.client else "?"
        if not limite_ping.permitir(ip):
            raise HTTPException(429, "demasiadas peticiones")
        return {"ok": True}

    # --- vinculación ---

    @app.get(PREFIJO + "/vincular/{codigo}", response_class=HTMLResponse)
    async def pagina_vinculo(codigo: str):
        codigo = vinculos.normalizar_codigo(codigo)[:8]
        bot = nucleo.config.bot_usuario
        return PAGINA_VINCULO.format(
            boton_telegram=BOTON_TELEGRAM.format(enlace=html.escape(f"https://t.me/{bot}"))
            if bot
            else "",
            codigo=html.escape(codigo),
            visible=html.escape(vinculos.mostrar_codigo(codigo)),
            api=html.escape(nucleo.config.api.url_publica + PREFIJO),
        )

    @app.get(PREFIJO + "/privacidad", response_class=HTMLResponse)
    async def privacidad():
        return PAGINA_PRIVACIDAD

    @app.post(PREFIJO + "/vincular")
    async def vincular(cuerpo: Vincular, request: Request):
        ip = request.client.host if request.client else "?"
        if not limite_vincular.permitir(ip):
            raise HTTPException(429, "demasiados intentos")
        resultado = vinculos.canjear(
            nucleo.base, cuerpo.codigo, cuerpo.nombre, cuerpo.version, nucleo.ahora()
        )
        if resultado is None:
            raise HTTPException(400, "código inválido, vencido o ya usado")
        token, usuario_id = resultado
        await nucleo.notificar({"tipo": "navegador_vinculado", "usuario_id": usuario_id})
        return {"token": token}

    # --- latido y asignación ---

    @app.post(PREFIJO + "/latido")
    async def latido(cuerpo: Latido, nav: vinculos.Navegador = Depends(navegador_actual)):
        ahora = nucleo.ahora()
        anteriores = _portales_guardados(nucleo.base, nav.id)
        cuentas_ok: dict[str, bool] = {}
        disponibles: set[str] = set()  # cuenta verificada y sesión iniciada
        visto = a_texto(ahora)
        for plataforma, portal in cuerpo.portales.items():
            if plataforma not in nucleo.config.plataformas:
                continue
            previo = anteriores.get(plataforma, {})
            # Último estado con sesión, para no repetir el aviso al volver de «sin sesión»
            aviso = previo["aviso"] if "aviso" in previo else previo.get("estado")
            if portal.estado == "sin_sesion":
                if portal.motivo:
                    log.info("%s sin sesión en el navegador %s: %s", plataforma, nav.id,
                             portal.motivo)  # fmt: skip
                cuentas_ok[plataforma] = False
                anteriores[plataforma] = {
                    "estado": "sin_sesion", "motivo": portal.motivo, "cuenta": previo.get("cuenta"),
                    "aviso": aviso, "visto": visto,
                }  # fmt: skip
                continue
            if portal.pagina_correo:
                # Solo la ruta, sin el correo: indica qué página fijar en los selectores
                log.info("Correo de %s leído en %s", plataforma, portal.pagina_correo)
            verificacion = nucleo.cuentas.verificar(
                nav.usuario_id, plataforma, portal.correo, ahora
            )
            ok = verificacion.estado == EstadoCuenta.OK
            cuentas_ok[plataforma] = ok
            # Al reabrir la sesión se vuelve a pedir la cuenta que sigue sin resolverse
            reabierta = previo.get("estado") == "sin_sesion" and verificacion.estado in (
                EstadoCuenta.POR_CONFIRMAR, EstadoCuenta.DISTINTA,
            )  # fmt: skip
            if verificacion.estado != EstadoCuenta.OK and (
                verificacion.nuevo or reabierta or previo.get("cuenta") != verificacion.estado
            ):
                await nucleo.notificar({
                    "tipo": f"cuenta_{verificacion.estado}", "usuario_id": nav.usuario_id,
                    "plataforma": plataforma, "asociado": verificacion.asociado,
                    "encontrado": verificacion.encontrado_oculto,
                })  # fmt: skip
            elif ok and aviso != portal.estado:
                await nucleo.notificar({
                    "tipo": f"portal_{portal.estado}", "usuario_id": nav.usuario_id,
                    "plataforma": plataforma, "asociado": verificacion.asociado,
                })  # fmt: skip
            if ok:
                disponibles.add(plataforma)
                if portal.estado == "incompleto":
                    nucleo.cola.encolar_completar_perfil(nav.usuario_id, plataforma, ahora)
            # El correo nunca se guarda: solo el resultado de verificarlo
            anteriores[plataforma] = {
                "estado": portal.estado, "motivo": None, "cuenta": verificacion.estado,
                "aviso": portal.estado, "visto": visto,
            }  # fmt: skip
        for plataforma in nucleo.config.plataformas:
            # Con selectores cargados y ausente del latido: la extensión no tiene su permiso
            if plataforma not in cuerpo.portales and nucleo.selectores(plataforma):
                previo = anteriores.get(plataforma, {})
                aviso = previo["aviso"] if "aviso" in previo else previo.get("estado")
                anteriores[plataforma] = {
                    "estado": "sin_permiso", "motivo": None, "cuenta": previo.get("cuenta"),
                    "aviso": aviso, "visto": visto,
                }  # fmt: skip
        anteriores["_pausado"] = bool(cuerpo.pausado)
        with nucleo.base.transaccion() as cx:
            cx.execute(
                "UPDATE navegadores SET ultimo_latido = ?, version = ?, portales_json = ? "
                "WHERE id = ?",
                (a_texto(ahora), cuerpo.version, json.dumps(anteriores), nav.id),
            )
        listos = {p for p in disponibles if cuerpo.portales[p].estado == "listo"}
        nucleo.cola.portales_actualizados(nav.usuario_id, listos, ahora)
        # Plataforma apagada con /plataformas: no se entregan trabajos nuevos (las que esperan
        # sesión se reanudan arriba y las que están en curso no se tocan)
        asignables = {p for p in disponibles if nucleo.config.plataformas[p].automatica}

        version_minima = nucleo.config.extension.version_minima
        actualizar = version_tupla(cuerpo.version) < version_tupla(version_minima)
        trabajo = None
        if not actualizar:
            siguiente = nucleo.cola.siguiente(nav.usuario_id, asignables, ahora)
            if siguiente and (
                siguiente.tipo == Tipo.COMPLETAR_PERFIL or siguiente.plataforma in listos
            ):
                trabajo = _trabajo(nucleo, siguiente)
                if trabajo.get("ensayo") and version_tupla(cuerpo.version) < VERSION_CON_ENSAYO:
                    trabajo = None  # la 1.1.x ignora el ensayo y enviaría de verdad
        if nucleo.cola.en_espera(nav.usuario_id):
            # Que las cards en cola reflejen lo que acaba de reportar este navegador
            await nucleo.notificar({"tipo": "esperas", "usuario_id": nav.usuario_id})
        selectores = {p: s[0] for p in nucleo.config.plataformas if (s := nucleo.selectores(p))}
        return {
            "trabajo": trabajo,
            "version_minima": version_minima,
            "actualizar": actualizar,
            "selectores": selectores,
            # Versión de las reglas del motor genérico (None: motor apagado)
            "motor_generico": reglas_motor.reglas().version
            if nucleo.config.motor_generico.activo
            else None,
            "cuentas": cuentas_ok,
            "latido_s": nucleo.config.extension.latido_s,
            # Accesos del botón de chat del popup
            "enlaces": {
                "bot": f"https://t.me/{nucleo.config.bot_usuario}"
                if nucleo.config.bot_usuario
                else None,
                "grupo": getattr(nucleo, "enlace_grupo", None),
            },
        }

    @app.get(PREFIJO + "/selectores/{plataforma}")
    async def selectores(plataforma: str, nav: vinculos.Navegador = Depends(navegador_actual)):
        datos_selectores = nucleo.selectores(plataforma)
        if datos_selectores is None:
            raise HTTPException(404, "plataforma no soportada")
        version, contenido = datos_selectores
        return {"version": version, "selectores": contenido}

    @app.get(PREFIJO + "/motor_generico")
    async def motor_generico(nav: vinculos.Navegador = Depends(navegador_actual)):
        if not nucleo.config.motor_generico.activo:
            raise HTTPException(404, "motor genérico apagado")
        actuales = reglas_motor.reglas()
        return {"version": actuales.version, "reglas": actuales.model_dump(exclude={"nota"})}

    # --- engranaje de cada portal (preferencias y cuenta) ---

    @app.get(PREFIJO + "/preferencias/{plataforma}")
    async def ver_preferencias(
        plataforma: str, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        if plataforma not in nucleo.config.plataformas:
            raise HTTPException(404, "plataforma no soportada")
        pref = nucleo.preferencias.obtener(nav.usuario_id, plataforma)
        return {
            "automatico": pref.automatico,
            "umbral": pref.umbral,
            "avisar": pref.avisar,
            "revisar_respuestas": pref.revisar_respuestas,
            "cuenta": nucleo.cuentas.detalle(nav.usuario_id, plataforma),
        }

    @app.post(PREFIJO + "/preferencias/{plataforma}")
    async def guardar_preferencias(
        plataforma: str,
        cuerpo: PreferenciasPortalCuerpo,
        nav: vinculos.Navegador = Depends(navegador_actual),
    ):
        if plataforma not in nucleo.config.plataformas:
            raise HTTPException(404, "plataforma no soportada")
        nucleo.preferencias.guardar(
            nav.usuario_id, plataforma, nucleo.ahora(),
            automatico=cuerpo.automatico, umbral=cuerpo.umbral, avisar=cuerpo.avisar,
            revisar_respuestas=cuerpo.revisar_respuestas,
        )  # fmt: skip
        return {"ok": True}

    # --- nivel de uso de IA del usuario (el selector del popup) ---

    @app.get(PREFIJO + "/nivel_ia")
    async def ver_nivel_ia(nav: vinculos.Navegador = Depends(navegador_actual)):
        return nucleo.preferencias.resumen_nivel_ia(
            nav.usuario_id, nucleo.config.niveles_ia, nucleo.ahora()
        )

    @app.post(PREFIJO + "/nivel_ia")
    async def guardar_nivel_ia(
        cuerpo: NivelIACuerpo, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        nucleo.preferencias.fijar_nivel_ia(nav.usuario_id, cuerpo.nivel)
        return {"ok": True, "nivel": cuerpo.nivel}

    @app.post(PREFIJO + "/cuenta/{plataforma}/olvidar")
    async def olvidar_cuenta(plataforma: str, nav: vinculos.Navegador = Depends(navegador_actual)):
        """Desasocia la cuenta de ese portal; la próxima sesión detectada vuelve a pedirse
        confirmar en el bot, igual que "No es mía"."""
        nucleo.cuentas.olvidar(nav.usuario_id, plataforma)
        return {"ok": True}

    @app.post(PREFIJO + "/postulaciones/{pid}/tomar")
    async def tomar(pid: int, nav: vinculos.Navegador = Depends(navegador_actual)):
        postulacion_de(pid, nav)
        ahora = nucleo.ahora()
        if not (nucleo.cola.tomar(pid, nav.id, ahora) and nucleo.cola.iniciar(pid, nav.id, ahora)):
            raise HTTPException(409, "la postulación ya no está disponible")
        await nucleo.notificar({"tipo": "postulando", "postulacion_id": pid,
                                "usuario_id": nav.usuario_id})  # fmt: skip
        return {"ok": True}

    @app.post(PREFIJO + "/postulaciones/{pid}/paso")
    async def paso(pid: int, cuerpo: Paso, nav: vinculos.Navegador = Depends(navegador_actual)):
        postulacion_de(pid, nav)
        if not nucleo.cola.registrar_paso(pid, nav.id, cuerpo.paso, cuerpo.detalle, nucleo.ahora()):
            raise HTTPException(409, "la postulación no es de este navegador")
        await nucleo.notificar({"tipo": "paso", "postulacion_id": pid, "paso": cuerpo.paso,
                                "usuario_id": nav.usuario_id})  # fmt: skip
        return {"ok": True}

    @app.post(PREFIJO + "/postulaciones/{pid}/formulario")
    async def formulario(
        pid: int, cuerpo: Formulario, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        p = postulacion_en_curso(pid, nav)
        preguntas = preguntas_de(p, cuerpo.campos, receta=receta_de(p, cuerpo.campos))
        resultado = await resolver_con_latido(p, nav, preguntas)
        if resultado.revisar or any(r.pregunta.obligatoria for r in resultado.faltan):
            nucleo.cola.esperar_usuario(pid, nav.id, nucleo.ahora())
            return {"esperar_usuario": True}
        respuestas = pantalla.respuestas_de(preguntas, resultado)
        cv_url = publicar_cv(resultado.cv)
        return {"esperar_usuario": False, "respuestas": respuestas, "cv_url": cv_url,
                "cv_nombre": resultado.cv.name if resultado.cv else None}  # fmt: skip

    @app.post(PREFIJO + "/postulaciones/{pid}/pantalla")
    async def pantalla_actual(
        pid: int, cuerpo: Pantalla, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        """Decisión de una pantalla del bucle genérico: respuestas y siguiente acción.

        Las reglas deciden la clase y el botón; si dudan, decide el árbitro (con tope por
        postulación). Si el servidor no puede decidir, responde `respaldo` y la extensión se
        detiene sin pulsar nada."""
        motor = nucleo.config.motor_generico
        if not motor.activo:
            raise HTTPException(404, "el motor genérico está apagado")
        p = postulacion_en_curso(pid, nav)
        peticion = peticion_de(p, cuerpo)

        async def resolver(preguntas):
            return await nucleo.resolver_formulario(p, preguntas)

        async def arbitrar(consulta: pantalla.Consulta):
            nucleo.cola.registrar_paso(
                pid, nav.id, "arbitro",
                f"{cuerpo.clase}; {len(cuerpo.botones)} botones", nucleo.ahora(),
            )  # fmt: skip
            return await nucleo.arbitrar_pantalla(p, consulta)

        hechas = nucleo.base.cx.execute(
            "SELECT COUNT(*) FROM postulacion_pasos WHERE postulacion_id = ? AND paso = 'arbitro'",
            (pid,),
        ).fetchone()[0]
        # Los topes de `motor_generico` son el máximo absoluto; el nivel del usuario puede bajarlos
        nivel = nivel_de(p)
        tope = min(motor.max_arbitro, getattr(nucleo.config.niveles_ia, nivel).max_arbitro)
        decision = await con_latido(
            p, nav,
            pantalla.decidir(
                peticion, resolver, arbitrar if hechas < tope else None,
                "nivel_ahorro" if nivel == "ahorro" else "tope_arbitro",
            ),
            "pantalla_resuelta",
        )  # fmt: skip
        if decision.esperar_usuario:
            nucleo.cola.esperar_usuario(pid, nav.id, nucleo.ahora())
            return {"esperar_usuario": True}
        anotar_pantalla(pid, cuerpo, decision)
        paquete = PaqueteDocumentos()
        if peticion.pide_archivo and (decision.accion or {}).get("tipo") != "respaldo":
            paquete = await con_latido(
                p, nav, nucleo.documentos_pantalla(p, peticion.preguntas), "documentos_listos"
            )
            if paquete.faltan:  # un documento obligatorio que no hay: la card se lo pide
                nucleo.cola.esperar_usuario(pid, nav.id, nucleo.ahora())
                return {"esperar_usuario": True}
        return {"esperar_usuario": False, "respuestas": decision.respuestas,
                "cv_url": publicar_cv(decision.cv),
                "cv_nombre": decision.cv.name if decision.cv else None,
                "documentos": {tipo: {"url": publicar(contenido, nombre), "nombre": nombre}
                               for tipo, (nombre, contenido) in paquete.documentos.items()},
                "accion": decision.accion}  # fmt: skip

    @app.post(PREFIJO + "/postulaciones/{pid}/reparar")
    async def reparar(
        pid: int, cuerpo: Reparar, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        """Corrección de un paso que falló ANTES del envío, con índices y acciones de la lista
        cerrada. Tope de reparaciones por postulación según su nivel de IA (y `max_reparaciones`).
        Sin IA, sin cuota o sin reparación posible responde `respaldo` y la extensión se detiene
        sin pulsar nada."""
        motor = nucleo.config.motor_generico
        if not motor.activo:
            raise HTTPException(404, "el motor genérico está apagado")
        p = postulacion_en_curso(pid, nav)
        hechas = nucleo.base.cx.execute(
            "SELECT COUNT(*) FROM postulacion_pasos WHERE postulacion_id = ? "
            "AND paso = 'reparacion'",
            (pid,),
        ).fetchone()[0]
        nivel = nivel_de(p)
        tope = min(
            motor.max_reparaciones, getattr(nucleo.config.niveles_ia, nivel).max_reparaciones
        )
        if hechas >= tope:
            return respuesta_reparacion(
                "nivel_ahorro" if nivel == "ahorro" else "tope_reparaciones"
            )
        nucleo.cola.registrar_paso(
            pid, nav.id, "reparacion", f"{cuerpo.paso}: {cuerpo.fallo}"[:200], nucleo.ahora()
        )
        peticion = peticion_de(p, cuerpo)
        consulta = pantalla.ConsultaReparacion(peticion, cuerpo.paso, cuerpo.fallo)
        veredicto = await con_latido(
            p, nav, nucleo.reparar_pantalla(p, consulta), "reparacion_resuelta"
        )
        if veredicto is None:
            return respuesta_reparacion("sin_ia")
        acciones = pantalla.acciones_validas(veredicto.acciones, cuerpo.botones, cuerpo.resumen)
        if not acciones:
            return respuesta_reparacion("sin_reparacion", veredicto.diagnostico)
        return {"acciones": [a.model_dump() for a in acciones],
                "diagnostico": veredicto.diagnostico, "accion": None}  # fmt: skip

    @app.get(PREFIJO + "/cv/{token}")
    async def descargar_cv(token: str, nav: vinculos.Navegador = Depends(navegador_actual)):
        contenido, nombre, vence = descargas_cv.pop(token, (None, "", None))
        if contenido is None or vence < nucleo.ahora():
            raise HTTPException(404, "enlace vencido o ya usado")
        if isinstance(contenido, bytes):
            return Response(
                contenido, media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
            )  # fmt: skip
        if not contenido.is_file():
            raise HTTPException(404, "enlace vencido o ya usado")
        return FileResponse(contenido, media_type="application/pdf", filename=nombre)

    @app.post(PREFIJO + "/postulaciones/{pid}/envio")
    async def envio(pid: int, nav: vinculos.Navegador = Depends(navegador_actual)):
        """La extensión lo llama justo antes de pulsar enviar y espera la confirmación."""
        postulacion_de(pid, nav)
        if not nucleo.cola.marcar_envio_pulsado(pid, nav.id, nucleo.ahora()):
            raise HTTPException(409, "no se puede enviar esta postulación")
        return {"ok": True}

    @app.post(PREFIJO + "/postulaciones/{pid}/verificacion")
    async def verificacion(
        pid: int, cuerpo: Verificacion, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        postulacion_de(pid, nav)
        ahora = nucleo.ahora()
        if cuerpo.estado == "pendiente":
            ok = nucleo.cola.verificacion(pid, nav.id, ahora)
            if ok:
                await nucleo.notificar({"tipo": "verificacion", "postulacion_id": pid,
                                        "usuario_id": nav.usuario_id})  # fmt: skip
        else:
            ok = nucleo.cola.verificacion_resuelta(pid, nav.id, ahora)
        if not ok:
            raise HTTPException(409, "estado no válido")
        return {"ok": True}

    @app.post(PREFIJO + "/postulaciones/{pid}/resultado")
    async def resultado(
        pid: int, cuerpo: Resultado, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        postulacion_de(pid, nav)
        try:
            estado = E(cuerpo.estado)
        except ValueError as exc:
            raise HTTPException(422, "estado desconocido") from exc
        ahora = nucleo.ahora()
        try:
            evento = nucleo.cola.terminar(pid, nav.id, estado, ahora, cuerpo.motivo)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if evento is None:
            raise HTTPException(409, "la postulación no está activa en este navegador")
        if cuerpo.html:
            _guardar_evidencia(nucleo, pid, cuerpo.html[:MAX_HTML_EVIDENCIA], ahora)
        if cuerpo.confirmacion:
            nucleo.cola.registrar_paso(pid, nav.id, "confirmacion", cuerpo.confirmacion, ahora)
        await _aprender(nucleo, trazas, pid, estado, cuerpo, ahora)
        await nucleo.notificar(evento)
        return {"ok": True}

    @app.exception_handler(404)
    async def no_encontrado(request: Request, exc):
        return JSONResponse({"detail": "no encontrado"}, status_code=404)

    return app


def _portales_guardados(base: BaseAsistente, navegador_id: int) -> dict[str, dict]:
    fila = base.cx.execute(
        "SELECT portales_json FROM navegadores WHERE id = ?", (navegador_id,)
    ).fetchone()
    return json.loads(fila["portales_json"]) if fila and fila["portales_json"] else {}


async def _aprender(
    nucleo: Nucleo, trazas: recetas.Trazas, pid: int, estado: E, cuerpo: Resultado, ahora: datetime
) -> None:
    """Lo que enseña el resultado: refuerza o apaga la receta y los parches que llevó el
    trabajo, guarda la receta de un envío con señal explícita, un parche candidato si el
    bucle genérico reparó un paso declarado, y recuerda el dominio que exige cuenta."""
    base = nucleo.base
    fila = base.cx.execute(
        "SELECT tipo, plataforma, id_corto, receta_id, parches_json FROM postulaciones "
        "WHERE id = ?",
        (pid,),
    ).fetchone()
    ultima = trazas.ultima_url(pid)
    traza = trazas.sacar(pid)
    trazas.olvidar(pid)
    if fila is None:
        return
    ok, fallo = estado == E.ENVIADA, estado == E.FORMULARIO_DESCONOCIDO
    if fila["receta_id"] and (ok or fallo):
        if recetas.registrar_resultado_receta(base, fila["receta_id"], ok):
            await nucleo.notificar({"tipo": "receta_apagada", "receta_id": fila["receta_id"],
                                    "postulacion_id": pid})  # fmt: skip
    ids = json.loads(fila["parches_json"]) if fila["parches_json"] else []
    if ids and (ok or fallo):
        for cambio in recetas.resultado_parches(base, ids, ok, ahora):
            await nucleo.notificar({"tipo": f"parche_{cambio['estado']}", "parche_id": cambio["id"],
                                    "plataforma": cambio["plataforma"], "paso": cambio["paso"],
                                    "postulacion_id": pid})  # fmt: skip
    vacante = nucleo.vacante(fila["id_corto"]) if fila["id_corto"] else None
    url = traza[0] if traza else (vacante or {}).get("url")
    host = recetas.host_de(url)
    if ok and fila["tipo"] == "postular" and traza:
        recetas.guardar_receta(
            base, host=host, ruta=recetas.ruta_patron(url),
            familia=recetas.familia_de_host(host, fila["plataforma"]), receta=traza[1],
            origen="real", ahora=ahora, enviada=True,
        )  # fmt: skip
    if estado == E.ENSAYADA and fila["tipo"] in ("postular", "vigia") and traza:
        # El ensayo no envió: su receta sirve para el mapeo y los botones, sin señal de éxito
        recetas.guardar_receta(
            base, host=host, ruta=recetas.ruta_patron(url),
            familia=recetas.familia_de_host(host, fila["plataforma"]), receta=traza[1],
            origen="ensayo", ahora=ahora,
        )  # fmt: skip
    if (ok or estado == E.ENSAYADA) and cuerpo.parche and fila["plataforma"]:
        reparo = base.cx.execute(
            "SELECT 1 FROM postulacion_pasos WHERE postulacion_id = ? "
            "AND paso IN ('respaldo_generico', 'reparacion')",
            (pid,),
        ).fetchone()
        parche_id = reparo and recetas.proponer_parche(
            base, fila["plataforma"], cuerpo.parche.paso, cuerpo.parche.selector, ahora, pid
        )
        if parche_id:
            await nucleo.notificar({"tipo": "parche_nuevo", "parche_id": parche_id,
                                    "plataforma": fila["plataforma"], "paso": cuerpo.parche.paso,
                                    "postulacion_id": pid})  # fmt: skip
    if estado in (E.BLOQUEADA, E.RESPALDO, E.FORMULARIO_DESCONOCIDO) and cuerpo.motivo in (
        recetas.MOTIVOS_BARRERA
    ):
        host = recetas.host_de(ultima) or host  # el sitio donde apareció la barrera
        if recetas.marcar_barrera(base, host, cuerpo.motivo, ahora):
            await nucleo.notificar({"tipo": "dominio_barrera", "host": host,
                                    "motivo": cuerpo.motivo, "postulacion_id": pid})  # fmt: skip


def _con_aprendizaje(nucleo: Nucleo, p: Postulacion, trabajo: dict[str, Any]) -> None:
    """La receta del sitio (o de su familia) y los parches de la plataforma que lleva el
    trabajo; queda anotado cuáles para premiarlos o descartarlos con el resultado."""
    receta = None
    if p.tipo in ("postular", "vigia") and p.id_corto:
        url = (nucleo.vacante(p.id_corto) or {}).get("url")
        host = recetas.host_de(url)
        if host:
            receta = recetas.receta_para(
                nucleo.base, host, recetas.familia_de_host(host, p.plataforma),
                recetas.ruta_patron(url),
            )  # fmt: skip
    parches = recetas.parches_aplicables(nucleo.base, p.plataforma) if p.plataforma else []
    if receta:
        trabajo["receta"] = receta
    if parches:
        trabajo["parches"] = parches
    with nucleo.base.transaccion() as cx:
        cx.execute(
            "UPDATE postulaciones SET receta_id = ?, parches_json = ? WHERE id = ?",
            (receta["id"] if receta else None,
             json.dumps([x["id"] for x in parches]) if parches else None, p.id),
        )  # fmt: skip


def _trabajo(nucleo: Nucleo, p: Postulacion) -> dict[str, Any]:
    # Para la extensión el ensayo del vigía es una postulación en ensayo
    tipo = "postular" if p.tipo == Tipo.VIGIA else p.tipo
    trabajo: dict[str, Any] = {"id": p.id, "tipo": tipo, "plataforma": p.plataforma}
    fila = nucleo.base.cx.execute(
        "SELECT actualizar_cv_portal FROM usuarios WHERE id = ?", (p.usuario_id,)
    ).fetchone()
    # Sin la autorización del usuario la extensión no toca el CV guardado en el portal
    trabajo["actualizar_cv_portal"] = bool(fila and fila["actualizar_cv_portal"])
    motor = nucleo.config.motor_generico
    if motor.activo:
        # Topes del bucle genérico y si respalda a los flujos declarados (la extensión 1.1.x
        # ignora esta clave)
        trabajo["motor_generico"] = {
            "respaldo_declarado": motor.respaldo_declarado,
            "max_pantallas": motor.max_pantallas,
            "max_pantallas_una_pregunta": motor.max_pantallas_una_pregunta,
            "max_minutos": motor.max_minutos,
        }
    if p.id_corto:
        vacante = nucleo.vacante(p.id_corto) or {}
        trabajo["url"] = vacante.get("url")
        trabajo["titulo"] = vacante.get("titulo")
    if nucleo.en_ensayo(p):
        # La extensión llena y avanza como siempre y se detiene justo antes de registrar el envío
        # (la 1.1.x ignora esta clave: por eso `version_minima` sube con el ensayo)
        trabajo["ensayo"] = True
    if motor.activo and (resuelto := nucleo.esquema_resuelto(p)):
        # Esquema anticipado: lo ya respondido, por clave de campo; la extensión llena esos
        # campos sin consultar al servidor (la 1.1.x ignora esta clave)
        trabajo["esquema"] = {"respuestas": resuelto}
    if motor.activo:
        _con_aprendizaje(nucleo, p, trabajo)
    return trabajo


def _guardar_evidencia(nucleo: Nucleo, pid: int, documento: str, ahora: datetime) -> None:
    carpeta = nucleo.archivos / "postulaciones" / str(pid)
    carpeta.mkdir(parents=True, exist_ok=True)
    carpeta.chmod(0o700)
    archivo = carpeta / f"{ahora.strftime('%Y%m%dT%H%M%S')}.html"
    archivo.write_text(sin_valores(documento), encoding="utf-8")
    with nucleo.base.transaccion() as cx:
        cx.execute(
            "INSERT INTO evidencia(postulacion_id, ts, tipo, archivo) VALUES (?, ?, 'html', ?)",
            (pid, a_texto(ahora), str(archivo)),
        )


Notificar = Callable[[Evento | dict], Awaitable[None]]
