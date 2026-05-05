import pandas as pd
import streamlit as st
from config import CSV_PATH, CSV_PATH_LAB

_MESES_ES = {
    1: "Enero",    2: "Febrero",   3: "Marzo",     4: "Abril",
    5: "Mayo",     6: "Junio",     7: "Julio",      8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

_MAX_POR_HORA = 60


def _mes_str(ts: pd.Timestamp) -> str:
    return f"{_MESES_ES[ts.month]} {ts.year}"


def _seek(fuente) -> None:
    if hasattr(fuente, "seek"):
        fuente.seek(0)


def _leer_df(fuente) -> pd.DataFrame:
    """Lee y normaliza un CSV en formato largo (TimeStamp, TAG, Value)."""
    _seek(fuente)
    df = pd.read_csv(fuente, dtype={"TAG": str, "Value": float})
    df.columns = df.columns.str.strip()
    df["TimeStamp"] = pd.to_datetime(df["TimeStamp"])
    df["TAG"] = df["TAG"].str.strip()
    _seek(fuente)
    return df


def _downsample_hora(df: pd.DataFrame, n: int = _MAX_POR_HORA) -> pd.DataFrame:
    """
    Por cada (TAG, hora), conserva las n lecturas más próximas al mínimo y
    máximo observados en esa hora. Grupos con ≤ n filas no se modifican.
    Operación completamente vectorizada (sin apply por filas).
    """
    df = df.copy()
    df["_hora"] = df["TimeStamp"].dt.floor("1h")

    grp = df.groupby(["TAG", "_hora"])["Value"]
    grp_min = grp.transform("min")
    grp_max = grp.transform("max")

    dist_lo = (df["Value"] - grp_min).abs()
    dist_hi = (df["Value"] - grp_max).abs()
    # distancia al límite dinámico más cercano: min(|v - min_hora|, |v - max_hora|)
    df["_dist"] = dist_lo.where(dist_lo < dist_hi, dist_hi)

    df["_rank"] = df.groupby(["TAG", "_hora"])["_dist"].rank(method="first", ascending=True)
    df["_cnt"]  = grp.transform("count")

    # Para grupos con más de n filas → quedar con los n de menor distancia.
    # Para grupos con ≤ n filas → _cnt.clip(upper=n) == _cnt, se conservan todos.
    keep = df["_rank"] <= df["_cnt"].clip(upper=n)
    return df[keep].drop(columns=["_hora", "_dist", "_rank", "_cnt"]).reset_index(drop=True)


@st.cache_data(show_spinner="Leyendo lista de TAGs…")
def leer_tags(fuente=CSV_PATH) -> list[str]:
    """Devuelve los TAGs únicos presentes en el CSV (columna TAG)."""
    _seek(fuente)
    df = pd.read_csv(fuente, usecols=["TAG"], dtype={"TAG": str})
    _seek(fuente)
    return sorted(df["TAG"].str.strip().unique().tolist())


@st.cache_data(show_spinner="Cargando datos PLC (pH)…")
def cargar_ph(fuente=CSV_PATH) -> pd.DataFrame:
    """
    Carga el CSV del PLC, aplica downsampling a máximo 60 lecturas/hora y
    devuelve df_ph (fecha_hora, TAGs…, mes).
    """
    df = _downsample_hora(_leer_df(fuente))
    tags = sorted(df["TAG"].unique().tolist())

    if not tags:
        return pd.DataFrame(columns=["fecha_hora", "mes"])

    wide = (
        df
        .pivot_table(index="TimeStamp", columns="TAG", values="Value", aggfunc="mean")
        .reset_index()
    )
    wide.columns.name = None
    wide = wide.rename(columns={"TimeStamp": "fecha_hora"})
    wide["mes"] = wide["fecha_hora"].apply(_mes_str)
    return wide


@st.cache_data(show_spinner="Cargando datos de laboratorio (DQO)…")
def cargar_dqo(fuente=CSV_PATH_LAB) -> pd.DataFrame:
    """
    Carga el CSV de laboratorio, aplica downsampling a máximo 60 lecturas/hora y
    devuelve df_dqo (fecha, TAGs…, mes).
    """
    df = _downsample_hora(_leer_df(fuente))
    tags = sorted(df["TAG"].unique().tolist())

    if not tags:
        return pd.DataFrame(columns=["fecha", "mes"])

    wide = (
        df
        .pivot_table(index="TimeStamp", columns="TAG", values="Value", aggfunc="mean")
        .reset_index()
    )
    wide.columns.name = None
    wide = wide.rename(columns={"TimeStamp": "fecha"})
    wide["fecha"] = pd.to_datetime(wide["fecha"]).dt.normalize()
    wide["mes"] = wide["fecha"].apply(_mes_str)
    return wide
