"""Generador de datos sintéticos de DQO para el tren de tratamiento PTAR.

Proceso (4 etapas, cada una reduce la carga):
    DAF-ENTRADA  →  CLARI1_OUT  →  RAB-SALIDA  →  DQO_Filtros (efluente)

Rangos esperados (ppm):
    - DAF-ENTRADA  : 900 – 1300   (afluente)
    - CLARI1_OUT   : 500 – 650    (intermedio, salida del clarificador 1)
    - RAB-SALIDA   : 230 – 350    (intermedio, salida del reactor anaeróbico)
    - DQO_Filtros  : 110 – 210    (efluente, salida de filtros de pulimiento)

Modelo:
    - Una lectura cada 15 min por TAG (96 slots/día, 384 lecturas/día).
    - Cada día tiene una "carga base diaria" c_dia ∈ [0, 1] común a las 4 etapas:
        c bajo  → planta operando bien (valores en parte baja del rango).
        c alto  → día de alta carga / peor desempeño (valores hacia parte alta).
    - 10 % de los días tienen carga "alta" (c_dia ∈ [0.7, 1.0]) → simula picos.
    - Sobre c_dia se aplica una modulación intra-día (coseno 24 h, máx ~14:00,
      mín ~02:00) más ruido gaussiano por slot, dando una carga por slot c_slot.
    - Cada etapa interpola linealmente entre su MIN y MAX según c_slot, y se le
      añade ruido gaussiano leve para que las 4 trazas no sean perfectamente
      paralelas dentro del slot.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Iterator

TAG_ENTRADA = "DAF-ENTRADA"
TAG_CLARI1 = "CLARI1_OUT"
TAG_RAB = "RAB-SALIDA"
TAG_FILTROS = "DQO_Filtros"

DAF_MIN,    DAF_MAX    = 900.0, 1300.0
CLARI_MIN,  CLARI_MAX  = 500.0, 650.0
RAB_MIN,    RAB_MAX    = 230.0, 350.0
FILTROS_MIN, FILTROS_MAX = 110.0, 210.0

CARGA_NORMAL = (0.00, 0.70)
CARGA_ALTA   = (0.70, 1.00)
PROB_CARGA_ALTA = 0.10

# Sigma del ruido gaussiano por etapa, expresado como fracción del ancho del rango.
SIGMA_REL = 0.04

# Cadencia de lectura: una muestra cada 15 min → 96 slots/día.
SLOT_MINUTOS = 3
SLOTS_POR_DIA = (24 * 60) // SLOT_MINUTOS

# Amplitud de la modulación diaria de carga (±AMPLITUD_DIA sobre la base).
AMPLITUD_DIA = 0.15
# Hora del día (decimal) en la que la modulación alcanza su máximo.
HORA_PICO_DIARIO = 14.0
# Sigma del ruido gaussiano aplicado a la carga por slot.
SIGMA_C_SLOT = 0.03


@dataclass(frozen=True)
class Lectura:
    tag_id: str
    timestamp: datetime
    value: float


def _rango_fechas(desde: date, hasta: date) -> Iterator[date]:
    actual = desde
    while actual <= hasta:
        yield actual
        actual += timedelta(days=1)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _lerp_con_ruido(rng: random.Random, c: float, lo: float, hi: float) -> float:
    """Interpola lo→hi según c ∈ [0,1] y añade ruido gaussiano leve, recortando."""
    centro = lo + c * (hi - lo)
    sigma = (hi - lo) * SIGMA_REL
    return _clamp(centro + rng.gauss(0.0, sigma), lo, hi)


def sample_carga_dia(rng: random.Random) -> float:
    """Carga base diaria, con 10 % de probabilidad de caer en el rango alto."""
    if rng.random() < PROB_CARGA_ALTA:
        return rng.uniform(*CARGA_ALTA)
    return rng.uniform(*CARGA_NORMAL)


def carga_slot(rng: random.Random, carga_dia: float, hora_decimal: float) -> float:
    """Carga del slot: c_dia + modulación 24h (máx ~14:00) + ruido."""
    omega = 2.0 * math.pi / 24.0
    modulacion = AMPLITUD_DIA * math.cos((hora_decimal - HORA_PICO_DIARIO) * omega)
    return _clamp(carga_dia + modulacion + rng.gauss(0.0, SIGMA_C_SLOT), 0.0, 1.0)


def calc_valores(rng: random.Random, c_slot: float) -> dict[str, float]:
    """Mapea c_slot → un valor por TAG (con ruido individual de etapa)."""
    return {
        TAG_ENTRADA: round(_lerp_con_ruido(rng, c_slot, DAF_MIN,     DAF_MAX),     2),
        TAG_CLARI1:  round(_lerp_con_ruido(rng, c_slot, CLARI_MIN,   CLARI_MAX),   2),
        TAG_RAB:     round(_lerp_con_ruido(rng, c_slot, RAB_MIN,     RAB_MAX),     2),
        TAG_FILTROS: round(_lerp_con_ruido(rng, c_slot, FILTROS_MIN, FILTROS_MAX), 2),
    }


def generar(
    desde: date = date(2025, 1, 1),
    hasta: date | None = None,
    seed: int = 42,
) -> list[Lectura]:
    """Devuelve la lista de Lecturas para [desde 00:00, hasta 23:45], 96 slots/día × 4 TAGs."""
    if hasta is None:
        hasta = date.today()
    if hasta < desde:
        raise ValueError(f"hasta ({hasta}) debe ser >= desde ({desde})")

    rng = random.Random(seed)
    lecturas: list[Lectura] = []
    paso = timedelta(minutes=SLOT_MINUTOS)

    for d in _rango_fechas(desde, hasta):
        carga_dia = sample_carga_dia(rng)
        ts = datetime.combine(d, time(0, 0))
        for slot in range(SLOTS_POR_DIA):
            hora = slot * SLOT_MINUTOS / 60.0  # hora decimal del día [0, 24)
            c_slot = carga_slot(rng, carga_dia, hora)
            for tag, valor in calc_valores(rng, c_slot).items():
                lecturas.append(Lectura(tag, ts, valor))
            ts += paso

    return lecturas


def resumen(lecturas: Iterable[Lectura]) -> dict[str, dict[str, float | int]]:
    """Estadísticas básicas por TAG, útiles para validar la generación."""
    por_tag: dict[str, list[float]] = {}
    for lec in lecturas:
        por_tag.setdefault(lec.tag_id, []).append(lec.value)

    out: dict[str, dict[str, float | int]] = {}
    for tag, vals in por_tag.items():
        out[tag] = {
            "n": len(vals),
            "min": min(vals),
            "max": max(vals),
            "promedio": round(sum(vals) / len(vals), 2),
        }
    return out
