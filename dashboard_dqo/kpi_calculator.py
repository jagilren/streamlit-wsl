"""Lógica de evaluación de estados (semáforo) y rangos de fechas."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal

from .config import (
    COLOR_ALERTA, COLOR_CRITICO, COLOR_NEUTRO, COLOR_OK,
    LIMITE_DQO_EFLUENTE, META_EFICIENCIA,
)

Estado = Literal["ok", "alerta", "critico", "neutro"]


def calcular_estado_dqo(
    valor: float | None,
    limite: float = LIMITE_DQO_EFLUENTE,
    umbral_alerta: float | None = None,
) -> Estado:
    """Estado semáforo del DQO efluente relativo al límite normativo.

    - critico:  valor > límite
    - alerta:   valor entre el 80 % y el 100 % del límite (margen < 20 %)
    - ok:       valor ≤ 80 % del límite (margen ≥ 20 %)

    Si `umbral_alerta` no se pasa explícitamente, se calcula como
    `limite * 0.80` para que escale al cambiar el límite en el sidebar.
    """
    if valor is None:
        return "neutro"
    if valor > limite:
        return "critico"
    if umbral_alerta is None:
        umbral_alerta = limite * 0.80
    if valor > umbral_alerta:
        return "alerta"
    return "ok"


def calcular_estado_eficiencia(
    pct: float | None, meta: float = META_EFICIENCIA,
) -> Estado:
    if pct is None:
        return "neutro"
    if pct >= meta:
        return "ok"
    if pct >= meta - 10.0:
        return "alerta"
    return "critico"


def calcular_estado_cumplimiento(pct: float | None) -> Estado:
    if pct is None:
        return "neutro"
    if pct >= 100.0:
        return "ok"
    if pct >= 95.0:
        return "alerta"
    return "critico"


def color_estado(estado: Estado) -> str:
    return {
        "ok": COLOR_OK,
        "alerta": COLOR_ALERTA,
        "critico": COLOR_CRITICO,
        "neutro": COLOR_NEUTRO,
    }[estado]


def icono_estado(estado: Estado) -> str:
    return {"ok": "🟢", "alerta": "🟡", "critico": "🔴", "neutro": "⚪"}[estado]


def estado_global(
    dqo_efluente: float | None,
    eficiencia: float | None,
    pct_cumplimiento: float | None,
    limite_dqo: float = LIMITE_DQO_EFLUENTE,
    alerta_dqo: float | None = None,
    meta_eff: float = META_EFICIENCIA,
) -> Estado:
    """Peor estado entre los tres KPIs principales."""
    estados = [
        calcular_estado_dqo(dqo_efluente, limite_dqo, alerta_dqo),
        calcular_estado_eficiencia(eficiencia, meta_eff),
        calcular_estado_cumplimiento(pct_cumplimiento),
    ]
    orden = {"critico": 3, "alerta": 2, "ok": 1, "neutro": 0}
    return max(estados, key=lambda e: orden[e])


# ── Rangos de fechas ──────────────────────────────────────────────────────────
def get_rango_fechas(periodo: str) -> tuple[datetime, datetime]:
    """Convierte un literal del sidebar en (inicio, fin) datetime."""
    hoy = date.today()
    fin = datetime.combine(hoy, time(23, 59, 59))
    if periodo == "Hoy":
        inicio = datetime.combine(hoy, time.min)
    elif periodo == "Esta semana":
        inicio = datetime.combine(hoy - timedelta(days=hoy.weekday()), time.min)
    elif periodo == "Este mes":
        inicio = datetime.combine(hoy.replace(day=1), time.min)
    elif periodo == "Últimos 90 días":
        inicio = datetime.combine(hoy - timedelta(days=89), time.min)
    elif periodo == "Este año":
        inicio = datetime.combine(hoy.replace(month=1, day=1), time.min)
    else:
        inicio = datetime.combine(hoy.replace(day=1), time.min)
    return inicio, fin


def periodo_anterior(fi: datetime, ff: datetime) -> tuple[datetime, datetime]:
    """Mismo largo que [fi, ff], pero inmediatamente anterior — para deltas %."""
    dur = ff - fi
    return fi - dur, fi


def delta_pct(actual: float | None, anterior: float | None) -> float | None:
    if actual is None or anterior is None or anterior == 0:
        return None
    return (actual - anterior) / abs(anterior) * 100.0


# ── Formato ───────────────────────────────────────────────────────────────────
_MESES_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def formato_fecha_display(fecha: datetime | date | None) -> str:
    if fecha is None:
        return "Sin dato"
    if isinstance(fecha, datetime):
        return f"{fecha.day:02d} {_MESES_ES[fecha.month]} {fecha.year} {fecha.strftime('%H:%M')}"
    return f"{fecha.day:02d} {_MESES_ES[fecha.month]} {fecha.year}"


def fmt_num(v: float | None, dec: int = 1, sufijo: str = "") -> str:
    if v is None or v != v:  # cubre NaN
        return "Sin dato"
    return f"{v:.{dec}f}{sufijo}"
