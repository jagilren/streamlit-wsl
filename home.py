"""Home / orquestador multi-dashboard para PTAR.

Lanza ambos dashboards en el mismo proceso/puerto con navegación nativa de
Streamlit (`st.navigation`). Cada dashboard sigue siendo ejecutable de forma
autónoma (`streamlit run dashboard_xxx/dashboard_xxx.py`).

Uso:
    streamlit run home.py --server.port 8501
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ModuleNotFoundError:
    pass


# `set_page_config` debe ejecutarse antes que cualquier otra llamada a Streamlit.
# Cada page hace su propio set_page_config envuelto en try/except, así que solo
# este (el del orquestador) tiene efecto real.
try:
    st.set_page_config(
        page_title="PTAR — Dashboards",
        page_icon="💧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass


# ── Navegación multi-dashboard ────────────────────────────────────────────────
# Cada st.Page apunta al archivo entry de cada dashboard. Los archivos se
# ejecutan tal cual (con su propia auth + sidebar + autorefresh).
pg = st.navigation(
    {
        "Operación": [
            st.Page(
                "dashboard_dqo/dashboard_dqo.py",
                title="DQO",
                icon="🟠",
                default=True,
            ),
            st.Page(
                "dashboard_ph/dashboard_ph.py",
                title="pH",
                icon="🧪",
            ),
        ],
    }
)
pg.run()
