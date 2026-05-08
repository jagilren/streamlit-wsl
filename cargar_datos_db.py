#!/usr/bin/env python3
"""
Carga los CSV de PLC (pH) y Laboratorio (DQO) a la tabla sensors_data
de TimescaleDB.

La tabla se crea automáticamente si no existe.  Las cargas repetidas
ignoran duplicados (ON CONFLICT DO NOTHING) salvo que se use --truncate.

Uso:
    python cargar_datos_db.py [--truncate] [--plc PATH] [--lab PATH]

Flags:
    --truncate   Borra los datos existentes de cada fuente antes de insertar.
    --plc PATH   CSV del PLC   (por defecto: config.CSV_PATH).
    --lab PATH   CSV del Lab   (por defecto: config.CSV_PATH_LAB).
"""

import argparse
import io
import sys
import time as _time
from pathlib import Path

# Cargar .env antes de importar db (que lee os.environ al importarse)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass  # python-dotenv opcional; se puede exportar las vars manualmente

import pandas as pd

from db import get_connection
from config import CSV_PATH, CSV_PATH_LAB

CHUNK_ROWS = 500_000  # filas por lote (ajustar según RAM disponible)

# ── Esquema ────────────────────────────────────────────────────────────────────
_SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE",
    """
    CREATE TABLE IF NOT EXISTS sensors_data (
        time   TIMESTAMPTZ      NOT NULL,
        tag    TEXT             NOT NULL,
        value  DOUBLE PRECISION,
        source TEXT             NOT NULL      -- 'plc' | 'lab'
    )
    """,
    """
    SELECT create_hypertable(
        'sensors_data', 'time',
        if_not_exists => TRUE,
        migrate_data  => TRUE
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uix_sensors_time_tag
        ON sensors_data (time, tag)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sensors_tag_time
        ON sensors_data (tag, time DESC)
    """,
]


def init_schema(conn) -> None:
    with conn.cursor() as cur:
        for sql in _SCHEMA:
            cur.execute(sql)
    conn.commit()
    print("  Esquema sensors_data OK.")


# ── Carga ─────────────────────────────────────────────────────────────────────

def _row_count(conn, source: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM sensors_data WHERE source = %s", (source,))
        return cur.fetchone()[0]


def cargar(conn, path: Path, source: str, truncate: bool = False) -> None:
    if truncate:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensors_data WHERE source = %s", (source,))
        conn.commit()
        print(f"  Datos previos de source='{source}' eliminados.")
    else:
        n_prev = _row_count(conn, source)
        if n_prev:
            print(f"  Ya existen {n_prev:,} filas (source='{source}'). "
                  "Duplicados se ignorarán (--truncate para reemplazar).")

    # Tabla temporal a nivel de sesión: se reutiliza entre lotes
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE IF NOT EXISTS _tmp_load (
                time   TEXT,
                tag    TEXT,
                value  DOUBLE PRECISION,
                source TEXT
            )
        """)
    conn.commit()

    total = 0
    inserted_total = 0
    t0 = _time.monotonic()

    reader = pd.read_csv(path, parse_dates=["TimeStamp"], chunksize=CHUNK_ROWS)
    for chunk in reader:
        chunk = chunk.rename(columns={"TimeStamp": "time", "TAG": "tag", "Value": "value"})
        chunk["source"] = source
        # Timestamps sin zona → UTC implícito al insertarlos en TIMESTAMPTZ
        chunk["time"] = chunk["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        total += len(chunk)

        buf = io.StringIO()
        chunk[["time", "tag", "value", "source"]].to_csv(buf, index=False, header=False)
        buf.seek(0)

        with conn.cursor() as cur:
            cur.execute("TRUNCATE _tmp_load")
            cur.copy_expert(
                "COPY _tmp_load (time, tag, value, source) FROM STDIN WITH CSV",
                buf,
            )
            cur.execute("""
                INSERT INTO sensors_data (time, tag, value, source)
                SELECT time::TIMESTAMPTZ, tag, value, source
                FROM _tmp_load
                ON CONFLICT (time, tag) DO NOTHING
            """)
            inserted_total += cur.rowcount
        conn.commit()

        elapsed = _time.monotonic() - t0
        rate = int(total / elapsed) if elapsed else 0
        print(
            f"  {total:>9,} leídas | {inserted_total:>9,} insertadas "
            f"| {rate:>8,} filas/s",
            end="\r",
        )

    elapsed = _time.monotonic() - t0
    print(
        f"  {total:>9,} leídas | {inserted_total:>9,} insertadas "
        f"| {elapsed:.1f} s{' ' * 20}"
    )


# ── Punto de entrada ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--plc",      default=None, metavar="PATH",
                        help="Ruta al CSV del PLC (pH)")
    parser.add_argument("--lab",      default=None, metavar="PATH",
                        help="Ruta al CSV del Laboratorio (DQO)")
    parser.add_argument("--truncate", action="store_true",
                        help="Borrar datos existentes antes de cargar")
    args = parser.parse_args()

    plc_path = Path(args.plc) if args.plc else Path(CSV_PATH)
    lab_path = Path(args.lab) if args.lab else Path(CSV_PATH_LAB)

    print("Conectando a TimescaleDB…")
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"[ERROR] No se pudo conectar: {exc}", file=sys.stderr)
        print(
            "  Verifica que el contenedor esté activo y que las variables\n"
            "  DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD sean correctas.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        print("Inicializando esquema…")
        init_schema(conn)

        if plc_path.exists():
            size_mb = plc_path.stat().st_size / 1e6
            print(f"\nCargando PLC ← {plc_path}  ({size_mb:.1f} MB)")
            cargar(conn, plc_path, "plc", args.truncate)
        else:
            print(f"[WARN] CSV PLC no encontrado: {plc_path}")

        if lab_path.exists():
            size_mb = lab_path.stat().st_size / 1e6
            print(f"\nCargando Laboratorio ← {lab_path}  ({size_mb:.1f} MB)")
            cargar(conn, lab_path, "lab", args.truncate)
        else:
            print(f"[WARN] CSV Laboratorio no encontrado: {lab_path}")

        print("\n✓ Carga completada.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
