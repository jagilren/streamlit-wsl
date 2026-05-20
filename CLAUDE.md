# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**PTAR Streamlit Dashboard** is a real-time water treatment plant (PTAR) monitoring system built with Streamlit. It provides multiple interactive dashboards for monitoring water quality metrics (DQO, pH, OD) and pump operating hours, with continuous data ingestion from TimescaleDB/PostgreSQL.

### Tech Stack
- **Frontend:** Streamlit 1.57.0 (Python web framework)
- **Database:** TimescaleDB (PostgreSQL 16 with timescaledb extension for time-series data)
- **Charting:** Plotly 6.7.0
- **Authentication:** streamlit-authenticator 0.4.2
- **Data Processing:** pandas, numpy
- **Deployment:** Docker Compose (6 services: Streamlit app, TimescaleDB, pgAdmin, 3 data generators)

## Architecture & Data Flow

### High-Level Structure

The repository is organized into four main dashboard modules (pH, DQO, OD, Bombas), each runnable standalone or unified via home.py.

**Core Files:**
- `home.py` - Multi-dashboard orchestrator (entry point, port 8501)
- `db.py` - Root-level DB connection & schema initialization
- `config.py` - Global TAG configuration metadata
- `data.py` - Shared data loading utilities
- `credentials.yaml` - User credentials (bcrypt-hashed)

**Dashboard Modules (dashboard_xxx/):**
- Each has: dashboard_xxx.py (entry point), db_init.py, queries.py, data_generator.py, view.py, components/
- Can run standalone on separate ports or unified via home.py navigation

**Data Generator Service:**
- `datos_dqo/` - Standalone DQO data generator CLI and streamer service
- Other dashboards have data_generator.py modules running as Docker services

**Shared Components:**
- `components/auth.py` - Idempotent authentication (works standalone or via home.py)
- `components/shared_time_filter.py` - Time range picker shared across dashboards
- Other helpers: cookie_banner, refresh_bar, chart_gaps, reload_tags

### Data Flow

1. **Data Ingestion:** Background services push metrics to TimescaleDB every 2-3 minutes
2. **Dashboard Queries:** Time-filtered queries (never full SELECT) with caching via @st.cache_data()
3. **Authentication:** Centralized in components/auth.py, idempotent and standalone-compatible
4. **Multi-Dashboard Navigation:** home.py orchestrates via st.navigation()

## Database Schema

All timestamp columns are TIMESTAMPTZ (stored as UTC). Core tables:

- **sensor_data** - Hypertable for pH/DQO ingestion with time-bucketing
- **dqo, ph, od** - Long-format measurement tables
- **pump_counters** - Pump operating hours (write-only by data_generator)
- **tag_config** - TAG-to-dashboard mapping
- **pump_pairs** - Pump pair relationships for comparison

## Key Configuration Files

**config.py (root):** Global TAG_MAP with metadata (nombre, tipo, color, limite, norma)

**dashboard_xxx/config.py:** Dashboard-specific constants (limits, thresholds, cache TTL, auto-refresh)

**.env / .env.dev:** Database connection, Streamlit settings

## Build, Run & Deploy

### Local Development
```bash
streamlit run home.py --server.port 8501
```
Or run individual dashboards standalone (ports 8502-8505).

### Generate DQO Data
```bash
python -m datos_dqo --solo-generar --desde 2025-01-01
python -m datos_dqo.streamer  # Continuous ingestion
```

### Docker Compose
```bash
docker network create ptar-shared
docker compose up -d
```

### Code Quality
No formal linting configured. Project follows PEP 8 (88-char lines, Black formatter). No test suite — validate via manual testing with dev data generators.

## Common Development Tasks

### Add New Dashboard
1. Create dashboard_newmetric/ with dashboard_newmetric.py, db_init.py, data_generator.py
2. Register in home.py navigation
3. Add Docker service to docker-compose.yml

### Add New TAG/Sensor
Update config.py TAG_MAP or dashboard-specific config.py.
Data generator auto-populates tag_config on startup.

### Modify Thresholds
Edit dashboard-specific config.py. Changes take effect on next reload (cache TTL).

### Debug Queries
Check /logs/db.log or connect via PgAdmin (port 5050). Test in Python REPL with db.get_connection().

## Important Patterns & Conventions

### Idempotent Authentication
setup_auth() called by both home.py and dashboards, caches in session_state to avoid duplicates.

### Mandatory Time-Range Filters
All queries MUST include WHERE timestamp BETWEEN ? AND ?. Reason: tables can have millions of rows.

### Data Caching with TTL
@st.cache_data(ttl=900) for historical data, ttl=60 for live KPIs. Never cache credentials.

### Generator-Driven Data
Each data generator runs in its own Docker service, write-only to its table, uses ON CONFLICT for idempotency.

### Tag Catalog & Resolution
Known TAGs in config.py. Unknown TAGs surfaced in dashboard_dqo/pages/1_Admin_TAGs.py for admin assignment.

## Key Files to Read First

1. home.py - Multi-dashboard orchestrator
2. db.py - DB connection & schema
3. config.py - Global TAG definitions
4. dashboard_dqo/dashboard_dqo.py - Full dashboard example
5. dashboard_dqo/db_connector.py - Query patterns
6. components/auth.py - Authentication pattern
7. docker-compose.yml - Service orchestration

## Breaking Changes to Avoid

- Changing timestamp column types breaks all dashboards
- Removing a dashboard dir requires updating home.py
- Renaming TAGs requires config.py update and migrations
- Modifying auth cookie key logs out all users

