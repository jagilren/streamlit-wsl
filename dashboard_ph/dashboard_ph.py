"""Dashboard ejecutivo pH — Gerencia Ambiental PTAR.

App autónoma paralela al dashboard DQO. Ejecutar:
    streamlit run dashboard_ph/dashboard_ph.py --server.port 8503
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from streamlit_autorefresh import st_autorefresh

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ModuleNotFoundError:
    pass

from components.refresh_bar import render_refresh_bar
from components.shared_time_filter import (
    get_datetime_range, render_shared_time_filter,
)
from db import get_connection
from dashboard_ph.components.sidebar_filters import render_ph_sidebar_filters
from dashboard_ph.db_init import init_safe
from dashboard_ph.view import render as render_ph


# ── Configuración de página ───────────────────────────────────────────────────
# Cuando este archivo se ejecuta como page bajo home.py, set_page_config ya fue
# llamado por el orquestador y vuelve a llamar aquí lanza StreamlitAPIException.
try:
    st.set_page_config(
        page_title="Dashboard pH — PTAR",
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

# Auto-refresh cada 60s para reflejar las lecturas nuevas del generator (3 min).
AUTOREFRESH_MS = 60_000
st_autorefresh(interval=AUTOREFRESH_MS, key="ph-autorefresh")


# ── Inicialización idempotente del esquema pH ────────────────────────────────
init_safe()


# ── Autenticación (reusa credentials.yaml del proyecto) ───────────────────────
_CREDS_FILE = _ROOT / "credentials.yaml"
if not _CREDS_FILE.exists():
    st.error("No se encontró `credentials.yaml`. Contacta al administrador.")
    st.stop()

with open(_CREDS_FILE, encoding="utf-8") as _f:
    _creds_cfg = yaml.safe_load(_f)

_authenticator = stauth.Authenticate(
    str(_CREDS_FILE.resolve()),
    _creds_cfg["cookie"]["name"],
    _creds_cfg["cookie"]["key"],
    _creds_cfg["cookie"]["expiry_days"],
)
_authenticator.login(location="main")

if st.session_state.get("authentication_status") is False:
    st.error("Usuario o contraseña incorrectos.")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.get('name', '')}**")
    _authenticator.logout("Cerrar sesión", location="sidebar")
    st.divider()
    st.markdown("### 🧪 pH — PTAR")
    st.caption("Lecturas cada 3 min · 4 transmisores.")

    # Filtro de tiempo compartido con el dashboard DQO (mismas keys → persiste
    # al navegar entre páginas dentro de home.py).
    periodo, fi_date, ff_date = render_shared_time_filter()
    render_ph_sidebar_filters()


# Construye el rango de fechas para pasarlo al render.
_fi, _ff = get_datetime_range()


# ── Encabezado ───────────────────────────────────────────────────────────────
st.title("🧪 Dashboard pH — PTAR")
render_refresh_bar(
    autorefresh_seconds=AUTOREFRESH_MS // 1000,
    extra=f"Período: {_fi.date()} al {_ff.date()}",
)
st.divider()


# ── Cuerpo ───────────────────────────────────────────────────────────────────
try:
    _conn = get_connection()
except Exception as exc:
    st.error(
        f"No se pudo conectar a TimescaleDB: {exc}\n\n"
        "Verifica el contenedor `timescaledb` y las variables del `.env`."
    )
    st.stop()

try:
    render_ph(_conn, time_filter={"start": _fi, "end": _ff})
finally:
    _conn.close()
