"""Estado persistente en SQLite (WAL): vistas, fuentes, rotación, intentos, corridas, IA."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from buscador_vacantes.comun.modelo import Categoria, Vacante

ESQUEMA_VERSION = 3

# Columnas que el esquema 2 agrega al 1 (tabla, columna, definición). Una base nueva ya nace con
# ellas en ESQUEMA; una del esquema 1 las recibe con ALTER TABLE en _migrar_esquema
COLUMNAS_ESQUEMA_2 = (
    ("vistas", "ubicacion", "TEXT"),
    ("vistas", "modalidad", "TEXT"),
    ("clasificaciones", "version_prompt", "TEXT"),
    ("corridas", "practicas_recategorizadas", "INTEGER NOT NULL DEFAULT 0"),
    ("corridas", "practicas_rechazadas", "INTEGER NOT NULL DEFAULT 0"),
)

# Columnas que el esquema 3 agrega al 2: las cifras del detalle de cada corrida
COLUMNAS_ESQUEMA_3 = tuple(
    ("corridas", columna, "INTEGER NOT NULL DEFAULT 0")
    for columna in (
        "detalles_pedidos",
        "detalles_fallidos",
        "detalles_recuperadas",
        "detalles_cerradas",
        "detalles_vencidas",
    )
)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS esquema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS vistas (
    clave TEXT PRIMARY KEY,
    huella TEXT NOT NULL,
    fuente TEXT NOT NULL,
    titulo TEXT,
    empresa TEXT,
    url TEXT,
    categoria TEXT,
    primera_vez TEXT NOT NULL,
    enviada_en TEXT,
    prueba_en TEXT,
    ubicacion TEXT,
    modalidad TEXT
);
CREATE INDEX IF NOT EXISTS vistas_huella ON vistas(huella);

CREATE TABLE IF NOT EXISTS por_enviar (
    clave TEXT PRIMARY KEY,
    huella TEXT NOT NULL,
    vacante_json TEXT NOT NULL,
    desde TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fuentes_estado (
    fuente TEXT PRIMARY KEY,
    cooldown_hasta TEXT,
    escalon INTEGER NOT NULL DEFAULT 0,
    fallos_consecutivos INTEGER NOT NULL DEFAULT 0,
    ultimo_exito TEXT
);

CREATE TABLE IF NOT EXISTS rotacion (
    fuente TEXT NOT NULL,
    grupo TEXT NOT NULL,
    indice INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (fuente, grupo)
);

CREATE TABLE IF NOT EXISTS intentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    corrida_id INTEGER,
    fuente TEXT NOT NULL,
    keyword TEXT,
    url TEXT,
    status INTEGER,
    ms INTEGER,
    items INTEGER,
    tipo_error TEXT,
    desafio INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS intentos_fuente_ts ON intentos(fuente, ts);

CREATE TABLE IF NOT EXISTS corridas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio TEXT NOT NULL,
    fin TEXT,
    modo TEXT NOT NULL,
    crudas INTEGER NOT NULL DEFAULT 0,
    descartes_json TEXT,
    duplicadas INTEGER NOT NULL DEFAULT 0,
    dudosas INTEGER NOT NULL DEFAULT 0,
    ia_aceptadas INTEGER NOT NULL DEFAULT 0,
    ia_rechazadas INTEGER NOT NULL DEFAULT 0,
    pendientes INTEGER NOT NULL DEFAULT 0,
    enviadas INTEGER NOT NULL DEFAULT 0,
    sin_red INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    practicas_recategorizadas INTEGER NOT NULL DEFAULT 0,
    practicas_rechazadas INTEGER NOT NULL DEFAULT 0,
    detalles_pedidos INTEGER NOT NULL DEFAULT 0,
    detalles_fallidos INTEGER NOT NULL DEFAULT 0,
    detalles_recuperadas INTEGER NOT NULL DEFAULT 0,
    detalles_cerradas INTEGER NOT NULL DEFAULT 0,
    detalles_vencidas INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clasificaciones (
    huella TEXT PRIMARY KEY,
    aceptar INTEGER NOT NULL,
    categoria TEXT,
    motivo TEXT,
    ts TEXT NOT NULL,
    version_prompt TEXT
);

CREATE TABLE IF NOT EXISTS pendientes (
    huella TEXT PRIMARY KEY,
    vacante_json TEXT NOT NULL,
    desde TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pendientes_detalle (
    clave TEXT PRIMARY KEY,
    huella TEXT NOT NULL,
    vacante_json TEXT NOT NULL,
    desde TEXT NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    proximo_intento TEXT,
    ultimo_error TEXT
);

CREATE TABLE IF NOT EXISTS detalles (
    clave TEXT PRIMARY KEY,
    texto TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fuente TEXT NOT NULL,
    tipo TEXT NOT NULL,
    abierto_desde TEXT NOT NULL,
    ultimo_reporte TEXT,
    cerrado_en TEXT,
    detalle_json TEXT
);
CREATE INDEX IF NOT EXISTS incidentes_abiertos ON incidentes(fuente, tipo, cerrado_en);

CREATE TABLE IF NOT EXISTS ia_uso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    proposito TEXT NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    ok INTEGER NOT NULL,
    motivo TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
"""


