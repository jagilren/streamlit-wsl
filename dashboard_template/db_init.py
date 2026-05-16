"""DDL del módulo plantilla: crea template_measurements (hypertable) y
template_tag_config (sin seed — el clonador lo siembra a mano)."""

from __future__ import annotations

import logging

log = logging.getLogger("dashboard_template.db_init")

# DDL idempotente. Se ejecuta al arrancar el dashboard. Es barato (todos los
# CREATE usan IF NOT EXISTS) y permite levantar la app sin pasos manuales.
_DDL = [
    "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE",

    # Tabla de hechos: una fila por TAG por timestamp.
    """
    CREATE TABLE IF NOT EXISTS template_measurements (
        id         BIGSERIAL,
        tag_id     VARCHAR(20)   NOT NULL,
        timestamp  TIMESTAMPTZ   NOT NULL,
        value      NUMERIC(12,3) NOT NULL,
        quality    INTEGER       NOT NULL DEFAULT 192,
        PRIMARY KEY (timestamp, id)
    )
    """,
    """
    SELECT create_hypertable(
        'template_measurements', 'timestamp',
        if_not_exists => TRUE,
        migrate_data  => TRUE
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uix_template_tag_timestamp
        ON template_measurements (tag_id, timestamp)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_template_tag_time
        ON template_measurements (tag_id, timestamp DESC)
    """,

    # Tabla de configuración: rangos óptimos y críticos por TAG.
    """
    CREATE TABLE IF NOT EXISTS template_tag_config (
        tag_id          VARCHAR(20)      PRIMARY KEY,
        tag_description VARCHAR(100)     NOT NULL,
        process_point   VARCHAR(100)     NOT NULL,
        opt_min         DOUBLE PRECISION NOT NULL,
        opt_max         DOUBLE PRECISION NOT NULL,
        crit_min        DOUBLE PRECISION NOT NULL,
        crit_max        DOUBLE PRECISION NOT NULL,
        unit            VARCHAR(20)      DEFAULT 'u',
        active          BOOLEAN          DEFAULT TRUE,
        updated_at      TIMESTAMPTZ      DEFAULT NOW()
    )
    """,
]


def init_template_tables(conn) -> None:
    """Crea tablas de measurements + tag_config. Idempotente.

    No siembra TAGs: cada deployment debe poblar template_tag_config con sus
    instrumentos reales (vía SQL directo o una UI de admin futura). El
    dashboard maneja la tabla vacía con un st.warning.
    """
    with conn.cursor() as cur:
        for sql in _DDL:
            cur.execute(sql)
    conn.commit()
    log.info("template_measurements + template_tag_config listos.")


def init_safe() -> bool:
    """Intenta inicializar el esquema. Devuelve True/False sin tumbar la app."""
    try:
        from db import get_connection
        conn = get_connection()
        try:
            init_template_tables(conn)
        finally:
            conn.close()
        return True
    except Exception as exc:
        log.warning("init_safe: no se pudo inicializar el esquema template — %s", exc)
        return False
