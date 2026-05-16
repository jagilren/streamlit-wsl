"""Helpers de clasificación de estado para los valores del dashboard plantilla."""

from __future__ import annotations

from typing import Literal

Status = Literal[
    "ok", "warn_high", "warn_low", "critical_high", "critical_low", "no_data",
]


def compute_template_status(value: float | None, cfg: dict) -> Status:
    """Clasifica un valor según los umbrales del TAG."""
    if value is None:
        return "no_data"
    if value > cfg["crit_max"]:
        return "critical_high"
    if value < cfg["crit_min"]:
        return "critical_low"
    if value > cfg["opt_max"]:
        return "warn_high"
    if value < cfg["opt_min"]:
        return "warn_low"
    return "ok"


# Paleta consistente con los demás dashboards (pH/OD).
STATUS_CONFIG: dict[str, dict[str, str]] = {
    "ok":            {"label": "Normal",         "color": "#1D9E75",
                      "badge_fg": "#FFFFFF", "badge_bg": "#1D9E75"},
    "warn_high":     {"label": "⚠ Alto óptimo",  "color": "#B86A00",
                      "badge_fg": "#FFFFFF", "badge_bg": "#E07B00"},
    "warn_low":      {"label": "⚠ Bajo óptimo",  "color": "#B86A00",
                      "badge_fg": "#FFFFFF", "badge_bg": "#E07B00"},
    "critical_high": {"label": "🚨 ALTO CRÍTICO", "color": "#A32D2D",
                      "badge_fg": "#FFFFFF", "badge_bg": "#C62828"},
    "critical_low":  {"label": "🚨 BAJO CRÍTICO", "color": "#A32D2D",
                      "badge_fg": "#FFFFFF", "badge_bg": "#C62828"},
    "no_data":       {"label": "Sin datos",      "color": "#666666",
                      "badge_fg": "#FFFFFF", "badge_bg": "#777777"},
}


def classify_violation(value: float, cfg: dict) -> tuple[str, str]:
    """Devuelve (violation_type, severity) para la tabla de eventos."""
    if value < cfg["crit_min"]:
        return ("Bajo crítico", "crítico")
    if value > cfg["crit_max"]:
        return ("Alto crítico", "crítico")
    if value < cfg["opt_min"]:
        return ("Bajo óptimo", "advertencia")
    return ("Alto óptimo", "advertencia")


def deviation(value: float, cfg: dict) -> float:
    """Desviación firmada del valor respecto al rango óptimo."""
    if value < cfg["opt_min"]:
        return round(value - cfg["opt_min"], 2)
    if value > cfg["opt_max"]:
        return round(value - cfg["opt_max"], 2)
    return 0.0
