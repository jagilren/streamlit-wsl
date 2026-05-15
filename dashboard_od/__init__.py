"""Módulo dashboard_OD — Monitoreo de Oxígeno Disuelto en 4 puntos del proceso PTAR.

TAGs: 100-DOT-01, 200-DOT-01, 450-DOT-01, 600-DOT-01

Ejecutar como app autónoma:
    streamlit run dashboard_od/dashboard_od.py --server.port 8504

Generador de datos (servicio Docker):
    python -m dashboard_od.data_generator
"""
