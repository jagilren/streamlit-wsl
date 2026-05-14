"""Funciones que retornan figuras Plotly listas para renderizar."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import (
    COLOR_ENTRADA, COLOR_LIMITE, COLOR_OK, COLOR_SALIDA,
    LIMITE_DQO_ALERTA, LIMITE_DQO_EFLUENTE,
)


# ── Zona 3 — Tendencia ────────────────────────────────────────────────────────
def chart_tendencia(
    df: pd.DataFrame,
    catalogo: dict[str, dict],
    limite: float = LIMITE_DQO_EFLUENTE,
    alerta: float = LIMITE_DQO_ALERTA,
) -> go.Figure:
    """Tendencia multi-TAG.

    df: long format (TimeStamp, tag_id, valor).
    catalogo: subset de TAG_CATALOG con los TAGs a mostrar (orden = orden visual).
    """
    fig = go.Figure()

    if df.empty:
        fig.add_annotation(text="Sin datos en el período",
                           xref="paper", yref="paper", x=0.5, y=0.5,
                           showarrow=False, font=dict(size=16, color="#888"))
        fig.update_layout(template="plotly_white",
                          title="Tendencia DQO — proceso")
        return fig

    titulo_tags = " · ".join(meta["nombre"].split(" (")[0] for meta in catalogo.values())
    y_max = 0.0
    for tag, meta in catalogo.items():
        sub = df[df["tag_id"] == tag]
        if sub.empty:
            continue
        es_efluente = meta.get("rol") == "efluente"
        fill = "tozeroy" if es_efluente else None
        fillcolor = "rgba(24,95,165,0.1)" if es_efluente else None
        fig.add_trace(go.Scatter(
            x=sub["TimeStamp"], y=sub["valor"],
            mode="lines", name=meta["nombre"],
            line=dict(color=meta["color"], width=3.5),
            fill=fill, fillcolor=fillcolor,
            hovertemplate=f"<b>{meta['nombre']}</b>: %{{y:.1f}} mg/L<extra></extra>",
        ))
        y_max = max(y_max, float(sub["valor"].max() or 0))

    fig.add_hline(y=limite, line_dash="dash", line_color=COLOR_LIMITE,
                  annotation_text=f"Límite {limite:.0f} mg/L",
                  annotation_position="top right")
    fig.add_hline(y=alerta, line_dash="dash", line_color="#BA7517",
                  annotation_text=f"Alerta {alerta:.0f} mg/L",
                  annotation_position="bottom right")

    y_max = max(y_max, limite)
    fig.update_layout(
        template="plotly_white",
        title=f"Tendencia DQO — {titulo_tags}",
        xaxis=dict(
            title="",
            type="date",
            rangeslider=dict(
                visible=True,
                thickness=0.06,
                bgcolor="#F5F5F5",
                bordercolor="#DADADA",
                borderwidth=1,
                yaxis=dict(rangemode="fixed", range=[0, 1]),
            ),
        ),
        yaxis=dict(title="DQO (mg/L)", range=[0, y_max * 1.2]),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
        margin=dict(l=10, r=10, t=60, b=10),
        height=440,
    )
    return fig


def chart_gauge_eficiencia(eficiencia: float | None, meta: float = 90.0) -> go.Figure:
    val = float(eficiencia) if eficiencia is not None else 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val,
        number={"suffix": "%", "font": {"size": 36}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#888"},
            "bar": {"color": COLOR_OK if val >= meta else "#BA7517" if val >= meta - 10 else "#E24B4A"},
            "steps": [
                {"range": [0, 80],  "color": "#FCEBEB"},
                {"range": [80, 90], "color": "#FAEEDA"},
                {"range": [90, 100], "color": "#EAF3DE"},
            ],
            "threshold": {
                "line": {"color": "#185FA5", "width": 4},
                "thickness": 0.85, "value": meta,
            },
        },
        title={"text": "Eficiencia de Remoción", "font": {"size": 16}},
    ))
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=50, b=10),
        height=300,
    )
    return fig


# ── Zona 4 — Barras DQO mensual (últimos 6 meses) ─────────────────────────────
def _color_dqo(valor: float, limite: float, alerta: float) -> str:
    if valor > limite:
        return "#E24B4A"
    if valor > alerta:
        return "#BA7517"
    return COLOR_OK


def chart_barras_mensual(
    df: pd.DataFrame, limite: float = LIMITE_DQO_EFLUENTE,
    alerta: float = LIMITE_DQO_ALERTA, n_meses: int = 6,
) -> go.Figure:
    """Barras apiladas por mes que decomponen el rango Mín → Promedio → Máx
    del efluente. La altura total de la pila iguala al máximo del mes.

    Segmentos (de abajo hacia arriba):
        - verde  → 0 al Mínimo  (lo mejor del mes)
        - azul   → Mínimo al Promedio (qué tan arriba estuvo la tendencia)
        - rojo   → Promedio al Máximo (cuánto se disparó en el peor día)
    """
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="Sin datos mensuales", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#888"))
        fig.update_layout(template="plotly_white",
                          title="DQO Efluente — Mín · Promedio · Máx mensual",
                          height=420)
        return fig

    d = df.tail(n_meses).copy()
    etiquetas = [m.strftime("%b %Y") for m in d["Mes"]]
    mins = d["DQO_Salida_Min"].tolist()
    avgs = d["DQO_Salida_Avg"].tolist()
    maxs = d["DQO_Salida_Max"].tolist()

    # Segmentos del stack: cada uno es un delta, no el valor absoluto.
    seg_min = mins
    seg_avg = [a - m for m, a in zip(mins, avgs)]
    seg_max = [mx - a for a, mx in zip(avgs, maxs)]

    fig.add_trace(go.Bar(
        x=etiquetas, y=seg_min, name="Mínimo",
        marker_color=COLOR_OK,
        text=[f"{v:.0f}" for v in mins],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=11, color="#FFFFFF"),
        customdata=mins,
        hovertemplate="<b>%{x} · Mínimo</b><br>%{customdata:.1f} mg/L<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=etiquetas, y=seg_avg, name="Mín → Promedio",
        marker_color="#185FA5",
        text=[f"{v:.0f}" for v in avgs],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=11, color="#FFFFFF"),
        customdata=[[m, a] for m, a in zip(mins, avgs)],
        hovertemplate=(
            "<b>%{x} · Promedio</b><br>"
            "Promedio: %{customdata[1]:.1f} mg/L<br>"
            "Δ desde mín: %{y:.1f} mg/L<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        x=etiquetas, y=seg_max, name="Promedio → Máximo",
        marker_color="#E24B4A",
        text=[f"{v:.0f}" for v in maxs],
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=11, color="#FFFFFF"),
        customdata=[[a, mx] for a, mx in zip(avgs, maxs)],
        hovertemplate=(
            "<b>%{x} · Máximo</b><br>"
            "Máximo: %{customdata[1]:.1f} mg/L<br>"
            "Δ desde prom: %{y:.1f} mg/L<extra></extra>"
        ),
    ))

    fig.add_hline(y=limite, line_dash="dash", line_color=COLOR_LIMITE,
                  annotation_text=f"Límite {limite:.0f}",
                  annotation_position="top right")
    fig.add_hline(y=alerta, line_dash="dash", line_color="#BA7517",
                  annotation_text=f"Alerta {alerta:.0f}",
                  annotation_position="bottom right")

    y_top = max(max(maxs), limite) * 1.12
    fig.update_layout(
        template="plotly_white",
        title=f"DQO Efluente — Decomposición Mín · Promedio · Máx (últ. {n_meses} meses)",
        xaxis_title="", yaxis_title="DQO (mg/L)",
        yaxis=dict(range=[0, y_top]),
        barmode="stack",
        bargap=0.30,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=70, b=10),
        height=420,
    )
    return fig


# ── Zona 5 — Histograma con colores por bin ───────────────────────────────────
def chart_histograma(
    serie: pd.Series, limite: float = LIMITE_DQO_EFLUENTE,
) -> go.Figure:
    fig = go.Figure()
    if serie.empty:
        fig.add_annotation(text="Sin datos en el período", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#888"))
        fig.update_layout(template="plotly_white",
                          title="Distribución DQO Efluente — 0 registros",
                          height=420)
        return fig

    bin_size = 10
    v_max = max(serie.max(), limite) + 50
    bins = list(range(0, int(v_max) + bin_size, bin_size))
    cortes = pd.cut(serie, bins=bins, include_lowest=True)
    conteo = cortes.value_counts().sort_index()

    centros = [(b.left + b.right) / 2 for b in conteo.index]
    colores = []
    for c in centros:
        if c <= 120:
            colores.append("#C0DD97")
        elif c <= 160:
            colores.append("#FAC775")
        elif c <= 200:
            colores.append("#EF9F27")
        else:
            colores.append("#E24B4A")

    fig.add_trace(go.Bar(
        x=centros, y=conteo.values,
        marker_color=colores,
        width=[bin_size] * len(centros),
        hovertemplate="DQO: %{x:.0f} mg/L<br>Frecuencia: %{y}<extra></extra>",
        showlegend=False,
    ))

    promedio = float(serie.mean())
    fig.add_vline(x=limite, line_dash="dash", line_color=COLOR_LIMITE,
                  annotation_text="Límite", annotation_position="top")
    fig.add_vline(x=promedio, line_dash="dash", line_color="#185FA5",
                  annotation_text=f"Promedio {promedio:.0f}", annotation_position="top")

    fig.update_layout(
        template="plotly_white",
        title=f"Distribución DQO Efluente — {len(serie):,} registros",
        xaxis_title="DQO (mg/L)", yaxis_title="Frecuencia (registros)",
        bargap=0.05,
        margin=dict(l=10, r=10, t=60, b=10),
        height=420,
    )
    return fig


# ── Zona 5 — Comparativo anual (barras DQO + línea eficiencia) ────────────────
def chart_comparativo_anual(
    df: pd.DataFrame, limite: float = LIMITE_DQO_EFLUENTE,
) -> tuple[go.Figure, float | None]:
    """Devuelve (figura, delta_pct_12meses)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if df.empty:
        fig.add_annotation(text="Sin datos suficientes", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False)
        fig.update_layout(template="plotly_white", title="Tendencia Anual DQO — Eficiencia",
                          height=420)
        return fig, None

    d = df.copy()
    etiquetas = [m.strftime("%b %Y") for m in d["Mes"]]
    mes_actual = datetime.now().replace(day=1).date()
    colores = [
        "#185FA5" if m.date() == mes_actual else "#85B7EB"
        for m in d["Mes"]
    ]

    fig.add_trace(
        go.Bar(x=etiquetas, y=d["DQO_Salida_Avg"], name="DQO Salida",
               marker_color=colores,
               text=[f"{v:.0f}" for v in d["DQO_Salida_Avg"]],
               textposition="outside",
               hovertemplate="%{x}<br>DQO Salida: %{y:.1f} mg/L<extra></extra>"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=etiquetas, y=d["Eficiencia_Pct"], name="Eficiencia",
                   mode="lines+markers",
                   line=dict(color=COLOR_OK, width=2),
                   marker=dict(size=8),
                   hovertemplate="%{x}<br>Eficiencia: %{y:.1f}%<extra></extra>"),
        secondary_y=True,
    )
    fig.add_hline(y=limite, line_dash="dash", line_color=COLOR_LIMITE,
                  annotation_text=f"Límite {limite:.0f} mg/L",
                  annotation_position="top left")

    fig.update_layout(
        template="plotly_white",
        title="Tendencia Anual DQO — Eficiencia de Remoción",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=60, b=10),
        height=420,
    )
    fig.update_yaxes(title_text="DQO (mg/L)", secondary_y=False)
    fig.update_yaxes(title_text="Eficiencia (%)", secondary_y=True, range=[0, 100])

    delta = None
    if len(d) >= 12:
        primero = d.iloc[0]["DQO_Salida_Avg"]
        ultimo = d.iloc[-1]["DQO_Salida_Avg"]
        if primero and primero > 0:
            delta = (ultimo - primero) / primero * 100.0
    return fig, delta
