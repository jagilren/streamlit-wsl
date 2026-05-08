"""
Crea la tabla sensor_data en TimescaleDB y carga datos desde datos_ptar.csv.
"""
import os
import io
import csv
import time
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", 5432),
    "dbname": os.getenv("DB_NAME", "ptar_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

CSV_PATH = os.path.join(os.path.dirname(__file__), "datos_ptar.csv")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sensor_data (
    tag_id      VARCHAR        NOT NULL,
    timestamp   TIMESTAMPTZ    NOT NULL,
    valor       DOUBLE PRECISION,
    CONSTRAINT sensor_data_tag_ts_uq UNIQUE (tag_id, timestamp)
);
"""

CREATE_HYPERTABLE_SQL = """
SELECT create_hypertable(
    'sensor_data',
    'timestamp',
    if_not_exists => TRUE,
    migrate_data  => TRUE
);
"""


def create_table(cur):
    cur.execute(CREATE_TABLE_SQL)
    print("Tabla sensor_data creada (o ya existía).")
    cur.execute(CREATE_HYPERTABLE_SQL)
    print("Hypertable configurada.")


def load_csv(conn, cur):
    print(f"Cargando datos desde {CSV_PATH} …")
    t0 = time.time()

    # COPY no admite ON CONFLICT, así que usamos una tabla temporal de staging.
    cur.execute("DROP TABLE IF EXISTS sensor_data_stage;")
    cur.execute("""
        CREATE TEMP TABLE sensor_data_stage (
            timestamp   TEXT,
            tag_id      TEXT,
            valor       TEXT
        );
    """)

    copy_sql = """
        COPY sensor_data_stage (timestamp, tag_id, valor)
        FROM STDIN
        WITH (FORMAT csv, HEADER false, NULL '')
    """

    CHUNK = 200_000  # filas por bloque
    total = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # saltar encabezado

        buf = io.StringIO()
        writer = csv.writer(buf)

        for row in reader:
            ts, tag, val = row[0], row[1], row[2]
            writer.writerow([ts, tag, val])
            total += 1

            if total % CHUNK == 0:
                buf.seek(0)
                cur.copy_expert(copy_sql, buf)
                buf = io.StringIO()
                writer = csv.writer(buf)
                elapsed = time.time() - t0
                print(f"  Staging: {total:,} filas — {elapsed:.1f}s", end="\r")

        # último bloque
        if buf.tell() > 0:
            buf.seek(0)
            cur.copy_expert(copy_sql, buf)

    elapsed_stage = time.time() - t0
    print(f"\n  Staging completo: {total:,} filas en {elapsed_stage:.1f}s")

    print("  Insertando en sensor_data (deduplicando) …")
    cur.execute("""
        INSERT INTO sensor_data (tag_id, timestamp, valor)
        SELECT DISTINCT ON (tag_id, timestamp::timestamptz)
            tag_id,
            timestamp::timestamptz,
            NULLIF(valor, '')::double precision
        FROM sensor_data_stage
        ORDER BY tag_id, timestamp::timestamptz
        ON CONFLICT (tag_id, timestamp) DO NOTHING;
    """)
    inserted = cur.rowcount
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Insertadas {inserted:,} filas en {elapsed:.1f}s ({inserted/elapsed:,.0f} filas/s).")


def verify(cur):
    cur.execute("SELECT COUNT(*) FROM sensor_data;")
    count = cur.fetchone()[0]
    cur.execute("SELECT tag_id, MIN(timestamp), MAX(timestamp) FROM sensor_data GROUP BY tag_id ORDER BY tag_id;")
    rows = cur.fetchall()
    print(f"\nTotal filas en sensor_data: {count:,}")
    print(f"{'TAG_ID':<30} {'DESDE':<25} {'HASTA'}")
    print("-" * 80)
    for tag, mn, mx in rows:
        print(f"{tag:<30} {str(mn):<25} {mx}")


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        create_table(cur)
        conn.commit()
        load_csv(conn, cur)
        verify(cur)
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
