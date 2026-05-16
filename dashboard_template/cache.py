"""Capa de caché Streamlit para las queries de la plantilla.

Regla crítica: el primer argumento es la conexión y debe prefijarse con `_`
para que Streamlit no intente hashearla (psycopg2 connections no son hashables).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from . import queries


@st.cache_data(ttl=60, show_spinner=False)    # 1 min — config de TAGs
def get_cached_template_tag_configs(_conn) -> list[dict]:
    return queries.get_template_tag_configs(_conn)


@st.cache_data(ttl=30, show_spinner=False)    # 30 s — valores actuales (KPI cards)
def get_cached_current_template(_conn) -> pd.DataFrame:
    return queries.get_current_template_values(_conn)


@st.cache_data(ttl=60, show_spinner=False)    # 1 min — tendencia 24h (legacy)
def get_cached_template_trend(_conn, tag_id: str) -> pd.DataFrame:
    return queries.get_template_trend_24h(_conn, tag_id)


@st.cache_data(ttl=60, show_spinner=False)    # 1 min — tendencia en rango custom
def get_cached_template_trend_range(
    _conn, tag_id: str, fi: datetime, ff: datetime,
) -> pd.DataFrame:
    return queries.get_template_trend_range(_conn, tag_id, fi, ff)


@st.cache_data(ttl=120, show_spinner=False)   # 2 min — violaciones semana móvil
def get_cached_template_violations(
    _conn, tag_id: str, tag_config: dict,
) -> pd.DataFrame:
    return queries.get_template_violations_rolling_week(_conn, tag_id, tag_config)


@st.cache_data(ttl=120, show_spinner=False)   # 2 min — violaciones en rango custom
def get_cached_template_violations_range(
    _conn, tag_id: str, tag_config: dict, fi: datetime, ff: datetime,
) -> pd.DataFrame:
    return queries.get_template_violations_range(_conn, tag_id, tag_config, fi, ff)
