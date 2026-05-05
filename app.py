import streamlit as st
import streamlit_authenticator as stauth
import plotly.graph_objects as go
import pandas as pd
import yaml
import datetime
from pathlib import Path

pd.set_option("styler.render.max_elements", 5_000_000)

from data import cargar_ph, cargar_dqo, leer_tags
from config import CSV_PATH, CSV_PATH_LAB, TAG_MAP

st.set_page_config(
    page_title="Dashboard PTAR D'Vida — pH y DQO",
    page_icon="💧",
    layout="wide",
)

# ── Autenticación ─────────────────────────────────────────────────────────────
_CREDS_FILE = Path("credentials.yaml")
if not _CREDS_FILE.exists():
    st.error("No se encontró `credentials.yaml`. Contacta al administrador.")
    st.stop()

with open(_CREDS_FILE, encoding="utf-8") as _f:
    _creds_cfg = yaml.safe_load(_f)

_authenticator = stauth.Authenticate(
    str(_CREDS_FILE.resolve()),
    _creds_cfg["cookie"]["name"],
    _creds_cfg["cookie"]["key"],
    _creds_cfg["cookie"]["expiry_days"],
)

_authenticator.login(location="main")

if st.session_state.get("authentication_status") is False:
    st.error("Usuario o contraseña incorrectos.")
    st.stop()
elif st.session_state.get("authentication_status") is None:
    st.stop()

# A partir de aquí el usuario está autenticado.

PH_MIN = 6.0
PH_MAX = 9.0

_PALETTE = ["#7C4DFF", "#FF5722", "#00ACC1", "#43A047",
            "#FF9800", "#E91E63", "#009688", "#3F51B5"]

_MESES_ES = {
    1: "Enero",    2: "Febrero",   3: "Marzo",     4: "Abril",
    5: "Mayo",     6: "Junio",     7: "Julio",      8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}
_MESES_NUM = {v: k for k, v in _MESES_ES.items()}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt(val, spec=".2f") -> str:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return "N/A"
    return "N/A" if f != f else format(f, spec)


def _pct(exc: int, total: int) -> str:
    return "—" if total == 0 else f"{exc / total * 100:.1f}%"


def _info(tag: str, idx: int = 0) -> dict:
    if tag in TAG_MAP:
        return TAG_MAP[tag]
    return {
        "nombre": tag,
        "tipo":   None,
        "color":  _PALETTE[idx % len(_PALETTE)],
        "limite": None,
        "norma":  None,
        "bg_exc": "#F5F5F5",
    }


def _col_names(tags: list, fmt: str) -> dict:
    raw = {tag: fmt.format(nombre=_info(tag, i)["nombre"]) for i, tag in enumerate(tags)}
    counts = {}
    for name in raw.values():
        counts[name] = counts.get(name, 0) + 1
    return {
        tag: (f"{name} ({tag})" if counts[name] > 1 else name)
        for tag, name in raw.items()
    }


_ORDEN_MESES_STR = [
    f"{_MESES_ES[m]} {y}"
    for y in range(2000, 2051)
    for m in range(1, 13)
]


def _mes_cat(series: pd.Series) -> pd.Categorical:
    """Convierte la columna 'Mes YYYY' a Categorical ordenado cronológicamente."""
    presentes = set(series)
    cats = [m for m in _ORDEN_MESES_STR if m in presentes]
    return pd.Categorical(series, categories=cats, ordered=True)


# ── Título ────────────────────────────────────────────────────────────────────
st.title("💧 Dashboard PTAR")
st.markdown("Monitoreo de parámetros de calidad de agua")
st.divider()

# ── Sidebar: uploaders ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.get('name', '')}**")
    _authenticator.logout("Cerrar sesión", location="sidebar")
    st.divider()

    st.header("Datos")
    st.caption("📡 PLC — pH")
    archivo_plc = st.file_uploader(
        "CSV PLC", type="csv", key="up_plc",
        help="Formato: TimeStamp, TAG, Value  |  TAGs de pH",
    )
    st.caption("🧪 Laboratorio — DQO")
    archivo_lab = st.file_uploader(
        "CSV Laboratorio", type="csv", key="up_lab",
        help="Formato: TimeStamp, TAG, Value  |  TAGs de DQO",
    )
    st.divider()

