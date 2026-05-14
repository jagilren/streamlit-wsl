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


STATUS_CONFIG: dict[str, dict[str, str]] = {
    "ok":            {"label": "Normal",            "color": "#1D9E75", "badge_bg": "#E1F5EE"},
    "warn_high":     {"label": "⚠ Alto óptimo",     "color": "#BA7517", "badge_bg": "#FAEEDA"},
    "warn_low":      {"label": "⚠ Bajo óptimo",     "color": "#BA7517", "badge_bg": "#FAEEDA"},
    "critical_high": {"label": "🚨 Alto crítico",    "color": "#A32D2D", "badge_bg": "#FCEBEB"},
    "critical_low":  {"label": "🚨 Bajo crítico",    "color": "#A32D2D", "badge_bg": "#FCEBEB"},
    "no_data":       {"label": "Sin datos",         "color": "#888780", "badge_bg": "#F1EFE8"},
}


def classify_violation(ph_value: float, cfg: dict) -> tuple[str, str]:
    """Para la tabla de eventos: devuelve (violation_type, severity)."""
    if ph_value < cfg["crit_min"]:
        return ("Bajo crítico", "crit")
    if ph_value > cfg["crit_max"]:
        return ("Alto crítico", "crit")
    if ph_value < cfg["opt_min"]:
        return ("Bajo óptimo", "warn")
    return ("Alto óptimo", "warn")


def deviation(ph_value: float, cfg: dict) -> float:
    """Desviación firmada del valor respecto al rango óptimo (negativa = por debajo)."""
    if ph_value < cfg["opt_min"]:
        return round(ph_value - cfg["opt_min"], 2)
    if ph_value > cfg["opt_max"]:
        return round(ph_value - cfg["opt_max"], 2)
    return 0.0
