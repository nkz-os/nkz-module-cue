# nkz-module-cue — Cuaderno de Campo de Explotación

Módulo SIEX del ecosistema Nekazari. Implementa el **Cuaderno de Explotación Único** conforme al Real Decreto 1054/2022 para explotaciones agrícolas en España.

## Estado

**Fase 1 — Backend funcional.** API REST con CRUD NGSI-LD sobre Orion-LD y caché espacial PostGIS. Sin frontend todavía.

## Arquitectura

```
Agricultor / App → API REST (Flask) → Orion-LD (lectura/escritura NGSI-LD)
                                     → PostGIS (solo lectura espacial)

                    Orion-LD → suscripción → /notify → PostGIS (caché geometrías)
```

- **Orion-LD** es la fuente de verdad de todas las entidades del cuaderno (AgriFarm, AgriParcel, AgriCropDeclaration, SigpacEnclosure)
- **PostGIS** es una caché espacial de solo lectura para las geometrías de los recintos SIGPAC. Se puebla exclusivamente mediante webhook de suscripción desde Orion-LD. **La API nunca escribe directamente en PostGIS.**
- **API Flask** actúa como pasarela: valida, construye payloads NGSI-LD y escribe en Orion-LD. Para consultas espaciales, lee de PostGIS.

## Modelo de datos (entidades NGSI-LD)

```
AgriFarm (Explotación)
  └─1:N─▶ AgriParcel (Unidad de producción)
            └─1:N─▶ AgriCropDeclaration (Línea de declaración)
                      └─1:N─▶ SigpacEnclosure (Recinto SIGPAC) ◀── geometría en PostGIS
```

| Entidad | Tipo NGSI-LD | Origen |
|---------|-------------|--------|
| `AgriFarm` | SDM (FIWARE Smart Data Model) | `dataModel.Agrifood/AgriFarm` |
| `AgriParcel` | SDM | `dataModel.Agrifood/AgriParcel` |
| `AgriCropDeclaration` | Custom (CUE) | `@context` propio del módulo |
| `SigpacEnclosure` | Custom (CUE) | `@context` propio del módulo, geometría en PostGIS |

El `@context` custom se sirve en `/ngsi-ld/cue-context.jsonld` y define los atributos específicos del cuaderno de campo español.

## API REST — Endpoints

Todos bajo `/api/modules/cue`. Autenticación JWT requerida (`@require_auth`). El tenant se extrae de la cabecera `X-Tenant-ID` (establecida por el API Gateway).

### Explotaciones (AgriFarm)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/explotaciones?municipio=&nombre=` | Listar explotaciones del tenant. Filtros opcionales por municipio y nombre |
| `POST` | `/explotaciones` | Crear explotación |
| `GET` | `/explotaciones/<id>` | Obtener explotación |
| `PUT` | `/explotaciones/<id>` | Actualizar explotación |
| `DELETE` | `/explotaciones/<id>` | Baja lógica (isActive=false) |

### Unidades de producción (AgriParcel)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/explotaciones/<id>/parcelas` | Listar parcelas de una explotación |
| `POST` | `/parcelas` | Crear parcela |
| `GET` | `/parcelas/<id>` | Obtener parcela |
| `PUT` | `/parcelas/<id>` | Actualizar parcela |
| `DELETE` | `/parcelas/<id>` | Baja lógica |

### Líneas de declaración (AgriCropDeclaration)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/parcelas/<id>/declaraciones` | Listar declaraciones de una parcela |
| `POST` | `/declaraciones` | Crear declaración |
| `POST` | `/declaraciones/<id>/duplicar` | Duplicar declaración para nueva campaña |
| `GET` | `/declaraciones/<id>` | Obtener declaración |
| `PUT` | `/declaraciones/<id>` | Actualizar declaración |
| `DELETE` | `/declaraciones/<id>` | Baja lógica |

### Recintos SIGPAC (SigpacEnclosure)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/declaraciones/<id>/recintos` | Listar recintos con geometrías GeoJSON (desde PostGIS) |
| `POST` | `/recintos` | Crear recinto individual |
| `POST` | `/recintos/batch` | Crear múltiples recintos en lote |
| `GET` | `/recintos/<id>` | Obtener recinto con geometría GeoJSON |
| `PUT` | `/recintos/<id>` | Actualizar recinto |
| `DELETE` | `/recintos/<id>` | Baja lógica |

