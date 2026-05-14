"""Streamer en vivo de DQO: cada 15 min inserta 1 lectura por TAG.

Diseñado para correr como servicio docker (`python -m datos_dqo.streamer`).
- Calcula el próximo borde alineado a SLOT_MINUTOS y duerme hasta ahí.
- Genera 4 lecturas (una por TAG) con `timestamp = ese borde` usando la misma
  fórmula del generador histórico (carga_dia + modulación 24h + ruido).
- Inserta con `cargar()`, que es idempotente vía ON CONFLICT DO NOTHING.
- Reacciona a SIGINT/SIGTERM para apagado limpio.
"""

from __future__ import annotations

import logging
import os
import random
import signal
import sys
import time as _time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PARENT / ".env")
except ModuleNotFoundError:
    pass

from datos_dqo.cargador import cargar, verificar_db
from datos_dqo.generador import (
    Lectura, SLOT_MINUTOS, calc_valores, carga_slot, sample_carga_dia,
)

logging.basicConfig(
    level=os.getenv("DQO_STREAMER_LOG", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("dqo-streamer")

_RUNNING = True


def _stop(signum, _frame) -> None:
    global _RUNNING
    _RUNNING = False
    log.info("Señal %s recibida — cerrando…", signum)


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def _ahora_utc() -> datetime:
    """Hora UTC actual sin tzinfo (naive). La BD interpreta naive como UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _proximo_borde(ahora: datetime) -> datetime:
    """Próximo timestamp estrictamente futuro alineado a SLOT_MINUTOS."""
    minuto = (ahora.minute // SLOT_MINUTOS + 1) * SLOT_MINUTOS
    if minuto >= 60:
        return (ahora + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return ahora.replace(minute=minuto, second=0, microsecond=0)


def _dormir_hasta(objetivo: datetime) -> None:
    """Sleep en cortes de 5 s para responder rápido a SIGTERM."""
    while _RUNNING:
        restante = (objetivo - _ahora_utc()).total_seconds()
        if restante <= 0:
            return
        _time.sleep(min(5.0, restante))


def main() -> int:
    log.info("Streamer iniciado — slot = %d min", SLOT_MINUTOS)

    if not verificar_db():
        return 1
    log.info("Conexión a la base de datos OK.")

    rng = random.Random()  # entropía del SO (no determinista entre ejecuciones)
    carga_dia: float | None = None
    dia_actual: date | None = None

    while _RUNNING:
        objetivo = _proximo_borde(_ahora_utc())
        log.info("Próximo slot (UTC): %s", objetivo.strftime("%Y-%m-%d %H:%M"))
        _dormir_hasta(objetivo)
        if not _RUNNING:
            break

        if dia_actual != objetivo.date():
            dia_actual = objetivo.date()
            carga_dia = sample_carga_dia(rng)
            log.info("Nuevo día %s — carga_dia=%.3f", dia_actual, carga_dia)

        hora_decimal = objetivo.hour + objetivo.minute / 60.0
        c_slot = carga_slot(rng, carga_dia, hora_decimal)
        valores = calc_valores(rng, c_slot)
        lecturas = [Lectura(tag, objetivo, v) for tag, v in valores.items()]

        try:
            enviadas, insertadas = cargar(lecturas)
            resumen = ", ".join(f"{t}={v:.1f}" for t, v in valores.items())
            log.info(
                "Slot %s OK — c_slot=%.3f insertadas=%d/%d | %s",
                objetivo.strftime("%H:%M"), c_slot, insertadas, enviadas, resumen,
            )
        except Exception as exc:
            log.exception("Falló inserción del slot %s: %s", objetivo, exc)

    log.info("Streamer detenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
