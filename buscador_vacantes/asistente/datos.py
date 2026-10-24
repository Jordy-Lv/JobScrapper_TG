"""Base propia del asistente (data/asistente.db, WAL) y acceso de solo lectura a vacantes.db."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ESQUEMA_VERSION = 7

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
    aviso_inactividad_en TEXT,
    nivel_ia TEXT NOT NULL DEFAULT 'normal',   -- ahorro | normal | maximo (esquema 6)
    ensayo INTEGER NOT NULL DEFAULT 0          -- 1: sus postulaciones se ensayan (esquema 7)
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

-- Plataformas que el dueño (o el vigía) puso en ensayo para todos los usuarios (esquema 7); se
-- suman a `asistente.ensayo.plataformas` de la configuración
CREATE TABLE IF NOT EXISTS plataformas_en_ensayo (
    plataforma TEXT PRIMARY KEY,
    motivo TEXT,
    desde TEXT NOT NULL
);

-- Documentos PDF del usuario además del CV (esquema 7): el archivo vive cifrado en su carpeta
CREATE TABLE IF NOT EXISTS documentos_usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,                        -- certificado_notas | carta | portafolio | otro
    nombre TEXT NOT NULL,
    ruta TEXT NOT NULL,                        -- archivo cifrado (Fernet)
    bytes INTEGER NOT NULL,                    -- tamaño del PDF en claro
    creado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS documentos_usuario_tipo ON documentos_usuario(usuario_id, tipo);

-- Preferencias del usuario por portal (botón del engranaje en la extensión). Sin fila: valores
-- por defecto (participa del modo automático, sin afinidad propia, avisa por Telegram).
CREATE TABLE IF NOT EXISTS preferencias_portal (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    plataforma TEXT NOT NULL,
    automatico INTEGER NOT NULL DEFAULT 1,     -- participa del modo automático del usuario
    umbral INTEGER,                            -- afinidad mínima propia; NULL: la del usuario
    avisar INTEGER NOT NULL DEFAULT 1,         -- avisar por Telegram las postulaciones solas
    revisar_respuestas INTEGER NOT NULL DEFAULT 0,  -- mostrar lo redactado antes de enviar (4)
    actualizada TEXT,
    PRIMARY KEY (usuario_id, plataforma)
);

-- Índice de vacantes publicadas (id corto del enlace) y caché de su detalle.
CREATE TABLE IF NOT EXISTS vacantes (
    id_corto TEXT PRIMARY KEY,
    clave TEXT NOT NULL UNIQUE,
    fuente TEXT NOT NULL,
    plataforma TEXT,                           -- clave de vacantes.PLATAFORMAS o NULL
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
    ficha_json TEXT,                           -- salario, ubicación… (esquema 2)
    esquema_json TEXT                          -- campos del formulario leídos de antemano (7)
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
    receta_id INTEGER,                         -- receta que llevó el trabajo (esquema 5)
    parches_json TEXT,                         -- ids de los parches que llevó (esquema 5)
    nivel_ia TEXT,                             -- nivel del usuario al encolar (esquema 6)
    forzar_real INTEGER NOT NULL DEFAULT 0,    -- 1: «Enviar de verdad», aunque haya ensayo (7)
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
    origen TEXT NOT NULL,                      -- perfil | banco | aprendida | ia | usuario
    pregunta_norm TEXT,                        -- esquema 4: una fila por pregunta
    estado TEXT NOT NULL DEFAULT 'enviada'     -- enviada | propuesta | aprobada
);

-- Mensajes del bot que se borran solos (esquema 3); sobreviven a un reinicio del servicio
CREATE TABLE IF NOT EXISTS mensajes_efimeros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    chat_id INTEGER NOT NULL,
    mensaje_id INTEGER NOT NULL,
    clave TEXT NOT NULL,                       -- p. ej. res:14:r (postulación y botón)
    borrar_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS mensajes_efimeros_borrar ON mensajes_efimeros(borrar_en);

CREATE TABLE IF NOT EXISTS evidencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    postulacion_id INTEGER NOT NULL REFERENCES postulaciones(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    tipo TEXT NOT NULL,                        -- html | captura
    archivo TEXT NOT NULL
);

-- Qué dato pide cada pregunta: compartido entre usuarios, sin respuestas personales. El campo
-- «redactar» marca las preguntas compuestas o de prosa, que van al redactor por formulario.
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
    opciones_json TEXT,                        -- opciones del portal, o sugerencias si es dato
    campo TEXT,
    tipo TEXT NOT NULL DEFAULT 'formulario',   -- formulario | dato (esquema 4)
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

-- Lo que el asistente aprende de cada postulación (esquema 5). Sin valores ni contacto.
CREATE TABLE IF NOT EXISTS recetas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    ruta_patron TEXT NOT NULL,
    familia TEXT NOT NULL,
    firma TEXT NOT NULL,                       -- claves de los campos de la primera pantalla
    receta_json TEXT NOT NULL,
    exitos INTEGER NOT NULL DEFAULT 0,
    fallos_seguidos INTEGER NOT NULL DEFAULT 0,
    activa INTEGER NOT NULL DEFAULT 1,
    origen TEXT NOT NULL DEFAULT 'real',       -- real | ensayo
    actualizada TEXT NOT NULL,
    UNIQUE (host, ruta_patron, firma)
);
CREATE INDEX IF NOT EXISTS recetas_familia ON recetas(familia, activa);

CREATE TABLE IF NOT EXISTS parches_flujo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plataforma TEXT NOT NULL,
    paso TEXT NOT NULL,
    selector_json TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'candidato',  -- candidato | firme | descartado
    exitos INTEGER NOT NULL DEFAULT 0,
    postulacion_id INTEGER,                    -- la que terminó enviada y lo originó
    creado TEXT NOT NULL,
    actualizado TEXT NOT NULL,
    UNIQUE (plataforma, paso, selector_json)
);

CREATE TABLE IF NOT EXISTS dominios_barrera (
    host TEXT PRIMARY KEY,
    motivo TEXT NOT NULL,                      -- ats_con_cuenta | oauth | mensajeria
    creado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bajas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL
);
"""

