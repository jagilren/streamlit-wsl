# Instrucciones para Claude Code — Módulo `dashboard_pH`
## Proyecto: PTAR Streamlit App

> **Propósito de este documento:** Guiar a Claude Code para implementar el módulo `dashboard_pH` dentro del proyecto Streamlit existente de la PTAR, el cual ya cuenta con el módulo `dashboard_dqo` funcionando. Leer este documento completo antes de escribir cualquier línea de código.

---

## 1. Contexto del proyecto existente

El proyecto es una aplicación Streamlit multi-dashboard para monitoreo de una Planta de Tratamiento de Aguas Residuales (PTAR). La infraestructura corre en Docker y usa TimescaleDB como base de datos de series de tiempo.

### Estructura actual del proyecto (referencia)

```
ptar_app/
├── app.py                        # Punto de entrada principal de Streamlit
├── config.py                     # Configuración global (dashboard por defecto, etc.)
├── db.py                         # Módulo de conexión y queries a TimescaleDB
├── docker-compose.yml            # Orquestación de servicios Docker
├── requirements.txt
├── dashboard_dqo/
│   ├── __init__.py
│   ├── view.py                   # Render del dashboard DQO
│   ├── queries.py                # Queries SQL específicas de DQO
│   ├── data_generator.py         # Generador de datos sintéticos DQO (servicio Docker)
│   └── components/               # Gráficas, tablas, widgets propios de DQO
│       ├── charts.py
│       └── sidebar_filters.py    # Filtros de TAGs específicos de DQO
└── dashboard_ph/                 # ← NUEVO MÓDULO A CREAR
    ├── __init__.py
    ├── view.py
    ├── queries.py
    ├── data_generator.py
    └── components/
        ├── charts.py
        └── sidebar_filters.py
```

### Principio fundamental de arquitectura

**Cada módulo de dashboard es autónomo.** Contiene sus propias queries, componentes visuales y filtros de sidebar. El `app.py` y el `db.py` son los únicos archivos verdaderamente compartidos. Respetar esta separación al 100%.

---

## 2. Base de datos — TimescaleDB

### Conexión