class EstadoNoInicializado(Exception):
    """La base no tiene historial: enviar inundaría el canal."""


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def a_texto(momento: datetime) -> str:
    """Fechas guardadas siempre en UTC ISO-8601, comparables como texto."""
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def de_texto(texto: str | None) -> datetime | None:
    return datetime.fromisoformat(texto) if texto else None


def vacante_a_json(vacante: Vacante) -> str:
    datos = asdict(vacante)
    datos["publicada"] = vacante.publicada.isoformat() if vacante.publicada else None
    datos["categoria"] = vacante.categoria.value if vacante.categoria else None
    return json.dumps(datos, ensure_ascii=False)


def vacante_de_json(texto: str) -> Vacante:
    datos = json.loads(texto)
    datos["publicada"] = de_texto(datos.get("publicada"))
    datos["categoria"] = Categoria(datos["categoria"]) if datos.get("categoria") else None
    return Vacante(**datos)


class Estado:
    def __init__(self, conexion: sqlite3.Connection) -> None:
        self.cx = conexion

    @classmethod
    def abrir(cls, ruta: Path | str) -> Estado:
        ruta = Path(ruta)
        if str(ruta) != ":memory:":
            ruta.parent.mkdir(parents=True, exist_ok=True)
        cx = sqlite3.connect(ruta, timeout=30)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA journal_mode=WAL")
        cx.execute("PRAGMA synchronous=NORMAL")
        estado = cls(cx)
        estado._migrar_esquema()
        return estado

    def cerrar(self) -> None:
        self.cx.close()

    def _migrar_esquema(self) -> None:
        with self.cx:
            self.cx.executescript(ESQUEMA)
            fila = self.cx.execute("SELECT version FROM esquema_version").fetchone()
            if fila is None:
                # Base nueva: las tablas ya se crearon con las columnas del esquema vigente
                self.cx.execute("INSERT INTO esquema_version VALUES (?)", (ESQUEMA_VERSION,))
                return
            version = fila["version"]
            if version > ESQUEMA_VERSION:
                raise RuntimeError(
                    f"La base tiene esquema {version} y el código soporta hasta {ESQUEMA_VERSION}"
                )
            if version < ESQUEMA_VERSION:
                self.cx.execute("BEGIN")  # todas las migraciones pendientes en una transacción
            if version < 2:
                self._migrar(COLUMNAS_ESQUEMA_2, 2)
            if version < 3:
                self._migrar(COLUMNAS_ESQUEMA_3, 3)

    def _migrar(self, columnas: tuple[tuple[str, str, str], ...], version: int) -> None:
        """Un paso de migración: solo agrega columnas, sin tocar filas.

        Las tablas nuevas ya las creó ``ESQUEMA`` (``IF NOT EXISTS``). Ignora las columnas que
        ya existen: tras volver atrás con ``UPDATE esquema_version`` (el código anterior las
        ignora) la base las conserva.
        """
        for tabla, columna, definicion in columnas:
            existentes = {f["name"] for f in self.cx.execute(f"PRAGMA table_info({tabla})")}
            if columna not in existentes:
                self.cx.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        self.cx.execute("UPDATE esquema_version SET version = ?", (version,))

    @contextmanager
    def transaccion(self) -> Iterator[sqlite3.Connection]:
        with self.cx:
            yield self.cx

    def tablas(self) -> list[str]:
        filas = self.cx.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return sorted(f["name"] for f in filas if not f["name"].startswith("sqlite_"))

    # --- kv -------------------------------------------------------------------------

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

    # --- inicialización ---------------------------------------------------------------

    def inicializada(self) -> bool:
        return self.kv_obtener("inicializada_en") is not None

    def marcar_inicializada(self, momento: datetime | None = None) -> None:
        if not self.inicializada():
            self.kv_guardar("inicializada_en", a_texto(momento or ahora_utc()))

    def exigir_inicializada(self) -> None:
        if not self.inicializada():
            raise EstadoNoInicializado(
                "La base de estado no está inicializada: ejecuta primero "
                "`buscador.py migrar` o `buscador.py --seed` para no inundar el canal."
            )

    # --- deduplicación -------------------------------------------------------------------

    def ya_vista(self, clave: str, huella: str, *, prueba: bool = False) -> bool:
        """Una vacante está vista si su clave o su huella ya existen.

        Los registros creados solo por envíos al chat de prueba no cuentan para el canal real.
        """
        condicion = "" if prueba else " AND (enviada_en IS NOT NULL OR prueba_en IS NULL)"
        fila = self.cx.execute(
            f"SELECT 1 FROM vistas WHERE (clave = ? OR huella = ?){condicion} LIMIT 1",
            (clave, huella),
        ).fetchone()
        return fila is not None

    def registrar_vista(
        self,
        vacante: Vacante,
        huella: str,
        *,
        momento: datetime | None = None,
        enviada: bool = False,
        prueba: bool = False,
    ) -> None:
        """Inserta o actualiza una vista. ``enviada`` y ``prueba`` fijan la fecha de envío."""
        ts = a_texto(momento or ahora_utc())
        enviada_en = ts if enviada and not prueba else None
        prueba_en = ts if prueba else None
        with self.cx:
            self.cx.execute(
                """
                INSERT INTO vistas(clave, huella, fuente, titulo, empresa, url, categoria,
                                   primera_vez, enviada_en, prueba_en, ubicacion, modalidad)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(clave) DO UPDATE SET
                    enviada_en = COALESCE(vistas.enviada_en, excluded.enviada_en),
                    prueba_en = COALESCE(vistas.prueba_en, excluded.prueba_en),
                    categoria = COALESCE(excluded.categoria, vistas.categoria),
                    ubicacion = COALESCE(vistas.ubicacion, excluded.ubicacion),
                    modalidad = COALESCE(vistas.modalidad, excluded.modalidad)
                """,
                (
                    vacante.clave,
                    huella,
                    vacante.fuente,
                    vacante.titulo,
                    vacante.empresa,
                    vacante.url,
                    vacante.categoria.value if vacante.categoria else None,
                    ts,
                    enviada_en,
                    prueba_en,
                    vacante.ubicacion,
                    vacante.modalidad,
                ),
            )

    def promover_prueba(self) -> int:
        """Marca como enviadas al canal las vacantes enviadas solo al chat de prueba.

        Se usa al pasar a producción para que el canal no reciba el atraso de la fase de prueba.
        """
        with self.cx:
            return self.cx.execute(
                "UPDATE vistas SET enviada_en = prueba_en "
                "WHERE enviada_en IS NULL AND prueba_en IS NOT NULL"
            ).rowcount

    def contar_vistas(self, *, enviadas: bool | None = None) -> int:
        consulta = "SELECT COUNT(*) FROM vistas"
        if enviadas is True:
            consulta += " WHERE enviada_en IS NOT NULL"
        elif enviadas is False:
            consulta += " WHERE enviada_en IS NULL"
        return self.cx.execute(consulta).fetchone()[0]

    # --- vacantes aceptadas cuyo envío falló ------------------------------------------------

    def guardar_por_enviar(self, vacante: Vacante, huella: str, momento: datetime) -> None:
        with self.cx:
            self.cx.execute(
                "INSERT INTO por_enviar(clave, huella, vacante_json, desde) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET vacante_json = excluded.vacante_json",
                (vacante.clave, huella, vacante_a_json(vacante), a_texto(momento)),
            )

    def quitar_por_enviar(self, clave: str) -> None:
        with self.cx:
            self.cx.execute("DELETE FROM por_enviar WHERE clave = ?", (clave,))

    def obtener_por_enviar(self) -> list[tuple[Vacante, str, datetime]]:
        filas = self.cx.execute(
            "SELECT huella, vacante_json, desde FROM por_enviar ORDER BY desde"
        ).fetchall()
        return [
            (vacante_de_json(f["vacante_json"]), f["huella"], de_texto(f["desde"])) for f in filas
        ]

    # --- cola de ofertas pendientes de detalle ------------------------------------------------

    def encolar_detalle(self, vacante: Vacante, huella: str, momento: datetime) -> bool:
        """Agrega la oferta a la cola sin duplicarla. Devuelve si era nueva."""
        with self.cx:
            return (
                self.cx.execute(
                    "INSERT OR IGNORE INTO pendientes_detalle(clave, huella, vacante_json, desde) "
                    "VALUES (?, ?, ?, ?)",
                    (vacante.clave, huella, vacante_a_json(vacante), a_texto(momento)),
                ).rowcount
                > 0
            )

    def en_cola_detalle(self, clave: str) -> bool:
        fila = self.cx.execute(
            "SELECT 1 FROM pendientes_detalle WHERE clave = ?", (clave,)
        ).fetchone()
        return fila is not None

    def contar_cola_detalle(self) -> int:
        return self.cx.execute("SELECT COUNT(*) FROM pendientes_detalle").fetchone()[0]

    def cola_detalle_lista(
        self, momento: datetime, fuente: str | None = None
    ) -> list[tuple[Vacante, str, datetime]]:
        """Ofertas cuyo próximo intento ya llegó, de la más antigua a la más reciente.

        Con ``fuente``, solo las de esa fuente.
        """
        filas = self.cx.execute(
            "SELECT clave, huella, vacante_json, desde FROM pendientes_detalle "
            "WHERE proximo_intento IS NULL OR proximo_intento <= ? ORDER BY desde, clave",
            (a_texto(momento),),
        ).fetchall()
        return [
            (vacante_de_json(f["vacante_json"]), f["huella"], de_texto(f["desde"]))
            for f in filas
            if fuente is None or f["clave"].startswith(f"{fuente}:")
        ]

    def fallo_detalle(self, clave: str, momento: datetime, error: str, espera_min: float) -> int:
        """Registra un fallo: sube ``intentos`` y espera ``espera_min × intentos`` minutos."""
        with self.cx:
            self.cx.execute(
                "UPDATE pendientes_detalle SET intentos = intentos + 1, ultimo_error = ? "
                "WHERE clave = ?",
                (error, clave),
            )
            fila = self.cx.execute(
                "SELECT intentos FROM pendientes_detalle WHERE clave = ?", (clave,)
            ).fetchone()
            if fila is None:
                return 0
            proximo = momento + timedelta(minutes=espera_min * fila["intentos"])
            self.cx.execute(
                "UPDATE pendientes_detalle SET proximo_intento = ? WHERE clave = ?",
                (a_texto(proximo), clave),
            )
            return fila["intentos"]

    def quitar_cola_detalle(self, clave: str) -> None:
        with self.cx:
            self.cx.execute("DELETE FROM pendientes_detalle WHERE clave = ?", (clave,))

    def vencer_cola_detalle(
        self, momento: datetime, horas: float, fuente: str | None = None
    ) -> list[Vacante]:
        """Saca de la cola las ofertas que esperan más de ``horas`` y las devuelve.

        Con ``fuente``, solo las de esa fuente.
        """
        limite = a_texto(momento - timedelta(hours=horas))
        with self.cx:
            filas = self.cx.execute(
                "SELECT clave, vacante_json FROM pendientes_detalle WHERE desde < ? ORDER BY desde",
                (limite,),
            ).fetchall()
            filas = [f for f in filas if fuente is None or f["clave"].startswith(f"{fuente}:")]
            for fila in filas:
                self.cx.execute("DELETE FROM pendientes_detalle WHERE clave = ?", (fila["clave"],))
        return [vacante_de_json(f["vacante_json"]) for f in filas]

    # --- descripciones ya obtenidas --------------------------------------------------------

    def guardar_detalle(self, clave: str, texto: str, momento: datetime) -> None:
        with self.cx:
            self.cx.execute(
                "INSERT INTO detalles(clave, texto, ts) VALUES (?, ?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET texto = excluded.texto, ts = excluded.ts",
                (clave, texto, a_texto(momento)),
            )

    def leer_detalle(self, clave: str) -> str | None:
        fila = self.cx.execute("SELECT texto FROM detalles WHERE clave = ?", (clave,)).fetchone()
        return fila["texto"] if fila else None

    # --- limpieza ---------------------------------------------------------------------------

    def limpiar(
        self,
        momento: datetime,
        dias_vistas: int = 90,
        dias_intentos: int = 30,
        dias_detalles: int = 15,
    ) -> dict[str, int]:
        """Borra registros antiguos. Los incidentes abiertos nunca se borran."""
        limite_vistas = a_texto(momento - timedelta(days=dias_vistas))
        limite_corto = a_texto(momento - timedelta(days=dias_intentos))
        limite_detalles = a_texto(momento - timedelta(days=dias_detalles))
        sentencias = {
            "vistas": ("DELETE FROM vistas WHERE primera_vez < ?", limite_vistas),
            "clasificaciones": ("DELETE FROM clasificaciones WHERE ts < ?", limite_vistas),
            "intentos": ("DELETE FROM intentos WHERE ts < ?", limite_corto),
            "corridas": ("DELETE FROM corridas WHERE inicio < ?", limite_corto),
            "ia_uso": ("DELETE FROM ia_uso WHERE ts < ?", limite_corto),
            "detalles": ("DELETE FROM detalles WHERE ts < ?", limite_detalles),
            # Red de seguridad: la cola se vacía sola por vencimiento mucho antes
            "pendientes_detalle": (
                "DELETE FROM pendientes_detalle WHERE desde < ?",
                limite_corto,
            ),
            "incidentes": (
                "DELETE FROM incidentes WHERE cerrado_en IS NOT NULL AND cerrado_en < ?",
                limite_corto,
            ),
        }
        borrados = {}
        with self.cx:
            for tabla, (sql, limite) in sentencias.items():
                borrados[tabla] = self.cx.execute(sql, (limite,)).rowcount
        return borrados