# Se crea después de migrar: en una base v3 la columna aún no existe al correr ESQUEMA
INDICES_V4 = """
CREATE UNIQUE INDEX IF NOT EXISTS respuestas_pregunta ON respuestas(postulacion_id, pregunta_norm);
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
            self.cx.executescript(INDICES_V4)

    def _actualizar_desde(self, version: int) -> None:
        """Cambios a una base existente (CREATE TABLE IF NOT EXISTS no agrega columnas)."""
        if version < 2:
            columnas = {f["name"] for f in self.cx.execute("PRAGMA table_info(vacantes)")}
            if "ficha_json" not in columnas:
                self.cx.execute("ALTER TABLE vacantes ADD COLUMN ficha_json TEXT")
        if version < 4:
            self._a_v4()
        if version < 5:
            self._a_v5()
        if version < 6:
            self._a_v6()
        if version < 7:
            self._a_v7()

    def _columnas(self, tabla: str) -> set[str]:
        return {f["name"] for f in self.cx.execute(f"PRAGMA table_info({tabla})")}

    def _a_v7(self) -> None:
        """Esquema anticipado de la vacante. La tabla de documentos del usuario es nueva y la
        crea `ESQUEMA`."""
        if "esquema_json" not in self._columnas("vacantes"):
            self.cx.execute("ALTER TABLE vacantes ADD COLUMN esquema_json TEXT")
        if "ensayo" not in self._columnas("usuarios"):
            self.cx.execute("ALTER TABLE usuarios ADD COLUMN ensayo INTEGER NOT NULL DEFAULT 0")
        if "forzar_real" not in self._columnas("postulaciones"):
            self.cx.execute(
                "ALTER TABLE postulaciones ADD COLUMN forzar_real INTEGER NOT NULL DEFAULT 0"
            )

    def _a_v6(self) -> None:
        """Nivel de uso de IA del usuario y el que llevó cada postulación al encolarse."""
        if "nivel_ia" not in self._columnas("usuarios"):
            self.cx.execute(
                "ALTER TABLE usuarios ADD COLUMN nivel_ia TEXT NOT NULL DEFAULT 'normal'"
            )
        if "nivel_ia" not in self._columnas("postulaciones"):
            self.cx.execute("ALTER TABLE postulaciones ADD COLUMN nivel_ia TEXT")

    def _a_v5(self) -> None:
        """Recetas, parches y dominios barrera (tablas nuevas) y qué receta y parches llevó cada
        postulación."""
        columnas = self._columnas("postulaciones")
        if "receta_id" not in columnas:
            self.cx.execute("ALTER TABLE postulaciones ADD COLUMN receta_id INTEGER")
        if "parches_json" not in columnas:
            self.cx.execute("ALTER TABLE postulaciones ADD COLUMN parches_json TEXT")

    def _a_v4(self) -> None:
        """Redactor por formulario: tipos de pendiente, revisión por portal y una respuesta por
        pregunta. Las clasificaciones de la IA se borran para reclasificarse con el formato."""
        from buscador_vacantes.asistente.respuestas import normalizar_pregunta

        nuevas = {
            "pendientes_usuario": ("tipo", "TEXT NOT NULL DEFAULT 'formulario'"),
            "preferencias_portal": ("revisar_respuestas", "INTEGER NOT NULL DEFAULT 0"),
        }
        for tabla, (columna, definicion) in nuevas.items():
            if columna not in self._columnas(tabla):
                self.cx.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        columnas = self._columnas("respuestas")
        if "pregunta_norm" not in columnas:
            self.cx.execute("ALTER TABLE respuestas ADD COLUMN pregunta_norm TEXT")
        if "estado" not in columnas:
            self.cx.execute(
                "ALTER TABLE respuestas ADD COLUMN estado TEXT NOT NULL DEFAULT 'enviada'"
            )
        vistas: set[tuple[int, str]] = set()
        filas = self.cx.execute("SELECT id, postulacion_id, pregunta FROM respuestas ORDER BY id")
        for fila in filas.fetchall():
            norma = normalizar_pregunta(fila["pregunta"])
            if (fila["postulacion_id"], norma) in vistas:
                # Una pregunta repetida en la misma postulación: el índice único no la admite
                self.cx.execute("DELETE FROM respuestas WHERE id = ?", (fila["id"],))
                continue
            vistas.add((fila["postulacion_id"], norma))
            self.cx.execute(
                "UPDATE respuestas SET pregunta_norm = ? WHERE id = ?", (norma, fila["id"])
            )
        self.cx.execute("DELETE FROM banco_preguntas WHERE origen = 'ia'")

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

    def kv_con_prefijo(self, prefijo: str) -> list[tuple[str, str]]:
        """Pares (clave, valor) no vacíos cuya clave empieza por el prefijo."""
        filas = self.cx.execute(
            "SELECT clave, valor FROM kv WHERE substr(clave, 1, ?) = ? AND valor != ''",
            (len(prefijo), prefijo),
        ).fetchall()
        return [(f["clave"], f["valor"]) for f in filas]

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
