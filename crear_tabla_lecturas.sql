-- Tabla unificada para lecturas PLC (pH) y Laboratorio (DQO)
-- UNIQUE (timestamp, tag) garantiza que no entren duplicados
-- en cargas sucesivas (INSERT ... ON CONFLICT DO NOTHING).

CREATE TABLE IF NOT EXISTS lecturas (
    id        BIGSERIAL        PRIMARY KEY,
    timestamp TIMESTAMPTZ      NOT NULL,
    tag       TEXT             NOT NULL,
    value     DOUBLE PRECISION NOT NULL,

    CONSTRAINT uq_lectura UNIQUE (timestamp, tag)
);

-- Índice para consultas por rango de tiempo (el más frecuente en dashboards)
CREATE INDEX IF NOT EXISTS idx_lecturas_timestamp ON lecturas (timestamp);

-- Índice para filtrar por TAG
CREATE INDEX IF NOT EXISTS idx_lecturas_tag ON lecturas (tag);
