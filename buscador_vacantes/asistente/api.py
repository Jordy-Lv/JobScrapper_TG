"""API v1 para la extensión de navegador (FastAPI). Se publica con Tailscale Funnel.

Todo vive bajo /api/v1/; cualquier otra ruta responde 404. Cada navegador se autentica con su
token (Authorization: Bearer); el servidor solo guarda su hash.
"""

from __future__ import annotations

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
from typing import Any, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente import vinculos
from buscador_vacantes.asistente.cola import Cola, E, Evento, Postulacion, Tipo
from buscador_vacantes.asistente.cuentas_portal import CuentasPortal, EstadoCuenta
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.preferencias import Preferencias
from buscador_vacantes.asistente.respuestas import Pregunta, Respuesta
from buscador_vacantes.estado import a_texto

log = logging.getLogger(__name__)

PREFIJO = "/api/v1"
MAX_CUERPO = 512 * 1024
MAX_HTML_EVIDENCIA = 300 * 1024
LIMITE_POR_MINUTO = 120
LIMITE_VINCULAR_POR_MINUTO = 20
VIGENCIA_CV = timedelta(minutes=10)


# --- contrato con el resto del asistente --------------------------------------------------


@dataclass
class ResultadoFormulario:
    respuestas: list[Respuesta] = field(default_factory=list)
    faltan: list[Respuesta] = field(default_factory=list)
    cv: Path | None = None  # PDF a adjuntar o subir al perfil del portal


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


class PreferenciasPortalCuerpo(BaseModel):
    automatico: bool = True
    umbral: int | None = Field(None, ge=0, le=100)
    avisar: bool = True


class Campo(BaseModel):
    texto: str = Field(max_length=1000)
    tipo: str = Field("texto", max_length=20)
    opciones: list[str] = Field(default_factory=list, max_length=100)
    obligatoria: bool = True
    nombre: str | None = Field(None, max_length=200)


class Formulario(BaseModel):
    campos: list[Campo] = Field(max_length=80)


class Paso(BaseModel):
    paso: str = Field(max_length=60)
    detalle: str | None = Field(None, max_length=2000)


class Verificacion(BaseModel):
    estado: str = Field(pattern="^(pendiente|resuelta)$")


class Resultado(BaseModel):
    estado: str
    motivo: str | None = Field(None, max_length=500)
    html: str | None = None  # evidencia, con los valores de los campos borrados
    confirmacion: str | None = Field(None, max_length=500)


# --- utilidades ---------------------------------------------------------------------------


