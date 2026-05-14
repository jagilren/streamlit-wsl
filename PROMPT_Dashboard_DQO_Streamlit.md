# PROMPT COMPLETO — Dashboard DQO PTAR en Streamlit
## Para usar en GitHub Copilot Chat, Cursor AI o cualquier asistente de código en VS Code

---

## INSTRUCCIÓN PRINCIPAL

Crea una aplicación Streamlit completa en Python llamada `dashboard_dqo.py` que genere un dashboard profesional de control de DQO (Demanda Química de Oxígeno) para el Gerente Ambiental de una Planta de Tratamiento de Aguas Residuales (PTAR). La aplicación debe ser production-ready, con manejo de errores, caché de datos, y visualizaciones interactivas con Plotly.

---

## 1. ESTRUCTURA DE BASE DE DATOS

La tabla de datos se llama `DQO` y tiene formato **despivoteado (narrow/long)**:

```sql
-- Estructura de la tabla
CREATE TABLE DQO (
    ID          BIGINT PRIMARY KEY,
    TAG_ID      VARCHAR(50),    -- Identificador del sensor/punto de medición
    TimeStamp   DATETIME,       -- Fecha y hora del registro
    Valor       FLOAT           -- Valor medido en mg/L
);

-- TAGs relevantes para este dashboard:
-- 'DAF-ENTRADA'  → DQO Afluente (entrada a la planta)
-- 'RAB-SALIDA'   → DQO Efluente (salida tratada)
```

**Importante:** la tabla puede tener más de 10 millones de registros. Todas las queries deben filtrar siempre por `TAG_ID` y por rango de fechas antes de traer datos. Nunca hacer `SELECT *` sin filtros.

---

## 2. CONEXIÓN A BASE DE DATOS

Usar **SQLAlchemy** con soporte para múltiples motores. Leer las credenciales desde variables de entorno (archivo `.env`). Crear la función de conexión así:

```python
# Variables de entorno requeridas en .env:
# DB_ENGINE=mssql+pyodbc   (o postgresql, mysql, sqlite)
# DB_SERVER=localhost
# DB_NAME=PTAR_DB
# DB_USER=sa
# DB_PASSWORD=tu_password
# DB_DRIVER=ODBC+Driver+17+for+SQL+Server   (solo para SQL Server)
```

La función de conexión debe:
- Usar `python-dotenv` para cargar el `.env`
- Construir la connection string según el motor configurado
- Retornar un engine de SQLAlchemy
- Manejar errores de conexión con try/except y mostrar `st.error()` con mensaje claro
- Usar `@st.cache_resource` para que la conexión persista entre reruns de Streamlit

---

## 3. CONSTANTES NORMATIVAS

Definir al inicio del archivo como constantes globales:

```python
# Límites normativos (ajustables según regulación local)
LIMITE_DQO_EFLUENTE   = 200.0   # mg/L — límite máximo permitido en descarga
META_EFICIENCIA       = 90.0    # % — eficiencia mínima de remoción requerida
LIMITE_DQO_ALERTA     = 160.0   # mg/L — umbral de alerta (80% del límite)
PICO_DQO_AFLUENTE     = 1800.0  # mg/L — umbral de pico de carga en entrada
RANGO_PH_MIN          = 6.5
RANGO_PH_MAX          = 8.5

# Colores del dashboard (paleta profesional)
COLOR_OK     = "#639922"   # Verde
COLOR_ALERTA = "#BA7517"   # Ámbar
COLOR_CRITICO= "#E24B4A"   # Rojo
COLOR_ENTRADA= "#E24B4A"   # Rojo para DQO entrada
COLOR_SALIDA = "#185FA5"   # Azul para DQO salida
COLOR_LIMITE = "#E24B4A"   # Línea de límite normativo
COLOR_BG_CARD= "#F8F8F8"   # Fondo de tarjetas KPI
```

---

## 4. QUERIES SQL — FUNCIONES DE DATOS

Crear las siguientes funciones de acceso a datos, todas con `@st.cache_data(ttl=900)` (caché de 15 minutos):

