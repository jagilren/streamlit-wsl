"""Home / orquestador multi-dashboard para PTAR.

Lanza ambos dashboards en el mismo proceso/puerto con navegación nativa de
Streamlit (`st.navigation`). Cada dashboard sigue siendo ejecutable de forma
autónoma (`streamlit run dashboard_xxx/dashboard_xxx.py`).

Uso:
    streamlit run home.py --server.port 8501
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import html as components_html

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


# ── Encabezado global ─────────────────────────────────────────────────────────
# Todo el encabezado vive en un único iframe (`components_html`) para poder
# aplicar media queries CSS reales — `st.columns` no es responsive.
_LOGO = _ROOT / "assets" / "logo_rpci.png"


def _logo_html() -> str:
    """Devuelve el HTML del logo. Si existe el archivo, lo embebe en base64;
    si no, usa un fallback de texto con las iniciales 'RPCI'."""
    if _LOGO.exists():
        b64 = base64.b64encode(_LOGO.read_bytes()).decode("ascii")
        return (
            f'<img class="rpci-logo" alt="RPCI" '
            f'src="data:image/png;base64,{b64}" />'
        )
    return (
        '<div style="font-weight:800;color:#1B7FB8;font-size:20px;'
        'letter-spacing:0.05em">RPCI</div>'
        '<div style="font-size:10px;color:#666">Red Proyectos con Ingeniería</div>'
    )


_HEADER_HTML = f"""
<style>
  .rpci-header {{
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 4px 0;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  .rpci-logo-wrap {{ flex: 0 0 auto; width: 140px; }}
  .rpci-logo {{ width: 100%; max-height: 70px; object-fit: contain; display: block; }}
  .rpci-titulo {{ flex: 1 1 auto; min-width: 0; }}
  .rpci-titulo h2 {{
    margin: 0; color: #185FA5; font-weight: 700;
    font-size: 1.6rem; line-height: 1.2;
  }}
  .rpci-modulo {{ color: #555; font-size: 13px; margin-top: 4px; }}
  .rpci-modulo strong {{ color: #185FA5; }}
  .rpci-reloj {{ flex: 0 0 auto; text-align: right; min-width: 160px; }}
  .rpci-time {{
    font-size: 24px; font-weight: 700;
    font-family: "Courier New", monospace; color: #185FA5; line-height: 1.2;
  }}
  .rpci-date {{ font-size: 12px; color: #666; }}

  /* Móvil: layout vertical centrado. */
  @media (max-width: 640px) {{
    .rpci-header {{ flex-direction: column; gap: 8px; text-align: center; }}
    .rpci-logo-wrap {{ width: 120px; }}
    .rpci-reloj {{ text-align: center; min-width: 0; }}
    .rpci-titulo h2 {{ font-size: 1.3rem; }}
  }}
</style>

<div class="rpci-header">
  <div class="rpci-logo-wrap">{_logo_html()}</div>
  <div class="rpci-titulo">
    <h2>💧 PTAR Industrial — Sistema de Monitoreo</h2>
    <div class="rpci-modulo">
      Módulo activo: <strong>{pg.icon} {pg.title}</strong>
    </div>
  </div>
  <div class="rpci-reloj">
    <div class="rpci-time" id="rpci-time">--:--:--</div>
    <div class="rpci-date" id="rpci-date">—</div>
  </div>
</div>

<script>
  // Reloj en vivo: tick cada segundo, solo actualiza el iframe (no re-rerenderiza
  // el resto de Streamlit).
  const _meses = ['ene','feb','mar','abr','may','jun',
                  'jul','ago','sep','oct','nov','dic'];
  const _dias  = ['Domingo','Lunes','Martes','Miércoles',
                  'Jueves','Viernes','Sábado'];
  const _t = document.getElementById('rpci-time');
  const _d = document.getElementById('rpci-date');
  function _tick() {{
    const n  = new Date();
    const hh = String(n.getHours()).padStart(2, '0');
    const mm = String(n.getMinutes()).padStart(2, '0');
    const ss = String(n.getSeconds()).padStart(2, '0');
    _t.textContent = hh + ':' + mm + ':' + ss;
    const dd  = String(n.getDate()).padStart(2, '0');
    const mes = _meses[n.getMonth()];
    _d.textContent = _dias[n.getDay()] + ', ' + dd + ' ' + mes + ' ' + n.getFullYear();
  }}
  _tick();
  setInterval(_tick, 1000);

  // Ajuste dinámico de la altura del iframe — necesario porque al colapsar
  // a vertical en móvil, la altura del contenido crece de ~80px a ~200px.
  function _resize() {{
    const h = document.body.scrollHeight;
    window.parent.postMessage(
      {{type: 'streamlit:setFrameHeight', height: h}}, '*'
    );
  }}
  new ResizeObserver(_resize).observe(document.body);
  window.addEventListener('load', _resize);
</script>
"""

# height inicial = 100 px (suficiente para desktop); _resize() lo ajusta luego.
components_html(_HEADER_HTML, height=100)

st.markdown(
    "<hr style='margin:6px 0 14px 0;border:none;"
    "border-top:2px solid #185FA5;opacity:0.3'>",
    unsafe_allow_html=True,
)


# ── Render del dashboard activo ──────────────────────────────────────────────
pg.run()
