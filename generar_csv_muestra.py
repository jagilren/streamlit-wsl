"""
Genera datos_ptar.csv (PLC – pH) y datos_laboratorio.csv (Lab – DQO).
Ambos en formato LARGO:  TimeStamp, TAG, Value

Ejecutar una sola vez para tener CSVs de prueba; luego reemplazar con datos reales.
"""
import numpy as np
import pandas as pd
from config import CSV_PATH, CSV_PATH_LAB

np.random.seed(42)

# ── PH_SERP_DAF: 1 lectura/hora, primer dato a las 00:10 de cada día ─────────
fechas_daf = pd.date_range("2020-05-01 00:10", "2026-04-30 23:10", freq="1h")
n_daf = len(fechas_daf)
rows_daf = [
    {"TimeStamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "TAG": "PH_SERP_DAF", "Value": v}
    for ts, v in zip(
        fechas_daf,
        np.clip(np.random.normal(8.5, 0.5, n_daf), 6.0, 11.0).round(2),
    )
]

# ── PH_VERTIMIENTO: 1 lectura cada 30 s → 2 880 datos/día ────────────────────
fechas_vert = pd.date_range("2020-05-01 00:00:00", "2026-04-30 23:59:30", freq="30s")
n_vert = len(fechas_vert)
rows_vert = [
    {"TimeStamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "TAG": "PH_VERTIMIENTO", "Value": v}
    for ts, v in zip(
        fechas_vert,
        np.clip(np.random.normal(7.2, 0.4, n_vert), 5.5, 9.0).round(2),
    )
]

df_plc = pd.concat([pd.DataFrame(rows_daf), pd.DataFrame(rows_vert)], ignore_index=True)
df_plc.sort_values("TimeStamp", inplace=True)
df_plc.to_csv(CSV_PATH, index=False)
print(f"CSV PLC generado:  {CSV_PATH}  ({len(df_plc):,} filas, formato largo)")
print(f"  PH_SERP_DAF   : {n_daf:,} filas  (1/hora, inicio 00:10)")
print(f"  PH_VERTIMIENTO: {n_vert:,} filas  (1/30 s, 2 880/día)")

# ── CSV Laboratorio: DQO, formato ESTRECHO, 4 días aleatorios por semana ─────
_todas = pd.date_range("2020-01-01", "2026-04-30", freq="D")
_rng   = np.random.default_rng(seed=99)
_dias_sel = []
for _, grp in pd.DataFrame({"fecha": _todas}).groupby(_todas.to_period("W")):
    idx = _rng.choice(len(grp), size=min(4, len(grp)), replace=False)
    _dias_sel.extend(grp["fecha"].iloc[sorted(idx)].tolist())

fechas_dqo = pd.DatetimeIndex(sorted(_dias_sel))
n_dqo = len(fechas_dqo)

rows_dqo = []
for ts, dqo_r, dqo_v in zip(
    fechas_dqo,
    np.clip(np.random.normal(700, 160, n_dqo), 400, 1050).round(1),
    np.clip(np.random.normal(400, 140, n_dqo), 180,  780).round(1),
):
    rows_dqo.append({"TimeStamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "TAG": "DQO_REACTOR_BIO", "Value": dqo_r})
    rows_dqo.append({"TimeStamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "TAG": "DQO_VERTIMIENTO", "Value": dqo_v})

df_lab = pd.DataFrame(rows_dqo)
df_lab.to_csv(CSV_PATH_LAB, index=False)
print(f"CSV Lab generado:  {CSV_PATH_LAB}  ({len(df_lab):,} filas, formato estrecho)")
