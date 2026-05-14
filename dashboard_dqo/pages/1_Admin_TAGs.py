"""Página de administración de metadatos de TAGs.

Permite editar inline (st.data_editor) la tabla `tag_metadata` que mapea
TAG_ID → label, color, rol, unidad. Funciona para DQO inicialmente y
extensible a pH, Caudal, Químicos seleccionando otro tipo.

Esta página es auto-descubierta por Streamlit gracias a su ubicación en
`dashboard_dqo/pages/`. Aparece en el sidebar cuando se ejecuta
`streamlit run dashboard_dqo/dashboard_dqo.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ModuleNotFoundError:
    pass

from dashboard_dqo.tag_admin import (
    ROLES_VALIDOS, TIPOS_VALIDOS, eliminar_tag, listar_tags,
    migrar_desde_codigo, reemplazar_lote,
)
from dashboard_dqo.ui_components import inyectar_css


st.set_page_config(
    page_title="Admin TAGs — PTAR",
    page_icon="⚙️",
    layout="wide",
)
inyectar_css()


# ── Auth (delega en la sesión iniciada en el dashboard principal) ─────────────
if not st.session_state.get("authentication_status"):
    st.warning(
        "Debes iniciar sesión en el **Dashboard DQO** primero. "
        "Vuelve a la página principal desde el sidebar y autentícate."
    )
    st.stop()


st.title("⚙️ Administración de TAGs")
st.caption(
    "Configura cómo se muestran los TAGs (label, color, rol, unidad) en todos los "
    "tableros. Los cambios se aplican al guardar y limpian el caché del catálogo."
)

# ── Selector de tipo ──────────────────────────────────────────────────────────
col_t, col_b = st.columns([2, 1])
with col_t:
    tipo = st.selectbox("Tipo de medición", TIPOS_VALIDOS, index=0)

with col_b:
    st.write("")  # spacer
    st.write("")
    if st.button("📥 Sembrar desde código (sólo DQO)",
                 help="Inserta los TAGs definidos en TAG_CATALOG_FALLBACK. "
                      "No pisa filas existentes.",
                 disabled=(tipo != "DQO"), use_container_width=True):
        n = migrar_desde_codigo()
        if n:
            st.success(f"Insertados {n} TAGs desde el catálogo hardcoded.")
            st.rerun()
        else:
            st.info("No había TAGs nuevos por insertar.")


# ── Carga de datos actuales ───────────────────────────────────────────────────
try:
    df = listar_tags(tipo=tipo)
except Exception as exc:
    st.error(
        f"No se pudo leer la tabla `tag_metadata`: {exc}\n\n"
        "Verifica el contenedor de la BD y las variables del `.env`."
    )
    st.stop()

if df.empty:
    st.info(
        f"No hay TAGs registrados de tipo **{tipo}**. "
        + ("Usa el botón de la derecha para sembrar desde código, o "
           "agrega filas nuevas en el editor abajo." if tipo == "DQO"
           else "Agrega filas nuevas en el editor abajo.")
    )
    # DataFrame vacío con las columnas para que el editor las muestre
    df = pd.DataFrame(columns=[
        "tag_id", "tipo", "label", "rol", "unidad", "color", "orden", "activo",
    ])

# ── Editor inline ─────────────────────────────────────────────────────────────
st.markdown("### Editor")
st.caption(
    "Edita celdas, agrega filas (botón ➕ en la última fila), "
    "o desactiva un TAG con la columna **activo**. "
    "El **rol** controla la lógica del dashboard (afluente=entrada, "
    "efluente=salida normativa, intermedio=opcional)."
)

# Quitar `tipo` de la edición — se hereda del selectbox de arriba
df_editable = df.drop(columns=["tipo"], errors="ignore").copy()

editado = st.data_editor(
    df_editable,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "tag_id": st.column_config.TextColumn(
            "TAG_ID", help="Identificador exacto en la tabla `dqo`. Case-sensitive.",
            required=True, max_chars=64,
        ),
        "label": st.column_config.TextColumn(
            "Label (mostrar)", help="Nombre amigable que se ve en gráficos y tablas.",
            required=True, max_chars=80,
        ),
        "rol": st.column_config.SelectboxColumn(
            "Rol", options=[r for r in ROLES_VALIDOS if r is not None] + [""],
            help="afluente: entrada al proceso. efluente: salida normativa. "
                 "intermedio: etapa opcional. Vacío = sin rol asignado.",
        ),
        "unidad": st.column_config.TextColumn(
            "Unidad", help="mg/L, %, L/s, ppm, °C, etc.", max_chars=12,
        ),
        "color": st.column_config.TextColumn(
            "Color (hex)", help="Hex con #, ej. #185FA5",
            max_chars=7, validate=r"^#[0-9A-Fa-f]{6}$",
        ),
        "orden": st.column_config.NumberColumn(
            "Orden", help="Orden visual (0 = primero).", min_value=0, max_value=999, step=1,
        ),
        "activo": st.column_config.CheckboxColumn(
            "Activo", help="Si está desactivado no aparece en el dashboard.",
        ),
    },
    hide_index=True,
    key=f"editor_{tipo}",
)

# ── Acciones ──────────────────────────────────────────────────────────────────
col_g, col_r, _ = st.columns([1, 1, 4])

with col_g:
    if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
        # Validación
        if editado["tag_id"].duplicated().any():
            st.error("Hay TAG_IDs duplicados — corrige antes de guardar.")
            st.stop()
        if editado["tag_id"].isna().any() or (editado["tag_id"] == "").any():
            st.error("Hay filas sin TAG_ID — completa antes de guardar.")
            st.stop()
        if editado["label"].isna().any() or (editado["label"] == "").any():
            st.error("Hay filas sin label — completa antes de guardar.")
            st.stop()

        filas = []
        for _, r in editado.iterrows():
            filas.append({
                "tag_id": str(r["tag_id"]).strip(),
                "label":  str(r["label"]).strip(),
                "rol":    (str(r["rol"]).strip() or None) if pd.notna(r.get("rol")) else None,
                "unidad": (str(r["unidad"]).strip() or None) if pd.notna(r.get("unidad")) else None,
                "color":  (str(r["color"]).strip() or None) if pd.notna(r.get("color")) else None,
                "orden":  int(r["orden"]) if pd.notna(r.get("orden")) else 0,
                "activo": bool(r["activo"]) if pd.notna(r.get("activo")) else True,
            })
        try:
            aplicadas, borradas = reemplazar_lote(tipo, filas)
            st.success(
                f"Guardado: {aplicadas} fila(s) aplicada(s), "
                f"{borradas} fila(s) eliminada(s) (no estaban en el editor)."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Error guardando: {exc}")

with col_r:
    if st.button("🔄 Recargar desde BD", use_container_width=True):
        st.rerun()


# ── Vista previa del catálogo cargado ─────────────────────────────────────────
with st.expander("Vista previa del catálogo activo (lo que verá el dashboard)"):
    from dashboard_dqo.tag_admin import cargar_catalog
    cat = cargar_catalog(tipo)
    if not cat:
        st.info("Catálogo vacío.")
    else:
        st.json(cat)
