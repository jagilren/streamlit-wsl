#!/usr/bin/env python3
"""
Crea la tabla tag_config en TimescaleDB y la pre-popula con los TAGs
definidos en config.TAG_MAP.

Uso:
    python crear_tabla_tag_config.py
"""

import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

import os
import psycopg2
from config import TAG_MAP

def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ.get("DB_NAME", "ptar_db"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
    )

_CREATE = """
CREATE TABLE IF NOT EXISTS tag_config (
    tag  TEXT PRIMARY KEY,
    tab  TEXT NOT NULL CHECK (tab IN ('pH', 'DQO'))
)
"""

def main() -> None:
    print("Conectando a TimescaleDB…")
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"[ERROR] No se pudo conectar: {exc}", file=sys.stderr)
        sys.exit(1)

    with conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE)
            print("  Tabla tag_config creada (o ya existía).")

            insertados = 0
            for tag, cfg in TAG_MAP.items():
                tab = cfg.get("tipo")
                if tab not in ("pH", "DQO"):
                    print(f"  [WARN] TAG '{tag}' tiene tipo='{tab}' inválido, se omite.")
                    continue
                cur.execute(
                    """
                    INSERT INTO tag_config (tag, tab)
                    VALUES (%s, %s)
                    ON CONFLICT (tag) DO UPDATE SET tab = EXCLUDED.tab
                    """,
                    (tag, tab),
                )
                if cur.rowcount:
                    insertados += 1

    print(f"  {insertados} TAGs insertados/actualizados en tag_config.")
    conn.close()
    print("✓ Listo.")


if __name__ == "__main__":
    main()
