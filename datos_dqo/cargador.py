"""Carga registros de DQO a TimescaleDB en la tabla `dqo` (hypertable, append-only).

- Verifica conectividad con la base antes de tocar nada.
- Crea la tabla y la convierte en hypertable si no existe.
- Inserta en lotes con COPY + ON CONFLICT DO NOTHING para idempotencia.
"""

from __future__ import annotations

import io
import sys
from typing import Iterable, Sequence

from .generador import Lectura

TABLA = "dqo"

_SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE",
    """
    CREATE TABLE IF NOT EXISTS dqo (
        id         BIGSERIAL,
        tag_id     VARCHAR(64)   NOT NULL,
        timestamp  TIMESTAMPTZ   NOT NULL,
        value      NUMERIC(10,2) NOT NULL,
        PRIMARY KEY (timestamp, id)
    )
    """,
    """
    SELECT create_hypertable(
        'dqo', 'timestamp',
        if_not_exists => TRUE,
        migrate_data  => TRUE
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uix_dqo_tag_timestamp
        ON dqo (tag_id, timestamp)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_dqo_tag_time
        ON dqo (tag_id, timestamp DESC)
    """,
]


def verificar_db() -> bool:
    """True si la base de datos está alcanzable con la configuración actual."""
    try:
        from db import get_connection
        conn = get_connection()
        conn.close()
        return True
    except Exception as exc:
        print(
            f"[ERROR] No se pudo conectar a la base de datos: {exc}\n"
            "  Revisa que el contenedor `timescaledb` esté Up\n"
            "  (docker compose ps) y que DB_HOST/DB_PORT/DB_NAME/DB_USER/\n"
            "  DB_PASSWORD del .env sean correctos.",
            file=sys.stderr,
        )
        return False


def _crear_esquema(conn) -> None:
    with conn.cursor() as cur:
        for sql in _SCHEMA:
            cur.execute(sql)
    conn.commit()


def truncar() -> int:
    """Borra todas las filas de `dqo` y reinicia la secuencia de id.

    Devuelve el número de filas que había antes del truncate.
    """
    from db import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {TABLA}")
            n_prev = cur.fetchone()[0] or 0
            cur.execute(f"TRUNCATE TABLE {TABLA} RESTART IDENTITY")
        conn.commit()
        return int(n_prev)
    finally:
        conn.close()


def cargar(lecturas: Sequence[Lectura], lote: int = 5_000) -> tuple[int, int]:
    """Inserta las lecturas en la tabla `dqo`.

    Retorna (total_enviadas, total_insertadas). Las duplicadas (mismo tag_id +
    timestamp) se descartan silenciosamente gracias a ON CONFLICT DO NOTHING.
    """
    if not lecturas:
        return 0, 0

    from db import get_connection
    conn = get_connection()
    enviadas = 0
    insertadas = 0
    try:
        _crear_esquema(conn)

        with conn.cursor() as cur:
            cur.execute("""
                CREATE TEMP TABLE IF NOT EXISTS _tmp_dqo (
                    tag_id    VARCHAR(64),
                    timestamp TEXT,
                    value     NUMERIC(10,2)
                )
            """)
        conn.commit()

        for offset in range(0, len(lecturas), lote):
            chunk = lecturas[offset:offset + lote]
            buf = io.StringIO()
            for lec in chunk:
                ts_str = lec.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                buf.write(f"{lec.tag_id},{ts_str},{lec.value:.2f}\n")
            buf.seek(0)

            with conn.cursor() as cur:
                cur.execute("TRUNCATE _tmp_dqo")
                cur.copy_expert(
                    "COPY _tmp_dqo (tag_id, timestamp, value) FROM STDIN WITH CSV",
                    buf,
                )
                cur.execute("""
                    INSERT INTO dqo (tag_id, timestamp, value)
                    SELECT tag_id, timestamp::TIMESTAMPTZ, value
                    FROM _tmp_dqo
                    ON CONFLICT (tag_id, timestamp) DO NOTHING
                """)
                insertadas += cur.rowcount
            conn.commit()
            enviadas += len(chunk)
    finally:
        conn.close()

    return enviadas, insertadas
