-- Migration 001: Create spatial cache table for SigpacEnclosure geometries
-- Populated exclusively by Orion-LD subscription webhook (POST /notify)
-- NEVER written directly by the API.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS cue_recinto_sigpac (
    id                 SERIAL PRIMARY KEY,
    orion_entity_id    VARCHAR(255) UNIQUE NOT NULL,
    tenant_id          VARCHAR(255) NOT NULL,
    geometria          GEOMETRY(Polygon, 4326) NOT NULL,
    centroid           GEOMETRY(Point, 4326) GENERATED ALWAYS AS (ST_Centroid(geometria)) STORED,
    area_ha            DECIMAL(10,4) GENERATED ALWAYS AS (ST_Area(geometria::geography) / 10000) STORED,
    created_at         TIMESTAMP DEFAULT NOW(),
    updated_at         TIMESTAMP DEFAULT NOW()
);

-- Spatial indexes
CREATE INDEX IF NOT EXISTS idx_cue_recinto_geom
    ON cue_recinto_sigpac USING GIST (geometria);

CREATE INDEX IF NOT EXISTS idx_cue_recinto_centroid
    ON cue_recinto_sigpac USING GIST (centroid);

-- Tenant isolation index
CREATE INDEX IF NOT EXISTS idx_cue_recinto_tenant
    ON cue_recinto_sigpac (tenant_id);

-- Entity ID lookup index
CREATE INDEX IF NOT EXISTS idx_cue_recinto_entity
    ON cue_recinto_sigpac (orion_entity_id);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_cue_recinto_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cue_recinto_updated_at ON cue_recinto_sigpac;
CREATE TRIGGER trg_cue_recinto_updated_at
    BEFORE UPDATE ON cue_recinto_sigpac
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();
