"""Base propia del asistente (data/asistente.db, WAL) y acceso de solo lectura a vacantes.db."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ESQUEMA_VERSION = 2

ESQUEMA = """
CREATE TABLE IF NOT EXISTS esquema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS kv (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

-- Usuarios: miembros del grupo privado. Sin datos hasta aceptar la política.
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    nombre TEXT,
    estado TEXT NOT NULL DEFAULT 'alta',      -- alta | activo | suspendido | inactivo
    motivo_estado TEXT,
    paso_alta TEXT,
    directorio TEXT NOT NULL UNIQUE,           -- uuid de data/asistente/usuarios/<uuid>/
    creado TEXT NOT NULL,
    ultima_actividad TEXT,
    politica_version INTEGER,
    politica_aceptada_en TEXT,
    miembro_verificado_en TEXT,
    gemini_clave TEXT,                         -- cifrada (Fernet)
    gemini_ult4 TEXT,
    gemini_valida INTEGER,
    perfil_json TEXT,
    enfoque_json TEXT,
    cuestionario_json TEXT,
    cv_archivo TEXT,                           -- CV original subido por el usuario
    cv_base_archivo TEXT,                      -- CV base generado
    actualizar_cv_portal INTEGER,
    automatico_umbral INTEGER,                 -- NULL: modo automático desactivado
    pausado INTEGER NOT NULL DEFAULT 0,
    vacante_pendiente TEXT,                    -- id_corto a retomar al terminar el alta
    aviso_inactividad_en TEXT
);

CREATE TABLE IF NOT EXISTS codigos_vinculo (
    codigo TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creado TEXT NOT NULL,
    vence TEXT NOT NULL,
    usado INTEGER NOT NULL DEFAULT 0,
    intentos INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS navegadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    nombre TEXT,
    version TEXT,
    creado TEXT NOT NULL,
    ultimo_latido TEXT,
    portales_json TEXT,                        -- {plataforma: {estado, cuenta_ok}}
    revocado INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cuentas_portal (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    plataforma TEXT NOT NULL,
    correo_cifrado TEXT NOT NULL,
    correo_hash TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente | confirmada
    confirmada_en TEXT,
    PRIMARY KEY (usuario_id, plataforma)
);

-- Preferencias del usuario por portal (botón del engranaje en la extensión). Sin fila: valores
-- por defecto (participa del modo automático, sin afinidad propia, avisa por Telegram).
CREATE TABLE IF NOT EXISTS preferencias_portal (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    plataforma TEXT NOT NULL,
    automatico INTEGER NOT NULL DEFAULT 1,     -- participa del modo automático del usuario
    umbral INTEGER,                            -- afinidad mínima propia; NULL: la del usuario
    avisar INTEGER NOT NULL DEFAULT 1,         -- avisar por Telegram las postulaciones solas
    actualizada TEXT,
    PRIMARY KEY (usuario_id, plataforma)
);

-- Índice de vacantes publicadas (id corto del enlace) y caché de su detalle.
CREATE TABLE IF NOT EXISTS vacantes (
    id_corto TEXT PRIMARY KEY,
    clave TEXT NOT NULL UNIQUE,
    fuente TEXT NOT NULL,
    plataforma TEXT,                           -- computrabajo | magneto | NULL
    url TEXT NOT NULL,
    titulo TEXT,
    empresa TEXT,
    categoria TEXT,
    enviada_en TEXT,
    detalle TEXT,
    estado_pagina TEXT,                        -- ok | cerrada | bloqueada
    detalle_en TEXT,
    requisitos_json TEXT,
    indexada_en TEXT NOT NULL,
    ficha_json TEXT                            -- salario, ubicación… (esquema 2)
);

CREATE TABLE IF NOT EXISTS postulaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    id_corto TEXT,                             -- NULL en trabajos completar_perfil
    tipo TEXT NOT NULL DEFAULT 'postular',     -- postular | completar_perfil
    plataforma TEXT,
    estado TEXT NOT NULL,
    motivo TEXT,
    origen TEXT NOT NULL DEFAULT 'boton',      -- boton | automatico
    navegador_id INTEGER REFERENCES navegadores(id) ON DELETE SET NULL,
    envio_pulsado INTEGER NOT NULL DEFAULT 0,
    cv_archivo TEXT,
    afinidad INTEGER,
    mensaje_id INTEGER,
    creada TEXT NOT NULL,
    actualizada TEXT NOT NULL,
    tomada_en TEXT,
    terminada_en TEXT,
    seguimiento TEXT,
    recordado INTEGER NOT NULL DEFAULT 0,
    UNIQUE (usuario_id, id_corto)
);
CREATE INDEX IF NOT EXISTS postulaciones_estado ON postulaciones(estado, creada);

CREATE TABLE IF NOT EXISTS postulacion_pasos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulacion_id INTEGER NOT NULL REFERENCES postulaciones(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    estado TEXT,
    paso TEXT NOT NULL,
    detalle TEXT
);

