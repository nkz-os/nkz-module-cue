-- Migration 007: Legal masters (ROMA equipment, ROPO applicators/advisors)
-- and per-use MAPA phytosanitary authorizations (product x crop x pest).
-- Idempotent; infrastructure/master tables owned by nkz_module_cue.

-- 1. Equipos de aplicación de fitosanitarios (ROMA + ITEAF)
CREATE TABLE IF NOT EXISTS cue_equipo_aplicacion (
    id                  SERIAL PRIMARY KEY,
    tenant_id           VARCHAR(255) NOT NULL,
    nombre              VARCHAR(255) NOT NULL,
    numero_roma         VARCHAR(64) NOT NULL,
    tipo_equipo         VARCHAR(100) NOT NULL DEFAULT 'pulverizador_hidraulico',
    capacidad_litros    DECIMAL(10,2),
    fecha_ultima_iteaf  DATE,
    fecha_proxima_iteaf DATE,
    activo              BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_cue_equipo_tenant_roma UNIQUE (tenant_id, numero_roma)
);

CREATE INDEX IF NOT EXISTS idx_cue_equipo_tenant ON cue_equipo_aplicacion (tenant_id, activo);

DROP TRIGGER IF EXISTS trg_cue_equipo_updated_at ON cue_equipo_aplicacion;
CREATE TRIGGER trg_cue_equipo_updated_at
    BEFORE UPDATE ON cue_equipo_aplicacion
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();

-- 2. Personal aplicador y asesores GIP (ROPO)
CREATE TABLE IF NOT EXISTS cue_aplicador_ropo (
    id                  SERIAL PRIMARY KEY,
    tenant_id           VARCHAR(255) NOT NULL,
    nombre              VARCHAR(255) NOT NULL,
    nif                 VARCHAR(20),
    numero_carne_ropo   VARCHAR(64) NOT NULL,
    nivel_capacitacion  VARCHAR(40) NOT NULL DEFAULT 'cualificado',
    fecha_caducidad     DATE,
    activo              BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_cue_aplicador_tenant_carne UNIQUE (tenant_id, numero_carne_ropo),
    CONSTRAINT chk_cue_nivel_capacitacion CHECK (
        nivel_capacitacion IN ('basico', 'cualificado', 'fumigador', 'piloto', 'asesor_gip')
    )
);

CREATE INDEX IF NOT EXISTS idx_cue_aplicador_tenant ON cue_aplicador_ropo (tenant_id, activo);

DROP TRIGGER IF EXISTS trg_cue_aplicador_updated_at ON cue_aplicador_ropo;
CREATE TRIGGER trg_cue_aplicador_updated_at
    BEFORE UPDATE ON cue_aplicador_ropo
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();

-- 3. Usos autorizados MAPA (terna producto x cultivo x plaga, SCD Type 2)
CREATE TABLE IF NOT EXISTS cue_producto_ropo_uso (
    id                       SERIAL PRIMARY KEY,
    numero_registro          VARCHAR(50) NOT NULL,
    cultivo                  VARCHAR(255) NOT NULL,
    plaga                    VARCHAR(255) NOT NULL DEFAULT '',
    dosis_minima             DECIMAL(10,4),
    dosis_maxima             DECIMAL(10,4),
    unidad_dosis             VARCHAR(30) DEFAULT 'L/ha',
    plazo_seguridad_dias     INTEGER,
    max_aplicaciones         INTEGER,
    volumen_caldo_min_l_ha   DECIMAL(10,2),
    volumen_caldo_max_l_ha   DECIMAL(10,2),
    condiciones_especificas  TEXT,
    fecha_inicio_validez     DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin_validez        DATE,
    fuente_hash              VARCHAR(64),
    created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ropo_uso_lookup
    ON cue_producto_ropo_uso (numero_registro, fecha_inicio_validez, fecha_fin_validez);
CREATE INDEX IF NOT EXISTS idx_ropo_uso_cultivo
    ON cue_producto_ropo_uso (lower(cultivo));

DROP TRIGGER IF EXISTS trg_cue_ropo_uso_updated_at ON cue_producto_ropo_uso;
CREATE TRIGGER trg_cue_ropo_uso_updated_at
    BEFORE UPDATE ON cue_producto_ropo_uso
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();
