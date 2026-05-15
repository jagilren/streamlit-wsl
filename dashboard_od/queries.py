"""Queries SQL específicas del dashboard OD.

Todas devuelven pandas.DataFrame. La conexión se pasa explícitamente para
respetar el patrón del proyecto (cache via cache.py con prefijo `_conn`).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import psycopg2.extras

from .utils import classify_violation, deviation


def _run_df(conn, sql: str, params: dict | None = None) -> pd.DataFrame:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or {})
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
    return pd.DataFrame([dict(r) for r in rows], columns=cols)


def get_od_tag_configs(conn) -> list[dict]:
    """Lee od_tag_config para los TAGs activos."""
    sql = """
        SELECT tag_id, tag_description, process_point,
               opt_min, opt_max, crit_min, crit_max, unit
        FROM od_tag_config
        WHERE active = TRUE
        ORDER BY tag_id
    """
    df = _run_df(conn, sql)
    return df.to_dict("records")


def get_current_od_values(conn) -> pd.DataFrame:
    """Última medición de cada TAG. Columnas: tag_id, timestamp, value, quality."""
    sql = """
        SELECT DISTINCT ON (tag_id)
               tag_id, timestamp, value::float AS value, quality
        FROM od_measurements
        ORDER BY tag_id, timestamp DESC
    """
    return _run_df(conn, sql)


def get_od_last_timestamp(conn) -> datetime | None:
    """Timestamp del registro más reciente en od_measurements (cualquier TAG).

    Usado por el refresh_bar para mostrar cuándo entró el último dato.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(timestamp) FROM od_measurements")
        row = cur.fetchone()
    return row[0] if row else None


def get_od_trend_24h(conn, tag_id: str) -> pd.DataFrame:
    """Mediciones de las últimas 24h para un TAG, ordenadas ascendente."""
    sql = """
        SELECT timestamp, value::float AS value
        FROM od_measurements
        WHERE tag_id = %(tag)s
          AND timestamp >= NOW() - INTERVAL '24 hours'
        ORDER BY timestamp ASC
    """
    return _run_df(conn, sql, {"tag": tag_id})


def get_od_trend_range(conn, tag_id: str, fi: datetime, ff: datetime) -> pd.DataFrame:
    """Mediciones de un TAG en [fi, ff], ordenadas ascendente."""
    sql = """
        SELECT timestamp, value::float AS value
        FROM od_measurements
        WHERE tag_id = %(tag)s
          AND timestamp >= %(fi)s
          AND timestamp <= %(ff)s
        ORDER BY timestamp ASC
    """
    return _run_df(conn, sql, {"tag": tag_id, "fi": fi, "ff": ff})


def get_od_violations_rolling_week(
    conn, tag_id: str, tag_config: dict, max_records: int = 60,
) -> pd.DataFrame:
    """Eventos fuera del rango óptimo en los últimos 7 días."""
    sql = """
        SELECT timestamp, value::float AS value
        FROM od_measurements
        WHERE tag_id = %(tag)s
          AND timestamp >= NOW() - INTERVAL '7 days'
          AND (value < %(opt_min)s OR value > %(opt_max)s)
        ORDER BY timestamp DESC
        LIMIT %(lim)s
    """
    df = _run_df(conn, sql, {
        "tag": tag_id,
        "opt_min": tag_config["opt_min"],
        "opt_max": tag_config["opt_max"],
        "lim": max_records,
    })
    return _enrich_violations(df, tag_config)


def get_od_violations_range(
    conn, tag_id: str, tag_config: dict, fi: datetime, ff: datetime,
    max_records: int = 60,
) -> pd.DataFrame:
    """Eventos fuera del rango óptimo en [fi, ff]. Mismo shape que rolling_week."""
    sql = """
        SELECT timestamp, value::float AS value
        FROM od_measurements
        WHERE tag_id = %(tag)s
          AND timestamp >= %(fi)s
          AND timestamp <= %(ff)s
          AND (value < %(opt_min)s OR value > %(opt_max)s)
        ORDER BY timestamp DESC
        LIMIT %(lim)s
    """
    df = _run_df(conn, sql, {
        "tag": tag_id, "fi": fi, "ff": ff,
        "opt_min": tag_config["opt_min"], "opt_max": tag_config["opt_max"],
        "lim": max_records,
    })
    return _enrich_violations(df, tag_config)


def _enrich_violations(df: pd.DataFrame, tag_config: dict) -> pd.DataFrame:
    """Anota cada fila con `deviation`, `violation_type`, `severity`."""
    if df.empty:
        df["deviation"] = []
        df["violation_type"] = []
        df["severity"] = []
        return df
    df["deviation"] = df["value"].apply(lambda v: deviation(float(v), tag_config))
    cls = df["value"].apply(lambda v: classify_violation(float(v), tag_config))
    df["violation_type"] = [c[0] for c in cls]
    df["severity"] = [c[1] for c in cls]
    return df


def insert_od_measurement(
    conn, tag_id: str, value: float, quality: int = 192,
    ts: datetime | None = None,
) -> int:
    """Inserta una lectura. Idempotente: (tag_id, timestamp) único.

    Devuelve 1 si insertó, 0 si era duplicada.
    """
    if ts is None:
        ts = datetime.now(timezone.utc).replace(tzinfo=None)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO od_measurements (tag_id, timestamp, value, quality)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tag_id, timestamp) DO NOTHING
            """,
            (tag_id, ts, round(value, 2), quality),
        )
        inserted = cur.rowcount
    conn.commit()
    return inserted
