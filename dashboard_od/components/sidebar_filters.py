"""Filtros específicos del dashboard OD en el sidebar.

Por ahora solo expone el botón de recarga del catálogo de TAGs. El render
del dashboard se basa en `od_tag_config`, así que cuando se agrega o
elimina un transmisor en BD, este botón evita esperar el TTL del cache.
"""

from __future__ import annotations

import streamlit as st

from components.reload_tags import render_reload_tags_button

from ..cache import get_cached_od_tag_configs


def render_od_sidebar_filters() -> None:
    st.divider()
    render_reload_tags_button(get_cached_od_tag_configs, key="od_reload_tags")