### 4.1 Query principal — serie temporal DQO entrada y salida
```python
def get_dqo_serie_temporal(engine, fecha_inicio, fecha_fin):
    """
    Devuelve DataFrame con columnas: TimeStamp, DQO_Entrada, DQO_Salida
    Pivotea en Python los registros de TAG_ID DAF-ENTRADA y RAB-SALIDA.
    Agrupa por hora usando AVG para reducir volumen de datos al gráfico.
    """
    query = """
        SELECT 
            DATEADD(HOUR, DATEDIFF(HOUR, 0, TimeStamp), 0) AS TimeStamp,
            TAG_ID,
            AVG(Valor) AS Valor
        FROM DQO
        WHERE TAG_ID IN ('DAF-ENTRADA', 'RAB-SALIDA')
          AND TimeStamp BETWEEN :fecha_inicio AND :fecha_fin
          AND Valor IS NOT NULL
          AND Valor > 0
        GROUP BY 
            DATEADD(HOUR, DATEDIFF(HOUR, 0, TimeStamp), 0),
            TAG_ID
        ORDER BY TimeStamp
    """
    # Después de ejecutar el query, pivotar:
    # df.pivot(index='TimeStamp', columns='TAG_ID', values='Valor')
    # Renombrar columnas: 'DAF-ENTRADA' → 'DQO_Entrada', 'RAB-SALIDA' → 'DQO_Salida'
```

### 4.2 KPI actual — último valor disponible
```python
def get_kpi_actual(engine, horas_atras=24):
    """
    Devuelve dict con:
    - dqo_efluente_actual: promedio últimas N horas de RAB-SALIDA
    - dqo_afluente_actual: promedio últimas N horas de DAF-ENTRADA  
    - eficiencia_remocion: (1 - salida/entrada) * 100
    - fecha_ultimo_registro: timestamp más reciente
    """
```

### 4.3 Días de cumplimiento normativo en el período
```python
def get_dias_cumplimiento(engine, fecha_inicio, fecha_fin):
    """
    Agrupa RAB-SALIDA por día, calcula AVG diario.
    Retorna:
    - dias_cumplimiento: días donde AVG diario <= LIMITE_DQO_EFLUENTE
    - dias_total: total de días con datos
    - pct_cumplimiento: porcentaje
    - df_diario: DataFrame con columnas Fecha, DQO_Salida_Avg, Cumple (bool)
    """
```

### 4.4 Histograma de distribución DQO salida
```python
def get_distribucion_dqo_salida(engine, fecha_inicio, fecha_fin):
    """
    Trae todos los valores de RAB-SALIDA en el período.
    Retorna Serie de pandas con los valores para graficar histograma.
    Bins recomendados: cada 20 mg/L desde 0 hasta LIMITE_DQO_EFLUENTE + 100
    """
```

### 4.5 Comparativo mensual (últimos 12 meses)
```python
def get_comparativo_mensual(engine):
    """
    Agrupa RAB-SALIDA por mes, devuelve DataFrame con:
    - Mes (período YYYY-MM)
    - DQO_Salida_Avg (promedio mensual)
    - DQO_Entrada_Avg
    - Eficiencia_Pct
    Últimos 12 meses desde hoy hacia atrás.
    """
```

### 4.6 Detección de alarmas activas
```python
def get_alarmas_activas(engine, horas_atras=48):
    """
    Detecta eventos anómalos en las últimas N horas:
    1. Picos de DQO entrada > PICO_DQO_AFLUENTE mg/L
    2. DQO salida promedio horario > LIMITE_DQO_ALERTA mg/L
    3. Eficiencia horaria < META_EFICIENCIA - 5 %
    Devuelve lista de dicts: {tipo, descripcion, valor, timestamp, severidad}
    severidad: 'critico' | 'alerta'
    """
```

---

## 5. LAYOUT Y ESTRUCTURA DE LA APP STREAMLIT

### 5.1 Configuración de página

```python
st.set_page_config(
    page_title="Dashboard DQO — PTAR",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)
```

### 5.2 CSS personalizado

Inyectar con `st.markdown(..., unsafe_allow_html=True)` el siguiente CSS:

```css
/* Tarjetas KPI */
.kpi-card {
    background: #f0f2f6;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    border-left: 4px solid {color};  /* color dinámico según estado */
}
.kpi-label { font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-value { font-size: 28px; font-weight: 600; margin: 4px 0; }
.kpi-sub   { font-size: 12px; }

/* Semáforo */
.estado-ok     { color: #639922; }
.estado-alerta { color: #BA7517; }
.estado-critico{ color: #E24B4A; }

/* Título del dashboard */
.dash-header { border-bottom: 2px solid #185FA5; padding-bottom: 8px; margin-bottom: 1rem; }

/* Panel de alarmas */
.alarma-critica { background: #FCEBEB; border-left: 4px solid #E24B4A; 
                  border-radius: 6px; padding: 8px 12px; margin: 4px 0; }
.alarma-alerta  { background: #FAEEDA; border-left: 4px solid #BA7517;
                  border-radius: 6px; padding: 8px 12px; margin: 4px 0; }
```

