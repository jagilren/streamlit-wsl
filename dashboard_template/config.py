"""Constantes del dashboard plantilla.

Al clonar este módulo, basta con cambiar las cuatro constantes de abajo y
los nombres de tablas/funciones en el resto de archivos via sed (ver
README.md). Todo lo demás (queries, charts, view) es genérico.
"""

# ── Identidad del módulo ─────────────────────────────────────────────────────
# Nombre corto en lowercase. Se usa como prefijo de tablas SQL
# (`<MODULE>_measurements`, `<MODULE>_tag_config`) y como key de session_state.
MODULE = "template"

# Etiqueta human-friendly para títulos, captions y mensajes.
MODULE_LABEL = "Template"

# Unidad que se muestra junto a los valores numéricos (ej. "mg/L", "L/s", "°C").
UNIT = "u"

# Ícono Streamlit (emoji o ícono Material) para el page_title y los markdown.
ICON = "📊"


# ── Auto-refresh ─────────────────────────────────────────────────────────────
AUTOREFRESH_MS = 60_000   # cada cuánto rerunea el dashboard (1 min)
