import datetime
import streamlit as st
import streamlit_authenticator as stauth
import plotly.graph_objects as go
import pandas as pd
import yaml
from pathlib import Path

pd.set_option("styler.render.max_elements", 5_000_000)

from data import cargar_ph, cargar_dqo, leer_tags_db, leer_tags_sin_config, meses_disponibles, MESES_ES
from db import insertar_csv, asignar_tab
from config import TAG_MAP

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

PH_MIN = 6.0
PH_MAX = 9.0

_PALETTE = ["#7C4DFF", "#FF5722", "#00ACC1", "#43A047",
            "#FF9800", "#E91E63", "#009688", "#3F51B5"]

_MESES_NUM = {v: k for k, v in MESES_ES.items()}


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
    f"{MESES_ES[m]} {y}"
    for y in range(2000, 2051)
    for m in range(1, 13)
]


def _mes_cat(series: pd.Series) -> pd.Categorical:
    presentes = set(series)
    cats = [m for m in _ORDEN_MESES_STR if m in presentes]
    return pd.Categorical(series, categories=cats, ordered=True)


def _csv_uploader(caption: str, key: str, button_label: str) -> None:
    st.caption(caption)

    msg_ok_key  = f"_msg_ok_{key}"
    msg_err_key = f"_msg_err_{key}"
    if msg_ok_key in st.session_state:
        st.success(st.session_state.pop(msg_ok_key))
    if msg_err_key in st.session_state:
        st.error(st.session_state.pop(msg_err_key))

    f = st.file_uploader("CSV", type="csv", key=key, help="Formato: TimeStamp, TAG, Value")
    if f is not None:
        if st.button(button_label, use_container_width=True):
            barra  = st.progress(0, text="Preparando carga…")
            estado = st.empty()
            try:
                def _progreso(lote, total_lotes):
                    pct = lote / total_lotes
                    barra.progress(pct, text=f"Cargando lote {lote} de {total_lotes}…")
                    estado.caption(f"{pct*100:.0f} %  —  lote {lote}/{total_lotes}")

                total, ins = insertar_csv(f, progress_cb=_progreso)
                st.session_state[msg_ok_key] = f"✓ {ins:,} filas nuevas de {total:,}"
                st.cache_data.clear()
                st.session_state["_reset_año"] = True
                st.session_state["_reset_mes"] = True
                st.rerun()
            except Exception as e:
                barra.empty()
                estado.empty()
                st.session_state[msg_err_key] = f"Error: {e}"
                st.rerun()


def _rango_a_fechas(mes_rango: tuple) -> tuple[datetime.datetime, datetime.datetime]:
    """Convierte ("Mes YYYY", "Mes YYYY") al intervalo [fecha_ini, fecha_fin)."""
    def _parse(s):
        parts = s.split()
        return datetime.datetime(int(parts[1]), _MESES_NUM[parts[0]], 1)
    ini = _parse(mes_rango[0])
    fin_m = _parse(mes_rango[1])
    if fin_m.month == 12:
        fin = datetime.datetime(fin_m.year + 1, 1, 1)
    else:
        fin = datetime.datetime(fin_m.year, fin_m.month + 1, 1)
    return ini, fin


# ── Título ────────────────────────────────────────────────────────────────────
st.title("💧 Dashboard PTAR")
st.markdown("Monitoreo de parámetros de calidad de agua")
st.divider()

# ── TAGs y meses desde la BD ──────────────────────────────────────────────────
tags_ph  = leer_tags_db("pH")
tags_dqo = leer_tags_db("DQO")

for tag in tags_ph:
    st.session_state.setdefault(f"ph_act_{tag}", True)
for tag in tags_dqo:
    st.session_state.setdefault(f"dqo_act_{tag}", True)

tags_ph_activos  = [t for t in tags_ph  if st.session_state.get(f"ph_act_{t}",  True)]
tags_dqo_activos = [t for t in tags_dqo if st.session_state.get(f"dqo_act_{t}", True)]

_meses_ordenados = meses_disponibles()
_años_ordenados  = sorted({int(m.split()[1]) for m in _meses_ordenados}) if _meses_ordenados else []

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.get('name', '')}**")
    _authenticator.logout("Cerrar sesión", location="sidebar")
    st.divider()

    st.header("Filtros")

    if not _meses_ordenados:
        st.info("Sin datos en la base de datos.")
        año_rango   = None
        mes_rango   = None
        _meses_sel  = set()
        _n_años_sel = 0
    else:
        _año_actual  = datetime.date.today().year
        _año_default = _año_actual if _año_actual in _años_ordenados else _años_ordenados[-1]

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
        else:
            año_rango = (_años_ordenados[0], _años_ordenados[0])
            st.caption(f"Año: {_años_ordenados[0]}")

        _años_sel       = set(range(año_rango[0], año_rango[1] + 1))
        _meses_en_rango = [m for m in _meses_ordenados if int(m.split()[1]) in _años_sel]
        _n_años_sel     = año_rango[1] - año_rango[0] + 1

        if _n_años_sel == 1 and len(_meses_en_rango) > 1:
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
            _ini_idx = _meses_en_rango.index(mes_rango[0])
            _fin_idx = _meses_en_rango.index(mes_rango[1])
            _meses_sel = set(_meses_en_rango[_ini_idx : _fin_idx + 1])
        else:
            _meses_sel = set(_meses_en_rango)

    # Reserva el espacio del filtro de semanas; se rellena tras cargar datos
    _semana_slot = st.container()

    st.divider()
    with st.expander("⬆ Cargar datos a BD", expanded=False):
        _csv_uploader("CSV (TimeStamp, TAG, Value)", "up_csv", "⬆ Cargar a BD")

