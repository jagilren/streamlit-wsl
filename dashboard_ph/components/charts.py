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
    """Tabla scrollable con los eventos fuera del rango óptimo de la semana móvil."""
    if df_viol.empty:
        st.success("Sin eventos fuera de rango en los últimos 7 días")
        return

    n_total = len(df_viol)
    n_crit = int((df_viol["severity"] == "crit").sum())
    n_warn = int((df_viol["severity"] == "warn").sum())
    st.markdown(
        f"<span style='font-size:13px;color:#444'>"
        f"<strong>{n_total}</strong> evento(s) — "
        f"<span style='color:#A32D2D'>{n_crit} crítico(s)</span>, "
        f"<span style='color:#BA7517'>{n_warn} advertencia(s)</span>"
        f"</span>",
        unsafe_allow_html=True,
    )

    df_show = df_viol.copy()
    df_show["timestamp"] = pd.to_datetime(df_show["timestamp"]).dt.strftime("%d/%m %H:%M")
    df_show = df_show.rename(columns={
        "timestamp": "Fecha/Hora", "value": "pH",
        "deviation": "Desviación", "violation_type": "Tipo",
    })

    def _row_color(sev: str) -> str:
        if sev == "crit":
            return "background-color: #FCEBEB"
        return "background-color: #FAEEDA"

    styled = (
        df_show[["Fecha/Hora", "pH", "Desviación", "Tipo", "severity"]]
        .style.format({"pH": "{:.2f}", "Desviación": "{:+.2f}"})
        .apply(lambda r: [_row_color(r["severity"])] * len(r), axis=1)
        .hide(axis="columns", subset=["severity"])
    )

    st.dataframe(styled, height=170, use_container_width=True, hide_index=True)


# ── 7.3 — KPI card por TAG (HTML para st.markdown) ─────────────────────────
def render_ph_kpi_card(tag_id: str, current_value: float | None, tag_config: dict) -> str:
    """Devuelve HTML (no lo imprime). Usar con st.markdown(..., unsafe_allow_html=True)."""
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

    return (
        f"<div style='background:#F0F2F6;border-radius:10px;padding:14px 18px;"
        f"border-left:6px solid {cfg['color']};min-height:130px;'>"
        f"<div style='font-size:11px;color:#666;text-transform:uppercase;letter-spacing:0.05em'>"
        f"{tag_id}</div>"
        f"<div style='font-size:13px;color:#333;margin-bottom:6px'>"
        f"{tag_config['process_point']}</div>"
        f"<div style='margin:4px 0'>{valor_html}</div>"
        f"<div style='display:inline-block;background:{cfg['badge_bg']};color:{cfg['color']};"
        f"padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-top:4px'>"
        f"{cfg['label']}</div>"
        f"<div style='font-size:11px;color:#666;margin-top:6px'>"
        f"Óptimo: {tag_config['opt_min']}–{tag_config['opt_max']} · "
        f"Crítico: {tag_config['crit_min']}–{tag_config['crit_max']}</div>"
        f"</div>"
    )
