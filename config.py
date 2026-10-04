"""Carga y validación de config.yaml (configuración funcional) y .env (secretos)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from modelo import Categoria

RAIZ = Path(__file__).resolve().parent


class ErrorConfiguracion(Exception):
    """Configuración inválida o secreto faltante. El mensaje es apto para el usuario."""


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rutas(Modelo):
    base_datos: Path = Path("data/vacantes.db")
    logs: Path = Path("logs")
    lock: Path = Path("data/buscador.lock")


class Registro(Modelo):
    retencion_dias: int = Field(14, ge=1)


class Red(Modelo):
    timeout_s: float = Field(20, gt=0)
    pausa_min_s: float = Field(4, ge=0)
    pausa_max_s: float = Field(10, ge=0)
    user_agent: str
    accept_language: str = "es-CO,es;q=0.9"
    cooldown_horas: list[float] = Field(default_factory=lambda: [2, 6, 24], min_length=1)
    marcadores_desafio: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pausas(self) -> Red:
        if self.pausa_max_s < self.pausa_min_s:
            raise ValueError("pausa_max_s debe ser mayor o igual que pausa_min_s")
        return self


class PalabrasClave(Modelo):
    nucleo: list[str] = Field(min_length=1)
    cola_larga: dict[str, list[str]] = Field(min_length=1)

    @property
    def cola_larga_plana(self) -> list[str]:
        """Cola larga en el orden del archivo, sin repetidos."""
        vistas: dict[str, None] = {}
        for terminos in self.cola_larga.values():
            for termino in terminos:
                vistas.setdefault(termino, None)
        return list(vistas)


class Fuente(Modelo):
    activa: bool = True
    presupuesto: int = Field(ge=0)
    reservado_nucleo: int = Field(1, ge=0)
    filtra_nivel: bool = False  # la fuente ya filtra por nivel de experiencia
    nota: str | None = None
    opciones: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reserva(self) -> Fuente:
        if self.reservado_nucleo > self.presupuesto:
            raise ValueError("reservado_nucleo no puede superar el presupuesto")
        return self


class Area(Modelo):
    categoria: Categoria
    terminos: list[str] = Field(min_length=1)


class Nivel(Modelo):
    practica: list[str] = Field(min_length=1)
    junior: list[str] = Field(min_length=1)


class Ubicacion(Modelo):
    colombia: list[str] = Field(min_length=1)
    remoto: list[str] = Field(min_length=1)
    latam: list[str] = Field(min_length=1)
    exterior: list[str] = Field(default_factory=list)
    patrones_restriccion: list[str] = Field(default_factory=list)
    fuentes_colombianas: list[str] = Field(default_factory=list)


class Filtros(Modelo):
    max_dias_publicada: int = Field(15, ge=1)
    exclusion_seniority: list[str] = Field(min_length=1)
    anios_experiencia_excluidos_desde: int = Field(3, ge=1)
    frases_ignoradas: list[str] = Field(default_factory=list)
    nivel: Nivel
    areas: list[Area] = Field(min_length=1)
    ti_generico: list[str] = Field(min_length=1)
    disparadores_dudosa: list[str] = Field(min_length=1)
    areas_no_ti: list[str] = Field(default_factory=list)
    ubicacion: Ubicacion

    @model_validator(mode="after")
    def _categorias_de_area(self) -> Filtros:
        invalidas = {Categoria.PRACTICAS, Categoria.OTROS_TI}
        for area in self.areas:
            if area.categoria in invalidas:
                raise ValueError(f"la categoría '{area.categoria}' no se asigna por área")
        return self


class TokenHermes(Modelo):
    archivo: Path
    variable: str = "TELEGRAM_BOT_TOKEN"


class Telegram(Modelo):
    modo: Literal["bot_api", "hermes_cli"] = "bot_api"
    token_hermes: TokenHermes | None = None
    hermes_comando: str = "hermes"
    timeout_s: float = Field(20, gt=0)


class Banner(Modelo):
    modo: Literal["diario", "nunca", "siempre"] = "diario"
    imagen: Path = Path("assets/encabezado_vacantes.jpg")


class PresupuestoIA(Modelo):
    clasificador: int = Field(60, ge=0)
    reportero: int = Field(8, ge=0)
    resumen: int = Field(1, ge=0)


class IA(Modelo):
    base_url: str = "https://api.deepseek.com"
    modelo: str = "deepseek-chat"
    timeout_s: float = Field(60, gt=0)
    saldo_minimo_usd: float = Field(1.0, ge=0)
    saldo_cache_min: float = Field(10, ge=0)
    presupuesto_dia: PresupuestoIA = Field(default_factory=PresupuestoIA)


class Clasificador(Modelo):
    activo: bool = True
    max_vacantes_por_llamada: int = Field(30, ge=1)
    politica_sin_ia: Literal["descartar", "aceptar"] = "descartar"
    horas_vencimiento_pendiente: float = Field(24, gt=0)
    temperatura: float = Field(0, ge=0, le=2)
    prompt_sistema: str


class Reportero(Modelo):
    activo: bool = True
    temperatura: float = Field(0.2, ge=0, le=2)
    max_tokens: int = Field(700, gt=0)
    max_muestra_cuerpo: int = Field(3000, gt=0)
    prompt_sistema: str


class Resumen(Modelo):
    activo: bool = True
    temperatura: float = Field(0.3, ge=0, le=2)
    max_tokens: int = Field(900, gt=0)
    prompt_sistema: str


class Incidentes(Modelo):
    corridas_bloqueo: int = Field(2, ge=1)
    corridas_error_servidor: int = Field(3, ge=1)
    umbral_caida_volumen: float = Field(0.30, gt=0, lt=1)
    horas_recordatorio: float = Field(24, gt=0)


class Estado(Modelo):
    dias_vistas: int = Field(90, ge=1)
    dias_intentos: int = Field(30, ge=1)


class Salud(Modelo):
    activo: bool = True
    timeout_s: float = Field(10, gt=0)


class Operacion(Modelo):
    timeout_corrida_min: float = Field(25, gt=0)


class Configuracion(Modelo):
    zona_horaria: str = "America/Bogota"
    rutas: Rutas = Field(default_factory=Rutas)
    registro: Registro = Field(default_factory=Registro)
    red: Red
    palabras_clave: PalabrasClave
    fuentes: dict[str, Fuente] = Field(min_length=1)
    filtros: Filtros
    telegram: Telegram = Field(default_factory=Telegram)
    banner: Banner = Field(default_factory=Banner)
    ia: IA = Field(default_factory=IA)
    clasificador: Clasificador
    reportero: Reportero
    resumen: Resumen
    incidentes: Incidentes = Field(default_factory=Incidentes)
    estado: Estado = Field(default_factory=Estado)
    salud: Salud = Field(default_factory=Salud)
    operacion: Operacion = Field(default_factory=Operacion)

    @property
    def usa_ia(self) -> bool:
        return self.clasificador.activo or self.reportero.activo or self.resumen.activo


class Secretos(BaseModel):
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_chat_prueba: str | None = None
    deepseek_api_key: str | None = None
    healthcheck_url: str | None = None

    def valores(self) -> list[str]:
        """Valores de secretos presentes, para enmascararlos en los logs."""
        return [v for v in self.model_dump().values() if v]


def _formatear_errores(error: ValidationError) -> str:
    lineas = []
    for detalle in error.errors():
        campo = ".".join(str(parte) for parte in detalle["loc"]) or "(raíz)"
        lineas.append(f"  - {campo}: {detalle['msg']}")
    return "\n".join(lineas)


def cargar_configuracion(ruta: Path | str = RAIZ / "config.yaml") -> Configuracion:
    ruta = Path(ruta)
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ErrorConfiguracion(f"No existe el archivo de configuración {ruta}") from exc
    except yaml.YAMLError as exc:
        raise ErrorConfiguracion(f"{ruta} no es YAML válido: {exc}") from exc
    if not isinstance(datos, dict):
        raise ErrorConfiguracion(f"{ruta} debe contener un diccionario en la raíz")
    try:
        return Configuracion.model_validate(datos)
    except ValidationError as exc:
        raise ErrorConfiguracion(
            f"Configuración inválida en {ruta}:\n{_formatear_errores(exc)}"
        ) from exc


def _leer_token_hermes(token: TokenHermes) -> str | None:
    archivo = token.archivo.expanduser()
    if not archivo.is_file():
        return None
    valor = dotenv_values(archivo).get(token.variable)
    return valor.strip() if valor else None


def cargar_secretos(
    config: Configuracion,
    ruta_env: Path | str = RAIZ / ".env",
    *,
    exigir_envio: bool = True,
    exigir_chat_prueba: bool = False,
    exigir_salud: bool | None = None,
) -> Secretos:
    """Lee los secretos del .env (las variables de entorno tienen prioridad).

    Con ``exigir_envio=False`` (dry-run) no se exigen el token ni los ids de chat.
    El token se lee en cada corrida, primero del .env y si no de la configuración de Hermes.
    """
    ruta_env = Path(ruta_env)
    archivo = dotenv_values(ruta_env) if ruta_env.is_file() else {}

    def leer(nombre: str) -> str | None:
        valor = os.environ.get(nombre) or archivo.get(nombre)
        return valor.strip() if valor and valor.strip() else None

    secretos = Secretos(
        telegram_bot_token=leer("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=leer("TELEGRAM_CHAT_ID"),
        telegram_chat_prueba=leer("TELEGRAM_CHAT_PRUEBA"),
        deepseek_api_key=leer("DEEPSEEK_API_KEY"),
        healthcheck_url=leer("HEALTHCHECK_URL"),
    )
    if not secretos.telegram_bot_token and config.telegram.token_hermes:
        secretos.telegram_bot_token = _leer_token_hermes(config.telegram.token_hermes)

    faltantes = []
    if exigir_envio:
        if config.telegram.modo == "bot_api" and not secretos.telegram_bot_token:
            faltantes.append(
                "TELEGRAM_BOT_TOKEN (en .env o en el archivo de telegram.token_hermes)"
            )
        if not secretos.telegram_chat_id:
            faltantes.append("TELEGRAM_CHAT_ID")
        if config.usa_ia and not secretos.deepseek_api_key:
            faltantes.append("DEEPSEEK_API_KEY (la IA está activada en config.yaml)")
        if exigir_salud is None:
            exigir_salud = config.salud.activo
        if exigir_salud and not secretos.healthcheck_url:
            faltantes.append("HEALTHCHECK_URL (salud.activo está en true)")
    if exigir_chat_prueba and not secretos.telegram_chat_prueba:
        faltantes.append("TELEGRAM_CHAT_PRUEBA (necesario para el chat de prueba)")
    if faltantes:
        lista = "\n".join(f"  - {nombre}" for nombre in faltantes)
        raise ErrorConfiguracion(f"Faltan secretos obligatorios en {ruta_env}:\n{lista}")
    return secretos