# ── Carga de datos (fuera del sidebar para evitar conflictos con spinners) ─────
if mes_rango:
    _fecha_ini, _fecha_fin = _rango_a_fechas(mes_rango)
    df_ph  = cargar_ph(_fecha_ini, _fecha_fin)  if tags_ph  else pd.DataFrame(columns=["fecha_hora", "mes"])
    df_dqo = cargar_dqo(_fecha_ini, _fecha_fin) if tags_dqo else pd.DataFrame(columns=["fecha", "mes"])
else:
    df_ph  = pd.DataFrame(columns=["fecha_hora", "mes"])
    df_dqo = pd.DataFrame(columns=["fecha", "mes"])

# ── Filtro de semanas (en el slot reservado dentro del sidebar) ────────────────
with _semana_slot:
    sem_rango = None
    if len(_meses_sel) == 1 and not df_ph.empty:
        _mes_unico    = next(iter(_meses_sel))
        _dias         = df_ph[df_ph["mes"] == _mes_unico]["fecha_hora"].dt.day
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
    st.session_state["_mes_prev"] = mes_rango

# Formato de fecha en ejes
_fmt_eje = "%d %b %Y" if _n_años_sel > 1 else "%d %b"

# ── Filtrar columnas activas ───────────────────────────────────────────────────
ph_cols  = [c for c in df_ph.columns  if c not in ("fecha_hora", "mes") and c in tags_ph_activos]
dqo_cols = [c for c in df_dqo.columns if c not in ("fecha", "mes")       and c in tags_dqo_activos]

# ── Aplicar filtro de semana en memoria ───────────────────────────────────────
if sem_rango is not None:
    _s_ini, _s_fin = sem_rango
    df_ph_f = df_ph[
        ((df_ph["fecha_hora"].dt.day - 1) // 7 + 1).between(_s_ini, _s_fin)
    ].reset_index(drop=True) if not df_ph.empty else df_ph
    df_dqo_f = df_dqo[
        ((df_dqo["fecha"].dt.day - 1) // 7 + 1).between(_s_ini, _s_fin)
    ].reset_index(drop=True) if not df_dqo.empty else df_dqo
else:
    df_ph_f  = df_ph
    df_dqo_f = df_dqo

# ── Tabs principales ──────────────────────────────────────────────────────────
tab_dqo, tab_ph, tab_datos, tab_config = st.tabs([
    "🟠 DQO (mg/L)", "🔵 pH", "📋 Datos", "⚙️ Configuración TAGs",
])

# ============================================================
# TAB pH
# ============================================================
with tab_ph:
    if not ph_cols or df_ph_f.empty:
        st.info("Sin datos de pH para el período seleccionado.")
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
        st.info("Sin datos de DQO para el período seleccionado.")
    else:
        _cols_mm = st.columns(len(dqo_cols) * 2)
        for i, tag in enumerate(dqo_cols):
            cfg = _info(tag, i)
            _cols_mm[i * 2].metric(f"{cfg['nombre']} — Máx. (mg/L)", _fmt(df_dqo_f[tag].max(), ".1f"))
            _cols_mm[i * 2 + 1].metric(f"{cfg['nombre']} — Mín. (mg/L)", _fmt(df_dqo_f[tag].min(), ".1f"))

        _reg = [(tag, cfg) for i, tag in enumerate(dqo_cols) if (cfg := _info(tag, i))["limite"] is not None]
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

    col_ph, col_dqo = st.columns(2)

    with col_ph:
        st.markdown("#### 🔵 TAGs pH")
        if not tags_ph:
            st.info("Sin TAGs de pH en la base de datos.")
        else:
            for tag in tags_ph:
                cfg = TAG_MAP.get(tag)
                etiqueta = f"`{tag}`" + (f"  —  {cfg['nombre']}" if cfg else "  *(TAG no configurado)*")
                st.checkbox(etiqueta, key=f"ph_act_{tag}")

    with col_dqo:
        st.markdown("#### 🟠 TAGs DQO")
        if not tags_dqo:
            st.info("Sin TAGs de DQO en la base de datos.")
        else:
            for tag in tags_dqo:
                cfg = TAG_MAP.get(tag)
                etiqueta = f"`{tag}`" + (f"  —  {cfg['nombre']}" if cfg else "  *(TAG no configurado)*")
                st.checkbox(etiqueta, key=f"dqo_act_{tag}")

    # ── TAGs sin clasificar ───────────────────────────────────────────────────
    tags_sin_config = leer_tags_sin_config()
    if tags_sin_config:
        st.divider()
        st.markdown("#### ⚠️ TAGs sin clasificar")
        st.caption("Estos TAGs existen en la base de datos pero no tienen tab asignada.")
        for tag in tags_sin_config:
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.code(tag)
            tab_sel = c2.selectbox(
                "Tab", ["pH", "DQO"],
                key=f"sel_tab_{tag}",
                label_visibility="collapsed",
            )
            if c3.button("Asignar", key=f"btn_asignar_{tag}"):
                asignar_tab(tag, tab_sel)
                st.cache_data.clear()
                st.rerun()
