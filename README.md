# nkz-module-cue — Cuaderno de Campo de Explotación (CUE) / Field Record Book

[![Backend](https://img.shields.io/badge/backend-%E2%9C%85%20Phase%204-brightgreen)]()
[![Frontend](https://img.shields.io/badge/frontend-%E2%9C%85%20Phase%203-brightgreen)]()
[![CI](https://img.shields.io/badge/CI-passing-brightgreen)]()
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue)]()
[![FIWARE](https://img.shields.io/badge/FIWARE-NGSI--LD-%23E60005)]()

**SIEX-compliant digital farm record book for Spain** — implements the *Cuaderno de Explotacion Unico* mandated by Real Decreto 1054/2022 for all Spanish agricultural holdings. Part of the [Nekazari](https://github.com/nkz-os) modular FIWARE platform.

Written in English, field-facing interfaces in Spanish.

---

## Architecture

The module follows the **NGSI-LD Source-of-Truth Architecture (SOTA)** pattern:

```
                    ┌──────────────────────────────────────────┐
                    │           End User (Farmer / API)        │
                    └────────────────────┬─────────────────────┘
                                         │ HTTPS
                                         ▼
                ┌──────────────────────────────────────────────┐
                │           API Gateway (ingress)              │
                │      https://nkz.robotika.cloud              │
                │   routes /api/modules/cue/*  →  CUE Backend  │
                └────────────────────┬─────────────────────────┘
                                     │
                                     ▼
           ┌──────────────────────────────────────────────────┐
           │              CUE Backend (Flask :5000)           │
           │                                                   │
           │  ┌──────────┐  ┌───────────┐  ┌──────────────┐   │
           │  │  Auth     │  │ Orion-LD  │  │  PostGIS     │   │
           │  │  JWT      │  │ Client    │  │  Reader      │   │
           │  └──────────┘  └─────┬─────┘  └──────┬───────┘   │
           └──────────────────────┼────────────────┼───────────┘
                                  │                │
                    ┌─────────────▼──────┐   ┌─────▼──────────┐
                    │    Orion-LD        │   │    PostGIS      │
                    │  (Context Broker)  │   │ (Spatial Cache) │
                    │  Source of Truth   │   │ Read-only       │
                    │  for all entities  │   │ Geometry index  │
                    └─────────┬──────────┘   └────────┬────────┘
                              │                       │
                              └────── subscribe ──────┘
                                  POST /notify (webhook)
```

### Data flow principles

1. **All writes** go through the CUE Backend API which validates and creates NGSI-LD entities in **Orion-LD** (the canonical source of truth).
2. **SigpacEnclosure geometries** are synced to **PostGIS** via an Orion-LD subscription webhook (`POST /notify`) for efficient spatial queries.
3. **Spatial reads** (GeoJSON geometry queries) hit PostGIS directly for performance; all other reads query Orion-LD.
4. The **API Gateway** terminates HTTPS, injects the tenant context via `X-Tenant-ID`, and forwards to the backend service.

---

## Entity Model

```
AgriFarm (Explotacion Agricola)
 │
 ├── 1:N ── AgriParcel (Unidad de Produccion)
 │            │
 │            └── 1:N ── AgriCropDeclaration (Linea de Declaracion)
 │                         │
 │                         └── 1:N ── SigpacEnclosure (Recinto SIGPAC)
 │                                        └── geometry synced to PostGIS
 │
 ├── 1:N ── AgriPestTreatment (Tratamiento Fitosanitario)
 │            └── references ROPO catalog (via numero_registro)
 │
 ├── 1:N ── AgriFertilizerApplication (Aplicacion de Fertilizante)
 │            └── references Fertilizantes catalog
 │
 └── (future: AgriIrrigation, AgriHarvest, AgriFertilizationPlan, ...)
```

### NGSI-LD entity catalog

| Entity | NGSI-LD Type | Source | Status |
|--------|-------------|--------|--------|
| `AgriFarm` | `https://.../AgriFarm` | FIWARE Smart Data Model | ✅ |
| `AgriParcel` | `https://.../AgriParcel` | FIWARE Smart Data Model | ✅ |
| `AgriCropDeclaration` | `https://.../AgriCropDeclaration` | Custom (CUE) | ✅ |
| `SigpacEnclosure` | `https://.../SigpacEnclosure` | Custom (CUE) + PostGIS | ✅ |
| `AgriPestTreatment` | `https://.../AgriPestTreatment` | FIWARE Smart Data Model | ✅ |
| `AgriFertilizerApplication` | `https://.../AgriFertilizerApplication` | FIWARE Smart Data Model | ✅ |

Custom entity types and attributes are defined in the module-specific `@context` served at `GET /ngsi-ld/cue-context.jsonld`.

---

## Quick Start

### Prerequisites

- Nekazari platform with Orion-LD and PostGIS enabled
- JWT token for a valid tenant (Farmer or TenantAdmin role)
- `X-Tenant-ID` header set to the tenant identifier

### Create a farm

```bash
curl -X POST https://nkz.robotika.cloud/api/modules/cue/explotaciones \
  -H "Authorization: Bearer <jwt>" \
  -H "X-Tenant-ID: mi-explotacion" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Finca Los Olivos",
    "municipio": "Tudela",
    "provincia": "Navarra",
    "nif": "12345678Z",
    "coordenadas": [-1.6, 42.1],
    "regepa": "NA12345"
  }'
```

### Create enclosures in batch

```bash
curl -X POST https://nkz.robotika.cloud/api/modules/cue/recintos/batch \
  -H "Authorization: Bearer <jwt>" \
  -H "X-Tenant-ID: mi-explotacion" \
  -H "Content-Type: application/json" \
  -d '{
    "recintos": [
      {
        "referencia_sigpac": "31:230:0:0:0:243:9003",
        "superficie_admisible_ha": 4.5,
        "declaracion_id": "abc123",
        "geometria": {
          "type": "Polygon",
          "coordinates": [[[-1.6, 42.1], [-1.59, 42.1], [-1.59, 42.11], [-1.6, 42.11], [-1.6, 42.1]]]
        }
      }
    ]
  }'
```

### Validate records before submission

```bash
curl -X POST https://nkz.robotika.cloud/api/modules/cue/validate \
  -H "Authorization: Bearer <jwt>" \
  -H "X-Tenant-ID: mi-explotacion" \
  -H "Content-Type: application/json" \
  -d '{"explotacion_id": "<farm_id>"}'
```

Detailed usage instructions: [MANUAL.md](MANUAL.md) (Spanish).

---

## API Overview

All endpoints under `/api/modules/cue`. Authentication: JWT Bearer + `X-Tenant-ID`.

| Resource | Methods | Description |
|----------|---------|-------------|
| `/explotaciones` | GET, POST | List / create farms |
| `/explotaciones/<id>` | GET, PUT, DELETE | Read / update / soft-delete farm |
| `/explotaciones/<id>/parcelas` | GET | List parcels by farm |
| `/parcelas` | POST | Create parcel |
| `/parcelas/<id>` | GET, PUT, DELETE | Read / update / soft-delete parcel |
| `/parcelas/<id>/declaraciones` | GET | List declarations by parcel |
| `/declaraciones` | POST | Create declaration |
| `/declaraciones/<id>` | GET, PUT, DELETE | Read / update / soft-delete |
| `/declaraciones/<id>/duplicar` | POST | Duplicate for new campaign year |
| `/declaraciones/<id>/recintos` | GET | List enclosures with GeoJSON geometries |
| `/recintos` | POST | Create single enclosure |
| `/recintos/batch` | POST | Batch-create enclosures |
| `/recintos/<id>` | GET, PUT, DELETE | Read / update / soft-delete enclosure |
| `/tratamientos` | GET, POST | List / create phytosanitary treatments |
| `/tratamientos/<id>` | GET, PUT, DELETE | Read / update / soft-delete treatment |
| `/fertilizaciones` | GET, POST | List / create fertilizer applications |
| `/fertilizaciones/<id>` | GET, PUT, DELETE | Read / update / soft-delete application |
| `/productos-ropo` | GET | List ROPO catalog (phytosanitary products) |
| `/productos-ropo/<num>` | GET | Lookup product by registration number |
| `/productos-fertilizantes` | GET | List fertilizer catalog |
| `/productos-fertilizantes/<num>` | GET | Lookup fertilizer by registration number |
| `/endpoints-autonomicos` | GET | List autonomous community IUWS endpoints |
| `/endpoints-autonomicos/<codigo>` | GET | Lookup endpoint by province code |
| `/validate` | POST | Validate all records against SIEX business rules |
| `/health` | GET | Health check (no auth, for K8s probes) |

### Infrastructure routes (no `/api/modules/cue` prefix)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ngsi-ld/cue-context.jsonld` | Custom `@context` for CUE entity types |
| POST | `/notify` | Orion-LD subscription webhook → PostGIS sync |

---

## Implementation Phases

| Phase | Scope | Status |
|-------|-------|--------|
| **1. Foundation** | NGSI-LD CRUD API, PostGIS spatial cache, JWT auth, K8s deployment, CI/CD | ✅ Complete |
| **2. Core** | Business rules engine, ETL ROPO+Fertilizantes (SCD Type 2), POST /validate, SIEX vocabulary | ✅ Complete |
| **3. Frontend** | React IIFE module, entity forms, CesiumJS map, SIGPAC enclosure layer, catalog selectors | ✅ Complete |
| **4. Integration** | IUWS client (REA download + CUE submit + status polling), Anti-Corruption Layer (NGSI-LD→XML/XSD), state machine (10 states), AutoFirma ephemeral cert widget, polling worker | ✅ Complete (pending external trámites) |
| **5. Audit** | Full security review, XSD oficiales FEGA, sandbox IUWS, production deployment with real certificates | 🔜 Pending external dependencies |

---

## Project Structure

```
nkz-module-cue/
├── manifest.json              # Module registration (id: "cue")
├── README.md                  # This file
├── MANUAL.md                  # Spanish user manual
├── backend/
│   ├── Dockerfile             # Python 3.11-alpine
│   ├── requirements.txt
│   ├── migrations/            # 001, 002, 003 SQL migrations
│   ├── tests/
│   └── app/
│       ├── cue_api.py         # Flask application (40+ routes)
│       ├── auth_middleware.py # JWT validation decorator
│       ├── orion_client.py    # NGSI-LD CRUD wrapper
│       ├── orion_sync.py      # Webhook /notify → PostGIS
│       └── common/
├── src/                       # Frontend (React IIFE module)
│   ├── moduleEntry.ts
│   ├── components/            # ExplotacionForm, RecintoForm, TratamientoForm, etc.
│   ├── services/              # cueApi.ts
│   ├── slots/                 # CUE viewer slot registration
│   └── locales/               # i18n (Spanish, English)
├── k8s/
│   └── backend-deployment.yaml
├── .github/workflows/
│   └── build-push.yml         # CI: test + Docker build/push to GHCR
└── vite.config.ts             # IIFE bundle configuration
```

---

## Deployment Requirements

- **PostGIS** extension in TimescaleDB
- **Orion-LD** Context Broker (running in cluster)
- **API Gateway** routes: `/api/modules/cue/*` → `cue-backend-service:5000`
- **Orion-LD subscription**: `SigpacEnclosure` → `http://cue-backend-service:5000/notify`
- **Env vars**: `POSTGRES_URL`, `ORION_URL`, `KEYCLOAK_URL`, `CONTEXT_URL`, `CUE_CONTEXT_URL`

Internal service URLs (cluster-internal, adjust per deployment):
- `ORION_URL`: `http://orion-ld-service:1026`
- `CUE Backend`: `cue-backend-service:5000`
- `CONTEXT_URL`: `http://api-gateway-service:5000/ngsi-ld-context.jsonld`

---

## License

**AGPL-3.0** — Copyright (c) Nekazari / robotika.cloud.

Powered by [FIWARE](https://www.fiware.org) Smart Data Models and the NGSI-LD standard (ETSI ISG CIM).

Built for the Spanish SIEX (Sistema de Informacion de Explotaciones Agricolas) ecosystem, compliant with:

- **Real Decreto 1054/2022** — Digital farm record book (CUE)
- **Real Decreto 1048/2022** — Fertilization planning
- **Orden APA/.../2024** — SIEX technical specifications (v9+)