CREATE TABLE IF NOT EXISTS respuestas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulacion_id INTEGER NOT NULL REFERENCES postulaciones(id) ON DELETE CASCADE,
    campo TEXT,
    pregunta TEXT NOT NULL,
    respuesta TEXT,
    origen TEXT NOT NULL                       -- perfil | banco | aprendida | ia | usuario
);

CREATE TABLE IF NOT EXISTS evidencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulacion_id INTEGER NOT NULL REFERENCES postulaciones(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    tipo TEXT NOT NULL,                        -- html | captura
    archivo TEXT NOT NULL
);

-- Qué dato pide cada pregunta: compartido entre usuarios, sin respuestas personales.
CREATE TABLE IF NOT EXISTS banco_preguntas (
    pregunta_norm TEXT PRIMARY KEY,
    campo TEXT NOT NULL,
    parametro TEXT,
    origen TEXT NOT NULL,                      -- semilla | ia
    usos INTEGER NOT NULL DEFAULT 0,
    creada TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS respuestas_aprendidas (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    pregunta_norm TEXT NOT NULL,
    respuesta TEXT NOT NULL,
    actualizada TEXT NOT NULL,
    PRIMARY KEY (usuario_id, pregunta_norm)
);

CREATE TABLE IF NOT EXISTS pendientes_usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    postulacion_id INTEGER REFERENCES postulaciones(id) ON DELETE CASCADE,
    pregunta TEXT NOT NULL,
    pregunta_norm TEXT NOT NULL,
    opciones_json TEXT,
    campo TEXT,
    creada TEXT NOT NULL,
    respondida_en TEXT,
    respuesta TEXT
);

CREATE TABLE IF NOT EXISTS selectores (
    plataforma TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    contenido_json TEXT NOT NULL,
    cargado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ia_uso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    tarea TEXT NOT NULL,
    ok INTEGER NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    motivo TEXT
);
CREATE INDEX IF NOT EXISTS ia_uso_usuario_ts ON ia_uso(usuario_id, ts);

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor INTEGER NOT NULL,                    -- telegram_id de quien actúa
    accion TEXT NOT NULL,
    objetivo TEXT,
    detalle TEXT
);

CREATE TABLE IF NOT EXISTS bajas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL
);
"""


class BaseAsistente:
    """Conexión a data/asistente.db. Cada hilo o tarea larga abre la suya."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self.cx = conexion

    @classmethod
    def abrir(cls, ruta: Path | str) -> BaseAsistente:
        ruta = Path(ruta)
        if str(ruta) != ":memory:":
            ruta.parent.mkdir(parents=True, exist_ok=True)
        cx = sqlite3.connect(ruta, timeout=30, check_same_thread=False)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA journal_mode=WAL")
        cx.execute("PRAGMA synchronous=NORMAL")
        cx.execute("PRAGMA foreign_keys=ON")
        base = cls(cx)
        base._migrar_esquema()
        return base

    def cerrar(self) -> None:
        self.cx.close()

    def _migrar_esquema(self) -> None:
        with self.cx:
            self.cx.executescript(ESQUEMA)
            fila = self.cx.execute("SELECT version FROM esquema_version").fetchone()
            if fila is None:
                self.cx.execute("INSERT INTO esquema_version VALUES (?)", (ESQUEMA_VERSION,))
            elif fila["version"] > ESQUEMA_VERSION:
                raise RuntimeError(
                    f"asistente.db tiene esquema {fila['version']} y el código soporta "
                    f"hasta {ESQUEMA_VERSION}"
                )
            elif fila["version"] < ESQUEMA_VERSION:
                self._actualizar_desde(fila["version"])
                self.cx.execute("UPDATE esquema_version SET version = ?", (ESQUEMA_VERSION,))

    def _actualizar_desde(self, version: int) -> None:
        """Cambios a una base existente (CREATE TABLE IF NOT EXISTS no agrega columnas)."""
        if version < 2:
            columnas = {f["name"] for f in self.cx.execute("PRAGMA table_info(vacantes)")}
            if "ficha_json" not in columnas:
                self.cx.execute("ALTER TABLE vacantes ADD COLUMN ficha_json TEXT")

    @contextmanager
    def transaccion(self) -> Iterator[sqlite3.Connection]:
        with self.cx:
            yield self.cx

    def tablas(self) -> list[str]:
        filas = self.cx.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return sorted(f["name"] for f in filas if not f["name"].startswith("sqlite_"))

    def kv_obtener(self, clave: str) -> str | None:
        fila = self.cx.execute("SELECT valor FROM kv WHERE clave = ?", (clave,)).fetchone()
        return fila["valor"] if fila else None

    def kv_guardar(self, clave: str, valor: str) -> None:
        with self.cx:
            self.cx.execute(
                "INSERT INTO kv(clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor),
            )


def abrir_vacantes_ro(ruta: Path | str) -> sqlite3.Connection:
    """Abre vacantes.db del buscador en solo lectura: el asistente nunca escribe en ella."""
    uri = Path(ruta).resolve().as_uri() + "?mode=ro"
    cx = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    return cx