### Infraestructura (rutas raíz, sin prefijo)

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| `GET` | `/health` | No | Health check para K8s |
| `GET` | `/ngsi-ld/cue-context.jsonld` | No | `@context` JSON-LD para entidades custom |
| `POST` | `/notify` | No | Webhook de suscripción Orion-LD → PostGIS |

## Ejemplos de uso

### Crear una explotación

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
    "coordenadas": [-1.6, 42.1]
  }'
```

### Crear recintos en lote

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

### Duplicar una declaración para la campaña siguiente

```bash
curl -X POST https://nkz.robotika.cloud/api/modules/cue/declaraciones/abc123/duplicar \
  -H "Authorization: Bearer <jwt>" \
  -H "X-Tenant-ID: mi-explotacion" \
  -H "Content-Type: application/json" \
  -d '{"campanya": 2026}'
```

### Filtrar explotaciones por municipio

```bash
curl "https://nkz.robotika.cloud/api/modules/cue/explotaciones?municipio=Tudela" \
  -H "Authorization: Bearer <jwt>" \
  -H "X-Tenant-ID: mi-explotacion"
```

## Estructura del proyecto

```
nkz-module-cue/
├── manifest.json              # Registro del módulo en Nekazari
├── README.md                  # Este documento
├── MANUAL.md                  # Manual de uso en castellano
├── backend/
│   ├── Dockerfile             # Python 3.11-alpine, psycopg2
│   ├── requirements.txt       # Flask + psycopg2 + PyJWT + requests
│   ├── pytest.ini
│   ├── migrations/
│   │   └── 001_create_cue_recinto_sigpac.sql
│   ├── tests/
│   │   └── test_api.py
│   └── app/
│       ├── cue_api.py         # Aplicación Flask + 27 rutas
│       ├── auth_middleware.py  # Decorador @require_auth (confía en API Gateway)
│       ├── orion_client.py    # Cliente NGSI-LD CRUD (Orion-LD)
│       ├── orion_sync.py      # Webhook /notify → PostGIS
│       └── common/
│           └── tenant_utils.py # Normalización y validación de tenant_id
├── k8s/
│   └── backend-deployment.yaml
├── .github/workflows/
│   └── build-push.yml
└── .gitignore
```

## Requisitos para despliegue

- **PostGIS** habilitado en la instancia TimescaleDB del cluster (`CREATE EXTENSION IF NOT EXISTS postgis`)
- **Orion-LD** en ejecución (ya en producción)
- **API Gateway** con rutas:
  - `/api/modules/cue/*` → `cue-backend-service:5000`
  - `/ngsi-ld/cue-context.jsonld` → `cue-backend-service:5000`
- **Suscripción Orion-LD** para entidades `SigpacEnclosure` → `http://cue-backend-service:5000/notify`
- **Variables de entorno** (desde ConfigMap/Secrets):
  - `POSTGRES_URL` (desde `postgresql-secret`)
  - `ORION_URL` (por defecto `http://orion-service:1026`)
  - `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `JWT_AUDIENCE`
  - `CONTEXT_URL`, `CUE_CONTEXT_URL`

## Fases de desarrollo

| Fase | Alcance | Estado |
|------|---------|--------|
| **1. Fundación** | API CRUD NGSI-LD, caché PostGIS, auth, K8s, CI/CD | ✅ Completada |
| **2. Core** | Motor de reglas, ETL ROPO/Fertilizantes, serializador XSD | Pendiente |
| **3. Frontend** | Módulo IIFE, formularios, mapa Cesium, selectores | Pendiente |
| **4. Integración** | Cliente SITNA, firma XAdES/CAdES, REA, máquina de estados | Pendiente |
| **5. Auditoría** | Revisión de seguridad completa | Pendiente |

## Licencia

AGPL-3.0. Copyright © Nekazari — robotika.cloud.

Potenciado por FIWARE Smart Data Models y el estándar NGSI-LD (ETSI ISG CIM).