def version_tupla(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)


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
<style>body{{font-family:system-ui,sans-serif;max-width:560px;margin:48px auto;padding:0 16px;
color:#1f2937}}h1{{color:#1f3a5f;font-size:1.4rem}}code{{font-size:1.3rem;background:#eef2f7;
padding:4px 8px;border-radius:6px}}.ok{{color:#2e7d4f}}.error{{color:#b42318}}</style></head>
<body><h1>Vincular tu navegador</h1>
<div id="asistente-vinculo" data-codigo="{codigo}" data-api="{api}"></div>
<p id="estado">Si tienes la extensión del asistente instalada, este navegador se vincula solo en
unos segundos.</p>
<p>¿No pasa nada? Instala la extensión, vuelve a abrir este enlace o escribe en la extensión
el código <code>{visible}</code> (vence en 10 minutos).</p>
</body></html>"""

PAGINA_PRIVACIDAD = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Política de privacidad · Asistente de postulación</title>
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;
color:#1f2937;line-height:1.55}h1{color:#1f3a5f;font-size:1.5rem}h2{color:#1f3a5f;
font-size:1.1rem;margin-top:1.8em}</style></head>
<body><h1>Política de privacidad de la extensión «Asistente de postulación»</h1>
<p>Última actualización: 4 de octubre de 2026.</p>
<p>La extensión es parte de un asistente privado para los miembros del canal de Telegram
«JOBS - PRÁCTICAS/APRENDIZ». Postula a vacantes de Computrabajo y Magneto (y, si el usuario las
activa, de elempleo, GetOnBoard, LinkedIn y el Servicio Público de Empleo) desde el navegador
del propio usuario, con su sesión, cuando el usuario lo pide desde el bot de Telegram.</p>
<h2>Qué datos usa la extensión</h2>
<ul>
<li><b>Token del navegador</b>: un código aleatorio que se guarda en el navegador para
identificarlo ante el servidor del asistente. El servidor solo guarda su huella (hash).</li>
<li><b>Estado de los portales</b>: si hay una sesión iniciada en Computrabajo o Magneto y el
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
    descargas_cv: dict[str, tuple[Path, datetime]] = {}

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

    def postulacion_de(pid: int, nav: vinculos.Navegador) -> Postulacion:
        p = nucleo.cola.obtener(pid)
        if p is None or p.usuario_id != nav.usuario_id:
            raise HTTPException(404, "postulación no encontrada")
        return p

    # --- vinculación ---

    @app.get(PREFIJO + "/vincular/{codigo}", response_class=HTMLResponse)
    async def pagina_vinculo(codigo: str):
        codigo = vinculos.normalizar_codigo(codigo)[:8]
        return PAGINA_VINCULO.format(
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
        for plataforma, portal in cuerpo.portales.items():
            if plataforma not in nucleo.config.plataformas:
                continue
            if portal.estado == "sin_sesion":
                if portal.motivo:
                    log.info("%s sin sesión en el navegador %s: %s", plataforma, nav.id,
                             portal.motivo)  # fmt: skip
                cuentas_ok[plataforma] = False
                continue
            if portal.pagina_correo:
                # Solo la ruta, sin el correo: indica qué página fijar en los selectores
                log.info("Correo de %s leído en %s", plataforma, portal.pagina_correo)
            verificacion = nucleo.cuentas.verificar(
                nav.usuario_id, plataforma, portal.correo, ahora
            )
            ok = verificacion.estado == EstadoCuenta.OK
            cuentas_ok[plataforma] = ok
            previo = anteriores.get(plataforma, {})
            if verificacion.estado != EstadoCuenta.OK and (
                verificacion.nuevo or previo.get("cuenta") != verificacion.estado
            ):
                await nucleo.notificar({
                    "tipo": f"cuenta_{verificacion.estado}", "usuario_id": nav.usuario_id,
                    "plataforma": plataforma, "asociado": verificacion.asociado,
                    "encontrado": verificacion.encontrado_oculto,
                })  # fmt: skip
            elif ok and previo.get("estado") != portal.estado:
                await nucleo.notificar({
                    "tipo": f"portal_{portal.estado}", "usuario_id": nav.usuario_id,
                    "plataforma": plataforma, "asociado": verificacion.asociado,
                })  # fmt: skip
            if ok:
                disponibles.add(plataforma)
                if portal.estado == "incompleto":
                    nucleo.cola.encolar_completar_perfil(nav.usuario_id, plataforma, ahora)
            anteriores[plataforma] = {"estado": portal.estado, "cuenta": verificacion.estado}
        with nucleo.base.transaccion() as cx:
            cx.execute(
                "UPDATE navegadores SET ultimo_latido = ?, version = ?, portales_json = ? "
                "WHERE id = ?",
                (a_texto(ahora), cuerpo.version, json.dumps(anteriores), nav.id),
            )
        listos = {p for p in disponibles if cuerpo.portales[p].estado == "listo"}
        nucleo.cola.portales_actualizados(nav.usuario_id, listos, ahora)

        version_minima = nucleo.config.extension.version_minima
        actualizar = version_tupla(cuerpo.version) < version_tupla(version_minima)
        trabajo = None
        if not actualizar:
            siguiente = nucleo.cola.siguiente(nav.usuario_id, disponibles, ahora)
            if siguiente and (
                siguiente.tipo == Tipo.COMPLETAR_PERFIL or siguiente.plataforma in listos
            ):
                trabajo = _trabajo(nucleo, siguiente)
        selectores = {p: s[0] for p in nucleo.config.plataformas if (s := nucleo.selectores(p))}
        return {
            "trabajo": trabajo,
            "version_minima": version_minima,
            "actualizar": actualizar,
            "selectores": selectores,
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
        )  # fmt: skip
        return {"ok": True}

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
        return {"ok": True}

    @app.post(PREFIJO + "/postulaciones/{pid}/formulario")
    async def formulario(
        pid: int, cuerpo: Formulario, nav: vinculos.Navegador = Depends(navegador_actual)
    ):
        p = postulacion_de(pid, nav)
        if p.navegador_id != nav.id or p.estado != E.EN_CURSO:
            raise HTTPException(409, "la postulación no está en curso en este navegador")
        preguntas = [Pregunta(c.texto, c.tipo, c.opciones, c.obligatoria, c.nombre)
                     for c in cuerpo.campos]  # fmt: skip
        resultado = await nucleo.resolver_formulario(p, preguntas)
        if any(r.pregunta.obligatoria for r in resultado.faltan):
            nucleo.cola.esperar_usuario(pid, nav.id, nucleo.ahora())
            return {"esperar_usuario": True}
        respuestas = []
        for indice, pregunta in enumerate(preguntas):
            r = next((x for x in resultado.respuestas if x.pregunta is pregunta), None)
            if r is None or r.falta:
                continue
            respuestas.append({"indice": indice, "valor": r.valor, "opcion": r.opcion,
                               "origen": r.origen})  # fmt: skip
        cv_url = None
        if resultado.cv is not None:
            token = secrets.token_urlsafe(24)
            descargas_cv[token] = (resultado.cv, nucleo.ahora() + VIGENCIA_CV)
            cv_url = f"{PREFIJO}/cv/{token}"
        return {"esperar_usuario": False, "respuestas": respuestas, "cv_url": cv_url,
                "cv_nombre": resultado.cv.name if resultado.cv else None}  # fmt: skip

    @app.get(PREFIJO + "/cv/{token}")
    async def descargar_cv(token: str, nav: vinculos.Navegador = Depends(navegador_actual)):
        ruta, vence = descargas_cv.pop(token, (None, None))
        if ruta is None or vence < nucleo.ahora() or not ruta.is_file():
            raise HTTPException(404, "enlace vencido o ya usado")
        return FileResponse(ruta, media_type="application/pdf", filename=ruta.name)

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


def _trabajo(nucleo: Nucleo, p: Postulacion) -> dict[str, Any]:
    trabajo: dict[str, Any] = {"id": p.id, "tipo": p.tipo, "plataforma": p.plataforma}
    fila = nucleo.base.cx.execute(
        "SELECT actualizar_cv_portal FROM usuarios WHERE id = ?", (p.usuario_id,)
    ).fetchone()
    # Sin la autorización del usuario la extensión no toca el CV guardado en el portal
    trabajo["actualizar_cv_portal"] = bool(fila and fila["actualizar_cv_portal"])
    if p.id_corto:
        vacante = nucleo.vacante(p.id_corto) or {}
        trabajo["url"] = vacante.get("url")
        trabajo["titulo"] = vacante.get("titulo")
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
