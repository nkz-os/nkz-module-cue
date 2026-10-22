-- Migration 005: Gestor authorization table
-- Tracks which gestores are authorized to access which farmer tenants.
-- Enforces exclusive gestor-tenant relationships.

CREATE TABLE IF NOT EXISTS cue_gestor_autorizaciones (
    id                 SERIAL PRIMARY KEY,
    gestor_sub         VARCHAR(255) NOT NULL,
    gestor_username    VARCHAR(255) NOT NULL,
    gestor_tenant      VARCHAR(255) NOT NULL,
    farmer_tenant      VARCHAR(255) NOT NULL,
    farmer_name        VARCHAR(255),
    farmer_sub         VARCHAR(255),
    autorizado         BOOLEAN NOT NULL DEFAULT FALSE,
    autorizado_at      TIMESTAMP,
    created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_gestor_farmer UNIQUE (gestor_sub, farmer_tenant)
);

CREATE INDEX IF NOT EXISTS idx_cue_gestor_sub ON cue_gestor_autorizaciones (gestor_sub);
CREATE INDEX IF NOT EXISTS idx_cue_gestor_farmer ON cue_gestor_autorizaciones (farmer_tenant);
CREATE INDEX IF NOT EXISTS idx_cue_gestor_autorizado ON cue_gestor_autorizaciones (gestor_sub, autorizado);

DROP TRIGGER IF EXISTS trg_cue_gestor_autorizaciones_updated_at ON cue_gestor_autorizaciones;
CREATE TRIGGER trg_cue_gestor_autorizaciones_updated_at
    BEFORE UPDATE ON cue_gestor_autorizaciones
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();