### 5.3 Sidebar — filtros y slicers

```
SIDEBAR contiene:
├── Logo / título "Control DQO — PTAR"
├── Separador
├── [Selectbox] Período de análisis:
│   ├── "Hoy"
│   ├── "Esta semana"
│   ├── "Este mes"        ← default
│   ├── "Últimos 90 días"
│   └── "Este año"
├── [Date input] Fecha inicio (editable, pre-cargado según período)
├── [Date input] Fecha fin   (editable, pre-cargado según período)
├── Separador
├── [Multiselect] Puntos de muestreo:
│   ├── ✅ DAF-ENTRADA
│   └── ✅ RAB-SALIDA
├── Separador
├── [Number input] Límite DQO efluente (mg/L): default 200
├── [Number input] Meta eficiencia (%):        default 90
├── Separador
├── [Button] 🔄 Actualizar datos   ← fuerza limpieza del caché
└── Texto: "Datos actualizados: {timestamp}"
```

### 5.4 Cuerpo principal — 5 zonas de contenido

---

#### ZONA 1 — Encabezado

```
Row completo:
├── Título: "Dashboard DQO — Gerencia Ambiental PTAR"
├── Subtítulo: "Actualización automática cada 15 min · Período: {fecha_inicio} al {fecha_fin}"
└── [derecha] Indicador de estado general: 🟢 Cumplimiento Normal / 🟡 En Alerta / 🔴 Excedencia
```

---

#### ZONA 2 — KPIs ejecutivos (4 columnas iguales)

Cada KPI usa la función `render_kpi_card(label, valor, unidad, meta, estado)`:

```
col1: DQO Efluente Actual
      valor = dqo_efluente_actual (mg/L)
      estado = OK si <= 160, ALERTA si <= 200, CRITICO si > 200
      sub = "Límite: 200 mg/L"
      borde izquierdo color según estado

col2: Eficiencia de Remoción
      valor = eficiencia_remocion (%)
      estado = OK si >= 90%, ALERTA si >= 80%, CRITICO si < 80%
      sub = "Meta: ≥ 90%"
      mostrar flecha ↑↓ vs mes anterior si hay datos

col3: DQO Afluente Actual
      valor = dqo_afluente_actual (mg/L)
      estado = neutro (siempre gris, es dato externo)
      sub = "Carga de entrada"
      mostrar variación % vs período anterior

col4: Cumplimiento Normativo
      valor = pct_cumplimiento (%)
      estado = OK si 100%, ALERTA si >= 95%, CRITICO si < 95%
      sub = "{dias_cumplimiento} de {dias_total} días"
```

---

#### ZONA 3 — Gráfico tendencia + Gauge (2 columnas: 70% / 30%)

**Columna izquierda (70%) — Gráfico de líneas DQO entrada vs salida:**

Usar `plotly.graph_objects`. Especificaciones:
- Dos trazas de línea: DQO Entrada (color rojo `#E24B4A`, línea continua) y DQO Salida (color azul `#185FA5`, línea continua)
- Línea horizontal de límite normativo (dashed roja, `LIMITE_DQO_EFLUENTE`) con anotación "Límite 200 mg/L"
- Línea horizontal de alerta (dashed ámbar, `LIMITE_DQO_ALERTA`) con anotación "Alerta 160 mg/L"
- Área sombreada bajo DQO Salida (fillcolor azul con opacidad 0.1)
- Eje X: fecha/hora con formato legible
- Eje Y: "DQO (mg/L)", rango automático con margen superior de 20%
- Hover con ambos valores en el mismo tooltip
- Rangeslider opcional en el eje X para zoom
- Título: "Tendencia DQO Afluente vs Efluente"
- Fondo: blanco, grid gris claro
- Legend posición: arriba derecha dentro del gráfico
- `use_container_width=True`

**Columna derecha (30%) — Gauge de eficiencia:**

Usar `plotly.graph_objects.Indicator` tipo gauge:
- Valor: `eficiencia_remocion`
- Rango: 0 a 100%
- Pasos de color:
  - 0–80%: rojo `#FCEBEB`
  - 80–90%: ámbar `#FAEEDA`
  - 90–100%: verde `#EAF3DE`
- Umbral (threshold): línea en 90% (meta)
- Número grande: `{eficiencia:.1f}%`
- Título: "Eficiencia de Remoción"
- Debajo del gauge: 3 métricas en tabla:
  - Promedio período / Mínimo semanal / Promedio anual

---

