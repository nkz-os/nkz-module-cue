-- =============================================================================
-- CUE Module Registration — Cuaderno de Campo SIEX
-- =============================================================================
-- Register CUE module in the marketplace_modules table
-- =============================================================================

INSERT INTO marketplace_modules (
    id,
    name,
    display_name,
    description,
    remote_entry_url,
    scope,
    exposed_module,
    version,
    author,
    category,
    route_path,
    label,
    module_type,
    required_plan_type,
    pricing_tier,
    is_local,
    is_active,
    required_roles,
    metadata
) VALUES (
    'cue',
    'cue',
    'Cuaderno de Campo (CUE)',
    'Cuaderno de Explotación Único conforme al RD 1054/2022 (SIEX). Registro de explotaciones, tratamientos fitosanitarios, fertilizaciones y recintos SIGPAC con validación legal.',
    'https://nekazari.robotika.cloud/modules/cue/nkz-module.js',
    'cue_module',
    './App',
    '0.2.0',
    'Nekazari',
    'agriculture',
    '/cue',
    'Cuaderno de Campo',
    'ADDON_FREE',
    'basic',
    'FREE',
    false,
    true,
    ARRAY['Farmer', 'TenantAdmin'],
    '{"icon": "📋", "color": "#22C55E"}'::jsonb
) ON CONFLICT (id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    remote_entry_url = EXCLUDED.remote_entry_url,
    scope = EXCLUDED.scope,
    exposed_module = EXCLUDED.exposed_module,
    is_active = true,
    updated_at = NOW();
