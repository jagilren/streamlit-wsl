# SPEC: Módulo de Horas de Operación — Bombas Centrífugas
## Para Claude Code · PTAR Dashboard · Módulo 4 de 4

---

## Contexto del Proyecto

Este es el **cuarto módulo** de un dashboard Streamlit existente para una Planta de Tratamiento de Aguas Residuales (PTAR). Los tres módulos previos ya están corriendo:

| Módulo | Archivo (referencia) | Estado |
|--------|----------------------|--------|
| 1 | `dashboard_ptar.py`  | ✅ Activo |
| 2 | `dashboard_dqo.py`   | ✅ Activo |
| 3 | `dashboard_od.py`    | ✅ Activo |
| **4** | **`dashboard_bombas.py`** | 🔨 Por crear |

Intégralo al sistema de navegación existente del proyecto exactamente igual que los otros tres módulos. No alteres los módulos existentes.

---

## Stack Técnico

- **Framework:** Streamlit
- **Base de datos:** La misma que tienes para los otros dashboards
- **ORM / conector:** (usa el que ya esté configurado en el proyecto)
- **Visualización:** Plotly Express / Plotly Graph Objects
- **Tipo de sistema:** Solo telemetría — **NUNCA incluir botones ni controles que ejecuten acciones sobre equipos**

---

## Esquema de Base de Datos

### Tabla existente (lectura)
```sql
-- Ya existe, solo lectura
pump_counters (
    id          SERIAL PRIMARY KEY,
    tag_id      VARCHAR(20),   -- ej: 'P-01A', 'P-01B'
    timestamp   TIMESTAMP,
    value       NUMERIC        -- horas acumuladas de operación
)
```

### Tablas de catálogo (crear si no existen)
```sql
-- Catálogo maestro de bombas
CREATE TABLE IF NOT EXISTS pump_assets (
    id          SERIAL PRIMARY KEY,
    tag_id      VARCHAR(20) UNIQUE NOT NULL,
    name        VARCHAR(100),
    subsystem   VARCHAR(20),            -- 'CRIBADO', 'FISICO-QUIMICO', 'CLARIFICADO SECUNDARIO'
    role        VARCHAR(10) CHECK (role IN ('principal', 'backup')),
    model       VARCHAR(100),
    max_hours   NUMERIC DEFAULT 5000
);

-- Relación principal ↔ backup por subsistema
CREATE TABLE IF NOT EXISTS pump_pairs (
    id              SERIAL PRIMARY KEY,
    subsystem_id    VARCHAR(20) NOT NULL,
    principal_id    INTEGER REFERENCES pump_assets(id),
    backup_id       INTEGER REFERENCES pump_assets(id),
    active_pump_id  INTEGER REFERENCES pump_assets(id),  -- actualizado por PLC/SCADA, nunca por el dashboard
    last_rotation   TIMESTAMP,
    notes           TEXT,
    CONSTRAINT no_self_pair CHECK (principal_id <> backup_id),
    CONSTRAINT active_must_be_pair CHECK (active_pump_id IN (principal_id, backup_id))
);
```

### Datos maestros iniciales (INSERT si tablas vacías)
```sql
INSERT INTO pump_assets (tag_id, name, subsystem, role, max_hours) VALUES
  ('000-P-01A', 'Bomba Cribado --> FísicoQuímico',      'CRIBADO', 'principal', 50000),
  ('000-P-01B', 'Bomba Cribado Backup --> FísicoQuímico',         'CRIBADO', 'backup',    50000),
  ('200-P-02A', 'Bomba DAF Primario Principal', 'FISICO-QUIMICO', 'principal', 50000),
  ('200-P-02B', 'Bomba DAF Primario Backup',    'FISICO-QUIMICO', 'backup',    50000),
('400-P-03A', 'Bomba Clarificado Principal',  'CLARIFICADO SECUNDARIO', 'principal', 50000),
  ('400-P-03B', 'Bomba Clarificado Backup',     'CLARIFICADO SECUNDARIO', 'backup',    50000)
ON CONFLICT (tag_id) DO NOTHING;
```