#### ZONA 4 — Tres paneles (3 columnas iguales)

**Columna 1 — Cumplimiento normativo (tabla semáforo):**

`st.dataframe` o HTML con los parámetros de control:
```
Parámetro      | Límite       | Valor actual  | Estado
DQO efluente   | 200 mg/L     | {valor}       | 🟢/🟡/🔴
Eficiencia     | ≥ 90%        | {valor}       | 🟢/🟡/🔴
DQO afluente   | Referencia   | {valor}       | —
pH             | 6.5–8.5      | (si hay dato) | 🟢/🟡/🔴
Temperatura    | ≤ 35°C       | (si hay dato) | 🟢/🟡/🔴
```
Si no hay datos de pH o temperatura en la tabla DQO, mostrar "Sin dato" con color gris.

**Columna 2 — Barras DQO promedio por mes (últimos 6 meses):**

`plotly.graph_objects.Bar` horizontal o vertical:
- Barras de DQO Salida promedio mensual
- Color de cada barra según estado: verde si ≤ 160, ámbar si ≤ 200, rojo si > 200
- Línea vertical/horizontal de límite normativo (dashed roja)
- Etiquetas de valor sobre cada barra
- Título: "DQO Salida — Promedios Mensuales"
- `use_container_width=True`

**Columna 3 — Panel de alarmas activas:**

Renderizar con `st.markdown(unsafe_allow_html=True)`:
- Si no hay alarmas: mostrar `st.success("✅ Sin alarmas activas")`
- Si hay alarmas: mostrar cada una como card HTML con:
  - Icono ⚠️ o 🔴 según severidad
  - Nombre del evento
  - Valor y unidad
  - Timestamp formateado
  - Zona/TAG afectado
- Ordenar: críticas primero, luego alertas
- Máximo 5 alarmas visibles; si hay más, mostrar contador

---

#### ZONA 5 — Análisis estadístico (2 columnas iguales)

**Columna izquierda — Histograma distribución DQO salida:**

`plotly.graph_objects.Histogram`:
- Datos: todos los valores de RAB-SALIDA en el período seleccionado
- Bins: cada 10 mg/L desde 0 hasta max(valor) + 50
- Color de barras: gradiente de verde a rojo según posición relativa al límite
  - Barras ≤ 120 mg/L: verde `#C0DD97`
  - Barras 120–160 mg/L: ámbar `#FAC775`
  - Barras 160–200 mg/L: naranja `#EF9F27`
  - Barras > 200 mg/L: rojo `#E24B4A`
- Línea vertical en LIMITE_DQO_EFLUENTE (dashed roja, anotación "Límite")
- Línea vertical en valor promedio (dashed azul, anotación "Promedio")
- Eje X: "DQO (mg/L)", Eje Y: "Frecuencia (registros)"
- Título: "Distribución DQO Efluente — {n_registros} registros"
- Debajo del gráfico: caja de estadísticas (min, max, media, mediana, p95)

**Columna derecha — Comparativo mensual 12 meses:**

`plotly.graph_objects.Bar` + `plotly.graph_objects.Scatter` (gráfico combinado):
- Barras: DQO Salida promedio mensual (color azul `#85B7EB`)
- Línea superpuesta: Eficiencia de remoción % (eje Y secundario, color verde)
- El mes actual en color azul oscuro `#185FA5` (destacado)
- Línea horizontal de límite 200 mg/L
- Eje Y izquierdo: "DQO mg/L", Eje Y derecho: "Eficiencia %"
- Anotación de tendencia: "↓ X% vs hace 12 meses" o "↑ X%"
- Título: "Tendencia Anual DQO — Eficiencia de Remoción"
- `use_container_width=True`

---

## 6. FUNCIONES AUXILIARES REQUERIDAS

```python
def calcular_estado_dqo(valor, limite, umbral_alerta=None):
    """Retorna 'ok', 'alerta' o 'critico' según valor vs límites"""

def calcular_estado_eficiencia(pct, meta):
    """Retorna 'ok', 'alerta' o 'critico' según % vs meta"""

def render_kpi_card(label, valor, unidad, sub_texto, estado, delta=None):
    """Genera HTML de tarjeta KPI con color semáforo. delta es variación % opcional."""
    
def render_alarma_card(alarma_dict):
    """Genera HTML de tarjeta de alarma con color según severidad"""

def formato_fecha_display(fecha):
    """Retorna string legible: '12 May 2026 09:15'"""

def get_rango_fechas(periodo_str):
    """Convierte string de período ('Este mes', etc.) a (fecha_inicio, fecha_fin)"""

def color_barra_dqo(valor):
    """Retorna color hex según valor de DQO vs límites normativos"""
```

