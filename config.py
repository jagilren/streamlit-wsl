CSV_PATH     = "datos_ptar.csv"        # CSV del PLC  (pH)
CSV_PATH_LAB = "datos_laboratorio.csv" # CSV de laboratorio (DQO)

# Diccionario de TAGs conocidos con su configuración completa.
# Edita las claves (nombres de TAG) para que coincidan con tu SCADA/historian.
# TAGs presentes en el CSV pero ausentes aquí aparecerán en la tab
# de Configuración y el operario podrá asignarlos manualmente.
TAG_MAP = {
    "PH_SERP_DAF": {
        "nombre": "Serpentín DAF",
        "tipo":   "pH",
        "color":  "#00ACC1",
        "limite": None,
        "norma":  None,
        "bg_exc": "#E0F7FA",
    },
    "PH_VERTIMIENTO": {
        "nombre": "Vertimiento",
        "tipo":   "pH",
        "color":  "#43A047",
        "limite": None,
        "norma":  None,
        "bg_exc": "#E8F5E9",
    },
    "DQO_REACTOR_BIO": {
        "nombre": "Reactor Biológico",
        "tipo":   "DQO",
        "color":  "#7C4DFF",
        "limite": None,
        "norma":  None,
        "bg_exc": "#EDE7F6",
    },
    "DQO_VERTIMIENTO": {
        "nombre": "Vertimiento",
        "tipo":   "DQO",
        "color":  "#FF5722",
        "limite": 700.0,
        "norma":  "Res. 0631/2015",
        "bg_exc": "#FFCDD2",
    },
}