Usar **exactamente** el mismo `db.py` y las mismas credenciales que usa `dashboard_dqo`. No crear un nuevo módulo de conexión. Revisar `db.py` existente para obtener:
- La función `get_connection()` o similar
- El pool de conexiones si existe
- Las variables de entorno usadas (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`)

### Tablas necesarias en la base de datos

#### 2.1 Tabla de hechos — mediciones pH (hypertable TimescaleDB)

Crear esta tabla si no existe. Seguir el mismo patrón DDL que usa la tabla de hechos de DQO:
recuerda crear un Unique con TAG_ID y Timestamp

```sql
CREATE TABLE IF NOT EXISTS ph_measurements (
    Id          Autonumeric       NOT NULL,
    tag_id      VARCHAR(20)       NOT NULL,
    timestamp   TIMESTAMPTZ       NOT NULL,
    value       Numeric(10,2)     NOT NULL,
);

SELECT create_hypertable('ph_measurements', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_ph_tag_time ON ph_measurements (tag_id, time DESC);
```

#### 2.2 Tabla de configuración de rangos y límites por TAG

Esta tabla almacena los rangos óptimos y límites críticos de pH para cada transmisor. La aplicación debe leerla en tiempo de arranque (o con caché corto de 5 min) para construir las alertas.

```sql
CREATE TABLE IF NOT EXISTS ph_tag_config (
    tag_id          VARCHAR(20)      PRIMARY KEY,
    tag_description VARCHAR(100)     NOT NULL,
    process_point   VARCHAR(100)     NOT NULL,   -- Ej: 'Afluente bruto'
    opt_min         DOUBLE PRECISION NOT NULL,   -- Límite inferior rango óptimo
    opt_max         DOUBLE PRECISION NOT NULL,   -- Límite superior rango óptimo
    crit_min        DOUBLE PRECISION NOT NULL,   -- Límite inferior crítico (alarma)
    crit_max        DOUBLE PRECISION NOT NULL,   -- Límite superior crítico (alarma)
    unit            VARCHAR(10)      DEFAULT 'pH',
    active          BOOLEAN          DEFAULT TRUE,
    updated_at      TIMESTAMPTZ      DEFAULT NOW()
);
```

#### 2.3 Datos iniciales de configuración — INSERT de referencia

```sql
INSERT INTO ph_tag_config (tag_id, tag_description, process_point, opt_min, opt_max, crit_min, crit_max)
VALUES
    ('100-AIT-01', 'Transmisor pH Afluente Bruto',        'Afluente bruto',         6.5, 8.0, 5.5, 9.5),
    ('200-AIT-01', 'Transmisor pH Reactor Biológico',     'Reactor biológico',      6.8, 7.4, 6.0, 8.5),
    ('450-AIT-01', 'Transmisor pH Sedimentador Sec.',     'Sedimentador secundario', 6.5, 7.5, 5.5, 9.0),
    ('600-AIT-01', 'Transmisor pH Efluente Tratado',      'Efluente tratado',       6.0, 9.0, 5.0, 9.5)
ON CONFLICT (tag_id) DO NOTHING;
```

### Script de inicialización de DB

Crear `dashboard_ph/db_init.py` con una función `init_ph_tables()` que ejecute los DDL anteriores. Llamarla desde `app.py` al inicio, después de la inicialización de DQO, con manejo de excepciones que no rompa el arranque.

---

## 3. TAGs de pH

Los cuatro transmisores de pH de la PTAR son:

| TAG ID       | Punto de proceso          | Rango óptimo | Límite crítico |
|--------------|---------------------------|--------------|----------------|
| 100-AIT-01   | Afluente bruto            | 6.5 – 8.0   | 5.5 – 9.5     |
| 200-AIT-01   | Reactor biológico         | 6.8 – 7.4   | 6.0 – 8.5     |
| 450-AIT-01   | Sedimentador secundario   | 6.5 – 7.5   | 5.5 – 9.0     |
| 600-AIT-01   | Efluente tratado          | 6.0 – 9.0   | 5.0 – 9.5     |

---

## 4. Generador de datos sintéticos — `dashboard_ph/data_generator.py`

### Propósito

Script Python independiente (no es parte de la app Streamlit) que corre como servicio Docker y genera una medición de pH cada **3 minutos** para cada uno de los 4 TAGs. Seguir el mismo patrón del generador de datos de DQO.

### Comportamiento del generador

```python
"""
Lógica de generación por TAG:
- Valor base: punto medio del rango óptimo del TAG
- Ruido normal: desviación estándar = 15% del ancho del rango óptimo
- Drift ocasional (5% de probabilidad por lectura): el valor puede salir
  del rango óptimo hasta un 40% del ancho del rango crítico
- Spike de alarma (1% de probabilidad): valor fuera del rango crítico
- Clamp: el valor nunca supera ±0.5 fuera de los límites críticos
- Calidad OPC: 192 (Good) en condiciones normales, 64 (Uncertain) en spikes
"""
```

### Estructura del script

```python
import time
import logging
import random
import math
from datetime import datetime, timezone
# Importar get_connection desde db.py del proyecto raíz

INTERVAL_SECONDS = 180  # 3 minutos

def fetch_tag_configs(conn):
    """Lee ph_tag_config desde la DB para obtener rangos dinámicamente."""
    ...

def generate_ph_value(config: dict) -> tuple[float, int]:
    """Retorna (ph_value, quality_code) según la lógica de ruido definida."""
    ...

def insert_measurement(conn, tag_id: str, ph_value: float, quality: int):
    """INSERT en ph_measurements con timestamp UTC."""
    ...

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    while True:
        try:
            with get_connection() as conn:
                configs = fetch_tag_configs(conn)
                for cfg in configs:
                    val, quality = generate_ph_value(cfg)
                    insert_measurement(conn, cfg['tag_id'], val, quality)
                    logging.info(f"Insertado {cfg['tag_id']} pH={val:.3f} quality={quality}")
        except Exception as e:
            logging.error(f"Error en ciclo de generación: {e}")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
```

---

## 5. Docker Compose — servicio generador de pH

Agregar el siguiente servicio al `docker-compose.yml` existente. **No modificar ningún otro servicio existente, solo agregar este bloque:**

```yaml
  ph-data-generator:
    build:
      context: .
      dockerfile: Dockerfile          # Usar el mismo Dockerfile de la app si es compatible
                                      # Si no, crear Dockerfile.generator con python slim
    command: python dashboard_ph/data_generator.py
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
    depends_on:
      - timescaledb                   # Nombre exacto del servicio DB en el compose existente
    restart: on-failure
    networks:
      - ptar_network                  # Usar la misma red que los demás servicios
```

> **Nota:** Verificar el nombre exacto del servicio de TimescaleDB y el nombre de la red en el `docker-compose.yml` existente y ajustar `depends_on` y `networks` en consecuencia.

---

## 6. Queries SQL — `dashboard_ph/queries.py`

Implementar las siguientes funciones, usando el patrón de `dashboard_dqo/queries.py`:

```python
def get_ph_tag_configs(conn) -> list[dict]:
    """
    Lee ph_tag_config para los 4 TAGs activos.
    Retorna lista de dicts con keys: tag_id, tag_description, process_point,
    opt_min, opt_max, crit_min, crit_max, unit.
    Cache recomendado: 5 minutos (ver sección 9).
    """

def get_current_ph_values(conn) -> pd.DataFrame:
    """
    Última medición de cada TAG (DISTINCT ON tag_id ORDER BY time DESC).
    Columnas: tag_id, time, ph_value, quality.
    """

def get_ph_trend_24h(conn, tag_id: str) -> pd.DataFrame:
    """
    Mediciones de las últimas 24 horas para un TAG.
    Columnas: time, ph_value.
    Ordenadas ascendente por time.
    """

def get_ph_violations_rolling_week(conn, tag_id: str, tag_config: dict,
                                    max_records: int = 60) -> pd.DataFrame:
    """
    Registros de los últimos 7 días donde ph_value < opt_min OR ph_value > opt_max.
    Clasificar en la query o en Python:
      - 'Bajo crítico'  si ph_value < crit_min
      - 'Alto crítico'  si ph_value > crit_max
      - 'Bajo óptimo'   si opt_min > ph_value >= crit_min
      - 'Alto óptimo'   si opt_max < ph_value <= crit_max
    Columnas: time, ph_value, deviation, violation_type, severity (warn|crit).
    Ordenar: time DESC. Limitar a max_records.
    """

def get_ph_daily_stats(conn, tag_id: str, days: int = 7) -> pd.DataFrame:
    """
    Estadísticas diarias: min, max, avg, count por día por TAG.
    Usar time_bucket('1 day', time) de TimescaleDB.
    """
```

---

## 7. Componentes visuales — `dashboard_ph/components/charts.py`

Usar **Plotly** para todas las gráficas (mismo framework que `dashboard_dqo`). Implementar:

### 7.1 `render_ph_trend_chart(df, tag_config, height=220)`

Gráfica de línea de tendencia 24h para un TAG individual:
- Serie principal: línea del pH medido, coloreada según estado (azul=normal, naranja=advertencia, rojo=crítico en el punto actual)
- Banda de área sombreada verde semitransparente entre `opt_min` y `opt_max`
- Líneas horizontales discontinuas rojas para `crit_min` y `crit_max`
- Líneas horizontales sólidas verdes para `opt_min` y `opt_max`
- Eje Y: rango `[crit_min - 1, crit_max + 1]`, título "pH"
- Eje X: formato hora `HH:MM`
- Layout compacto, sin leyenda interna (la leyenda va en el componente padre)
- `margin=dict(l=40, r=10, t=10, b=30)`

### 7.2 `render_violations_table(df_violations, tag_config)`

Tabla de eventos fuera de rango (semana móvil):
- Mostrar columnas: `Fecha/Hora`, `pH`, `Desviación`, `Tipo`
- Colorear filas: rojo claro para `severity='crit'`, amarillo claro para `severity='warn'`
- Máximo 60 registros, 5 filas visibles, scroll vertical
- Implementar con `st.dataframe()` usando `height=170` y `use_container_width=True`
- Si no hay registros, mostrar `st.success("Sin eventos fuera de rango en los últimos 7 días")`
- Encabezado de la tabla con contador: `f"{n} evento(s) — {n_crit} crítico(s), {n_warn} advertencia(s)"`

### 7.3 `render_ph_kpi_card(tag_id, current_value, tag_config)`

Card de valor actual por TAG. Retorna HTML string para usar con `st.markdown(..., unsafe_allow_html=True)`:
- Valor grande (28px) coloreado según estado
- Badge de estado: "Normal" (verde), "Advertencia" (naranja), "⚠ Alerta Crítica" (rojo)
- Rango óptimo y crítico en texto pequeño al pie
- Barra vertical de color a la izquierda (identificador visual del TAG)

---

## 8. Vista principal — `dashboard_ph/view.py`

### Estructura del render

```python
def render(conn, time_filter: dict):
    """
    Parámetro time_filter: dict con keys 'start' y 'end' (datetime objects)
    que viene del sidebar compartido del app.py. Ver sección 10.
    """

    # 1. Cargar configuración de TAGs (cacheado)
    tag_configs = get_cached_ph_tag_configs(conn)  # ver sección 9

    # 2. Cargar valores actuales (cacheado corto TTL)
    df_current = get_cached_current_ph(conn)

    # 3. Fila de KPI CARDS — una por TAG en 4 columnas
    cols = st.columns(4)
    for i, cfg in enumerate(tag_configs):
        current_val = df_current.loc[df_current.tag_id == cfg['tag_id'], 'ph_value'].values
        val = float(current_val[0]) if len(current_val) else None
        with cols[i]:
            st.markdown(render_ph_kpi_card(cfg['tag_id'], val, cfg),
                        unsafe_allow_html=True)

    st.markdown("---")

    # 4. Grid 2x2 de gráficas + tablas — una por TAG
    for row in [[0, 1], [2, 3]]:
        cols = st.columns(2)
        for col_idx, tag_idx in enumerate(row):
            cfg = tag_configs[tag_idx]
            with cols[col_idx]:
                # Header del panel
                status_badge = compute_status_badge(df_current, cfg)
                st.markdown(f"**{cfg['tag_id']} — {cfg['process_point']}** {status_badge}",
                             unsafe_allow_html=True)
                st.caption(f"Óptimo: {cfg['opt_min']}–{cfg['opt_max']} | "
                           f"Crítico: {cfg['crit_min']}–{cfg['crit_max']}")

                # Gráfica de tendencia 24h
                df_trend = get_cached_ph_trend(conn, cfg['tag_id'])
                fig = render_ph_trend_chart(df_trend, cfg)
                st.plotly_chart(fig, use_container_width=True, key=f"ph_chart_{cfg['tag_id']}")

                # Tabla de violaciones semana móvil
                df_viol = get_cached_ph_violations(conn, cfg['tag_id'], cfg)
                render_violations_table(df_viol, cfg)
```

---

## 9. Estrategia de caché — `dashboard_ph/cache.py`

Crear `dashboard_ph/cache.py` con funciones cacheadas usando `@st.cache_data`. Seguir el mismo patrón que `dashboard_dqo` si ya tiene caché implementado.

```python
import streamlit as st

@st.cache_data(ttl=300, show_spinner=False)   # 5 min — configuración de TAGs
def get_cached_ph_tag_configs(_conn):
    return get_ph_tag_configs(_conn)

@st.cache_data(ttl=30, show_spinner=False)    # 30 seg — valores actuales (KPI cards)
def get_cached_current_ph(_conn):
    return get_current_ph_values(_conn)

@st.cache_data(ttl=60, show_spinner=False)    # 1 min — tendencia 24h por TAG
def get_cached_ph_trend(_conn, tag_id: str):
    return get_ph_trend_24h(_conn, tag_id)

@st.cache_data(ttl=120, show_spinner=False)   # 2 min — violaciones semana móvil
def get_cached_ph_violations(_conn, tag_id: str, tag_config: dict):
    return get_ph_violations_rolling_week(_conn, tag_id, tag_config)
```

**Regla crítica:** El parámetro `conn` (conexión SQLAlchemy o psycopg2) debe recibirse con prefijo `_` (`_conn`) para que Streamlit no intente hashearlo y evitar errores de serialización.

### Invalidación de caché al cambiar de dashboard

En `app.py`, cuando el usuario cambia entre dashboards, NO invalidar el caché. Los datos en caché de DQO deben seguir disponibles cuando el usuario regrese a ese dashboard. La estrategia de TTL corto es suficiente.

---

## 10. Navegación multi-dashboard — modificaciones a `app.py`

### 10.1 Configuración del dashboard por defecto

En `config.py`, agregar o modificar:

```python
# Dashboard que se muestra al abrir la app por primera vez
DEFAULT_DASHBOARD = "dqo"   # Opciones: "dqo", "ph"

# Registro de todos los dashboards disponibles (orden = orden en sidebar)
DASHBOARDS = [
    {"key": "dqo", "label": "📊 DQO Dashboard",  "module": "dashboard_dqo"},
    {"key": "ph",  "label": "🧪 pH Dashboard",   "module": "dashboard_ph"},
]
```

El valor de `DEFAULT_DASHBOARD` puede cambiarse sin tocar el código de la app. En el futuro, simplemente agregar un nuevo dict a `DASHBOARDS`.

### 10.2 Lógica de selección en `app.py`

```python
# Inicializar estado de sesión con el dashboard por defecto
if "active_dashboard" not in st.session_state:
    st.session_state.active_dashboard = config.DEFAULT_DASHBOARD

# Sidebar — botones de navegación
with st.sidebar:
    st.markdown("### 🏭 PTAR — Dashboards")
    for dash in config.DASHBOARDS:
        if st.sidebar.button(dash["label"],
                             key=f"nav_{dash['key']}",
                             use_container_width=True,
                             type="primary" if st.session_state.active_dashboard == dash["key"]
                                  else "secondary"):
            st.session_state.active_dashboard = dash["key"]

    st.markdown("---")

    # Filtros de tiempo compartidos (aplican a todos los dashboards)
    st.markdown("#### Filtro de tiempo")
    time_filter = render_shared_time_filter()   # ver 10.3

    st.markdown("---")

    # Filtros específicos del dashboard activo — renderizado condicional
    active = st.session_state.active_dashboard
    if active == "dqo":
        from dashboard_dqo.components.sidebar_filters import render_dqo_sidebar_filters
        render_dqo_sidebar_filters()
    elif active == "ph":
        from dashboard_ph.components.sidebar_filters import render_ph_sidebar_filters
        render_ph_sidebar_filters()
    # Futuros dashboards: agregar elif aquí

# Render del dashboard activo
conn = db.get_connection()
if st.session_state.active_dashboard == "dqo":
    from dashboard_dqo.view import render as render_dqo
    render_dqo(conn, time_filter)
elif st.session_state.active_dashboard == "ph":
    from dashboard_ph.view import render as render_ph
    render_ph(conn, time_filter)
```

### 10.3 Filtro de tiempo compartido

Extraer el filtro de tiempo de `dashboard_dqo` a un componente compartido `components/shared_time_filter.py` en la raíz del proyecto (si no existe ya):

```python
# components/shared_time_filter.py
import streamlit as st
from datetime import datetime, timedelta

def render_shared_time_filter() -> dict:
    """
    Renderiza el selector de rango de tiempo en el sidebar.
    Retorna dict con keys 'start' (datetime) y 'end' (datetime).
    Opciones:  Últimas 24h / Últimos 7 días / Últimos 30 días / Rango personalizado
    """
    options = ["Últimas 24h", "Últimos 7 días", "Últimos 30 días", "Personalizado"]
    selected = st.selectbox("Período", options,
                            key="shared_time_range",
                            index=0)
    now = datetime.now()
    if selected == "Últimas 24h":
        return {"start": now - timedelta(hours=24), "end": now}
    elif selected == "Últimos 7 días":
        return {"start": now - timedelta(days=7), "end": now}
    elif selected == "Últimos 30 días":
        return {"start": now - timedelta(days=30), "end": now}
    else:
        start = st.date_input("Desde", value=now.date() - timedelta(days=7), key="custom_start")
        end   = st.date_input("Hasta", value=now.date(), key="custom_end")
        return {"start": datetime.combine(start, datetime.min.time()),
                "end":   datetime.combine(end,   datetime.max.time())}
```

> **Importante:** Si `dashboard_dqo` ya tiene un filtro de tiempo en su propio sidebar, refactorizarlo para que use este componente compartido. El comportamiento visual debe ser idéntico al actual.

---

## 11. Filtros específicos del dashboard pH — `dashboard_ph/components/sidebar_filters.py`

En esta primera versión el dashboard de pH **no requiere filtros adicionales** en el sidebar (no hay selección/deselección de TAGs equivalente a DQO, ya que los 4 transmisores siempre se muestran). Sin embargo, crear el archivo con la función vacía para mantener la consistencia arquitectónica:

```python
# dashboard_ph/components/sidebar_filters.py
import streamlit as st

def render_ph_sidebar_filters():
    """
    Filtros específicos del dashboard pH en el sidebar.
    Por ahora no hay filtros adicionales para pH.
    Reservado para futuras versiones.
    """
    pass
```

La función se llama condicionalmente desde `app.py` solo cuando el dashboard activo es "ph", por lo que cuando el usuario está en DQO, los filtros de TAGs de DQO aparecen normalmente; cuando cambia a pH, esa sección del sidebar queda vacía.

---

## 12. Alertas visuales — lógica de estado

Implementar en `dashboard_ph/utils.py`:

```python
def compute_ph_status(ph_value: float, cfg: dict) -> str:
    """
    Retorna: 'critical_high' | 'critical_low' | 'warn_high' | 'warn_low' | 'ok'
    """
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

STATUS_CONFIG = {
    "ok":            {"label": "Normal",           "color": "#1D9E75", "badge_bg": "#E1F5EE"},
    "warn_high":     {"label": "⚠ Alto óptimo",    "color": "#BA7517", "badge_bg": "#FAEEDA"},
    "warn_low":      {"label": "⚠ Bajo óptimo",    "color": "#BA7517", "badge_bg": "#FAEEDA"},
    "critical_high": {"label": "🚨 Alto crítico",   "color": "#A32D2D", "badge_bg": "#FCEBEB"},
    "critical_low":  {"label": "🚨 Bajo crítico",   "color": "#A32D2D", "badge_bg": "#FCEBEB"},
    "no_data":       {"label": "Sin datos",         "color": "#888780", "badge_bg": "#F1EFE8"},
}
```

---

## 13. Archivo `__init__.py` del módulo

```python
# dashboard_ph/__init__.py
"""
Módulo dashboard_pH — Monitoreo de pH en 4 puntos del proceso PTAR.
TAGs: 100-AIT-01, 200-AIT-01, 450-AIT-01, 600-AIT-01
"""
```

---

## 14. Dependencias Python

Verificar que estén en `requirements.txt`. Agregar solo las que falten (no duplicar):

```
plotly>=5.18.0
pandas>=2.0.0
psycopg2-binary>=2.9.0
sqlalchemy>=2.0.0
streamlit>=1.32.0
```

---

## 15. Checklist de implementación para Claude Code

Completar en este orden:

- [ ] Leer `db.py`, `app.py` y `dashboard_dqo/view.py` completos antes de escribir código
- [ ] Leer `docker-compose.yml` para identificar nombre del servicio DB y red
- [ ] Crear `dashboard_ph/__init__.py`
- [ ] Crear `dashboard_ph/db_init.py` con DDL de tablas
- [ ] Crear `dashboard_ph/queries.py` con las 5 funciones documentadas
- [ ] Crear `dashboard_ph/cache.py` con funciones `@st.cache_data`
- [ ] Crear `dashboard_ph/data_generator.py` siguiendo el patrón de DQO
- [ ] Crear `dashboard_ph/utils.py` con `compute_ph_status` y `STATUS_CONFIG`
- [ ] Crear `dashboard_ph/components/__init__.py`
- [ ] Crear `dashboard_ph/components/charts.py` con las 3 funciones de render
- [ ] Crear `dashboard_ph/components/sidebar_filters.py` (función vacía)
- [ ] Crear `dashboard_ph/view.py` con función `render(conn, time_filter)`
- [ ] Crear/verificar `components/shared_time_filter.py` en raíz del proyecto
- [ ] Refactorizar `app.py`: navegación multi-dashboard, filtros condicionales, DEFAULT_DASHBOARD
- [ ] Refactorizar `config.py`: agregar `DEFAULT_DASHBOARD` y `DASHBOARDS`
- [ ] Agregar servicio `ph-data-generator` en `docker-compose.yml`
- [ ] Ejecutar DDL de inicialización y verificar tablas en TimescaleDB
- [ ] Verificar que el filtro de tiempo de DQO sigue funcionando igual que antes

---

## 16. Restricciones y reglas importantes

1. **No romper DQO.** Cualquier modificación a `app.py` o `db.py` debe ser retrocompatible. Verificar que el dashboard DQO funciona exactamente igual que antes de cerrar la tarea.

2. **No duplicar código de conexión.** Usar siempre el `db.py` existente para conectar a TimescaleDB.

3. **No hardcodear rangos de pH en el código Python.** Los rangos siempre deben leerse de `ph_tag_config` en la base de datos.

4. **No mostrar filtros de DQO cuando el dashboard activo es pH.** La selección condicional en el sidebar de `app.py` es la única lógica para controlar esto.

5. **Los filtros de tiempo son compartidos.** El mismo `time_filter` dict se pasa como parámetro a `render()` en todos los dashboards. No replicar la lógica de selección de fechas dentro de `dashboard_ph/view.py`.

6. **Prefijo `_` en parámetros de funciones cacheadas** que reciban objetos no serializables (conexiones, engines). Obligatorio para evitar errores de Streamlit.

7. **Formato de timestamps:** Siempre usar UTC al insertar en TimescaleDB. Convertir a hora local solo en la capa de presentación (Streamlit).
