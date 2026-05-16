"""Botón 'Recargar configuración de TAGs' compartido entre dashboards.

Cada dashboard tiene su propio cache de configs (`get_cached_*_tag_configs`)
con TTL de 60s. Este botón es la salida de emergencia para no esperar el
TTL: invalida los caches indicados y dispara `st.rerun()`.

Uso típico (dentro del sidebar, después del filtro de tiempo):

    from components.reload_tags import render_reload_tags_button
    from dashboard_ph.cache import get_cached_ph_tag_configs

    render_reload_tags_button(get_cached_ph_tag_configs)

Se le pueden pasar varias funciones cacheadas si el dashboard tiene más de
una (por ejemplo, configs + catálogo). Solo invalida esas, no todo
`st.cache_data`.
"""
from __future__ import annotations

from typing import Callable

import streamlit as st


def render_reload_tags_button(
    *cache_funcs: Callable,
    label: str = "🔄 Recargar configuración de TAGs",
    help_text: str = (
        "Invalida el caché del catálogo de TAGs. Útil después de "
        "agregar, eliminar o modificar un instrumento en la BD."
    ),
    key: str = "reload_tags_btn",
) -> None:
    """Renderiza un botón que limpia los caches dados y rerunea.

    Cada función pasada debe ser un objeto cacheado con `@st.cache_data`
    (tiene método `.clear()`). Si el caller pasa algo que no sea cacheado,
    se ignora silenciosamente para no romper el dashboard.
    """
    if st.button(label, help=help_text, key=key, use_container_width=True):
        for fn in cache_funcs:
            clear = getattr(fn, "clear", None)
            if callable(clear):
                clear()
        st.rerun()