fuente_plc = archivo_plc if archivo_plc is not None else CSV_PATH
fuente_lab = archivo_lab if archivo_lab is not None else CSV_PATH_LAB

# Resetear asignaciones cuando cambia algún archivo
_file_id_plc = archivo_plc.name if archivo_plc is not None else "__plc_default__"
_file_id_lab = archivo_lab.name if archivo_lab is not None else "__lab_default__"

if st.session_state.get("_file_id_plc") != _file_id_plc:
    for k in [k for k in st.session_state if k.startswith("plc_act_")]:
        del st.session_state[k]
    st.session_state["_file_id_plc"] = _file_id_plc

if st.session_state.get("_file_id_lab") != _file_id_lab:
    for k in [k for k in st.session_state if k.startswith("lab_act_")]:
        del st.session_state[k]
    st.session_state["_file_id_lab"] = _file_id_lab

# Leer TAGs de cada fuente
try:
    tags_plc = leer_tags(fuente_plc)
except FileNotFoundError:
    tags_plc = []
except Exception as e:
    st.error(f"Error al leer CSV PLC: {e}")
    st.stop()

try:
    tags_lab = leer_tags(fuente_lab)
except FileNotFoundError:
    tags_lab = []
except Exception as e:
    st.error(f"Error al leer CSV Laboratorio: {e}")
    st.stop()

if not tags_plc and not tags_lab:
    st.warning(
        "No se encontraron archivos de datos. "
        "Carga los CSV en la barra lateral o ejecuta `generar_csv_muestra.py`."
    )
    st.stop()

# Inicializar estado de activación de TAGs (por defecto todos activos)
for tag in tags_plc:
    st.session_state.setdefault(f"plc_act_{tag}", True)
for tag in tags_lab:
    st.session_state.setdefault(f"lab_act_{tag}", True)

# Listas de TAGs activos
tags_ph_activos  = [t for t in tags_plc if st.session_state.get(f"plc_act_{t}", True)]
tags_dqo_activos = [t for t in tags_lab if st.session_state.get(f"lab_act_{t}", True)]

# Cargar datos — el resultado queda en caché; no vuelve a leer el CSV en cada rerun
try:
    df_ph = cargar_ph(fuente_plc) if tags_plc else pd.DataFrame(columns=["fecha_hora", "mes"])
except Exception as e:
    st.error(f"Error al procesar CSV PLC: {e}")
    st.stop()

try:
    df_dqo = cargar_dqo(fuente_lab) if tags_lab else pd.DataFrame(columns=["fecha", "mes"])
except Exception as e:
    st.error(f"Error al procesar CSV Laboratorio: {e}")
    st.stop()

# Filtro de TAGs activos en memoria (sin releer el CSV)
ph_cols  = [c for c in df_ph.columns  if c not in ("fecha_hora", "mes") and c in tags_ph_activos]
dqo_cols = [c for c in df_dqo.columns if c not in ("fecha", "mes")       and c in tags_dqo_activos]

# ── Sidebar: filtros ──────────────────────────────────────────────────────────
_meses_set = set()
if not df_ph.empty and "mes" in df_ph.columns:
    _meses_set |= set(df_ph["mes"].unique())
if not df_dqo.empty and "mes" in df_dqo.columns:
    _meses_set |= set(df_dqo["mes"].unique())

_meses_ordenados = sorted(
    _meses_set,
    key=lambda m: (int(m.split()[1]), _MESES_NUM[m.split()[0]]),
    reverse=True,
)
_años_ordenados = sorted({int(m.split()[1]) for m in _meses_set})

