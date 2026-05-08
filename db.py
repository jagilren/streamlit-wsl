import io
import logging
import os
import psycopg2
import psycopg2.extras
import pandas as pd
import streamlit as st
from config import TAG_MAP

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
_log = logging.getLogger("db")

_LOG_DIR = "/app/logs"
if os.path.isdir(_LOG_DIR) and os.access(_LOG_DIR, os.W_OK):
    _log_file = logging.FileHandler(os.path.join(_LOG_DIR, "db.log"))
    _log_file.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] — %(message)s"))
    _log.addHandler(_log_file)


_MISSING = object()


def _cfg(key: str, default=_MISSING):
    """Lee config desde st.secrets (Streamlit Cloud) y cae a os.environ (local).
    Si no hay default y la clave no se encuentra en ningún lado, lanza RuntimeError."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    val = os.environ.get(key)
    if val is not None:
        return val
    if default is _MISSING:
        raise RuntimeError(
            f"Falta la configuración {key!r}. Define el valor en "
            "Streamlit Cloud → Settings → Secrets, o como variable de entorno."
        )
    return default



_DSN = {
    "host":     _cfg("DB_HOST","4.tcp.ngrok.io"),
    "port":     int(_cfg("DB_PORT", 20916)),
    "dbname":   _cfg("DB_NAME", "ptar_db"),
    "user":     _cfg("DB_USER", "postgres"),
    "password": _cfg("DB_PASSWORD"),
}


def get_connection():
    _log.debug("get_connection: conectando a %s:%s/%s", _DSN["host"], _DSN["port"], _DSN["dbname"])
    try:
        conn = psycopg2.connect(**_DSN)
        _log.debug("get_connection: conexión exitosa")
        return conn
    except Exception as exc:
        _log.error("get_connection: falló la conexión — %s", exc)
        raise


def _ensure_schema() -> None:
    """Crea las tablas y pre-popula tag_config desde TAG_MAP al arrancar."""
    _log.debug("_ensure_schema: iniciando creación de esquema")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _log.debug("_ensure_schema: habilitando extensión timescaledb")
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

            _log.debug("_ensure_schema: creando tabla sensor_data")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sensor_data (
                    tag_id    TEXT        NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    valor     DOUBLE PRECISION,
                    UNIQUE (tag_id, timestamp)
                )
            """)
            cur.execute("""
                SELECT create_hypertable(
                    'sensor_data', 'timestamp', if_not_exists => TRUE
                )
            """)

            _log.debug("_ensure_schema: creando tabla tag_config")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tag_config (
                    tag TEXT PRIMARY KEY,
                    tab TEXT NOT NULL CHECK (tab IN ('pH', 'DQO'))
                )
            """)
            tags_insertados = 0
            for tag, cfg in TAG_MAP.items():
                tab = cfg.get("tipo")
                if tab in ("pH", "DQO"):
                    cur.execute("""
                        INSERT INTO tag_config (tag, tab) VALUES (%s, %s)
                        ON CONFLICT (tag) DO NOTHING
                    """, (tag, tab))
                    tags_insertados += cur.rowcount
        conn.commit()
        _log.info("_ensure_schema: esquema listo, %d tags pre-poblados en tag_config", tags_insertados)
    except Exception as exc:
        _log.error("_ensure_schema: error — %s", exc)
        raise
    finally:
        conn.close()


_schema_listo = False


def _ensure_schema_once() -> None:
    """Ejecuta _ensure_schema una sola vez por proceso, sin tumbar la app si la DB no responde."""
    global _schema_listo
    if _schema_listo:
        return
    try:
        _ensure_schema()
        _schema_listo = True
    except Exception as exc:
        _log.warning("_ensure_schema_once: DB no disponible al arrancar — %s", exc)


_ensure_schema_once()


def esta_disponible() -> bool:
    """Devuelve True si la base de datos es alcanzable."""
    _log.debug("esta_disponible: verificando conexión")
    try:
        conn = get_connection()
        conn.close()
        _log.debug("esta_disponible: DB accesible")
        _ensure_schema_once()
        return True
    except Exception as exc:
        _log.warning("esta_disponible: DB no accesible — %s", exc)
        return False


@st.cache_data(ttl=60, show_spinner="Consultando TimescaleDB…")
def query_df(sql: str, params=None) -> pd.DataFrame:
    """Ejecuta una consulta y devuelve un DataFrame de pandas."""
    _log.debug("query_df: sql=%r  params=%s", sql, params)
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                cols = [desc[0] for desc in cur.description] if cur.description else []
                df = pd.DataFrame([dict(r) for r in rows], columns=cols)
                _log.debug("query_df: devuelve %d filas, columnas=%s", len(df), list(df.columns))
                return df
    except Exception as exc:
        _log.error("query_df: error ejecutando consulta — %s", exc)
        raise


_CHUNK_SIZE = 50_000  # filas por lote


def insertar_csv(csv_file, progress_cb=None) -> tuple[int, int]:
    """Lee un CSV (TimeStamp, TAG, Value) e inserta en sensor_data por lotes.
    progress_cb(lote_actual, total_lotes) se llama tras cada lote si se provee.
    Retorna (total_leidas, total_insertadas)."""
    _log.debug("insertar_csv: inicio, progress_cb=%s", progress_cb is not None)
    if hasattr(csv_file, "seek"):
        csv_file.seek(0)
    raw = csv_file.read() if hasattr(csv_file, "read") else csv_file

    import math
    total_lotes = max(1, math.ceil((raw.count(b"\n") - 1) / _CHUNK_SIZE))
    _log.debug("insertar_csv: tamaño raw=%d bytes, lotes estimados=%d", len(raw), total_lotes)

    total = 0
    insertadas = 0
    lote = 0

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _log.debug("insertar_csv: creando tabla temporal _tmp_insert")
            cur.execute("""
                CREATE TEMP TABLE IF NOT EXISTS _tmp_insert (
                    tag_id TEXT, ts TEXT, valor DOUBLE PRECISION
                )
            """)
            conn.commit()
            cur.execute("SELECT to_regclass('_tmp_insert')")
            if cur.fetchone()[0] is None:
                _log.error("insertar_csv: no se pudo crear _tmp_insert")
                raise RuntimeError("No se pudo crear la tabla temporal _tmp_insert")

            reader = pd.read_csv(
                io.BytesIO(raw),
                dtype={"TAG": str, "Value": float},
                chunksize=_CHUNK_SIZE,
            )
            for chunk in reader:
                chunk.columns = chunk.columns.str.strip()
                chunk["TimeStamp"] = pd.to_datetime(chunk["TimeStamp"], errors="coerce")
                chunk["TAG"] = chunk["TAG"].str.strip()
                chunk = chunk.dropna(subset=["TimeStamp", "TAG"])
                if chunk.empty:
                    _log.warning("insertar_csv: lote %d vacío tras limpieza, saltando", lote + 1)
                    continue
                total += len(chunk)
                _log.debug("insertar_csv: lote %d — %d filas válidas (total acum.=%d)", lote + 1, len(chunk), total)

                chunk["TimeStamp"] = chunk["TimeStamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
                buf = io.StringIO()
                chunk[["TAG", "TimeStamp", "Value"]].to_csv(buf, index=False, header=False)
                buf.seek(0)

                cur.execute("TRUNCATE _tmp_insert")
                cur.copy_expert(
                    "COPY _tmp_insert (tag_id, ts, valor) FROM STDIN WITH CSV", buf
                )
                cur.execute("""
                    INSERT INTO sensor_data (tag_id, timestamp, valor)
                    SELECT tag_id, ts::TIMESTAMPTZ, valor FROM _tmp_insert
                    ON CONFLICT (tag_id, timestamp) DO NOTHING
                """)
                nuevas = cur.rowcount
                insertadas += nuevas
                conn.commit()
                _log.debug("FILAS_INSERTADAS=%d lote=%d omitidas=%d", nuevas, lote + 1, len(chunk) - nuevas)

                lote += 1
                if progress_cb:
                    progress_cb(lote, total_lotes)
    except Exception as exc:
        _log.error("insertar_csv: error en lote %d — %s", lote + 1, exc)
        raise
    finally:
        conn.close()

    _log.info("insertar_csv: finalizado — leídas=%d, insertadas=%d", total, insertadas)
    return total, insertadas


def asignar_tab(tag: str, tab: str) -> None:
    """Inserta o actualiza el tab de un TAG en tag_config."""
    _log.debug("asignar_tab: tag=%r, tab=%r", tag, tab)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tag_config (tag, tab) VALUES (%s, %s)
                ON CONFLICT (tag) DO UPDATE SET tab = EXCLUDED.tab
                """,
                (tag, tab),
            )
        conn.commit()
        _log.info("asignar_tab: tag=%r asignado a tab=%r", tag, tab)
    except Exception as exc:
        _log.error("asignar_tab: error — tag=%r tab=%r — %s", tag, tab, exc)
        raise
    finally:
        conn.close()
