-- Migration 002: IUWS endpoint routing table for multi-region support
-- Maps Spanish province codes (INE) to IUWS service URLs.
-- This is infrastructure configuration, NOT NGSI-LD entities.

CREATE TABLE IF NOT EXISTS cue_endpoints_autonomicos (
    id                SERIAL PRIMARY KEY,
    codigo_provincia  VARCHAR(2) NOT NULL UNIQUE,
    comunidad         VARCHAR(100) NOT NULL,
    iuws_base_url     VARCHAR(255) NOT NULL,
    sandbox_url       VARCHAR(255),
    activo            BOOLEAN DEFAULT true,
    created_at        TIMESTAMP DEFAULT NOW(),
    updated_at        TIMESTAMP DEFAULT NOW()
);

-- Auto-update trigger
CREATE OR REPLACE FUNCTION update_cue_endpoint_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cue_endpoint_updated_at ON cue_endpoints_autonomicos;
CREATE TRIGGER trg_cue_endpoint_updated_at
    BEFORE UPDATE ON cue_endpoints_autonomicos
    FOR EACH ROW EXECUTE FUNCTION update_cue_endpoint_updated_at();

-- Seed: Navarra (province code 31)
INSERT INTO cue_endpoints_autonomicos (codigo_provincia, comunidad, iuws_base_url, sandbox_url)
VALUES ('31', 'Navarra', 'https://pac.navarra.es:8443', 'https://pac.navarra.es:8443')
ON CONFLICT (codigo_provincia) DO NOTHING;

-- Seed: placeholder entries for other autonomous communities
-- These URLs will be updated as more CCAA integrations come online

-- Aragón (province codes 22, 44, 50)
INSERT INTO cue_endpoints_autonomicos (codigo_provincia, comunidad, iuws_base_url)
VALUES ('22', 'Aragón', 'https://iuws.aragon.es'), ('44', 'Aragón', 'https://iuws.aragon.es'), ('50', 'Aragón', 'https://iuws.aragon.es')
ON CONFLICT (codigo_provincia) DO NOTHING;

-- Cataluña (province codes 08, 17, 25, 43)
INSERT INTO cue_endpoints_autonomicos (codigo_provincia, comunidad, iuws_base_url)
VALUES ('08', 'Cataluña', 'https://iuws.catalunya.es'), ('17', 'Cataluña', 'https://iuws.catalunya.es'), ('25', 'Cataluña', 'https://iuws.catalunya.es'), ('43', 'Cataluña', 'https://iuws.catalunya.es')
ON CONFLICT (codigo_provincia) DO NOTHING;

-- La Rioja (province code 26)
INSERT INTO cue_endpoints_autonomicos (codigo_provincia, comunidad, iuws_base_url)
VALUES ('26', 'La Rioja', 'https://iuws.larioja.es')
ON CONFLICT (codigo_provincia) DO NOTHING;

-- País Vasco (province codes 01, 20, 48)
INSERT INTO cue_endpoints_autonomicos (codigo_provincia, comunidad, iuws_base_url)
VALUES ('01', 'País Vasco', 'https://iuws.euskadi.eus'), ('20', 'País Vasco', 'https://iuws.euskadi.eus'), ('48', 'País Vasco', 'https://iuws.euskadi.eus')
ON CONFLICT (codigo_provincia) DO NOTHING;