### Vista de balance (crear si no existe)
```sql
CREATE OR REPLACE VIEW v_pump_balance AS
SELECT
    pp.subsystem_id,
    pa_p.tag_id                                         AS tag_principal,
    pa_b.tag_id                                         AS tag_backup,
    MAX(pc_p.value)                                     AS horas_principal,
    MAX(pc_b.value)                                     AS horas_backup,
    ABS(MAX(pc_p.value) - MAX(pc_b.value))              AS delta_horas,
    ROUND(
        ABS(MAX(pc_p.value) - MAX(pc_b.value))
        / NULLIF(MAX(pc_p.value) + MAX(pc_b.value), 0) * 100, 1
    )                                                   AS desbalance_pct
FROM pump_pairs pp
JOIN pump_assets pa_p ON pa_p.id = pp.principal_id
JOIN pump_assets pa_b ON pa_b.id = pp.backup_id
JOIN pump_counters pc_p ON pc_p.tag_id = pa_p.tag_id
JOIN pump_counters pc_b ON pc_b.tag_id = pa_b.tag_id
GROUP BY pp.subsystem_id, pa_p.tag_id, pa_b.tag_id;
```

---

## Subsistemas

| ID      | Nombre          | Flujo de proceso                      |
|---------|-----------------|---------------------------------------|
| CRIBADO   | Cribado         | Pretratamiento → DAF Primario         |
| FISICO-QUIMICO   | DAF Primario    | Clarificado DAF → RAB                       |
| CLARIFICADO SECUNDARIO   | Clarificado Secundario | Post-tratamiento Clarificador Secundario → Filtros MM |

---

## Lógica de Alertas

### Umbral de desbalance
```python
ALERT_THRESHOLD_PCT = 35  # % de diferencia sobre el total acumulado
```

### Niveles de vida útil por bomba
| % de vida útil consumida | Nivel  | Color sugerido |
|--------------------------|--------|----------------|
| < 75%                    | Normal | Verde / azul   |
| 75% – 90%                | Aviso  | Naranja        |
| > 90%                    | Crítico| Rojo           |

### Regla de negocio
- Si `desbalance_pct > ALERT_THRESHOLD_PCT` → mostrar alerta prominente indicando que la bomba con más horas necesita rotación
- La rotación NO se ejecuta desde el dashboard (solo telemetría); la alerta es informativa para el operador

---

## Estructura del Módulo `dashboard_bombas.py`

### Secciones en orden

1. **Header del módulo**
   - Título: "Horas de Operación — Bombas Centrífugas"
   - Subtítulo: "PTAR ·  Telemetría · Horómetros del sistema"
   - Indicador de última actualización (`st.caption`)

2. **Diagrama de flujo de proceso** *(visual, no interactivo)*
   - Mostrar: `CRIBADO → FISICO-QUIMICO → CLARIFICADO SECUNDARIO` con el nombre de cada subsistema
   - Usar `st.columns` con flechas entre ellas
   - Colorear el borde/fondo del nodo según si tiene alerta o no

3. **KPIs globales** (`st.columns` con 4 métricas)
   - Total subsistemas activos, Mostrar texto en CARD
   - Bombas en marcha, Mostrar texto en CARD
   - Alertas de desbalance activas
   - Bombas con vida útil > 95%

4. **Panel por subsistema** (iterar sobre los 3 subsistemas)
   - Encabezado con ID, nombre y horas acumuladas totales
   - Dos columnas: tarjeta bomba principal | tarjeta bomba backup
   - Cada tarjeta muestra:
     - `tag_id` y rol
     - Estado operativo (EN MARCHA / STANDBY / FALLA) con `st.badge` o color
     - Horas acumuladas en grande (`st.metric`)
     - Barra de progreso hacia `max_hours` (`st.progress`)
     - Último servicio
   - Barra de balance horizontal (Plotly horizontal bar bicolor)
   - Alerta `st.warning` o `st.error` si desbalance > umbral