---

## 7. MANEJO DE ERRORES Y ESTADOS VACÍOS

- Si la conexión a BD falla: `st.error()` con instrucciones de configuración del `.env`
- Si no hay datos en el período seleccionado: `st.warning()` con mensaje y sugerencia de ampliar rango
- Si hay datos solo para un TAG: mostrar los disponibles y advertir cuál falta
- Todos los cálculos de división deben usar `np.where` o verificar denominador > 0
- Valores `NaN` o `None` en los KPIs mostrar como "Sin dato" en lugar de error
- Usar `st.spinner("Cargando datos...")` durante las queries

---

## 8. ARCHIVO requirements.txt

Generar con estas dependencias:

```
streamlit>=1.32.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.18.0
sqlalchemy>=2.0.0
pyodbc>=4.0.39          # Para SQL Server
python-dotenv>=1.0.0
```

---

## 9. ARCHIVO .env.example

Generar este archivo como plantilla:

```
DB_ENGINE=mssql+pyodbc
DB_SERVER=tu_servidor_sql
DB_NAME=PTAR_DB
DB_USER=sa
DB_PASSWORD=tu_password_aqui
DB_DRIVER=ODBC+Driver+17+for+SQL+Server
```

---

## 10. DETALLES ADICIONALES DE IMPLEMENTACIÓN

1. **Caché inteligente:** usar `st.cache_data(ttl=900)` en todas las funciones de datos (15 min). El botón "Actualizar datos" en el sidebar debe llamar `st.cache_data.clear()` y luego `st.rerun()`.

2. **Session state:** guardar en `st.session_state`:
   - `fecha_inicio`, `fecha_fin` (para persistir entre interacciones del sidebar)
   - `ultima_actualizacion` (timestamp del último fetch)

3. **Formato numérico:** todos los valores de DQO mostrar con 1 decimal (`f"{valor:.1f}"`). Porcentajes con 1 decimal. Fechas en formato `dd MMM YYYY HH:mm`.

4. **Responsividad:** usar siempre `use_container_width=True` en todos los gráficos Plotly.

5. **Tema Plotly:** usar `template="plotly_white"` en todos los gráficos para fondo limpio profesional.

6. **Título de la ventana:** incluir estado general: `st.set_page_config(page_title="DQO PTAR — 🟢 Normal")` (actualizable dinámicamente con `st.title()`).

7. **Footer:** al final de la página mostrar: "PTAR — Sistema de Monitoreo DQO · Datos desde PLC vía TAG_ID · Período: {fechas}"

8. **Paginación de alarmas:** si hay más de 5 alarmas, usar `st.expander("Ver todas las alarmas ({n})")` para mostrar el resto.

9. **Exportación:** agregar botón `st.download_button` que exporte el DataFrame del período seleccionado a CSV.

10. **Logging:** usar el módulo `logging` de Python para registrar cada consulta a BD con el tiempo de ejecución.

---

## 11. ESTRUCTURA DE ARCHIVOS A GENERAR

```
dashboard_dqo/
├── dashboard_dqo.py       ← App principal Streamlit
├── db_connector.py        ← Conexión y queries SQLAlchemy
├── kpi_calculator.py      ← Funciones de cálculo de KPIs y alarmas
├── chart_builder.py       ← Funciones que retornan figuras Plotly
├── ui_components.py       ← render_kpi_card, render_alarma_card, CSS
├── config.py              ← Constantes normativas y configuración
├── requirements.txt
├── .env.example
└── README.md              ← Instrucciones de instalación y ejecución
```

---

## 12. COMANDO DE EJECUCIÓN

```bash
# Instalar dependencias
pip install -r requirements.txt

# Copiar y configurar credenciales
cp .env.example .env
# Editar .env con los datos reales del servidor SQL

# Ejecutar dashboard
streamlit run dashboard_dqo.py --server.port 8501
```

---

## NOTAS FINALES PARA EL ASISTENTE DE CÓDIGO

- Generar código completo y funcional, no pseudocódigo ni esqueletos vacíos
- Cada función debe tener docstring en español explicando parámetros y retorno
- Los queries SQL deben usar parámetros vinculados (`:param`) para prevenir SQL injection
- El dashboard debe funcionar incluso si la BD no está disponible (modo demo con datos sintéticos)
- En modo demo, generar datos realistas: DQO entrada entre 800–2000 mg/L, salida entre 60–180 mg/L
- Comentar secciones complejas de los queries con el propósito de cada filtro
