"""Componentes Plotly + HTML del dashboard plantilla.

Mismo patrón que dashboard_ph: KPI card por TAG, gráfica de tendencia con
banda óptima sombreada, tabla de eventos colapsable.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..config import UNIT
from ..utils import STATUS_CONFIG, compute_template_status


# ── Gráfica de tendencia por TAG ───────────────────────────────────────────
def render_template_trend_chart(
    df: pd.DataFrame,
    tag_config: dict,
    height: int = 220,
    fi=None,
    ff=None,
) -> go.Figure:
    """Tendencia con banda óptima sombreada y líneas críticas.

    Si `fi`/`ff` se pasan, el eje X se ancla al rango del filtro (no al rango
    auto-detectado de los datos). Sin ese range explícito, Plotly hace
    auto-zoom y la gráfica se ve casi igual para "Hoy" o "Este mes".
    """
    fig = go.Figure()

    if not df.empty:
        ult_val = float(df["value"].iloc[-1])
        estado = compute_template_status(ult_val, tag_config)
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

    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["value"],
        mode="lines", line=dict(color=color_linea, width=2),
        name=UNIT,
        hovertemplate="%{x|%H:%M}<br>%{y:.2f}<extra></extra>",
        showlegend=False,
    ))

    fig.add_hline(y=tag_config["opt_min"], line_color="#1D9E75", line_width=1,
                  line_dash="solid", opacity=0.7)
    fig.add_hline(y=tag_config["opt_max"], line_color="#1D9E75", line_width=1,
                  line_dash="solid", opacity=0.7)
    fig.add_hline(y=tag_config["crit_min"], line_color="#A32D2D", line_width=1,
                  line_dash="dash", opacity=0.8)
    fig.add_hline(y=tag_config["crit_max"], line_color="#A32D2D", line_width=1,
                  line_dash="dash", opacity=0.8)

    xaxis_kwargs: dict = {"showgrid": True, "gridcolor": "#EEE"}
    if fi is not None and ff is not None:
        xaxis_kwargs["range"] = [fi, ff]
        span_days = (ff - fi).total_seconds() / 86400.0
        xaxis_kwargs["tickformat"] = "%H:%M" if span_days <= 1.5 else "%d %b %H:%M"
    else:
        xaxis_kwargs["tickformat"] = "%H:%M"

    span = tag_config["crit_max"] - tag_config["crit_min"]
    margen = max(span * 0.1, 0.5)
    fig.update_layout(
        height=height,
        margin=dict(l=40, r=10, t=10, b=30),
        xaxis=xaxis_kwargs,
        yaxis=dict(
            title=tag_config.get("unit", UNIT),
            range=[tag_config["crit_min"] - margen, tag_config["crit_max"] + margen],
            showgrid=True, gridcolor="#EEE",
        ),
        showlegend=False,
        plot_bgcolor="white",
    )
    return fig


# ── Tabla de eventos fuera de rango ────────────────────────────────────────
def render_violations_table(df_viol: pd.DataFrame, tag_config: dict) -> None:
    """Resumen de eventos como caption coloreado + detalle en expander."""
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
        bg, fg, border, icon = "#FCEBEB", "#A32D2D", "#C62828", "🚨"
        texto = f"{n_crit} crítico(s)"
        if n_warn:
            texto += f" · {n_warn} advertencia(s)"
    else:
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

    with st.expander("Ver detalle de eventos", expanded=False):
        df_show = df_viol.copy()
        df_show["timestamp"] = pd.to_datetime(df_show["timestamp"]).dt.strftime("%d/%m %H:%M")
        df_show = df_show.rename(columns={
            "timestamp": "Fecha/Hora", "value": "Valor",
            "deviation": "Desviación", "violation_type": "Tipo",
        })

        def _row_style(sev: str) -> str:
            if sev == "crítico":
                return "background-color: #F8C8C8; color: #5A0F0F; font-weight: 700"
            return "background-color: #FFDC9A; color: #5C3300; font-weight: 700"

        styled = (
            df_show[["Fecha/Hora", "Valor", "Desviación", "Tipo", "severity"]]
            .style.format({"Valor": "{:.2f}", "Desviación": "{:+.2f}"})
            .apply(lambda r: [_row_style(r["severity"])] * len(r), axis=1)
            .hide(axis="columns", subset=["severity"])
        )

        st.dataframe(styled, height=170, use_container_width=True, hide_index=True)


# ── CSS del badge "EN VIVO" pulsante ───────────────────────────────────────
TEMPLATE_LIVE_CSS = """
<style>
.template-kpi-card { position: relative; }
.template-kpi-live {
    position: absolute;
    top: 8px; right: 10px;
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 10px; font-weight: 700;
    letter-spacing: 0.08em; color: #639922;
    text-transform: uppercase;
}
.template-kpi-live-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #639922;
    box-shadow: 0 0 0 0 rgba(99,153,34,0.7);
    animation: templateKpiLivePulse 1.4s ease-out infinite;
}
@keyframes templateKpiLivePulse {
    0%   { box-shadow: 0 0 0 0   rgba(99,153,34,0.7); transform: scale(1);    }
    70%  { box-shadow: 0 0 0 10px rgba(99,153,34,0);   transform: scale(1.15); }
    100% { box-shadow: 0 0 0 0   rgba(99,153,34,0);   transform: scale(1);    }
}
</style>
"""


def inject_template_live_css() -> None:
    """Inyecta el CSS del badge 'EN VIVO' en cada rerun.

    No usar guard de session_state: cada rerun reconstruye el DOM y el
    `<style>` desaparece, por lo que el badge dejaría de pulsar después del
    primer render. Repetir el `<style>` no rompe nada (el navegador lo une).
    """
    st.markdown(TEMPLATE_LIVE_CSS, unsafe_allow_html=True)


# ── KPI card por TAG ───────────────────────────────────────────────────────
def render_template_kpi_card(
    tag_id: str,
    current_value: float | None,
    tag_config: dict,
    live: bool = False,
) -> str:
    """Devuelve HTML (no lo imprime). Usar con st.markdown(..., unsafe_allow_html=True)."""
    estado = compute_template_status(current_value, tag_config)
    cfg = STATUS_CONFIG[estado]

    if current_value is None:
        valor_html = "<span style='font-size:28px;color:#888'>—</span>"
    else:
        valor_html = (
            f"<span style='font-size:28px;font-weight:700;color:{cfg['color']}'>"
            f"{current_value:.2f}</span>"
            f"<span style='font-size:13px;color:#666'> "
            f"{tag_config.get('unit', UNIT)}</span>"
        )

    live_html = (
        "<div class='template-kpi-live'>"
        "<span class='template-kpi-live-dot'></span>En vivo</div>"
        if live else ""
    )

    return (
        f"<div class='template-kpi-card' style='background:#F0F2F6;"
        f"border:1px solid #D9DCE3;border-left:6px solid {cfg['badge_bg']};"
        f"border-radius:10px;padding:14px 18px;min-height:130px;'>"
        f"{live_html}"
        f"<div style='font-size:11px;color:#666;text-transform:uppercase;"
        f"letter-spacing:0.05em'>{tag_id}</div>"
        f"<div style='font-size:13px;color:#333;margin-bottom:6px'>"
        f"{tag_config['process_point']}</div>"
        f"<div style='margin:4px 0'>{valor_html}</div>"
        f"<div style='display:inline-block;background:{cfg['badge_bg']};"
        f"color:{cfg['badge_fg']};padding:4px 10px;border-radius:6px;"
        f"font-size:12px;font-weight:700;letter-spacing:0.03em;margin-top:4px;"
        f"box-shadow:0 1px 2px rgba(0,0,0,0.15);'>{cfg['label']}</div>"
        f"<div style='font-size:11px;color:#666;margin-top:6px'>"
        f"Óptimo: {tag_config['opt_min']}–{tag_config['opt_max']} · "
        f"Crítico: {tag_config['crit_min']}–{tag_config['crit_max']}</div>"
        f"</div>"
    )
