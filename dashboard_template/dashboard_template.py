"""Dashboard plantilla — entry point Streamlit.

App autónoma o page bajo home.py. Para correr standalone:
    streamlit run dashboard_template/dashboard_template.py --server.port 8505

Al clonar para un nuevo módulo (ej. caudal):
    1. cp -r dashboard_template dashboard_caudal
    2. mv dashboard_caudal/dashboard_template.py dashboard_caudal/dashboard_caudal.py
    3. grep -rli template dashboard_caudal | xargs sed -i \\
         -e 's/template/caudal/g' -e 's/Template/Caudal/g' -e 's/TEMPLATE/CAUDAL/g'
    4. Editar dashboard_caudal/config.py: MODULE_LABEL, UNIT, ICON.
    5. Sembrar caudal_tag_config con los TAGs reales.
    6. Agregar st.Page(...) en home.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ModuleNotFoundError:
    pass

from components.auth import setup_auth
from components.refresh_bar import format_ultimo_dato, render_refresh_bar
from components.shared_time_filter import (
    get_datetime_range, render_shared_time_filter,
)
from db import get_connection
from dashboard_template.components.sidebar_filters import (
    render_template_sidebar_filters,
)
from dashboard_template.config import AUTOREFRESH_MS, ICON, MODULE_LABEL
from dashboard_template.db_init import init_safe
from dashboard_template.queries import get_template_last_timestamp
from dashboard_template.view import render as render_template


# ── Configuración de página ──────────────────────────────────────────────────
try:
    st.set_page_config(
        page_title=f"Dashboard {MODULE_LABEL} — PTAR",
        page_icon=ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

st_autorefresh(interval=AUTOREFRESH_MS, key="template-autorefresh")


# ── Inicialización idempotente del esquema ───────────────────────────────────
init_safe()


# ── Autenticación compartida ─────────────────────────────────────────────────
setup_auth()


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### {ICON} {MODULE_LABEL} — PTAR")

    periodo, fi_date, ff_date = render_shared_time_filter()
    render_template_sidebar_filters()


_fi, _ff = get_datetime_range()


# ── Conexión a BD ────────────────────────────────────────────────────────────
try:
    _conn = get_connection()
except Exception as exc:
    st.error(
        f"No se pudo conectar a TimescaleDB: {exc}\n\n"
        "Verifica el contenedor `timescaledb` y las variables del `.env`."
    )
    st.stop()


# ── Encabezado ───────────────────────────────────────────────────────────────
st.title(f"{ICON} Dashboard {MODULE_LABEL} — PTAR")
_ult_ts = get_template_last_timestamp(_conn)
render_refresh_bar(
    autorefresh_seconds=AUTOREFRESH_MS // 1000,
    ultimo_dato_label=format_ultimo_dato(_ult_ts),
    extra=f"Período: {_fi.date()} al {_ff.date()}",
)
st.divider()


# ── Cuerpo ───────────────────────────────────────────────────────────────────
try:
    render_template(_conn, time_filter={"start": _fi, "end": _ff})
finally:
    _conn.close()
