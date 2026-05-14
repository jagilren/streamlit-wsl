"""DDL del módulo pH: crea ph_measurements (hypertable) y ph_tag_config (seed)."""

from __future__ import annotations

import logging

log = logging.getLogger("dashboard_ph.db_init")

# DDL idempotente. Se ejecuta tanto al arrancar el dashboard como en cada ciclo del
# data_generator (es barato porque todos los CREATE usan IF NOT EXISTS).
_DDL = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE",

    # Tabla de hechos: una fila por TAG por timestamp.
    """
    CREATE TABLE IF NOT EXISTS ph_measurements (
        id         BIGSERIAL,
        tag_id     VARCHAR(20)   NOT NULL,
        timestamp  TIMESTAMPTZ   NOT NULL,
        value      NUMERIC(10,2) NOT NULL,
        quality    INTEGER       NOT NULL DEFAULT 192,
        PRIMARY KEY (timestamp, id)
    )
    """,
    """
    SELECT create_hypertable(
        'ph_measurements', 'timestamp',
        if_not_exists => TRUE,
        migrate_data  => TRUE
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uix_ph_tag_timestamp
        ON ph_measurements (tag_id, timestamp)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ph_tag_time
        ON ph_measurements (tag_id, timestamp DESC)
    """,

    # Tabla de configuración: rangos óptimos y críticos por TAG.
    """
    CREATE TABLE IF NOT EXISTS ph_tag_config (
        tag_id          VARCHAR(20)      PRIMARY KEY,
        tag_description VARCHAR(100)     NOT NULL,
        process_point   VARCHAR(100)     NOT NULL,
        opt_min         DOUBLE PRECISION NOT NULL,
        opt_max         DOUBLE PRECISION NOT NULL,
        crit_min        DOUBLE PRECISION NOT NULL,
        crit_max        DOUBLE PRECISION NOT NULL,
        unit            VARCHAR(10)      DEFAULT 'pH',
        active          BOOLEAN          DEFAULT TRUE,
        updated_at      TIMESTAMPTZ      DEFAULT NOW()
    )
    """,
]

# Seed de los 4 transmisores de pH de la PTAR.
_SEED = [
    ('100-AIT-01', 'Transmisor pH Afluente Bruto',     'Afluente bruto',          6.5, 8.0, 5.5, 9.5),
    ('200-AIT-01', 'Transmisor pH Reactor Biológico',  'Reactor biológico',       6.8, 7.4, 6.0, 8.5),
    ('450-AIT-01', 'Transmisor pH Sedimentador Sec.',  'Sedimentador secundario', 6.5, 7.5, 5.5, 9.0),
    ('600-AIT-01', 'Transmisor pH Efluente Tratado',   'Efluente tratado',        6.0, 9.0, 5.0, 9.5),
]


def init_ph_tables(conn) -> None:
    """Crea tablas y siembra ph_tag_config si está vacía. Idempotente."""
    with conn.cursor() as cur:
        for sql in _DDL:
            cur.execute(sql)
        cur.executemany(
            """
            INSERT INTO ph_tag_config
                (tag_id, tag_description, process_point, opt_min, opt_max, crit_min, crit_max)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tag_id) DO NOTHING
            """,
            _SEED,
        )
    conn.commit()
    log.info("ph_measurements + ph_tag_config listos (seed: %d TAGs).", len(_SEED))


def init_safe() -> bool:
    """Intenta inicializar el esquema. Devuelve True/False sin tumbar la app."""
    try:
        from db import get_connection
        conn = get_connection()
        try:
            init_ph_tables(conn)
        finally:
            conn.close()
        return True
    except Exception as exc:
        log.warning("init_safe: no se pudo inicializar el esquema pH — %s", exc)
        return False
