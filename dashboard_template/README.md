# dashboard_template

Plantilla **tag-config-driven** lista para clonar como base de cualquier
dashboard nuevo de variable de proceso (caudal, SST, conductividad,
temperatura, nitrógeno, etc.).

Construida sobre el patrón ya validado en `dashboard_ph` y `dashboard_od`:

- Tabla de configuración (`<modulo>_tag_config`) controla cuántos lienzos
  y cuántos KPI cards se dibujan — agregar/quitar instrumentos = `INSERT`
  o `DELETE` en BD, sin tocar código.
- Tabla de hechos (`<modulo>_measurements`) como hypertable Timescale.
- Render itera los TAGs activos y arma un grid 2×N.
- Botón "Recargar TAGs" en sidebar para invalidar el cache de configs.
- Filtro de tiempo compartido (mismas keys de session_state que pH/OD/DQO).

## Cómo clonar

Para crear un módulo nuevo `dashboard_caudal` a partir de la plantilla:

```bash
cp -r dashboard_template dashboard_caudal
cd dashboard_caudal
mv dashboard_template.py dashboard_caudal.py

# Reemplazo masivo de identificadores
grep -rli template . | xargs sed -i \
    -e 's/template/caudal/g' \
    -e 's/Template/Caudal/g' \
    -e 's/TEMPLATE/CAUDAL/g'
```

Después editar manualmente:

1. **`config.py`** — `MODULE_LABEL`, `UNIT`, `ICON`.
2. **`db_init.py`** — ajustar precisión numérica de `value` si la variable lo
   necesita (`NUMERIC(p,s)`); la plantilla deja `(12,3)`.
3. **`home.py`** del proyecto raíz — agregar `st.Page("dashboard_caudal/dashboard_caudal.py", ...)`.
4. **Sembrar `caudal_tag_config`** con los TAGs reales (vía SQL directo o,
   si existe, la UI de admin de `dashboard_dqo/tag_admin.py`).

## Estructura

| Archivo | Qué hace |
|---|---|
| `config.py` | 4 constantes que personalizan el módulo (MODULE, MODULE_LABEL, UNIT, ICON). |
| `db_init.py` | DDL idempotente: `<modulo>_measurements` (hypertable) + `<modulo>_tag_config`. |
| `queries.py` | SQL para configs, valores actuales, tendencia 24h/rango, violaciones, último timestamp, insert. |
| `cache.py` | `@st.cache_data` con TTLs (60s configs, 30s actuales, 60s tendencia, 120s violaciones). |
| `utils.py` | `compute_*_status`, `classify_violation`, `deviation`, paleta `STATUS_CONFIG`. |
| `view.py` | `render(conn, time_filter)` que itera TAGs y dibuja KPI cards + grid 2×N. |
| `dashboard_template.py` | Entry Streamlit (set_page_config + autorefresh + auth + sidebar + render). |
| `components/charts.py` | KPI card, gráfica de tendencia con banda óptima, tabla de eventos, CSS "EN VIVO". |
| `components/sidebar_filters.py` | Botón "Recargar TAGs". |

## Suposiciones de diseño

- **Todos los TAGs son equivalentes**: cada uno se renderiza igual (mismo
  layout). Si tu variable necesita semántica de roles (afluente/efluente
  como en DQO), no uses esta plantilla — usa `dashboard_dqo` como base.
- **Una sola unidad por módulo**: la columna `unit` de `tag_config` permite
  override por TAG, pero el módulo asume que todos los instrumentos miden
  lo mismo (ej. todos en mg/L, todos en L/s).
- **Rangos óptimos y críticos por TAG**: definidos como `opt_min`,
  `opt_max`, `crit_min`, `crit_max` en `tag_config`. La clasificación
  (ok / warn / critical) es uniforme.

## Diferencias con dashboard_ph / dashboard_od

| Aspecto | Plantilla | pH | OD |
|---|---|---|---|
| Layout | Grid 2×N (igual a pH) | Grid 2×N | Vertical pleno-ancho |
| Gauge circular | No | No | Sí |
| Generador de datos demo | No incluido | `data_generator.py` | `data_generator.py` |
| Estadísticas diarias | No | `get_ph_daily_stats` | No |

Si necesitas alguna de esas extensiones, copia el archivo correspondiente
desde el módulo de pH/OD después de clonar.
