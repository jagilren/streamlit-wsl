"""Render principal del dashboard plantilla.

Itera `tag_configs` cargado desde template_tag_config y dibuja un grid 2×N
con un panel completo (KPI card + tendencia + violaciones) por TAG. Si la
tabla está vacía, muestra una advertencia y se detiene.
"""

from __future__ import annotations

import streamlit as st

from .cache import (
    get_cached_current_template, get_cached_template_tag_configs,
    get_cached_template_trend, get_cached_template_trend_range,
    get_cached_template_violations, get_cached_template_violations_range,
)
from .components.charts import (
    inject_template_live_css, render_template_kpi_card,
    render_template_trend_chart, render_violations_table,
)
from .config import UNIT
from .utils import STATUS_CONFIG, compute_template_status


def _status_badge(val: float | None, cfg: dict) -> str:
    """Badge HTML inline para el encabezado de cada panel."""
    estado = compute_template_status(val, cfg)
    s = STATUS_CONFIG[estado]
    return (
        f"<span style='background:{s['badge_bg']};color:{s['badge_fg']};"
        f"padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;"
        f"letter-spacing:0.03em;margin-left:8px;"
        f"box-shadow:0 1px 2px rgba(0,0,0,0.15);'>"
        f"{s['label']}</span>"
    )


def render(conn, time_filter: dict | None = None) -> None:
    """Renderiza el dashboard completo dentro del contenedor actual.

    Si `time_filter` es un dict con `start`/`end` (datetimes), las gráficas
    y la tabla de violaciones usan ese rango; en caso contrario, rangos por
    defecto (24h tendencia / 7d violaciones).
    """
    fi = time_filter.get("start") if time_filter else None
    ff = time_filter.get("end") if time_filter else None
    rango_custom = fi is not None and ff is not None

    tag_configs = get_cached_template_tag_configs(conn)
    if not tag_configs:
        st.warning(
            "No hay TAGs activos en `template_tag_config`. "
            "Siembra la tabla con SQL directo o desde la UI de admin."
        )
        return

    df_current = get_cached_current_template(conn)

    # CSS del badge "EN VIVO" — inyectado cada rerun (ver inject_template_live_css).
    inject_template_live_css()

    # ── KPI cards (fila de N columnas) ─────────────────────────────────────
    cols = st.columns(len(tag_configs))
    for i, cfg in enumerate(tag_configs):
        sub = df_current.loc[df_current["tag_id"] == cfg["tag_id"], "value"]
        val = float(sub.iloc[0]) if not sub.empty else None
        with cols[i]:
            st.markdown(
                render_template_kpi_card(cfg["tag_id"], val, cfg, live=True),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Grid 2×N: panel por TAG (encabezado + tendencia + violaciones) ────
    n = len(tag_configs)
    for fila_inicio in range(0, n, 2):
        row_cols = st.columns(2)
        for col_idx in range(2):
            tag_idx = fila_inicio + col_idx
            if tag_idx >= n:
                continue
            cfg = tag_configs[tag_idx]
            with row_cols[col_idx]:
                with st.container(border=True):
                    sub = df_current.loc[df_current["tag_id"] == cfg["tag_id"], "value"]
                    val = float(sub.iloc[0]) if not sub.empty else None
                    st.markdown(
                        f"**{cfg['tag_id']} — {cfg['process_point']}**"
                        f"{_status_badge(val, cfg)}",
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"Óptimo: {cfg['opt_min']}–{cfg['opt_max']} {cfg.get('unit', UNIT)} · "
                        f"Crítico: {cfg['crit_min']}–{cfg['crit_max']} {cfg.get('unit', UNIT)}"
                    )

                    if rango_custom:
                        df_trend = get_cached_template_trend_range(
                            conn, cfg["tag_id"], fi, ff,
                        )
                        st.caption(
                            f"Rango: {fi:%d %b %Y %H:%M} → {ff:%d %b %Y %H:%M} "
                            f"· {len(df_trend)} lecturas"
                        )
                    else:
                        df_trend = get_cached_template_trend(conn, cfg["tag_id"])
                        st.caption(f"Últimas 24 h · {len(df_trend)} lecturas")

                    fig = render_template_trend_chart(
                        df_trend, cfg,
                        fi=fi if rango_custom else None,
                        ff=ff if rango_custom else None,
                    )
                    st.plotly_chart(
                        fig, use_container_width=True,
                        key=f"template_chart_{cfg['tag_id']}",
                    )

                    if rango_custom:
                        df_viol = get_cached_template_violations_range(
                            conn, cfg["tag_id"], cfg, fi, ff,
                        )
                    else:
                        df_viol = get_cached_template_violations(
                            conn, cfg["tag_id"], cfg,
                        )
                    render_violations_table(df_viol, cfg)