5. **Gráfico histórico de horas** *(Plotly)*
   - Selector de subsistema (`st.selectbox`)
   - Serie de tiempo de `pump_counters` para las dos bombas del subsistema seleccionado
   - Dos líneas: principal vs backup
   - Eje X: timestamp | Eje Y: horas acumuladas

6. **Tabla resumen** (`st.dataframe`)
   - Columnas: Subsistema | Tag | Rol | Horas | % Vida Útil | Δ Horas | Desbalance % | Alerta
   - Colorear celdas de "Desbalance %" con `st.dataframe` styler

---

## Datos de Prueba (Mock)

Si la conexión a PostgreSQL falla o está en modo desarrollo, usar este mock para que el módulo no rompa:

```python
MOCK_DATA = {
    "CRIBADO": {
        "nombre": "Subsistema Cribado",
        "flujo": "Pretratamiento → DAF Primario",
        "principal": {"tag": "P-01A", "horas": 3842, "status": "running", "last_service": "2024-11-10"},
        "backup":    {"tag": "P-01B", "horas": 1120, "status": "standby", "last_service": "2024-10-22"},
        "max_hours": 5000,
    },
    "FISICO-QUIMICO": {
        "nombre": "DAF Primario",
        "flujo": "Flotación → RAB",
        "principal": {"tag": "P-02A", "horas": 2201, "status": "running", "last_service": "2025-01-05"},
        "backup":    {"tag": "P-02B", "horas": 2090, "status": "standby", "last_service": "2025-01-03"},
        "max_hours": 5000,
    },
    "CLARIFICADO SECUNDARIO": {
        "nombre": "Clarificado SECUNDARIO",
        "flujo": "Post-tratamiento biológico → Descarga",
        "principal": {"tag": "P-03A", "horas": 4510, "status": "fault",   "last_service": "2024-09-14"},
        "backup":    {"tag": "P-03B", "horas":  980, "status": "running", "last_service": "2024-12-01"},
        "max_hours": 5000,
    },
}
```

---

## Configuración de Conexión

Usa el mismo método de conexión que los módulos existentes (`dashboard_ptar.py`, `dashboard_dqo.py`, `dashboard_od.py`). No inventes un patrón nuevo — revisa cómo lo hacen los otros módulos y replica exactamente esa estructura.

Si usan `st.secrets`, la clave esperada es:
```toml
# .streamlit/secrets.toml
[postgres]
host     = "..."
port     = 5432
dbname   = "..."
user     = "..."
password = "..."
```

---

## Restricciones Críticas

| ✅ Permitido                                      | ❌ Prohibido                                      |
|--------------------------------------------------|--------------------------------------------------|
| `st.metric`, `st.progress`, `st.dataframe`       | Botones que ejecuten acciones sobre equipos      |
| `st.warning`, `st.error` para alertas            | Cambiar estado de bombas desde el UI             |
| Plotly para gráficos de solo lectura             | Escribir en `pump_counters` desde el dashboard   |
| `st.selectbox` para filtros de visualización     | Campos `st.text_input` para enviar comandos      |
| `st.cache_data` con TTL para queries             | Cualquier lógica de telecontrol                  |

---

## Archivos a Generar

```
dashboard_bombas.py          ← módulo principal (único archivo nuevo requerido)
```

No crear archivos adicionales a menos que el proyecto ya tenga una carpeta `utils/` o `db/` compartida entre módulos — en ese caso, agregar las queries allí siguiendo el patrón existente.

---

## Notas para Claude Code

- Revisar primero los tres módulos existentes para entender el patrón de navegación, conexión a DB y estilo visual antes de escribir una sola línea
- Mantener consistencia visual con los módulos existentes (colores, fuentes, layout)
- El módulo debe funcionar en modo mock si no hay conexión disponible
- No modificar `requirements.txt` si `plotly` y `psycopg2` ya están listados
