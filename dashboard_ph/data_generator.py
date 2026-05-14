"""Generador en vivo de pH: una lectura cada 3 min por TAG.

Pensado para correr como servicio Docker:
    python -m dashboard_ph.data_generator

Lógica por TAG (ver doc §4):
- Valor base: punto medio del rango óptimo.
- Ruido normal: sigma = 15 % del ancho del rango óptimo.
- Drift (5 %): puede salir del óptimo hasta 40 % del ancho crítico.
- Spike (1 %): fuera del rango crítico.
- Clamp: ±0.5 fuera de los límites críticos.
- Quality: 192 (Good) normal, 64 (Uncertain) en spikes.
"""

from __future__ import annotations

import logging
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PARENT / ".env")
except ModuleNotFoundError:
    pass

from dashboard_ph.db_init import init_ph_tables
from dashboard_ph.queries import get_ph_tag_configs, insert_ph_measurement

logging.basicConfig(
    level=os.getenv("PH_GENERATOR_LOG", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ph-data-generator")

INTERVAL_SECONDS = int(os.getenv("PH_INTERVAL_SECONDS", "180"))  # 3 min

PROB_DRIFT = 0.05
PROB_SPIKE = 0.01
NOISE_REL = 0.15           # sigma como fracción del rango óptimo
DRIFT_REL = 0.40           # extensión del drift como fracción del rango crítico
CLAMP_MARGIN = 0.5         # nunca más de ±0.5 fuera del rango crítico

QUALITY_GOOD = 192
QUALITY_UNCERTAIN = 64

_RUNNING = True


def _stop(signum, _frame) -> None:
    global _RUNNING
    _RUNNING = False
    log.info("Señal %s recibida — cerrando…", signum)


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def generate_ph_value(cfg: dict, rng: random.Random) -> tuple[float, int]:
    """Genera (ph_value, quality) según el modelo descrito."""
    opt_min, opt_max = float(cfg["opt_min"]), float(cfg["opt_max"])
    crit_min, crit_max = float(cfg["crit_min"]), float(cfg["crit_max"])
    opt_width = opt_max - opt_min
    crit_width = crit_max - crit_min
    base = (opt_min + opt_max) / 2.0

    r = rng.random()
    quality = QUALITY_GOOD

    if r < PROB_SPIKE:
        # Spike crítico: fuera del rango crítico hacia un lado u otro.
        margen = rng.uniform(0.05, CLAMP_MARGIN)
        if rng.random() < 0.5:
            value = crit_min - margen
        else:
            value = crit_max + margen
        quality = QUALITY_UNCERTAIN
    elif r < PROB_SPIKE + PROB_DRIFT:
        # Drift: sale del óptimo, hasta 40% del rango crítico de exceso.
        max_drift = crit_width * DRIFT_REL
        if rng.random() < 0.5:
            value = opt_min - rng.uniform(0.05, max_drift)
        else:
            value = opt_max + rng.uniform(0.05, max_drift)
    else:
        # Normal: ruido alrededor del base.
        sigma = opt_width * NOISE_REL
        value = rng.gauss(base, sigma)

    # Clamp: nunca más de ±CLAMP_MARGIN fuera de los críticos.
    lo = crit_min - CLAMP_MARGIN
    hi = crit_max + CLAMP_MARGIN
    value = max(lo, min(hi, value))
    return round(value, 2), quality


def _ahora_utc() -> datetime:
    """Hora UTC actual sin tzinfo (la BD almacena timestamptz, la interpreta como UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def main() -> int:
    log.info("ph-data-generator iniciado — intervalo=%d s", INTERVAL_SECONDS)
    rng = random.Random()

    # Asegura el esquema una vez al arrancar (idempotente).
    try:
        from db import get_connection
        conn = get_connection()
        try:
            init_ph_tables(conn)
        finally:
            conn.close()
        log.info("Esquema pH inicializado.")
    except Exception as exc:
        log.error("No se pudo inicializar el esquema pH: %s", exc)
        return 1

    while _RUNNING:
        try:
            conn = get_connection()
            try:
                configs = get_ph_tag_configs(conn)
                if not configs:
                    log.warning("ph_tag_config está vacía — esperando siguiente ciclo.")
                else:
                    ts = _ahora_utc()
                    resumen = []
                    insertadas_total = 0
                    for cfg in configs:
                        val, q = generate_ph_value(cfg, rng)
                        ins = insert_ph_measurement(conn, cfg["tag_id"], val, q, ts=ts)
                        insertadas_total += ins
                        resumen.append(f"{cfg['tag_id']}={val:.2f}({q})")
                    log.info(
                        "ts=%s ins=%d/%d | %s",
                        ts.strftime("%Y-%m-%d %H:%M:%S"),
                        insertadas_total, len(configs),
                        " ".join(resumen),
                    )
            finally:
                conn.close()
        except Exception as exc:
            log.exception("Error en ciclo de generación: %s", exc)

        # Sleep partido para responder rápido a SIGTERM.
        restante = INTERVAL_SECONDS
        while _RUNNING and restante > 0:
            paso = min(5, restante)
            time.sleep(paso)
            restante -= paso

    log.info("ph-data-generator detenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
