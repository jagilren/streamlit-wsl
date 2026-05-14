"""Barra de refresh compartida entre dashboards.

Renderiza un botón pequeño con icono Material `sync` (dos flechas circulares)
seguido de un caption con la cadencia del auto-refresh y, opcionalmente, la
fecha del último dato disponible en BD y/o información extra del módulo.

Diseñada para ser reutilizable en todos los módulos de operación (DQO, pH,
futuros). Mantiene un look consistente.

Uso típico:
    from components.refresh_bar import render_refresh_bar

    render_refresh_bar(
        autorefresh_seconds=60,
        ultimo_dato_label="14 may 2026 14:32",   # opcional
        extra="Período: 2026-05-01 al 2026-05-14",  # opcional
    )
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st


def render_refresh_bar(
    autorefresh_seconds: int,
    ultimo_dato_label: str | None = None,
    extra: str | None = None,
) -> None:
    """Botón sync (Material icon) + caption con cadencia de auto-refresh.

    Args:
        autorefresh_seconds: cadencia del autorefresh global (para el caption).
        ultimo_dato_label: texto ya formateado de la fecha del último dato en
            BD. Si None, no se muestra esa parte.
        extra: información adicional (e.g. período) que se prepone al caption.
    """
    col_btn, col_info = st.columns([0.08, 0.92], vertical_alignment="center")
    with col_btn:
        if st.button(
            ":material/sync:",
            type="primary",
            help="Actualizar datos ahora (limpia caché y consulta la BD)",
        ):
            st.cache_data.clear()
            st.session_state["ultima_actualizacion"] = datetime.now()
            st.rerun()
    with col_info:
        partes: list[str] = []
        if extra:
            partes.append(extra)
        partes.append(f"⟳ Auto-refresh cada {autorefresh_seconds} s")
        if ultimo_dato_label:
            partes.append(f"último dato en BD: {ultimo_dato_label}")
        st.caption(" · ".join(partes))
