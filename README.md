# nkz-module-cue — Cuaderno de Campo (CUE)

Módulo SIEX-compliant de Cuaderno de Explotación Único para España (RD 1054/2022).

## Estado

**Fase 1 en desarrollo.** Backend funcional con CRUD NGSI-LD sobre Orion-LD + caché espacial PostGIS.

## Arquitectura (SOTA NGSI-LD)

- **Orion-LD**: fuente de verdad para todas las entidades (AgriFarm, AgriParcel, AgriCropDeclaration, SigpacEnclosure)
- **PostGIS**: caché espacial read-only para geometrías SigpacEnclosure
- **API**: Flask passthrough → Orion-LD para escrituras, PostGIS para lecturas espaciales

## Fase 1 — Implementado

- [x] Scaffolding del módulo (Flask + psycopg2)
- [x] Auth middleware (JWT via api-gateway)
- [x] CRUD NGSI-LD: AgriFarm, AgriParcel, AgriCropDeclaration, SigpacEnclosure
- [x] Orion-LD sync webhook (/notify → PostGIS)
- [x] Custom @context (/ngsi-ld/cue-context.jsonld)
- [x] K8s manifests
- [x] CI/CD (GitHub Actions → GHCR)

## Pendiente (Fases 2+)

- Frontend IIFE
- ETL ROPO/Fertilizantes (SCD Tipo 2)
- Motor de reglas de negocio
- Anti-Corruption Layer (NGSI-LD → XSD SIEX)
- Integración B2B2G (SITNA, firma XAdES/CAdES, REA)
- Máquina de estados de envío

## Estructura

```
nkz-module-cue/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── migrations/
│   │   └── 001_create_cue_recinto_sigpac.sql
│   ├── tests/
│   │   └── test_api.py
│   └── app/
│       ├── cue_api.py
│       ├── auth_middleware.py
│       ├── orion_client.py
│       ├── orion_sync.py
│       └── common/
│           └── tenant_utils.py
├── k8s/
│   └── backend-deployment.yaml
├── manifest.json
└── README.md
```

## Licencia

AGPL-3.0
