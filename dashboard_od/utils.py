"""Helpers de clasificación de estado para valores de OD (Oxígeno Disuelto)."""

from __future__ import annotations

from typing import Literal

Status = Literal[
    "ok", "warn_high", "warn_low", "critical_high", "critical_low", "no_data",
]


def compute_od_status(od_value: float | None, cfg: dict) -> Status:
    """Clasifica un valor de OD según los umbrales del TAG."""
    if od_value is None:
        return "no_data"
    if od_value > cfg["crit_max"]:
        return "critical_high"
    if od_value < cfg["crit_min"]:
        return "critical_low"
    if od_value > cfg["opt_max"]:
        return "warn_high"
    if od_value < cfg["opt_min"]:
        return "warn_low"
    return "ok"


# Misma paleta que pH para coherencia visual entre módulos. Si en el futuro
# el OD necesita semántica distinta (ej. "demasiado oxígeno = gasto energético")
# se ajustan aquí los labels sin tocar la lógica.
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


def classify_violation(od_value: float, cfg: dict) -> tuple[str, str]:
    """Para la tabla de eventos: devuelve (violation_type, severity).

    Severity es un string interno (no se muestra en la UI; solo controla
    el color de fila). Valores: "crítico" | "advertencia".
    """
    if od_value < cfg["crit_min"]:
        return ("Bajo crítico", "crítico")
    if od_value > cfg["crit_max"]:
        return ("Alto crítico", "crítico")
    if od_value < cfg["opt_min"]:
        return ("Bajo óptimo", "advertencia")
    return ("Alto óptimo", "advertencia")


def deviation(od_value: float, cfg: dict) -> float:
    """Desviación firmada del valor respecto al rango óptimo (negativa = por debajo)."""
    if od_value < cfg["opt_min"]:
        return round(od_value - cfg["opt_min"], 2)
    if od_value > cfg["opt_max"]:
        return round(od_value - cfg["opt_max"], 2)
    return 0.0
