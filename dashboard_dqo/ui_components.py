"""Componentes visuales reutilizables: CSS y tarjetas (KPI, alarmas)."""

from __future__ import annotations

import streamlit as st

from .kpi_calculator import (
    Estado, color_estado, fmt_num, formato_fecha_display, icono_estado,
)

CSS = """
<style>
.kpi-card {
    background: #F0F2F6;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    border-left: 4px solid {border};
    min-height: 120px;
    position: relative;
}
.kpi-live {
    position: absolute;
    top: 8px;
    right: 10px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #639922;
    text-transform: uppercase;
}
.kpi-live-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #639922;
    box-shadow: 0 0 0 0 rgba(99,153,34,0.7);
    animation: kpiLivePulse 1.4s ease-out infinite;
}
@keyframes kpiLivePulse {
    0%   { box-shadow: 0 0 0 0   rgba(99,153,34,0.7); transform: scale(1);    }
    70%  { box-shadow: 0 0 0 10px rgba(99,153,34,0);   transform: scale(1.15); }
    100% { box-shadow: 0 0 0 0   rgba(99,153,34,0);   transform: scale(1);    }
}
.kpi-label {
    font-size: 12px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.kpi-value {
    font-size: 28px;
    font-weight: 600;
    margin: 4px 0;
    color: #222;
}
.kpi-sub {
    font-size: 12px;
    color: #555;
}
.kpi-delta-up   { color: #639922; font-size: 12px; }
.kpi-delta-down { color: #E24B4A; font-size: 12px; }
.kpi-delta-flat { color: #666;    font-size: 12px; }
.estado-ok      { color: #639922; }
.estado-alerta  { color: #BA7517; }
.estado-critico { color: #E24B4A; }
.estado-neutro  { color: #666;    }
.dash-header {
    border-bottom: 2px solid #185FA5;
    padding-bottom: 8px;
    margin-bottom: 1rem;
}
.alarma-critica, .alarma-alerta {
    border-radius: 6px;
    padding: 8px 12px;
    margin: 4px 0;
    color: #1A1A1A;
}
.alarma-critica { background: #FCEBEB; border-left: 4px solid #E24B4A; }
.alarma-alerta  { background: #FAEEDA; border-left: 4px solid #BA7517; }
.alarma-critica strong, .alarma-alerta strong { color: #1A1A1A; }
.alarma-critica span, .alarma-alerta span     { color: #444 !important; }
</style>
"""


def inyectar_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def render_kpi_card(
    label: str,
    valor: float | None,
    unidad: str,
    sub_texto: str,
    estado: Estado,
    delta_pct: float | None = None,
    decimales: int = 1,
    live: bool = False,
) -> None:
    """Renderiza una tarjeta KPI con borde de color según estado."""
    border = color_estado(estado)
    valor_str = fmt_num(valor, decimales)
    valor_html = f"{valor_str} <span style='font-size:14px;color:#666'>{unidad}</span>" if valor_str != "Sin dato" else valor_str

    delta_html = ""
    if delta_pct is not None and delta_pct == delta_pct:  # not NaN
        if abs(delta_pct) < 0.1:
            delta_html = f"<div class='kpi-delta-flat'>→ {delta_pct:+.1f}% vs período anterior</div>"
        elif delta_pct > 0:
            delta_html = f"<div class='kpi-delta-up'>↑ {delta_pct:+.1f}% vs período anterior</div>"
        else:
            delta_html = f"<div class='kpi-delta-down'>↓ {delta_pct:+.1f}% vs período anterior</div>"

    live_html = (
        "<div class='kpi-live'><span class='kpi-live-dot'></span>En vivo</div>"
        if live else ""
    )

    html = (
        f'<div class="kpi-card" style="border-left-color:{border};">'
        f'{live_html}'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{valor_html}</div>'
        f'<div class="kpi-sub">{sub_texto}</div>'
        f'{delta_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_alarma_card(alarma: dict) -> str:
    """Devuelve HTML de una tarjeta de alarma (no la imprime — para batch)."""
    sev = alarma["severidad"]
    css = "alarma-critica" if sev == "critico" else "alarma-alerta"
    icono = "🔴" if sev == "critico" else "⚠️"
    valor = fmt_num(alarma["valor"], 1, f" {alarma['unidad']}")
    ts = formato_fecha_display(alarma["timestamp"])
    return f"""
    <div class="{css}">
        <strong>{icono} {alarma['tipo']}</strong> · <span style='color:#555'>{ts}</span><br>
        <span style='font-size:13px'>{alarma['descripcion']}</span><br>
        <span style='font-size:12px;color:#666'>Valor: <b>{valor}</b> · TAG: {alarma['tag']}</span>
    </div>
    """


def render_tabla_cumplimiento(filas: list[dict]) -> None:
    """Render manual de la tabla de cumplimiento con semáforo HTML."""
    html = [
        "<table style='width:100%;border-collapse:collapse;font-size:13px;"
        "background:#FFFFFF;color:#1A1A1A;border-radius:6px;overflow:hidden;'>"
    ]
    html.append(
        "<thead><tr style='background:#185FA5;color:#FFFFFF;'>"
        "<th style='text-align:left;padding:8px;color:#FFFFFF;'>Parámetro</th>"
        "<th style='text-align:left;padding:8px;color:#FFFFFF;'>Límite</th>"
        "<th style='text-align:right;padding:8px;color:#FFFFFF;'>Valor actual</th>"
        "<th style='text-align:center;padding:8px;color:#FFFFFF;'>Estado</th>"
        "</tr></thead><tbody>"
    )
    for i, f in enumerate(filas):
        ic = icono_estado(f["estado"]) if f["estado"] != "neutro" else "—"
        valor_str = fmt_num(f["valor"], f.get("decimales", 1), f" {f.get('unidad', '')}".rstrip()) \
            if f["valor"] is not None else "Sin dato"
        bg = "#FFFFFF" if i % 2 == 0 else "#F4F6F9"
        html.append(
            f"<tr style='background:{bg};border-bottom:1px solid #E0E0E0;color:#1A1A1A;'>"
            f"<td style='padding:8px;color:#1A1A1A;'>{f['nombre']}</td>"
            f"<td style='padding:8px;color:#1A1A1A;'>{f['limite']}</td>"
            f"<td style='padding:8px;text-align:right;color:#1A1A1A;font-weight:600;'>{valor_str}</td>"
            f"<td style='padding:8px;text-align:center;font-size:18px;'>{ic}</td>"
            f"</tr>"
        )
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)
