"""Render principal del dashboard OD.

Hoy hay un único transmisor (Reactor Biológico CSTR), así que el layout es:
    [KPI card]  [Gauge circular]
    [Tendencia 24h o rango custom]
    [Resumen de eventos + expander con tabla]

Si en el futuro vuelven varios TAGs, el bucle al final del archivo está
preparado para iterarlos en grid 2×N.
"""

from __future__ import annotations

import streamlit as st

from .cache import (
    get_cached_current_od, get_cached_od_tag_configs,
    get_cached_od_trend, get_cached_od_trend_range,
    get_cached_od_violations, get_cached_od_violations_range,
)
from .components.charts import (
    inject_od_live_css, render_od_gauge, render_od_kpi_card,
    render_od_trend_chart, render_violations_table,
)
from .utils import STATUS_CONFIG, compute_od_status


def _status_badge(val: float | None, cfg: dict) -> str:
    """Badge HTML inline para el encabezado del panel."""
    estado = compute_od_status(val, cfg)
    s = STATUS_CONFIG[estado]
    return (
        f"<span style='background:{s['badge_bg']};color:{s['badge_fg']};"
        f"padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;"
        f"letter-spacing:0.03em;margin-left:8px;"
        f"box-shadow:0 1px 2px rgba(0,0,0,0.15);'>"
        f"{s['label']}</span>"
    )


def render(conn, time_filter: dict | None = None) -> None:
    """Renderiza el dashboard OD completo dentro del contenedor actual."""
    fi = time_filter.get("start") if time_filter else None
    ff = time_filter.get("end") if time_filter else None
    rango_custom = fi is not None and ff is not None

    tag_configs = get_cached_od_tag_configs(conn)
    if not tag_configs:
        st.warning(
            "No hay TAGs activos en `od_tag_config`. "
            "Verifica que `dashboard_od.db_init.init_od_tables` haya corrido."
        )
        return

    df_current = get_cached_current_od(conn)

    # CSS del badge "EN VIVO" — inyectado una sola vez por sesión.
    inject_od_live_css()

    # ── Render por TAG (hoy solo hay 1, pero el patrón soporta más) ─────────
    for cfg in tag_configs:
        sub = df_current.loc[df_current["tag_id"] == cfg["tag_id"], "value"]
        val = float(sub.iloc[0]) if not sub.empty else None

        # Encabezado del panel
        st.markdown(
            f"### {cfg['tag_id']} — {cfg['process_point']}"
            f"{_status_badge(val, cfg)}",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Óptimo: {cfg['opt_min']}–{cfg['opt_max']} mg/L · "
            f"Crítico: {cfg['crit_min']}–{cfg['crit_max']} mg/L"
        )

        # KPI card + Gauge lado a lado.
        col_kpi, col_gauge = st.columns([1, 1], vertical_alignment="center")
        with col_kpi:
            with st.container(border=True):
                st.markdown(
                    render_od_kpi_card(cfg["tag_id"], val, cfg, live=True),
                    unsafe_allow_html=True,
                )
        with col_gauge:
            with st.container(border=True):
                # Título "Estado actual" a la izquierda + badge EN VIVO
                # pulsante a la derecha (reusa el dot CSS ya inyectado).
                st.markdown(
                    "<div style='display:flex;justify-content:space-between;"
                    "align-items:center;font-size:13px;color:#555;"
                    "font-weight:600;margin-bottom:-10px'>"
                    "<span>Estado actual</span>"
                    "<span style='display:inline-flex;align-items:center;gap:4px;"
                    "font-size:10px;font-weight:700;letter-spacing:0.08em;"
                    "color:#639922;text-transform:uppercase'>"
                    "<span class='od-kpi-live-dot'></span>En vivo</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.plotly_chart(
                    render_od_gauge(val, cfg),
                    use_container_width=True,
                    key=f"od_gauge_{cfg['tag_id']}",
                )

        st.markdown("###### Tendencia")
        with st.container(border=True):
            if rango_custom:
                df_trend = get_cached_od_trend_range(conn, cfg["tag_id"], fi, ff)
                st.caption(
                    f"Rango aplicado: {fi:%d %b %Y %H:%M} → {ff:%d %b %Y %H:%M} "
                    f"· {len(df_trend)} lecturas"
                )
            else:
                df_trend = get_cached_od_trend(conn, cfg["tag_id"])
                st.caption(f"Últimas 24 h · {len(df_trend)} lecturas")
            fig = render_od_trend_chart(
                df_trend, cfg,
                fi=fi if rango_custom else None,
                ff=ff if rango_custom else None,
            )
            st.plotly_chart(
                fig, use_container_width=True,
                key=f"od_chart_{cfg['tag_id']}",
            )

        st.markdown("###### Eventos fuera de rango")
        if rango_custom:
            df_viol = get_cached_od_violations_range(conn, cfg["tag_id"], cfg, fi, ff)
        else:
            df_viol = get_cached_od_violations(conn, cfg["tag_id"], cfg)
        render_violations_table(df_viol, cfg)