with st.sidebar:
    st.header("Filtros")

    # ── Año ──────────────────────────────────────────────────────────────────
    _año_actual = datetime.date.today().year
    _año_default = _año_actual if _año_actual in _años_ordenados else (_años_ordenados[-1] if _años_ordenados else None)

    if len(_años_ordenados) > 1:
        if st.session_state.pop("_reset_año", False):
            st.session_state["año_slider"] = (_años_ordenados[0], _años_ordenados[-1])
        año_rango = st.select_slider(
            "Año",
            options=_años_ordenados,
            value=(_año_default, _año_default),
            key="año_slider",
        )
        if st.button("↺ Todos los años", use_container_width=True):
            st.session_state["_reset_año"] = True
            st.rerun()
    elif _años_ordenados:
        año_rango = (_años_ordenados[0], _años_ordenados[0])
        st.caption(f"Año: {_años_ordenados[0]}")
    else:
        año_rango = None

    _años_sel = set(range(año_rango[0], año_rango[1] + 1)) if año_rango else set()
    _meses_en_rango = [m for m in _meses_ordenados if int(m.split()[1]) in _años_sel]
    _n_años_sel = (año_rango[1] - año_rango[0] + 1) if año_rango else 0

    # ── Mes (solo si hay ≤ 2 años seleccionados) ─────────────────────────────
    if año_rango and _n_años_sel <= 2 and len(_meses_en_rango) > 1:
        if st.session_state.get("_año_prev") != año_rango or \
           st.session_state.pop("_reset_mes", False):
            st.session_state["mes_slider"] = (_meses_en_rango[0], _meses_en_rango[-1])
        mes_rango = st.select_slider(
            "Mes",
            options=_meses_en_rango,
            value=(_meses_en_rango[0], _meses_en_rango[-1]),
            key="mes_slider",
        )
        if st.button("↺ Todos los meses", use_container_width=True):
            st.session_state["_reset_mes"] = True
            st.rerun()
    elif _meses_en_rango:
        mes_rango = (_meses_en_rango[0], _meses_en_rango[-1])
    else:
        mes_rango = None

    st.session_state["_año_prev"] = año_rango

    if mes_rango and _meses_en_rango:
        _ini = _meses_en_rango.index(mes_rango[0])
        _fin = _meses_en_rango.index(mes_rango[1])
        _meses_sel = set(_meses_en_rango[_ini : _fin + 1])
    else:
        _meses_sel = set(_meses_en_rango)

    # ── Semana (solo si hay exactamente 1 mes seleccionado) ──────────────────
    if len(_meses_sel) == 1 and not df_ph.empty:
        _mes_unico = next(iter(_meses_sel))
        _dias = df_ph[df_ph["mes"] == _mes_unico]["fecha_hora"].dt.day
        _semanas_disp = sorted((((_dias - 1) // 7) + 1).unique()) if len(_dias) > 0 else [1]
        if len(_semanas_disp) > 1:
            if st.session_state.get("_mes_prev") != mes_rango or \
               st.session_state.pop("_reset_sem", False):
                st.session_state["sem_slider"] = (_semanas_disp[0], _semanas_disp[-1])
            sem_rango = st.slider(
                "Semanas",
                min_value=_semanas_disp[0],
                max_value=_semanas_disp[-1],
                value=(_semanas_disp[0], _semanas_disp[-1]),
                format="Semana %d",
                key="sem_slider",
            )
            if st.button("↺ Todas las semanas", use_container_width=True):
                st.session_state["_reset_sem"] = True
                st.rerun()
        else:
            st.caption(f"Semana {_semanas_disp[0]}")
            sem_rango = (_semanas_disp[0], _semanas_disp[0])
    else:
        sem_rango = None

    st.session_state["_mes_prev"] = mes_rango

# Formato de fecha en ejes según número de años seleccionados
_fmt_eje = "%d %b %Y" if _n_años_sel > 1 else "%d %b"

# ── Filtrar DataFrames ────────────────────────────────────────────────────────
if _meses_sel:
    df_ph_f  = df_ph[df_ph["mes"].isin(_meses_sel)].reset_index(drop=True)   if not df_ph.empty  else df_ph.copy()
    df_dqo_f = df_dqo[df_dqo["mes"].isin(_meses_sel)].reset_index(drop=True) if not df_dqo.empty else df_dqo.copy()
else:
    df_ph_f  = df_ph.copy()
    df_dqo_f = df_dqo.copy()

if sem_rango is not None:
    _s_ini, _s_fin = sem_rango
    if not df_ph_f.empty:
        df_ph_f = df_ph_f[
            ((df_ph_f["fecha_hora"].dt.day - 1) // 7 + 1).between(_s_ini, _s_fin)
        ].reset_index(drop=True)
    if not df_dqo_f.empty:
        df_dqo_f = df_dqo_f[
            ((df_dqo_f["fecha"].dt.day - 1) // 7 + 1).between(_s_ini, _s_fin)
        ].reset_index(drop=True)

# ── Tabs principales ──────────────────────────────────────────────────────────
tab_dqo, tab_ph, tab_datos, tab_config = st.tabs([
    "🟠 DQO (mg/L)", "🔵 pH", "📋 Datos", "⚙️ Configuración TAGs",
])

# ============================================================
# TAB pH
# ============================================================
with tab_ph:
    if not ph_cols or df_ph_f.empty:
        st.info("Sin datos de pH para el período seleccionado. Carga el CSV del PLC o activa TAGs en ⚙️ Configuración.")
    else:
        _cols_mm = st.columns(len(ph_cols) * 2)
        for i, tag in enumerate(ph_cols):
            cfg = _info(tag, i)
            _cols_mm[i * 2].metric(f"{cfg['nombre']} — Máx.", _fmt(df_ph_f[tag].max()))
            _cols_mm[i * 2 + 1].metric(f"{cfg['nombre']} — Mín.", _fmt(df_ph_f[tag].min()))

        _cols_exc = st.columns(len(ph_cols))
        for i, tag in enumerate(ph_cols):
            cfg = _info(tag, i)
            n_valid = int(df_ph_f[tag].notna().sum())
            exc = int(((df_ph_f[tag] < PH_MIN) | (df_ph_f[tag] > PH_MAX)).sum())
            _cols_exc[i].metric(
                f"Fuera de rango — {cfg['nombre']}",
                f"{exc} / {n_valid} ({_pct(exc, n_valid)})",
            )

        st.divider()

        fig_ph = go.Figure()
        for i, tag in enumerate(ph_cols):
            cfg = _info(tag, i)
            _mask = df_ph_f[tag].notna()
            fig_ph.add_trace(go.Scatter(
                x=df_ph_f.loc[_mask, "fecha_hora"],
                y=df_ph_f.loc[_mask, tag],
                mode="lines", line=dict(color=cfg["color"], width=1),
                name=cfg["nombre"],
            ))
        fig_ph.add_hline(y=PH_MIN, line_dash="dash", line_color="orange",
            annotation_text="Mínimo (6.0)", annotation_position="bottom right")
        fig_ph.add_hline(y=PH_MAX, line_dash="dash", line_color="red",
            annotation_text="Máximo (9.0)", annotation_position="top right")
        fig_ph.update_layout(
            xaxis=dict(title="Fecha / Hora", tickformat=_fmt_eje),
            yaxis=dict(title="pH", range=[4.5, 11.5]),
            hovermode="x unified", height=420,
            margin=dict(l=40, r=40, t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        st.plotly_chart(fig_ph, use_container_width=True)

        st.divider()

        _tcols = st.columns(len(ph_cols))
        for i, tag in enumerate(ph_cols):
            cfg = _info(tag, i)
            with _tcols[i]:
                st.markdown(f"**{cfg['nombre']} — fuera de rango [6.0 – 9.0]**")
                df_exc = df_ph_f[(df_ph_f[tag] < PH_MIN) | (df_ph_f[tag] > PH_MAX)].copy()
                if df_exc.empty:
                    st.success(f"Sin excedencias en {cfg['nombre']}.")
                else:
                    df_show = df_exc[["fecha_hora", tag, "mes"]].copy()
                    df_show["fecha_hora"] = df_show["fecha_hora"].dt.strftime("%d/%m/%Y %H:%M")
                    df_show.columns = ["Fecha / Hora", f"pH {cfg['nombre']}", "Mes"]
                    df_show["Mes"] = _mes_cat(df_show["Mes"])
                    st.dataframe(
                        df_show,
                        column_config={
                            f"pH {cfg['nombre']}": st.column_config.NumberColumn(format="%.2f"),
                        },
                        use_container_width=True, hide_index=True,
                    )

        st.divider()

        st.subheader("Tabla de mediciones — pH")
        df_ph_tabla = df_ph_f[["fecha_hora"] + ph_cols + ["mes"]].copy()
        df_ph_tabla["fecha_hora"] = df_ph_tabla["fecha_hora"].dt.strftime("%d/%m/%Y %H:%M")
        col_map = _col_names(ph_cols, "pH {nombre}")
        df_ph_tabla = df_ph_tabla.rename(columns={"fecha_hora": "Fecha / Hora", "mes": "Mes", **col_map})
        df_ph_tabla["Mes"] = _mes_cat(df_ph_tabla["Mes"])
        st.dataframe(
            df_ph_tabla.style.format({col_map[t]: "{:.2f}" for t in ph_cols}),
            use_container_width=True, hide_index=True,
        )

# ============================================================
# TAB DQO
# ============================================================
with tab_dqo:
    if not dqo_cols or df_dqo_f.empty:
        st.info("Sin datos de DQO para el período seleccionado. Carga el CSV de Laboratorio o activa TAGs en ⚙️ Configuración.")
    else:
        _cols_mm = st.columns(len(dqo_cols) * 2)
        for i, tag in enumerate(dqo_cols):
            cfg = _info(tag, i)
            _cols_mm[i * 2].metric(f"{cfg['nombre']} — Máx. (mg/L)", _fmt(df_dqo_f[tag].max(), ".1f"))
            _cols_mm[i * 2 + 1].metric(f"{cfg['nombre']} — Mín. (mg/L)", _fmt(df_dqo_f[tag].min(), ".1f"))

        _reg = [(tag, _info(tag, i)) for i, tag in enumerate(dqo_cols) if _info(tag, i)["limite"] is not None]
        if _reg:
            _cols_reg = st.columns(len(_reg))
            for i, (tag, cfg) in enumerate(_reg):
                _exc   = int((df_dqo_f[tag] >= cfg["limite"]).sum())
                _n_col = int(df_dqo_f[tag].notna().sum())
                _cols_reg[i].metric(
                    f"Días sobre límite — {cfg['nombre']} ({cfg['norma']})",
                    f"{_exc} / {_n_col} ({_pct(_exc, _n_col)})",
                )

        st.divider()

        fig_bar = go.Figure()
        for i, tag in enumerate(dqo_cols):
            cfg = _info(tag, i)
            fig_bar.add_trace(go.Bar(
                x=df_dqo_f["fecha"], y=df_dqo_f[tag],
                name=cfg["nombre"], marker_color=cfg["color"],
            ))
        for i, tag in enumerate(dqo_cols):
            cfg = _info(tag, i)
            if cfg["limite"] is not None:
                fig_bar.add_hline(y=cfg["limite"], line_dash="dash", line_color="red",
                    annotation_text=cfg["norma"], annotation_position="top left")
        fig_bar.update_layout(
            barmode="group", height=280,
            margin=dict(l=20, r=20, t=10, b=40),
            xaxis=dict(tickformat=_fmt_eje),
            yaxis=dict(title="DQO (mg/L)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        fig_line = go.Figure()
        for i, tag in enumerate(dqo_cols):
            cfg = _info(tag, i)
            fig_line.add_trace(go.Scatter(
                x=df_dqo_f["fecha"], y=df_dqo_f[tag],
                mode="lines+markers",
                line=dict(color=cfg["color"], width=2), marker=dict(size=6),
                name=cfg["nombre"],
            ))
        for i, tag in enumerate(dqo_cols):
            cfg = _info(tag, i)
            if cfg["limite"] is not None:
                fig_line.add_hline(y=cfg["limite"], line_dash="dash", line_color="red",
                    annotation_text=f"Límite máx. {cfg['norma']} ({cfg['limite']:.0f} mg/L)",
                    annotation_position="top right")
        fig_line.update_layout(
            xaxis=dict(title="Fecha", tickformat=_fmt_eje),
            yaxis=dict(title="DQO (mg/L)"),
            hovermode="x unified", height=380,
            margin=dict(l=40, r=40, t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        st.plotly_chart(fig_line, use_container_width=True)

        st.divider()

        if _reg:
            _cols_exc = st.columns(len(_reg))
            for i, (tag, cfg) in enumerate(_reg):
                with _cols_exc[i]:
                    st.markdown(f"**Días ≥ {cfg['limite']:.0f} mg/L — {cfg['nombre']} ({cfg['norma']})**")
                    df_exc = df_dqo_f[df_dqo_f[tag] >= cfg["limite"]].copy()
                    if df_exc.empty:
                        st.success(f"Ningún día superó el límite en {cfg['nombre']}.")
                    else:
                        df_show = df_exc[["fecha", tag, "mes"]].copy()
                        df_show["fecha"] = df_show["fecha"].dt.strftime("%d/%m/%Y")
                        df_show.columns = ["Fecha", "DQO (mg/L)", "Mes"]
                        df_show["Mes"] = _mes_cat(df_show["Mes"])
                        st.dataframe(
                            df_show,
                            column_config={
                                "DQO (mg/L)": st.column_config.NumberColumn(format="%.1f"),
                            },
                            use_container_width=True, hide_index=True,
                        )

        st.divider()

        st.subheader("Tabla de valores — DQO")
        df_dqo_tabla = df_dqo_f[["fecha"] + dqo_cols + ["mes"]].copy()
        df_dqo_tabla["fecha"] = df_dqo_tabla["fecha"].dt.strftime("%d/%m/%Y")
        col_map_dqo = _col_names(dqo_cols, "{nombre} (mg/L)")
        df_dqo_tabla = df_dqo_tabla.rename(columns={"fecha": "Fecha", "mes": "Mes", **col_map_dqo})
        df_dqo_tabla["Mes"] = _mes_cat(df_dqo_tabla["Mes"])
        st.dataframe(
            df_dqo_tabla.style.format({col_map_dqo[t]: "{:.1f}" for t in dqo_cols}),
            use_container_width=True, hide_index=True,
        )

# ============================================================
# TAB DATOS
# ============================================================
with tab_datos:
    st.subheader("Mediciones de pH")
    if not ph_cols or df_ph_f.empty:
        st.info("Sin datos de pH.")
    else:
        df_ph_raw = df_ph_f[["fecha_hora"] + ph_cols + ["mes"]].copy()
        df_ph_raw["fecha_hora"] = df_ph_raw["fecha_hora"].dt.strftime("%d/%m/%Y %H:%M")
        col_map_ph = _col_names(ph_cols, "pH {nombre}")
        df_ph_raw = df_ph_raw.rename(columns={"fecha_hora": "Fecha / Hora", "mes": "Mes", **col_map_ph})
        df_ph_raw["Mes"] = _mes_cat(df_ph_raw["Mes"])
        st.dataframe(
            df_ph_raw.style.format({col_map_ph[t]: "{:.2f}" for t in ph_cols}),
            use_container_width=True, hide_index=True,
        )

    st.divider()

    st.subheader("Mediciones de DQO")
    if not dqo_cols or df_dqo_f.empty:
        st.info("Sin datos de DQO.")
    else:
        df_dqo_raw = df_dqo_f[["fecha"] + dqo_cols + ["mes"]].copy()
        df_dqo_raw["fecha"] = df_dqo_raw["fecha"].dt.strftime("%d/%m/%Y")
        col_map_dqo2 = _col_names(dqo_cols, "{nombre} (mg/L)")
        df_dqo_raw = df_dqo_raw.rename(columns={"fecha": "Fecha", "mes": "Mes", **col_map_dqo2})
        df_dqo_raw["Mes"] = _mes_cat(df_dqo_raw["Mes"])
        st.dataframe(
            df_dqo_raw.style.format({col_map_dqo2[t]: "{:.1f}" for t in dqo_cols}),
            use_container_width=True, hide_index=True,
        )

# ============================================================
# TAB CONFIGURACIÓN TAGs
# ============================================================
with tab_config:
    st.subheader("Configuración de TAGs")
    st.markdown(
        "Activa o desactiva cada TAG para incluirlo o excluirlo de las gráficas. "
        "Los cambios aplican de inmediato al siguiente refresco."
    )
    st.divider()

    col_plc, col_lab = st.columns(2)

    with col_plc:
        st.markdown("#### 📡 CSV PLC — pH")
        if not tags_plc:
            st.info("Sin archivo PLC cargado.")
        else:
            for tag in tags_plc:
                cfg = TAG_MAP.get(tag)
                etiqueta = f"`{tag}`" + (f"  —  {cfg['nombre']}" if cfg else "  *(TAG no configurado)*")
                st.checkbox(etiqueta, key=f"plc_act_{tag}")

    with col_lab:
        st.markdown("#### 🧪 CSV Laboratorio — DQO")
        if not tags_lab:
            st.info("Sin archivo de Laboratorio cargado.")
        else:
            for tag in tags_lab:
                cfg = TAG_MAP.get(tag)
                etiqueta = f"`{tag}`" + (f"  —  {cfg['nombre']}" if cfg else "  *(TAG no configurado)*")
                st.checkbox(etiqueta, key=f"lab_act_{tag}")
