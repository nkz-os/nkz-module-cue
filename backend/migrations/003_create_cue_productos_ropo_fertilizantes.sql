-- Migration 003: Master catalogs for ROPO (phytosanitary products) and Fertilizantes
-- SCD Type 2: temporal validity via fecha_inicio_validez / fecha_fin_validez
-- These are INFRASTRUCTURE/DICTIONARY tables, NOT NGSI-LD entities.

-- ROPO: Registro Oficial de Productos y Operadores (phytosanitary products)
CREATE TABLE IF NOT EXISTS cue_producto_ropo (
    id                    SERIAL PRIMARY KEY,
    numero_registro       VARCHAR(50) NOT NULL,
    nombre_comercial      VARCHAR(255) NOT NULL,
    ingrediente_activo    VARCHAR(255),
    titular               VARCHAR(255),
    tipo                  VARCHAR(100),
    estado                VARCHAR(50) NOT NULL DEFAULT 'autorizado',
    cultivos_autorizados  TEXT[],
    plagas_autorizadas    TEXT[],
    dosis_maxima          DECIMAL(10,4),
    unidad_dosis          VARCHAR(20) DEFAULT 'L/ha',
    plazo_seguridad_dias  INTEGER,
    -- SCD Type 2: temporal validity
    fecha_inicio_validez  DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin_validez     DATE,
    -- ETL audit
    fuente_hash           VARCHAR(64),
    fecha_sincronizacion  TIMESTAMP DEFAULT NOW(),
    created_at            TIMESTAMP DEFAULT NOW(),
    updated_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ropo_numero_registro ON cue_producto_ropo (numero_registro);
CREATE INDEX IF NOT EXISTS idx_ropo_validez ON cue_producto_ropo (numero_registro, fecha_inicio_validez, fecha_fin_validez);
CREATE INDEX IF NOT EXISTS idx_ropo_cultivos ON cue_producto_ropo USING GIN (cultivos_autorizados);
CREATE INDEX IF NOT EXISTS idx_ropo_estado ON cue_producto_ropo (estado);

-- Trigger for updated_at (reuses existing function from migration 001)
DROP TRIGGER IF EXISTS trg_ropo_updated_at ON cue_producto_ropo;
CREATE TRIGGER trg_ropo_updated_at
    BEFORE UPDATE ON cue_producto_ropo
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();

-- Fertilizantes: Register of fertilizers (MAPA)
CREATE TABLE IF NOT EXISTS cue_producto_fertilizante (
    id                    SERIAL PRIMARY KEY,
    numero_registro       VARCHAR(50) NOT NULL,
    nombre_comercial      VARCHAR(255) NOT NULL,
    tipo                  VARCHAR(100) NOT NULL,
    composicion_n_pct     DECIMAL(6,2),
    composicion_p_pct     DECIMAL(6,2),
    composicion_k_pct     DECIMAL(6,2),
    fabricante            VARCHAR(255),
    estado                VARCHAR(50) NOT NULL DEFAULT 'autorizado',
    cultivos_autorizados  TEXT[],
    dosis_maxima_kg_ha    DECIMAL(10,4),
    -- SCD Type 2: temporal validity
    fecha_inicio_validez  DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin_validez     DATE,
    -- ETL audit
    fuente_hash           VARCHAR(64),
    fecha_sincronizacion  TIMESTAMP DEFAULT NOW(),
    created_at            TIMESTAMP DEFAULT NOW(),
    updated_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fert_numero_registro ON cue_producto_fertilizante (numero_registro);
CREATE INDEX IF NOT EXISTS idx_fert_validez ON cue_producto_fertilizante (numero_registro, fecha_inicio_validez, fecha_fin_validez);
CREATE INDEX IF NOT EXISTS idx_fert_estado ON cue_producto_fertilizante (estado);

DROP TRIGGER IF EXISTS trg_fert_updated_at ON cue_producto_fertilizante;
CREATE TRIGGER trg_fert_updated_at
    BEFORE UPDATE ON cue_producto_fertilizante
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();
