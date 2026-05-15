"""Dashboard ejecutivo OD (Oxígeno Disuelto) — Gerencia Ambiental PTAR.

App autónoma o page bajo home.py. Ejecutar standalone:
    streamlit run dashboard_od/dashboard_od.py --server.port 8504
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
from dashboard_od.components.sidebar_filters import render_od_sidebar_filters
from dashboard_od.db_init import init_safe
from dashboard_od.queries import get_od_last_timestamp
from dashboard_od.view import render as render_od


# ── Configuración de página ───────────────────────────────────────────────────
# Cuando este archivo se ejecuta como page bajo home.py, set_page_config ya fue
# llamado por el orquestador y vuelve a llamar aquí lanza StreamlitAPIException.
try:
    st.set_page_config(
        page_title="Dashboard OD — PTAR",
        page_icon="🫧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

# Auto-refresh cada 60s para reflejar las lecturas nuevas del generator (3 min).
AUTOREFRESH_MS = 60_000
st_autorefresh(interval=AUTOREFRESH_MS, key="od-autorefresh")


# ── Inicialización idempotente del esquema OD ────────────────────────────────
init_safe()


# ── Autenticación compartida ─────────────────────────────────────────────────
# Idempotente: si home.py ya autenticó, no muestra form. En modo standalone,
# pide credenciales y persiste la cookie como antes.
setup_auth()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🫧 OD — PTAR")
    st.caption("Lecturas cada 3 min · 4 transmisores.")

    # Filtro de tiempo compartido (mismas keys que DQO/pH → persiste al navegar).
    periodo, fi_date, ff_date = render_shared_time_filter()
    render_od_sidebar_filters()


# Construye el rango de fechas para pasarlo al render.
_fi, _ff = get_datetime_range()


# ── Conexión a BD (abrir antes del header para poder mostrar el timestamp
# del último dato en la barra de refresh, igual que en DQO). ─────────────────
try:
    _conn = get_connection()
except Exception as exc:
    st.error(
        f"No se pudo conectar a TimescaleDB: {exc}\n\n"
        "Verifica el contenedor `timescaledb` y las variables del `.env`."
    )
    st.stop()


# ── Encabezado ───────────────────────────────────────────────────────────────
st.title("🫧 Dashboard OD — Oxígeno Disuelto")
_ult_ts = get_od_last_timestamp(_conn)
render_refresh_bar(
    autorefresh_seconds=AUTOREFRESH_MS // 1000,
    ultimo_dato_label=format_ultimo_dato(_ult_ts),
    extra=f"Período: {_fi.date()} al {_ff.date()}",
)
st.divider()


# ── Cuerpo ───────────────────────────────────────────────────────────────────
try:
    render_od(_conn, time_filter={"start": _fi, "end": _ff})
finally:
    _conn.close()
