-- Migration 004: Submission state machine for IUWS tracking
-- Infrastructure data, NOT NGSI-LD entities.

CREATE TABLE IF NOT EXISTS cue_estado_envio (
    id                  SERIAL PRIMARY KEY,
    tenant_id           VARCHAR(255) NOT NULL,
    farm_id             VARCHAR(255) NOT NULL,
    id_ticket           VARCHAR(255),
    csv_trace_id        VARCHAR(255),
    estado              VARCHAR(50) NOT NULL DEFAULT 'borrador',
    payload_type        VARCHAR(20) NOT NULL DEFAULT 'Alta',
    provincia           VARCHAR(2),
    iuws_url            VARCHAR(255),
    xml_payload         TEXT,
    xsd_valid           BOOLEAN,
    detalle_respuesta   JSONB,
    fecha_presentacion  TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_envio_tenant ON cue_estado_envio (tenant_id);
CREATE INDEX IF NOT EXISTS idx_envio_farm ON cue_estado_envio (farm_id);
CREATE INDEX IF NOT EXISTS idx_envio_estado ON cue_estado_envio (estado);
CREATE INDEX IF NOT EXISTS idx_envio_ticket ON cue_estado_envio (id_ticket);

-- Auto-update trigger
DROP TRIGGER IF EXISTS trg_envio_updated_at ON cue_estado_envio;
CREATE TRIGGER trg_envio_updated_at
    BEFORE UPDATE ON cue_estado_envio
    FOR EACH ROW EXECUTE FUNCTION update_cue_recinto_updated_at();

-- State machine valid transitions
-- borrador -> validado -> firmado -> pendiente -> procesando -> aceptado | aceptado_con_advertencias | pendiente_de_subsanacion | rechazado_con_errores
-- pendiente_de_subsanacion -> subsanado -> pendiente (re-submit)
