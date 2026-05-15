"""Filtro de tiempo compartido entre dashboards.

Renderiza Período + Desde + Hasta dentro del contenedor actual. Usa keys
estables (`"periodo"`, `"fi"`, `"ff"`) en st.session_state, así los valores
persisten al cambiar de página dentro de la app multi-dashboard.

Uso típico:
    from components.shared_time_filter import render_shared_time_filter
    with st.sidebar:
        periodo, fi, ff = render_shared_time_filter()
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from dashboard_dqo.kpi_calculator import get_rango_fechas

_PERIODOS = ["Hoy", "Esta semana", "Este mes", "Últimos 90 días", "Este año"]
_DEFAULT_PERIODO = "Este mes"


def _sync_fechas_con_periodo() -> None:
    """Callback: al cambiar el período, reescribe fi/ff con el nuevo rango."""
    nuevo_fi, nuevo_ff = get_rango_fechas(st.session_state["periodo"])
    st.session_state["fi"] = nuevo_fi.date()
    st.session_state["ff"] = nuevo_ff.date()


def _seed_session_state() -> None:
    """Inicializa periodo/fi/ff la primera vez que se ejecuta el sidebar."""
    if "periodo" not in st.session_state:
        st.session_state["periodo"] = _DEFAULT_PERIODO
        fi0, ff0 = get_rango_fechas(_DEFAULT_PERIODO)
        st.session_state["fi"] = fi0.date()
        st.session_state["ff"] = ff0.date()


def render_shared_time_filter() -> tuple[str, date, date]:
    """Renderiza el bloque (período + fi + ff) y devuelve los tres valores.

    Asume que el caller ya está dentro de un contenedor (típicamente
    `with st.sidebar:`). Para que los valores persistan entre páginas, este
    componente reutiliza las mismas keys de session_state en ambos dashboards.
    """
    _seed_session_state()

    # Período + botón de refresh en la misma fila. El botón solo fuerza un
    # rerun (no muta estado): útil si al cambiar de dashboard la vista quedó
    # con datos cacheados de una selección previa y se quiere re-sincronizar
    # con el período activo.
    col_p, col_r = st.columns([5, 1], vertical_alignment="bottom")
    with col_p:
        st.selectbox(
            "Período de análisis", _PERIODOS,
            key="periodo", on_change=_sync_fechas_con_periodo,
        )
    with col_r:
        # `type="tertiary"` quita el borde + fondo gris del botón estándar,
        # dejando solo el ícono. Encaja mejor visualmente junto al selectbox.
        st.button(
            "🔄",
            key="periodo_refresh",
            help="Refrescar la vista con el período seleccionado",
            use_container_width=True,
            type="tertiary",
        )

    col1, col2 = st.columns(2)
    with col1:
        st.date_input("Desde", key="fi")
    with col2:
        st.date_input("Hasta", key="ff")

    return (
        st.session_state["periodo"],
        st.session_state["fi"],
        st.session_state["ff"],
    )


def get_datetime_range() -> tuple[datetime, datetime]:
    """Devuelve (fi 00:00, ff 23:59:59) como datetime, leyendo session_state.

    Útil para construir queries SQL después de que el filtro se haya renderizado.
    Si nunca se ha renderizado el filtro, devuelve el rango por defecto.
    """
    _seed_session_state()
    fi_d = st.session_state["fi"]
    ff_d = st.session_state["ff"]
    fi = datetime.combine(fi_d, datetime.min.time())
    ff = datetime.combine(ff_d, datetime.max.time().replace(microsecond=0))
    return fi, ff
