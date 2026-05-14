"""Constantes normativas y de presentación del dashboard de DQO."""

# ── Tabla y TAGs ──────────────────────────────────────────────────────────────
TABLA = "dqo"
TAG_ENTRADA = "DAF-ENTRADA"
TAG_CLARI1 = "CLARI1_OUT"
TAG_RAB = "RAB-SALIDA"
TAG_SALIDA = "DQO_Filtros"   # efluente final (referente normativo)

# Catálogo de TAGs conocidos. Para añadir/retirar un TAG basta con tocar este dict.
# rol:
#   "afluente"   → entrada del proceso. Único. Denominador en eficiencia.
#   "efluente"   → salida final. Único. Numerador en eficiencia, sujeto al límite normativo.
#   "intermedio" → etapa opcional, solo aporta a la tendencia y a la tabla como referencia.
TAG_CATALOG: dict[str, dict] = {
    TAG_ENTRADA: {
        "nombre": "DAF Entrada (afluente)",
        "rol": "afluente",
        "color": "#E24B4A",
    },
    TAG_CLARI1: {
        "nombre": "Clarificador 1 (intermedio)",
        "rol": "intermedio",
        "color": "#7C4DFF",
    },
    TAG_RAB: {
        "nombre": "RAB Salida (intermedio)",
        "rol": "intermedio",
        "color": "#FF9800",
    },
    TAG_SALIDA: {
        "nombre": "Filtros — pulimiento (efluente)",
        "rol": "efluente",
        "color": "#185FA5",
    },
}


def tags_por_rol(rol: str) -> list[str]:
    return [t for t, m in TAG_CATALOG.items() if m["rol"] == rol]

# ── Límites normativos (ajustables vía sidebar) ───────────────────────────────
LIMITE_DQO_EFLUENTE = 200.0   # mg/L — descarga máxima permitida
LIMITE_DQO_ALERTA = 160.0     # mg/L — umbral de alerta (80 % del límite)
META_EFICIENCIA = 90.0        # %   — meta mínima de remoción
PICO_DQO_AFLUENTE = 1800.0    # mg/L — pico de carga en entrada
RANGO_PH_MIN = 6.5
RANGO_PH_MAX = 8.5

# ── Paleta ────────────────────────────────────────────────────────────────────
COLOR_OK = "#639922"
COLOR_ALERTA = "#BA7517"
COLOR_CRITICO = "#E24B4A"
COLOR_ENTRADA = "#E24B4A"
COLOR_SALIDA = "#185FA5"
COLOR_LIMITE = "#E24B4A"
COLOR_BG_CARD = "#F0F2F6"
COLOR_NEUTRO = "#666666"

# ── Caché ─────────────────────────────────────────────────────────────────────
CACHE_TTL = 900   # 15 minutos — series temporales, distribuciones, cumplimientos
CACHE_TTL_LIVE = 60  # 1 minuto — KPIs "en vivo" (afluente / efluente actual)
# Intervalo de auto-refresh del dashboard (ms).
AUTOREFRESH_MS = 60_000
