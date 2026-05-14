"""Componentes Plotly + HTML de las tarjetas y tablas del dashboard pH."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..utils import STATUS_CONFIG, compute_ph_status


# ── 7.1 — Gráfica de tendencia 24h por TAG ──────────────────────────────────
def render_ph_trend_chart(df: pd.DataFrame, tag_config: dict, height: int = 220) -> go.Figure:
    """Tendencia 24h con banda óptima sombreada y líneas críticas."""
    fig = go.Figure()

    if not df.empty:
        ult_val = float(df["value"].iloc[-1])
        estado = compute_ph_status(ult_val, tag_config)
        color_linea = STATUS_CONFIG[estado]["color"]
    else:
        color_linea = STATUS_CONFIG["no_data"]["color"]

    # Banda óptima (verde semitransparente). Plotly hace fill='tonexty' entre dos trazas.
    if not df.empty:
        x_band = df["timestamp"]
        fig.add_trace(go.Scatter(
            x=x_band, y=[tag_config["opt_min"]] * len(x_band),
            mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=x_band, y=[tag_config["opt_max"]] * len(x_band),
            mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor="rgba(29, 158, 117, 0.15)",
            hoverinfo="skip", showlegend=False,
        ))

    # Serie principal
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["value"],
        mode="lines", line=dict(color=color_linea, width=2),
        name="pH", hovertemplate="%{x|%H:%M}<br>pH=%{y:.2f}<extra></extra>",
        showlegend=False,
    ))

    # Líneas de referencia
    fig.add_hline(y=tag_config["opt_min"], line_color="#1D9E75", line_width=1,
                  line_dash="solid", opacity=0.7)
    fig.add_hline(y=tag_config["opt_max"], line_color="#1D9E75", line_width=1,
                  line_dash="solid", opacity=0.7)
    fig.add_hline(y=tag_config["crit_min"], line_color="#A32D2D", line_width=1,
                  line_dash="dash", opacity=0.8)
    fig.add_hline(y=tag_config["crit_max"], line_color="#A32D2D", line_width=1,
                  line_dash="dash", opacity=0.8)

    fig.update_layout(
        height=height,
        margin=dict(l=40, r=10, t=10, b=30),
        xaxis=dict(tickformat="%H:%M", showgrid=True, gridcolor="#EEE"),
        yaxis=dict(
            title="pH",
            range=[tag_config["crit_min"] - 1.0, tag_config["crit_max"] + 1.0],
            showgrid=True, gridcolor="#EEE",
        ),
        showlegend=False,
        plot_bgcolor="white",
    )
    return fig


# ── 7.2 — Tabla de eventos fuera de rango ───────────────────────────────────
def render_violations_table(df_viol: pd.DataFrame, tag_config: dict) -> None:
    """Resumen de eventos como caption coloreado.

    La tabla detallada queda oculta dentro de un `st.expander` que el usuario
    expande con click. Sin eventos → caption verde 'todo bien'.
    """
    # ── Resumen siempre visible (caption con colores estándar) ──────────────
    if df_viol.empty:
        st.markdown(
            "<div style='background:#E1F5EE;color:#1D9E75;padding:8px 12px;"
            "border-radius:6px;font-size:13px;font-weight:600;"
            "border-left:4px solid #1D9E75;margin-top:6px;'>"
            "✓ Sin eventos fuera de rango en los últimos 7 días"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    n_crit = int((df_viol["severity"] == "crítico").sum())
    n_warn = int((df_viol["severity"] == "advertencia").sum())

    if n_crit > 0:
        # Predomina crítico → caption rojo (con conteo de advertencias si las hay).
        bg, fg, border, icon = "#FCEBEB", "#A32D2D", "#C62828", "🚨"
        texto = f"{n_crit} crítico(s)"
        if n_warn:
            texto += f" · {n_warn} advertencia(s)"
    else:
        # Solo advertencias → caption naranja.
        bg, fg, border, icon = "#FAEEDA", "#B86A00", "#E07B00", "⚠"
        texto = f"{n_warn} advertencia(s)"

    st.markdown(
        f"<div style='background:{bg};color:{fg};padding:8px 12px;"
        f"border-radius:6px;font-size:13px;font-weight:700;"
        f"border-left:4px solid {border};margin-top:6px;'>"
        f"{icon} {texto} en los últimos 7 días"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Detalle dentro de un expander (colapsado por defecto) ───────────────
    with st.expander("Ver detalle de eventos", expanded=False):
        df_show = df_viol.copy()
        df_show["timestamp"] = pd.to_datetime(df_show["timestamp"]).dt.strftime("%d/%m %H:%M")
        df_show = df_show.rename(columns={
            "timestamp": "Fecha/Hora", "value": "pH",
            "deviation": "Desviación", "violation_type": "Tipo",
        })

        # Tonos saturados + texto oscuro fuerte + bold → contraste alto sin
        # perder legibilidad de los números.
        def _row_style(sev: str) -> str:
            if sev == "crítico":
                return "background-color: #F8C8C8; color: #5A0F0F; font-weight: 700"
            return "background-color: #FFDC9A; color: #5C3300; font-weight: 700"

        styled = (
            df_show[["Fecha/Hora", "pH", "Desviación", "Tipo", "severity"]]
            .style.format({"pH": "{:.2f}", "Desviación": "{:+.2f}"})
            .apply(lambda r: [_row_style(r["severity"])] * len(r), axis=1)
            .hide(axis="columns", subset=["severity"])
        )

        st.dataframe(styled, height=170, use_container_width=True, hide_index=True)


# CSS para el badge "EN VIVO" pulsante. Se inyecta una sola vez desde view.py
# vía `inject_ph_live_css()` para que las cards lo puedan referenciar.
PH_LIVE_CSS = """
<style>
.ph-kpi-card  { position: relative; }
.ph-kpi-live {
    position: absolute;
    top: 8px;
    right: 10px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #639922;
    text-transform: uppercase;
}
.ph-kpi-live-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #639922;
    box-shadow: 0 0 0 0 rgba(99,153,34,0.7);
    animation: phKpiLivePulse 1.4s ease-out infinite;
}
@keyframes phKpiLivePulse {
    0%   { box-shadow: 0 0 0 0   rgba(99,153,34,0.7); transform: scale(1);    }
    70%  { box-shadow: 0 0 0 10px rgba(99,153,34,0);   transform: scale(1.15); }
    100% { box-shadow: 0 0 0 0   rgba(99,153,34,0);   transform: scale(1);    }
}
</style>
"""


def inject_ph_live_css() -> None:
    """Inyecta una sola vez el CSS del badge 'EN VIVO' (idempotente por sesión)."""
    if st.session_state.get("_ph_live_css"):
        return
    st.markdown(PH_LIVE_CSS, unsafe_allow_html=True)
    st.session_state["_ph_live_css"] = True


# ── 7.3 — KPI card por TAG (HTML para st.markdown) ─────────────────────────
def render_ph_kpi_card(
    tag_id: str,
    current_value: float | None,
    tag_config: dict,
    live: bool = False,
) -> str:
    """Devuelve HTML (no lo imprime). Usar con st.markdown(..., unsafe_allow_html=True).

    Si `live=True`, agrega un badge 'EN VIVO' con un dot pulsante en la esquina
    superior derecha. Requiere haber llamado `inject_ph_live_css()` antes.
    """
    estado = compute_ph_status(current_value, tag_config)
    cfg = STATUS_CONFIG[estado]

    if current_value is None:
        valor_html = "<span style='font-size:28px;color:#888'>—</span>"
    else:
        valor_html = (
            f"<span style='font-size:28px;font-weight:700;color:{cfg['color']}'>"
            f"{current_value:.2f}</span>"
            f"<span style='font-size:13px;color:#666'> {tag_config.get('unit', 'pH')}</span>"
        )

    live_html = (
        "<div class='ph-kpi-live'><span class='ph-kpi-live-dot'></span>En vivo</div>"
        if live else ""
    )

    return (
        f"<div class='ph-kpi-card' style='background:#F0F2F6;border:1px solid #D9DCE3;"
        f"border-left:6px solid {cfg['badge_bg']};border-radius:10px;"
        f"padding:14px 18px;min-height:130px;'>"
        f"{live_html}"
        f"<div style='font-size:11px;color:#666;text-transform:uppercase;letter-spacing:0.05em'>"
        f"{tag_id}</div>"
        f"<div style='font-size:13px;color:#333;margin-bottom:6px'>"
        f"{tag_config['process_point']}</div>"
        f"<div style='margin:4px 0'>{valor_html}</div>"
        f"<div style='display:inline-block;background:{cfg['badge_bg']};color:{cfg['badge_fg']};"
        f"padding:4px 10px;border-radius:6px;font-size:12px;font-weight:700;"
        f"letter-spacing:0.03em;margin-top:4px;"
        f"box-shadow:0 1px 2px rgba(0,0,0,0.15);'>"
        f"{cfg['label']}</div>"
        f"<div style='font-size:11px;color:#666;margin-top:6px'>"
        f"Óptimo: {tag_config['opt_min']}–{tag_config['opt_max']} · "
        f"Crítico: {tag_config['crit_min']}–{tag_config['crit_max']}</div>"
        f"</div>"
    )
