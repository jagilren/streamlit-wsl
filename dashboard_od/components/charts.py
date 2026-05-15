"""Componentes Plotly + HTML de las tarjetas y tablas del dashboard OD."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..utils import STATUS_CONFIG, compute_od_status


# ── Medidor circular (gauge) con bandas de color por estado ────────────────
def render_od_gauge(value: float | None, tag_config: dict, height: int = 180) -> go.Figure:
    """Gauge circular tipo velocímetro. Banda verde = óptimo, naranja = warn,
    rojo = crítico. La aguja apunta al valor actual; el color del número la
    refuerza."""
    opt_min = float(tag_config["opt_min"])
    opt_max = float(tag_config["opt_max"])
    crit_min = float(tag_config["crit_min"])
    crit_max = float(tag_config["crit_max"])

    # Margen visual: 20 % del rango crítico hacia cada lado, no negativo.
    span = crit_max - crit_min
    eje_min = max(0.0, crit_min - span * 0.2)
    eje_max = crit_max + span * 0.2

    # Color del número según estado actual.
    if value is None:
        color_num = STATUS_CONFIG["no_data"]["badge_bg"]
        valor_show = 0.0
    else:
        estado = compute_od_status(value, tag_config)
        color_num = STATUS_CONFIG[estado]["badge_bg"]
        valor_show = value

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=valor_show,
        number={
            "suffix": " mg/L",
            "font": {"size": 26, "color": color_num},
            "valueformat": ".2f",
        },
        gauge={
            "axis": {
                "range": [eje_min, eje_max],
                "tickwidth": 1,
                "tickcolor": "#BBB",
                "tickfont": {"size": 11, "color": "#DDD"},
            },
            "bar": {"color": color_num, "thickness": 0.25},
            "bgcolor": "black",
            "borderwidth": 1,
            "bordercolor": "#333",
            "steps": [
                # Bandas sobre fondo negro: tonos más saturados para destacar.
                {"range": [eje_min, crit_min], "color": "#5A1A1A"},
                {"range": [crit_min, opt_min], "color": "#5A3A12"},
                {"range": [opt_min, opt_max], "color": "#1A5A3A"},
                {"range": [opt_max, crit_max], "color": "#5A3A12"},
                {"range": [crit_max, eje_max], "color": "#5A1A1A"},
            ],
            "threshold": {
                "line": {"color": "#4DA3FF", "width": 3},
                "thickness": 0.8,
                "value": (opt_min + opt_max) / 2.0,  # marca el setpoint
            },
        },
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=10, b=4),
        paper_bgcolor="black",
        font={"family": "system-ui, sans-serif", "color": "#DDD"},
    )
    return fig


# ── Gráfica de tendencia por TAG ────────────────────────────────────────────
def render_od_trend_chart(
    df: pd.DataFrame,
    tag_config: dict,
    height: int = 220,
    fi=None,
    ff=None,
) -> go.Figure:
    """Tendencia con banda óptima sombreada y líneas críticas.

    Si `fi`/`ff` se pasan, el eje X se ancla al rango del filtro (no al rango
    auto-detectado de los datos). Esto es crítico para que el chart "obedezca"
    a los filtros de fecha del sidebar: sin ese range explícito, Plotly hace
    auto-zoom a los datos y el chart se ve casi igual para "Hoy" o "Este mes".
    """
    fig = go.Figure()

    if not df.empty:
        ult_val = float(df["value"].iloc[-1])
        estado = compute_od_status(ult_val, tag_config)
        color_linea = STATUS_CONFIG[estado]["color"]
    else:
        color_linea = STATUS_CONFIG["no_data"]["color"]

    # Banda óptima (verde semitransparente).
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
        name="OD", hovertemplate="%{x|%H:%M}<br>OD=%{y:.2f} mg/L<extra></extra>",
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

    # Eje X: si hay rango del filtro, anclamos el chart a ese rango y
    # adaptamos el tickformat según el span (multi-día muestra fechas).
    xaxis_kwargs: dict = {"showgrid": True, "gridcolor": "#EEE"}
    if fi is not None and ff is not None:
        xaxis_kwargs["range"] = [fi, ff]
        span_days = (ff - fi).total_seconds() / 86400.0
        xaxis_kwargs["tickformat"] = "%H:%M" if span_days <= 1.5 else "%d %b %H:%M"
    else:
        xaxis_kwargs["tickformat"] = "%H:%M"

    fig.update_layout(
        height=height,
        margin=dict(l=40, r=10, t=10, b=30),
        xaxis=xaxis_kwargs,
        yaxis=dict(
            title="OD (mg/L)",
            range=[max(0, tag_config["crit_min"] - 1.0), tag_config["crit_max"] + 1.0],
            showgrid=True, gridcolor="#EEE",
        ),
        showlegend=False,
        plot_bgcolor="white",
    )
    return fig


# ── Resumen de eventos + tabla detallada en expander ────────────────────────
def render_violations_table(df_viol: pd.DataFrame, tag_config: dict) -> None:
    """Resumen como caption coloreado; detalle dentro de st.expander."""
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
            "timestamp": "Fecha/Hora", "value": "OD (mg/L)",
            "deviation": "Desviación", "violation_type": "Tipo",
        })

        def _row_style(sev: str) -> str:
            if sev == "crítico":
                return "background-color: #F8C8C8; color: #5A0F0F; font-weight: 700"
            return "background-color: #FFDC9A; color: #5C3300; font-weight: 700"

        styled = (
            df_show[["Fecha/Hora", "OD (mg/L)", "Desviación", "Tipo", "severity"]]
            .style.format({"OD (mg/L)": "{:.2f}", "Desviación": "{:+.2f}"})
            .apply(lambda r: [_row_style(r["severity"])] * len(r), axis=1)
            .hide(axis="columns", subset=["severity"])
        )

        st.dataframe(styled, height=170, use_container_width=True, hide_index=True)


# ── KPI card por TAG con badge "EN VIVO" pulsante ──────────────────────────
OD_LIVE_CSS = """
<style>
.od-kpi-card  { position: relative; }
.od-kpi-live {
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
.od-kpi-live-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #639922;
    box-shadow: 0 0 0 0 rgba(99,153,34,0.7);
    animation: odKpiLivePulse 1.4s ease-out infinite;
}
@keyframes odKpiLivePulse {
    0%   { box-shadow: 0 0 0 0   rgba(99,153,34,0.7); transform: scale(1);    }
    70%  { box-shadow: 0 0 0 10px rgba(99,153,34,0);   transform: scale(1.15); }
    100% { box-shadow: 0 0 0 0   rgba(99,153,34,0);   transform: scale(1);    }
}
</style>
"""


def inject_od_live_css() -> None:
    """Inyecta el CSS del badge 'EN VIVO'.

    Se llama en cada rerun a propósito: en Streamlit, cada rerun reconstruye
    el DOM, así que un guard con session_state hacía que el `<style>` solo
    apareciera la primera vez y el badge dejara de parpadear en autorefresh.
    Los `<style>` repetidos en el HTML no rompen nada — el navegador los une.
    """
    st.markdown(OD_LIVE_CSS, unsafe_allow_html=True)


def render_od_kpi_card(
    tag_id: str,
    current_value: float | None,
    tag_config: dict,
    live: bool = False,
) -> str:
    """Devuelve HTML (no lo imprime). Usar con st.markdown(..., unsafe_allow_html=True)."""
    estado = compute_od_status(current_value, tag_config)
    cfg = STATUS_CONFIG[estado]

    if current_value is None:
        valor_html = "<span style='font-size:28px;color:#888'>—</span>"
    else:
        valor_html = (
            f"<span style='font-size:28px;font-weight:700;color:{cfg['color']}'>"
            f"{current_value:.2f}</span>"
            f"<span style='font-size:13px;color:#666'> {tag_config.get('unit', 'mg/L')}</span>"
        )

    live_html = (
        "<div class='od-kpi-live'><span class='od-kpi-live-dot'></span>En vivo</div>"
        if live else ""
    )

    return (
        f"<div class='od-kpi-card' style='background:#F0F2F6;border:1px solid #D9DCE3;"
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
