"""Dashboard ejecutivo DQO para Gerencia Ambiental PTAR.

Ejecutar:
    streamlit run dashboard_dqo/dashboard_dqo.py --server.port 8502
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ModuleNotFoundError:
    pass

from dashboard_dqo.chart_builder import (
    chart_barras_mensual, chart_comparativo_anual, chart_gauge_eficiencia,
    chart_histograma, chart_tendencia,
)
from streamlit_autorefresh import st_autorefresh

from dashboard_dqo.config import (
    AUTOREFRESH_MS, LIMITE_DQO_ALERTA, LIMITE_DQO_EFLUENTE, META_EFICIENCIA,
    PICO_DQO_AFLUENTE, RANGO_PH_MAX, RANGO_PH_MIN,
    TAG_ENTRADA as _TAG_ENTRADA_FALLBACK,
    TAG_SALIDA as _TAG_SALIDA_FALLBACK,
)
from components.reload_tags import render_reload_tags_button
from dashboard_dqo.tag_admin import cargar_catalog, resolve_tag_por_rol
from dashboard_dqo.db_connector import (
    get_alarmas_activas, get_comparativo_mensual, get_dias_cumplimiento,
    get_distribucion_dqo_salida, get_dqo_serie_temporal, get_eficiencia_stats,
    get_kpi_actual, get_kpi_periodo,
)
from dashboard_dqo.kpi_calculator import (
    calcular_estado_cumplimiento, calcular_estado_dqo,
    calcular_estado_eficiencia, color_estado, delta_pct, estado_global, fmt_num,
    formato_fecha_display, get_rango_fechas, icono_estado, periodo_anterior,
)
from dashboard_dqo.ui_components import (
    inyectar_css, render_alarma_card, render_kpi_card, render_tabla_cumplimiento,
)


# ── Configuración de página ───────────────────────────────────────────────────
# Cuando este archivo se ejecuta como page bajo home.py, set_page_config ya fue
# llamado por el orquestador y vuelve a llamar aquí lanza StreamlitAPIException.
try:
    st.set_page_config(
        page_title="Dashboard DQO — PTAR",
        page_icon="💧",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass
inyectar_css()


# ── Autenticación compartida ─────────────────────────────────────────────────
# Idempotente: si el usuario ya está autenticado por home.py, no muestra form.
# Si se ejecuta standalone, pide credenciales como antes.
from components.auth import setup_auth
setup_auth()


# ── Catálogo de TAGs (cargado desde BD; fallback a config si la BD falla) ────
TAG_CATALOG = cargar_catalog("DQO")

# Afluente y efluente se resuelven desde el catálogo (columna `rol`) en vez de
# leerse directamente de config.py. Si la BD no tiene un TAG marcado con ese
# rol, se cae al valor estático del config (compatibilidad hacia atrás).
TAG_ENTRADA = resolve_tag_por_rol(TAG_CATALOG, "afluente", _TAG_ENTRADA_FALLBACK)
TAG_SALIDA = resolve_tag_por_rol(TAG_CATALOG, "efluente", _TAG_SALIDA_FALLBACK)


def _tags_por_rol(rol: str) -> list[str]:
    """Filtra el catálogo activo por rol. Reemplaza al config.tags_por_rol estático."""
    return [t for t, m in TAG_CATALOG.items() if m.get("rol") == rol]


# ── Sidebar ───────────────────────────────────────────────────────────────────
def _sidebar() -> dict:
    with st.sidebar:
        st.markdown("### 💧 Control DQO — PTAR")
        st.divider()

        # Filtro de tiempo compartido (mismas keys en session_state → persiste
        # cuando el usuario navega a otro dashboard en home.py).
        from components.shared_time_filter import render_shared_time_filter
        periodo, fi, ff = render_shared_time_filter()

        st.divider()
        st.markdown("**Puntos de muestreo**")
        st.caption(
            f"Fijos: `{TAG_ENTRADA}` (afluente) · `{TAG_SALIDA}` (efluente). "
            "Necesarios para los KPIs."
        )
        intermedios_disp = _tags_por_rol("intermedio")
        intermedios_activos = st.multiselect(
            "TAGs intermedios",
            options=intermedios_disp,
            default=intermedios_disp,
            format_func=lambda t: TAG_CATALOG[t]["nombre"],
            help="Etapas opcionales del proceso. Aparecen en la tendencia y en la "
                 "tabla de cumplimiento como referencia.",
        )

        st.divider()
        limite = st.number_input(
            "Límite DQO efluente (mg/L)", min_value=0.0, max_value=2000.0,
            value=float(LIMITE_DQO_EFLUENTE), step=10.0,
        )
        alerta_dqo = st.number_input(
            "Umbral de alerta DQO (mg/L)", min_value=0.0, max_value=float(limite),
            value=float(LIMITE_DQO_ALERTA), step=5.0,
            help="Por encima de este valor se marca como alerta; por encima del "
                 "límite, como crítico. Usado en tabla, gráfico de tendencia, "
                 "barras mensuales y alarmas.",
        )
        meta_eff = st.number_input(
            "Meta eficiencia (%)", min_value=0.0, max_value=100.0,
            value=float(META_EFICIENCIA), step=1.0,
        )

        st.divider()
        st.markdown("**Alarmas**")
        ventana_alarmas = st.number_input(
            "Ventana (días atrás)", min_value=1, max_value=90, value=14, step=1,
            help="Período hacia atrás que se inspecciona para detectar alarmas activas.",
        )

        st.divider()
        if st.button("🔄 Actualizar datos", use_container_width=True):
            st.cache_data.clear()
            st.session_state["ultima_actualizacion"] = datetime.now()
            st.rerun()

        # Recarga puntual del catálogo de TAGs (no invalida el resto del cache).
        render_reload_tags_button(cargar_catalog, key="dqo_reload_tags")

        ult = st.session_state.get("ultima_actualizacion", datetime.now())
        st.caption(f"Datos actualizados: {formato_fecha_display(ult)}")

    tags_activos = (TAG_ENTRADA, *intermedios_activos, TAG_SALIDA)
    return {
        "fi": datetime.combine(fi, datetime.min.time()),
        "ff": datetime.combine(ff, datetime.max.time().replace(microsecond=0)),
        "limite": limite, "alerta_dqo": alerta_dqo,
        "meta_eff": meta_eff, "periodo": periodo,
        "ventana_alarmas": int(ventana_alarmas),
        "tags_activos": tags_activos,
        "intermedios_activos": tuple(intermedios_activos),
    }


# ── Cuerpo principal ──────────────────────────────────────────────────────────
def _zona_encabezado(filtros: dict, estado: str) -> None:
    leyenda = {
        "ok": "Cumplimiento Normal",
        "alerta": "En Alerta",
        "critico": "Excedencia",
        "neutro": "Sin datos",
    }[estado]
    color = color_estado(estado)
    parpadea = estado in ("alerta", "critico")
    clase_circulo = "estado-circulo estado-parpadea" if parpadea else "estado-circulo"

    st.markdown(
        """
        <style>
        .estado-circulo {
            display: inline-block;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-right: 8px;
            vertical-align: middle;
        }
        @keyframes estadoParpadeo {
            0%, 100% { opacity: 1; box-shadow: 0 0 0 0 currentColor; }
            50%      { opacity: 0.35; box-shadow: 0 0 12px 4px currentColor; }
        }
        .estado-parpadea {
            animation: estadoParpadeo 2s ease-in-out infinite;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="dash-header">', unsafe_allow_html=True)
    col_t, col_e = st.columns([3, 1])
    with col_t:
        st.markdown("# Dashboard DQO — Gerencia Ambiental PTAR")
        st.caption(
            f"Período: {filtros['fi'].date()} al {filtros['ff'].date()}"
        )
    with col_e:
        st.markdown(
            f"<div style='text-align:right;font-size:22px;'>"
            f"<span class='{clase_circulo}' style='background:{color};color:{color};'></span>"
            f"<strong>{leyenda}</strong></div>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _zona_kpis(filtros: dict, kpis: dict, cumpl: dict) -> None:
    # delta vs período anterior (mismo largo)
    fi_ant, ff_ant = periodo_anterior(filtros["fi"], filtros["ff"])
    kpi_ant = get_kpi_periodo(fi_ant, ff_ant, tag_in=TAG_ENTRADA, tag_out=TAG_SALIDA)

    eff = kpis["eficiencia_remocion"]
    delta_eff = delta_pct(eff, kpi_ant["eficiencia"])
    delta_afluente = delta_pct(kpis["dqo_afluente_actual"], kpi_ant["entrada"])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card(
            label="DQO Afluente Actual",
            valor=kpis["dqo_afluente_actual"],
            unidad="mg/L",
            sub_texto="Carga de entrada",
            estado="neutro",
            delta_pct=delta_afluente,
            live=True,
        )
    with c2:
        render_kpi_card(
            label="DQO Efluente Actual",
            valor=kpis["dqo_efluente_actual"],
            unidad="mg/L",
            sub_texto=f"Límite: {filtros['limite']:.0f} mg/L · últ. {kpis['ventana_dias']} días",
            estado=calcular_estado_dqo(
                kpis["dqo_efluente_actual"], filtros["limite"], filtros["alerta_dqo"],
            ),
            live=True,
        )
    with c3:
        render_kpi_card(
            label="Eficiencia de Remoción",
            valor=eff,
            unidad="%",
            sub_texto=f"Meta: ≥ {filtros['meta_eff']:.0f}%",
            estado=calcular_estado_eficiencia(eff, filtros["meta_eff"]),
            delta_pct=delta_eff,
        )
    with c4:
        sub = (
            f"{cumpl['dias_cumplimiento']} de {cumpl['dias_total']} días"
            if cumpl["dias_total"] else "Sin días en el rango"
        )
        render_kpi_card(
            label="Cumplimiento Normativo",
            valor=cumpl["pct_cumplimiento"],
            unidad="%",
            sub_texto=sub,
            estado=calcular_estado_cumplimiento(cumpl["pct_cumplimiento"]),
        )


# ── Zona 3 — Tendencia + Gauge ────────────────────────────────────────────────
def _zona_tendencia_gauge(filtros: dict, kpis: dict) -> None:
    col_l, col_r = st.columns([7, 3])
    with col_l:
        df_serie = get_dqo_serie_temporal(
            filtros["fi"], filtros["ff"], filtros["tags_activos"],
        )
        catalogo_activo = {t: TAG_CATALOG[t] for t in filtros["tags_activos"]}
        st.plotly_chart(
            chart_tendencia(df_serie, catalogo_activo, filtros["limite"], filtros["alerta_dqo"]),
            use_container_width=True,
        )
        if not df_serie.empty:
            csv = df_serie.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Descargar serie (CSV)", data=csv,
                file_name=f"dqo_serie_{filtros['fi'].date()}_{filtros['ff'].date()}.csv",
                mime="text/csv",
            )
    with col_r:
        st.plotly_chart(
            chart_gauge_eficiencia(kpis["eficiencia_remocion"], filtros["meta_eff"]),
            use_container_width=True,
        )
        stats = get_eficiencia_stats(
            filtros["fi"], filtros["ff"], tag_in=TAG_ENTRADA, tag_out=TAG_SALIDA,
        )
        st.markdown(
            f"""
            <table style='width:100%;font-size:13px;'>
              <tr><td>Promedio período</td><td style='text-align:right;'><b>{fmt_num(stats['promedio_periodo'], 1, '%')}</b></td></tr>
              <tr><td>Mínimo semanal</td><td style='text-align:right;'><b>{fmt_num(stats['minimo_semanal'], 1, '%')}</b></td></tr>
              <tr><td>Promedio anual</td><td style='text-align:right;'><b>{fmt_num(stats['promedio_anual'], 1, '%')}</b></td></tr>
            </table>
            """,
            unsafe_allow_html=True,
        )


# ── Zona 4 — Cumplimiento · Barras mensual · Alarmas ──────────────────────────
def _zona_paneles(filtros: dict, kpis: dict, df_comparativo: pd.DataFrame) -> None:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("##### Cumplimiento normativo")
        filas = [
            {"nombre": "DQO efluente", "limite": f"{filtros['limite']:.0f} mg/L",
             "valor": kpis["dqo_efluente_actual"], "unidad": "mg/L", "decimales": 1,
             "estado": calcular_estado_dqo(
                 kpis["dqo_efluente_actual"], filtros["limite"], filtros["alerta_dqo"],
             )},
            {"nombre": "Eficiencia", "limite": f"≥ {filtros['meta_eff']:.0f}%",
             "valor": kpis["eficiencia_remocion"], "unidad": "%", "decimales": 1,
             "estado": calcular_estado_eficiencia(kpis["eficiencia_remocion"], filtros["meta_eff"])},
            {"nombre": "DQO afluente", "limite": "Referencia",
             "valor": kpis["dqo_afluente_actual"], "unidad": "mg/L", "decimales": 1,
             "estado": "neutro"},
        ]
        # Filas dinámicas para los TAGs intermedios activos
        for tag in filtros["intermedios_activos"]:
            valor = kpis.get("valores_por_tag", {}).get(tag)
            filas.append({
                "nombre": TAG_CATALOG[tag]["nombre"].split(" (")[0],
                "limite": "Referencia",
                "valor": valor, "unidad": "mg/L", "decimales": 1,
                "estado": "neutro",
            })
        filas.extend([
            {"nombre": "pH", "limite": f"{RANGO_PH_MIN}–{RANGO_PH_MAX}",
             "valor": None, "unidad": "", "estado": "neutro"},
            {"nombre": "Temperatura", "limite": "≤ 35 °C",
             "valor": None, "unidad": "°C", "estado": "neutro"},
        ])
        render_tabla_cumplimiento(filas)

    with col2:
        st.plotly_chart(
            chart_barras_mensual(df_comparativo, filtros["limite"], filtros["alerta_dqo"]),
            use_container_width=True,
        )

    with col3:
        st.markdown(f"##### Alarmas activas · últ. {filtros['ventana_alarmas']} días")
        try:
            alarmas = get_alarmas_activas(
                dias_atras=filtros["ventana_alarmas"],
                pico_afluente=PICO_DQO_AFLUENTE,
                limite_efluente=filtros["limite"],
                alerta_efluente=filtros["alerta_dqo"],
                meta_eficiencia=filtros["meta_eff"],
                tag_in=TAG_ENTRADA, tag_out=TAG_SALIDA,
            )
        except Exception as exc:
            st.error(f"No se pudieron consultar alarmas: {exc}")
            alarmas = []

        alarmas_dqo = [a for a in alarmas if a.get("categoria") == "dqo"]
        alarmas_eff = [a for a in alarmas if a.get("categoria") == "eficiencia"]
        _render_grupo_alarmas("Límites de DQO", alarmas_dqo)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        _render_grupo_alarmas("Eficiencia de remoción", alarmas_eff)


def _render_grupo_alarmas(titulo: str, alarmas: list[dict], max_visibles: int = 3) -> None:
    st.markdown(
        f"<div style='font-size:13px;color:#185FA5;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:0.05em;margin:4px 0 6px;'>"
        f"{titulo}</div>",
        unsafe_allow_html=True,
    )
    if not alarmas:
        st.success(f"✅ Sin alarmas en {titulo.lower()}")
        return

    visibles = alarmas[:max_visibles]
    html = "".join(render_alarma_card(a) for a in visibles)
    st.markdown(html, unsafe_allow_html=True)
    if len(alarmas) > max_visibles:
        with st.expander(f"Ver todas ({len(alarmas)})"):
            extra = "".join(render_alarma_card(a) for a in alarmas[max_visibles:])
            st.markdown(extra, unsafe_allow_html=True)


# ── Zona 5 — Histograma + Comparativo anual ───────────────────────────────────
def _zona_analitica(filtros: dict, df_comparativo: pd.DataFrame) -> None:
    col_l, col_r = st.columns(2)

    with col_l:
        serie = get_distribucion_dqo_salida(
            filtros["fi"], filtros["ff"], tag_out=TAG_SALIDA,
        )
        st.plotly_chart(chart_histograma(serie, filtros["limite"]),
                        use_container_width=True)
        if not serie.empty:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Mín", f"{serie.min():.1f}")
            c2.metric("Máx", f"{serie.max():.1f}")
            c3.metric("Media", f"{serie.mean():.1f}")
            c4.metric("Mediana", f"{serie.median():.1f}")
            c5.metric("P95", f"{serie.quantile(0.95):.1f}")

    with col_r:
        fig, delta_anual = chart_comparativo_anual(df_comparativo, filtros["limite"])
        st.plotly_chart(fig, use_container_width=True)
        if delta_anual is not None:
            flecha = "↑" if delta_anual > 0 else "↓"
            color = "#E24B4A" if delta_anual > 0 else "#639922"
            st.markdown(
                f"<div style='text-align:center;color:{color};font-size:14px;'>"
                f"{flecha} {abs(delta_anual):.1f}% vs hace 12 meses</div>",
                unsafe_allow_html=True,
            )


# ── Main ──────────────────────────────────────────────────────────────────────
# Refresca el dashboard automáticamente para reflejar los nuevos slots del streamer.
st_autorefresh(interval=AUTOREFRESH_MS, key="dash-autorefresh")

filtros = _sidebar()

with st.spinner("Cargando datos…"):
    try:
        kpis = get_kpi_actual(
            dias_atras=7,
            tags_extra=filtros["intermedios_activos"],
            tag_in=TAG_ENTRADA, tag_out=TAG_SALIDA,
        )
        cumpl = get_dias_cumplimiento(
            filtros["fi"], filtros["ff"], filtros["limite"],
            tag_out=TAG_SALIDA,
        )
        df_comparativo = get_comparativo_mensual(
            meses=12, tag_in=TAG_ENTRADA, tag_out=TAG_SALIDA,
        )
    except Exception as exc:
        st.error(
            f"No se pudo leer la base de datos: {exc}\n\n"
            "Verifica el contenedor `timescaledb` y las variables del `.env`."
        )
        st.stop()

estado = estado_global(
    kpis["dqo_efluente_actual"],
    kpis["eficiencia_remocion"],
    cumpl["pct_cumplimiento"],
    limite_dqo=filtros["limite"],
    alerta_dqo=filtros["alerta_dqo"],
    meta_eff=filtros["meta_eff"],
)

_zona_encabezado(filtros, estado)

# Barra de acciones compartida (reutilizable en todos los dashboards).
from components.refresh_bar import render_refresh_bar
_ult = kpis.get("fecha_ultimo_registro")
render_refresh_bar(
    autorefresh_seconds=AUTOREFRESH_MS // 1000,
    ultimo_dato_label=formato_fecha_display(_ult) if _ult else None,
)

_zona_kpis(filtros, kpis, cumpl)

if cumpl["dias_total"] == 0:
    st.warning(
        "No hay datos en el período seleccionado. "
        "Amplía el rango de fechas en el sidebar."
    )

st.divider()
_zona_tendencia_gauge(filtros, kpis)

st.divider()
_zona_paneles(filtros, kpis, df_comparativo)

st.divider()
_zona_analitica(filtros, df_comparativo)

st.divider()
st.caption(
    f"PTAR — Sistema de Monitoreo DQO · Datos desde PLC vía TAG_ID · "
    f"Período: {filtros['fi'].date()} al {filtros['ff'].date()}"
)
