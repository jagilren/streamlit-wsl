"""Acceso a datos de la tabla `dqo` en TimescaleDB.

Reusa `db.get_connection()` del proyecto raíz para no duplicar configuración.
Las queries siempre filtran por `tag_id` y por rango de fechas — nunca SELECT
sin filtros.
"""

from __future__ import annotations

import logging
import sys
import time as _time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Permite ejecutar este módulo cuando streamlit invoca el script
# desde dashboard_dqo/.
_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from db import get_connection  # noqa: E402

from .config import CACHE_TTL, CACHE_TTL_LIVE, TABLA, TAG_ENTRADA, TAG_SALIDA

_log = logging.getLogger("dashboard_dqo.db")


def _run_df(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Ejecuta una consulta y devuelve un DataFrame, logueando el tiempo."""
    t0 = _time.monotonic()
    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    elapsed = (_time.monotonic() - t0) * 1000
    _log.info("query %.0f ms · %d filas · %s", elapsed, len(df), sql.split()[0])
    return df


# ── 4.1 Serie temporal en formato long (TimeStamp, tag_id, valor) ─────────────
@st.cache_data(ttl=CACHE_TTL, show_spinner="Consultando serie temporal…")
def get_dqo_serie_temporal(
    fecha_inicio: datetime, fecha_fin: datetime,
    tags: tuple[str, ...] = (TAG_ENTRADA, TAG_SALIDA),
) -> pd.DataFrame:
    """Devuelve DataFrame en formato long con columnas TimeStamp, tag_id, valor.

    Acepta cualquier tupla de TAGs — el chart_builder iterará sobre los presentes.
    Agrupa por hora usando time_bucket de TimescaleDB para reducir volumen.
    """
    sql = f"""
        SELECT
            time_bucket('1 hour', timestamp) AS ts,
            tag_id,
            AVG(value)::float AS valor
        FROM {TABLA}
        WHERE tag_id = ANY(%(tags)s)
          AND timestamp BETWEEN %(fi)s AND %(ff)s
          AND value IS NOT NULL
          AND value > 0
        GROUP BY ts, tag_id
        ORDER BY ts
    """
    df = _run_df(sql, {"tags": list(tags), "fi": fecha_inicio, "ff": fecha_fin})
    if df.empty:
        return pd.DataFrame(columns=["TimeStamp", "tag_id", "valor"])
    return df.rename(columns={"ts": "TimeStamp"})


# ── 4.2 KPIs actuales ─────────────────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL_LIVE, show_spinner="Calculando KPIs…")
def get_kpi_actual(
    dias_atras: int = 7, tags_extra: tuple[str, ...] = (),
    tag_in: str = TAG_ENTRADA, tag_out: str = TAG_SALIDA,
) -> dict[str, Any]:
    """KPIs sobre los últimos N días.

    Siempre consulta el afluente y el efluente (base de los KPIs principales).
    Los `tags_extra` (intermedios opcionales) se devuelven en `valores_por_tag`
    para que la tabla de cumplimiento los muestre como referencia.

    `tag_in`/`tag_out`: TAGs resueltos por el caller desde el catálogo BD.
    Defaults a las constantes de config.py para retro-compatibilidad.
    """
    todos_tags = (tag_in, tag_out, *tags_extra)
    sql = f"""
        SELECT
            tag_id,
            AVG(value)::float AS promedio,
            MAX(timestamp)    AS ultimo_ts
        FROM {TABLA}
        WHERE tag_id = ANY(%(tags)s)
          AND timestamp >= NOW() - (%(d)s::int * INTERVAL '1 day')
          AND value IS NOT NULL
        GROUP BY tag_id
    """
    df = _run_df(sql, {"tags": list(todos_tags), "d": dias_atras})

    out: dict[str, Any] = {
        "dqo_efluente_actual": None,
        "dqo_afluente_actual": None,
        "eficiencia_remocion": None,
        "fecha_ultimo_registro": None,
        "ventana_dias": dias_atras,
        "valores_por_tag": {},
    }
    if df.empty:
        return out

    por_tag = df.set_index("tag_id").to_dict("index")
    out["valores_por_tag"] = {t: v["promedio"] for t, v in por_tag.items()}
    entrada = por_tag.get(tag_in, {}).get("promedio")
    salida = por_tag.get(tag_out, {}).get("promedio")
    out["dqo_afluente_actual"] = entrada
    out["dqo_efluente_actual"] = salida
    if entrada and entrada > 0 and salida is not None:
        out["eficiencia_remocion"] = (1.0 - (salida / entrada)) * 100.0

    fechas = [v.get("ultimo_ts") for v in por_tag.values() if v.get("ultimo_ts")]
    if fechas:
        out["fecha_ultimo_registro"] = max(fechas)
    return out


# ── Comparativo período anterior (para delta % en KPIs) ───────────────────────
@st.cache_data(ttl=CACHE_TTL)
def get_kpi_periodo(
    fecha_inicio: datetime, fecha_fin: datetime,
    tag_in: str = TAG_ENTRADA, tag_out: str = TAG_SALIDA,
) -> dict[str, float | None]:
    """Promedios de DQO en un período arbitrario. Útil para calcular deltas
    contra el período inmediatamente anterior."""
    sql = f"""
        SELECT
            tag_id,
            AVG(value)::float AS promedio
        FROM {TABLA}
        WHERE tag_id IN (%(t_in)s, %(t_out)s)
          AND timestamp BETWEEN %(fi)s AND %(ff)s
          AND value IS NOT NULL
        GROUP BY tag_id
    """
    df = _run_df(sql, {
        "t_in": tag_in, "t_out": tag_out,
        "fi": fecha_inicio, "ff": fecha_fin,
    })
    if df.empty:
        return {"entrada": None, "salida": None, "eficiencia": None}
    por_tag = df.set_index("tag_id")["promedio"].to_dict()
    entrada = por_tag.get(tag_in)
    salida = por_tag.get(tag_out)
    eff = None
    if entrada and entrada > 0 and salida is not None:
        eff = (1.0 - (salida / entrada)) * 100.0
    return {"entrada": entrada, "salida": salida, "eficiencia": eff}


# ── 4.3 Días de cumplimiento ──────────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL, show_spinner="Calculando cumplimiento…")
def get_dias_cumplimiento(
    fecha_inicio: datetime, fecha_fin: datetime, limite: float,
    tag_out: str = TAG_SALIDA,
) -> dict[str, Any]:
    """Cuenta días donde el promedio diario del efluente <= límite."""
    sql = f"""
        SELECT
            (timestamp AT TIME ZONE 'UTC')::date AS fecha,
            AVG(value)::float AS dqo_salida_avg
        FROM {TABLA}
        WHERE tag_id = %(t_out)s
          AND timestamp BETWEEN %(fi)s AND %(ff)s
          AND value IS NOT NULL
        GROUP BY fecha
        ORDER BY fecha
    """
    df = _run_df(sql, {"t_out": tag_out, "fi": fecha_inicio, "ff": fecha_fin})

    if df.empty:
        return {
            "dias_cumplimiento": 0, "dias_total": 0,
            "pct_cumplimiento": None, "df_diario": df,
        }

    df["Cumple"] = df["dqo_salida_avg"] <= limite
    df = df.rename(columns={"fecha": "Fecha", "dqo_salida_avg": "DQO_Salida_Avg"})
    dias_total = len(df)
    dias_cumplimiento = int(df["Cumple"].sum())
    pct = (dias_cumplimiento / dias_total) * 100.0 if dias_total else None
    return {
        "dias_cumplimiento": dias_cumplimiento,
        "dias_total": dias_total,
        "pct_cumplimiento": pct,
        "df_diario": df,
    }


# ── 4.4 Distribución (histograma) ─────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL, show_spinner="Consultando distribución…")
def get_distribucion_dqo_salida(
    fecha_inicio: datetime, fecha_fin: datetime,
    tag_out: str = TAG_SALIDA,
) -> pd.Series:
    sql = f"""
        SELECT value::float AS value
        FROM {TABLA}
        WHERE tag_id = %(t_out)s
          AND timestamp BETWEEN %(fi)s AND %(ff)s
          AND value IS NOT NULL
          AND value > 0
        ORDER BY timestamp
    """
    df = _run_df(sql, {"t_out": tag_out, "fi": fecha_inicio, "ff": fecha_fin})
    return df["value"] if not df.empty else pd.Series(dtype=float)


# ── 4.5 Comparativo mensual (últimos 12 meses) ────────────────────────────────
@st.cache_data(ttl=CACHE_TTL, show_spinner="Calculando comparativo mensual…")
def get_comparativo_mensual(
    meses: int = 12,
    tag_in: str = TAG_ENTRADA, tag_out: str = TAG_SALIDA,
) -> pd.DataFrame:
    """Devuelve DataFrame con columnas:

        Mes, DQO_Entrada_Avg, DQO_Salida_Avg,
        DQO_Salida_Min, DQO_Salida_Max, Eficiencia_Pct

    Las columnas Min/Max del efluente alimentan el gráfico de barras agrupadas
    (mín · promedio · máx mensual). Promedios de entrada/salida y eficiencia
    se mantienen para el comparativo anual.
    """
    sql = f"""
        SELECT
            date_trunc('month', timestamp) AS mes,
            tag_id,
            AVG(value)::float AS promedio,
            MIN(value)::float AS minimo,
            MAX(value)::float AS maximo
        FROM {TABLA}
        WHERE tag_id IN (%(t_in)s, %(t_out)s)
          AND timestamp >= date_trunc('month', NOW()) - (%(m)s::int - 1) * INTERVAL '1 month'
          AND value IS NOT NULL
        GROUP BY mes, tag_id
        ORDER BY mes
    """
    df = _run_df(sql, {"t_in": tag_in, "t_out": tag_out, "m": meses})
    if df.empty:
        return pd.DataFrame(columns=[
            "Mes", "DQO_Entrada_Avg", "DQO_Salida_Avg",
            "DQO_Salida_Min", "DQO_Salida_Max", "Eficiencia_Pct",
        ])

    pivot = (
        df.pivot(index="mes", columns="tag_id", values="promedio")
          .rename(columns={tag_in: "DQO_Entrada_Avg", tag_out: "DQO_Salida_Avg"})
    )
    salida = df[df["tag_id"] == tag_out].set_index("mes")
    pivot["DQO_Salida_Min"] = salida["minimo"]
    pivot["DQO_Salida_Max"] = salida["maximo"]
    pivot = pivot.reset_index().rename(columns={"mes": "Mes"})
    pivot["Eficiencia_Pct"] = (
        (1.0 - pivot["DQO_Salida_Avg"] / pivot["DQO_Entrada_Avg"]) * 100.0
    )
    return pivot


# ── 4.6 Alarmas activas ───────────────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL, show_spinner="Detectando alarmas…")
def get_alarmas_activas(
    dias_atras: int = 14,
    pico_afluente: float = 1800.0,
    limite_efluente: float = 200.0,
    alerta_efluente: float = 160.0,
    meta_eficiencia: float = 90.0,
    tag_in: str = TAG_ENTRADA, tag_out: str = TAG_SALIDA,
) -> list[dict]:
    """Recorre los últimos N días y emite alarmas por:
       1) pico en el afluente   > pico_afluente   → crítico
       2) efluente promedio diario > límite       → crítico
                                   > alerta       → alerta
       3) eficiencia diaria < meta - 10           → crítico
                            < meta - 5            → alerta
    """
    sql = f"""
        SELECT
            (timestamp AT TIME ZONE 'UTC')::date AS dia,
            tag_id,
            MAX(value)::float AS max_val,
            AVG(value)::float AS avg_val
        FROM {TABLA}
        WHERE tag_id IN (%(t_in)s, %(t_out)s)
          AND timestamp >= NOW() - (%(d)s::int * INTERVAL '1 day')
          AND value IS NOT NULL
        GROUP BY dia, tag_id
        ORDER BY dia DESC
    """
    df = _run_df(sql, {"t_in": tag_in, "t_out": tag_out, "d": dias_atras})
    if df.empty:
        return []

    pivot_avg = df.pivot(index="dia", columns="tag_id", values="avg_val")
    pivot_max = df.pivot(index="dia", columns="tag_id", values="max_val")

    alarmas: list[dict] = []
    for dia in pivot_avg.index:
        entrada_avg = pivot_avg.at[dia, tag_in] if tag_in in pivot_avg.columns else None
        entrada_max = pivot_max.at[dia, tag_in] if tag_in in pivot_max.columns else None
        salida_avg = pivot_avg.at[dia, tag_out] if tag_out in pivot_avg.columns else None

        if entrada_max is not None and entrada_max > pico_afluente:
            alarmas.append({
                "categoria": "dqo",
                "tipo": "Pico de carga afluente",
                "descripcion": f"{tag_in} superó {pico_afluente:.0f} mg/L",
                "valor": entrada_max, "unidad": "mg/L",
                "timestamp": dia, "tag": tag_in, "severidad": "critico",
            })

        if salida_avg is not None:
            if salida_avg > limite_efluente:
                alarmas.append({
                    "categoria": "dqo",
                    "tipo": "Excedencia DQO efluente",
                    "descripcion": f"{tag_out} promedio diario > límite {limite_efluente:.0f} mg/L",
                    "valor": salida_avg, "unidad": "mg/L",
                    "timestamp": dia, "tag": tag_out, "severidad": "critico",
                })
            elif salida_avg > alerta_efluente:
                alarmas.append({
                    "categoria": "dqo",
                    "tipo": "Alerta DQO efluente",
                    "descripcion": f"{tag_out} > umbral de alerta {alerta_efluente:.0f} mg/L",
                    "valor": salida_avg, "unidad": "mg/L",
                    "timestamp": dia, "tag": tag_out, "severidad": "alerta",
                })

        if entrada_avg and salida_avg is not None and entrada_avg > 0:
            eff = (1.0 - salida_avg / entrada_avg) * 100.0
            if eff < meta_eficiencia - 10:
                alarmas.append({
                    "categoria": "eficiencia",
                    "tipo": "Eficiencia crítica",
                    "descripcion": f"Eficiencia diaria < {meta_eficiencia - 10:.0f}%",
                    "valor": eff, "unidad": "%",
                    "timestamp": dia, "tag": "ENTRADA/SALIDA", "severidad": "critico",
                })
            elif eff < meta_eficiencia - 5:
                alarmas.append({
                    "categoria": "eficiencia",
                    "tipo": "Eficiencia por debajo de meta",
                    "descripcion": f"Eficiencia diaria < {meta_eficiencia - 5:.0f}%",
                    "valor": eff, "unidad": "%",
                    "timestamp": dia, "tag": "ENTRADA/SALIDA", "severidad": "alerta",
                })

    # Críticos primero, luego por fecha desc
    orden_sev = {"critico": 0, "alerta": 1}
    alarmas.sort(key=lambda a: (orden_sev[a["severidad"]], -a["timestamp"].toordinal()))
    return alarmas


# ── Estadísticas de eficiencia para gauge (período, mín. semanal, anual) ──────
@st.cache_data(ttl=CACHE_TTL)
def get_eficiencia_stats(
    fecha_inicio: datetime, fecha_fin: datetime,
    tag_in: str = TAG_ENTRADA, tag_out: str = TAG_SALIDA,
) -> dict[str, float | None]:
    """Devuelve {promedio_periodo, minimo_semanal, promedio_anual} para el gauge."""
    sql_periodo = f"""
        SELECT
            (timestamp AT TIME ZONE 'UTC')::date AS dia,
            tag_id,
            AVG(value)::float AS avg_val
        FROM {TABLA}
        WHERE tag_id IN (%(t_in)s, %(t_out)s)
          AND timestamp BETWEEN %(fi)s AND %(ff)s
          AND value IS NOT NULL
        GROUP BY dia, tag_id
    """
    df = _run_df(sql_periodo, {"t_in": tag_in, "t_out": tag_out,
                               "fi": fecha_inicio, "ff": fecha_fin})

    def _eff_serie(d: pd.DataFrame) -> pd.Series:
        if d.empty:
            return pd.Series(dtype=float)
        p = d.pivot(index="dia", columns="tag_id", values="avg_val").dropna(how="any")
        if p.empty or tag_in not in p.columns or tag_out not in p.columns:
            return pd.Series(dtype=float)
        return (1.0 - p[tag_out] / p[tag_in]) * 100.0

    eff_periodo = _eff_serie(df)
    prom_periodo = float(eff_periodo.mean()) if not eff_periodo.empty else None

    sql_semana = sql_periodo.replace(
        "BETWEEN %(fi)s AND %(ff)s",
        ">= NOW() - INTERVAL '7 days'",
    )
    df_sem = _run_df(sql_semana, {"t_in": tag_in, "t_out": tag_out})
    eff_sem = _eff_serie(df_sem)
    min_sem = float(eff_sem.min()) if not eff_sem.empty else None

    sql_anual = sql_periodo.replace(
        "BETWEEN %(fi)s AND %(ff)s",
        ">= date_trunc('year', NOW())",
    )
    df_an = _run_df(sql_anual, {"t_in": tag_in, "t_out": tag_out})
    eff_an = _eff_serie(df_an)
    prom_anual = float(eff_an.mean()) if not eff_an.empty else None

    return {
        "promedio_periodo": prom_periodo,
        "minimo_semanal": min_sem,
        "promedio_anual": prom_anual,
    }
