"""Filtros específicos del dashboard plantilla en el sidebar.

Solo expone el botón de recarga del catálogo de TAGs. Cuando se agrega o
elimina un instrumento en BD, este botón evita esperar el TTL del cache.
"""

from __future__ import annotations

import streamlit as st

from components.reload_tags import render_reload_tags_button

from ..cache import get_cached_template_tag_configs


def render_template_sidebar_filters() -> None:
    st.divider()
    render_reload_tags_button(
        get_cached_template_tag_configs, key="template_reload_tags",
    )
