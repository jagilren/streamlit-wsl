import datetime
import pandas as pd
import streamlit as st
from db import query_df

MESES_ES = {
    1: "Enero",    2: "Febrero",   3: "Marzo",     4: "Abril",
    5: "Mayo",     6: "Junio",     7: "Julio",      8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

_MAX_POR_HORA = 60


def _mes_str(ts: pd.Timestamp) -> str:
    return f"{MESES_ES[ts.month]} {ts.year}"


def _downsample_hora(df: pd.DataFrame, n: int = _MAX_POR_HORA) -> pd.DataFrame:
    """
    Por cada (TAG, hora), conserva las n lecturas más próximas al mínimo y
    máximo observados en esa hora. Grupos con ≤ n filas no se modifican.
    """
    df = df.copy()
    df["_hora"] = df["TimeStamp"].dt.floor("1h")

    grp = df.groupby(["TAG", "_hora"])["Value"]
    grp_min = grp.transform("min")
    grp_max = grp.transform("max")

    dist_lo = (df["Value"] - grp_min).abs()
    dist_hi = (df["Value"] - grp_max).abs()
    df["_dist"] = dist_lo.where(dist_lo < dist_hi, dist_hi)

    df["_rank"] = df.groupby(["TAG", "_hora"])["_dist"].rank(method="first", ascending=True)
    df["_cnt"]  = grp.transform("count")

    keep = df["_rank"] <= df["_cnt"].clip(upper=n)
    return df[keep].drop(columns=["_hora", "_dist", "_rank", "_cnt"]).reset_index(drop=True)


@st.cache_data(ttl=120, show_spinner="Consultando meses disponibles…")
def meses_disponibles() -> list[str]:
    df = query_df("""
        SELECT DISTINCT date_trunc('month', timestamp) AS mes
        FROM sensor_data
        ORDER BY mes
    """)
    if df.empty:
        return []
    return [_mes_str(pd.Timestamp(m)) for m in df["mes"]]


@st.cache_data(ttl=120, show_spinner="Leyendo TAGs configurados…")
def leer_tags_db(tab: str) -> list[str]:
    df = query_df(
        "SELECT tag FROM tag_config WHERE tab = %s ORDER BY tag", (tab,)
    )
    return df["tag"].tolist() if not df.empty else []


@st.cache_data(ttl=120, show_spinner="Buscando TAGs sin clasificar…")
def leer_tags_sin_config() -> list[str]:
    df = query_df("""
        SELECT DISTINCT s.tag_id AS tag
        FROM sensor_data s
        LEFT JOIN tag_config c ON s.tag_id = c.tag
        WHERE c.tag IS NULL
        ORDER BY s.tag_id
    """)
    return df["tag"].tolist() if not df.empty else []


def _cargar_tab(
    tab: str,
    fecha_ini: datetime.datetime,
    fecha_fin: datetime.datetime,
    col_fecha: str,
    normalize: bool = False,
) -> pd.DataFrame:
    df = query_df("""
        SELECT timestamp AS "TimeStamp", tag_id AS "TAG", valor AS "Value"
        FROM sensor_data
        WHERE tag_id IN (SELECT tag FROM tag_config WHERE tab = %(tab)s)
          AND timestamp >= %(ini)s AND timestamp < %(fin)s
        ORDER BY timestamp
    """, {"tab": tab, "ini": fecha_ini, "fin": fecha_fin})
    if df.empty:
        return pd.DataFrame(columns=[col_fecha, "mes"])
    df = _downsample_hora(df)
    wide = (
        df.pivot_table(index="TimeStamp", columns="TAG", values="Value", aggfunc="mean")
        .reset_index()
    )
    wide.columns.name = None
    wide = wide.rename(columns={"TimeStamp": col_fecha})
    if normalize:
        wide[col_fecha] = pd.to_datetime(wide[col_fecha]).dt.normalize()
    wide["mes"] = wide[col_fecha].apply(_mes_str)
    return wide


@st.cache_data(ttl=120, show_spinner="Cargando datos de pH…")
def cargar_ph(fecha_ini: datetime.datetime, fecha_fin: datetime.datetime) -> pd.DataFrame:
    return _cargar_tab("pH", fecha_ini, fecha_fin, "fecha_hora")


@st.cache_data(ttl=120, show_spinner="Cargando datos de DQO…")
def cargar_dqo(fecha_ini: datetime.datetime, fecha_fin: datetime.datetime) -> pd.DataFrame:
    return _cargar_tab("DQO", fecha_ini, fecha_fin, "fecha", normalize=True)
