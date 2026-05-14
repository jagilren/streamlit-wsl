"""Helpers de clasificación de estado para valores de pH."""

from __future__ import annotations

from typing import Literal

Status = Literal[
    "ok", "warn_high", "warn_low", "critical_high", "critical_low", "no_data",
]


def compute_ph_status(ph_value: float | None, cfg: dict) -> Status:
    """Clasifica un valor de pH según los umbrales del TAG."""
    if ph_value is None:
        return "no_data"
    if ph_value > cfg["crit_max"]:
        return "critical_high"
    if ph_value < cfg["crit_min"]:
        return "critical_low"
    if ph_value > cfg["opt_max"]:
        return "warn_high"
    if ph_value < cfg["opt_min"]:
        return "warn_low"
    return "ok"


# Paleta con dos planos de color:
#   - `color`     → texto del valor numérico, borde-left de la card y línea de
#                   tendencia. Tono saturado sobre fondo claro de la card.
#   - `badge_fg`  → texto del badge (blanco para máximo contraste).
#   - `badge_bg`  → fondo del badge (color saturado).
# Los badges alertan, así que se buscan ratios WCAG ≥ 4.5:1.
STATUS_CONFIG: dict[str, dict[str, str]] = {
    "ok": {
        "label": "Normal",
        "color":    "#1D9E75",
        "badge_fg": "#FFFFFF",
        "badge_bg": "#1D9E75",
    },
    "warn_high": {
        "label": "⚠ Alto óptimo",
        "color":    "#B86A00",
        "badge_fg": "#FFFFFF",
        "badge_bg": "#E07B00",
    },
    "warn_low": {
        "label": "⚠ Bajo óptimo",
        "color":    "#B86A00",
        "badge_fg": "#FFFFFF",
        "badge_bg": "#E07B00",
    },
    "critical_high": {
        "label": "🚨 ALTO CRÍTICO",
        "color":    "#A32D2D",
        "badge_fg": "#FFFFFF",
        "badge_bg": "#C62828",
    },
    "critical_low": {
        "label": "🚨 BAJO CRÍTICO",
        "color":    "#A32D2D",
        "badge_fg": "#FFFFFF",
        "badge_bg": "#C62828",
    },
    "no_data": {
        "label": "Sin datos",
        "color":    "#666666",
        "badge_fg": "#FFFFFF",
        "badge_bg": "#777777",
    },
}


def classify_violation(ph_value: float, cfg: dict) -> tuple[str, str]:
    """Para la tabla de eventos: devuelve (violation_type, severity).

    Severity es un string interno (no se muestra en la UI; solo controla
    el color de fila). Valores: "crítico" | "advertencia".
    """
    if ph_value < cfg["crit_min"]:
        return ("Bajo crítico", "crítico")
    if ph_value > cfg["crit_max"]:
        return ("Alto crítico", "crítico")
    if ph_value < cfg["opt_min"]:
        return ("Bajo óptimo", "advertencia")
    return ("Alto óptimo", "advertencia")


def deviation(ph_value: float, cfg: dict) -> float:
    """Desviación firmada del valor respecto al rango óptimo (negativa = por debajo)."""
    if ph_value < cfg["opt_min"]:
        return round(ph_value - cfg["opt_min"], 2)
    if ph_value > cfg["opt_max"]:
        return round(ph_value - cfg["opt_max"], 2)
    return 0.0
