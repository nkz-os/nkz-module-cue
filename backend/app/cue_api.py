#!/usr/bin/env python3
# =============================================================================
# CUE API — Cuaderno de Campo (SIEX Spain) — NGSI-LD CRUD + PostGIS Spatial
# =============================================================================
# Phase 1 backend-only. Orion-LD source of truth, PostGIS spatial cache.
# Flask + psycopg2 + Orion-LD client wrappers.

import os
import logging
import json
from datetime import date
import psycopg2
import psycopg2.extras
from flask import Flask, Blueprint, jsonify, request
from flask_cors import CORS

from .auth_middleware import require_auth, get_current_tenant
from .orion_client import (
    _entity_uri, _property, _relationship, _geo_property,
    create_entity, get_entity, query_entities, update_entity, delete_entity,
)
from .orion_sync import process_notification, POSTGRES_URL

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CORS origins
# ---------------------------------------------------------------------------
CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app, origins=CORS_ORIGINS.split(',') if CORS_ORIGINS != '*' else '*',
     supports_credentials=True)


# ===========================================================================
# ROOT ROUTES (before Blueprint, no prefix)
# ===========================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check for K8s probes."""
    return jsonify({'status': 'healthy', 'service': 'cue-api'})


@app.route('/ngsi-ld/cue-context.jsonld', methods=['GET'])
def cue_context():
    """JSON-LD @context defining custom CUE entities."""
    context = {
        "@context": {
            "AgriCropDeclaration": "urn:ngsi-ld:AgriCropDeclaration",
            "SigpacEnclosure": "urn:ngsi-ld:SigpacEnclosure",

            "AgriPestTreatment": "https://smart-data-models.github.io/dataModel.Agrifood/AgriPestTreatment/context.jsonld",
            "AgriFertilizerApplication": "https://smart-data-models.github.io/dataModel.Agrifood/AgriFertilizerApplication/context.jsonld",
            "AgriIrrigation": "https://nekazari.robotika.cloud/ngsi-ld/cue/AgriIrrigation",
            "AgriHarvest": "https://nekazari.robotika.cloud/ngsi-ld/cue/AgriHarvest",
            "AgriFertilizationPlan": "https://nekazari.robotika.cloud/ngsi-ld/cue/AgriFertilizationPlan",
            "AgriSoilCharacterization": "https://nekazari.robotika.cloud/ngsi-ld/cue/AgriSoilCharacterization",
            "AgriEcoRegime": "https://nekazari.robotika.cloud/ngsi-ld/cue/AgriEcoRegime",

            "campaignYear": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:AgriCropDeclaration:campaignYear"
            },
            "cifEntidadHabilitada": {
                "@type": "Property"
            },
            "declaredCrop": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:AgriCropDeclaration:declaredCrop"
            },
            "declaredArea": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:AgriCropDeclaration:declaredArea",
                "unitCode": "HA"
            },
            "sigpacReference": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:SigpacEnclosure:sigpacReference"
            },
            "eligibleArea": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:SigpacEnclosure:eligibleArea",
                "unitCode": "HA"
            },
            "version": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:version"
            },
            "parentId": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:parentId"
            },
            "regepa": {
                "@type": "Property"
            },
            "tenantId": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:tenantId"
            },

            # Phase 2 — Anexo V attributes
            "productoROPORef": {"@type": "Property"},
            "dosisAplicada": {"@type": "Property", "unitCode": "L/ha"},
            "plagaObjeto": {"@type": "Property"},
            "equipoAplicacion": {"@type": "Property"},
            "aplicador": {"@type": "Property"},
            "horaAplicacion": {"@type": "Property"},
            "tipoFertilizante": {"@type": "Property"},
            "dosisFertilizante": {"@type": "Property", "unitCode": "kg/ha"},
            "contenidoN": {"@type": "Property", "unitCode": "%"},
            "contenidoP": {"@type": "Property", "unitCode": "%"},
            "volumenRiego": {"@type": "Property", "unitCode": "m3"},
            "sistemaRiego": {"@type": "Property"},
            "produccionCosecha": {"@type": "Property", "unitCode": "kg"},
            "calidadCosecha": {"@type": "Property"},
            "destinoCosecha": {"@type": "Property"},
            "tipoAbono": {"@type": "Property"},
            "dosisAbono": {"@type": "Property", "unitCode": "kg/ha"},
            "texturaSuelo": {"@type": "Property"},
            "phSuelo": {"@type": "Property"},
            "materiaOrganica": {"@type": "Property", "unitCode": "%"},
            "ecoregimenTipo": {"@type": "Property"},

            "hasAgriParcel": {
                "@type": "@id",
                "@id": "urn:ngsi-ld:AgriCropDeclaration:hasAgriParcel"
            },
            "hasAgriCropDeclaration": {
                "@type": "@id",
                "@id": "urn:ngsi-ld:AgriParcel:hasAgriCropDeclaration"
            },
            "hasSigpacEnclosure": {
                "@type": "@id",
                "@id": "urn:ngsi-ld:AgriCropDeclaration:hasSigpacEnclosure"
            },
            "hasAgriFarm": {
                "@type": "@id",
                "@id": "urn:ngsi-ld:AgriParcel:hasAgriFarm"
            }
        }
    }
    return jsonify(context)


@app.route('/notify', methods=['POST'])
def notify():
    """
    Process Orion-LD subscription notification.
    Receives {id, subscriptionId, data: [entities]}.
    """
    body = request.get_json(silent=True)
    if not body or 'data' not in body:
        return jsonify({'status': 'error', 'message': 'Cuerpo de notificación inválido'}), 400

    entities = body.get('data', [])
    summary = process_notification(body)

    return jsonify({
        'status': 'ok',
        'processed': summary.get('processed', len(entities)),
        'synced': summary.get('synced', 0),
        'errors': summary.get('errors', 0),
    })


# ===========================================================================
# Blueprint: /api/modules/cue
# ===========================================================================

cue_bp = Blueprint('cue', __name__, url_prefix='/api/modules/cue')


# ---- Helpers ---------------------------------------------------------------

def _tenant_filter():
    """Build NGSI-LD query filter string for current tenant."""
    tenant = get_current_tenant()
    return f'tenantId=="{tenant}"'


def get_pg_conn():
    """Get a psycopg2 connection with RealDictCursor."""
    conn = psycopg2.connect(POSTGRES_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def _validate_polygon(geom):
    """Validate a GeoJSON Polygon. Returns (bool, error_message)."""
    if not isinstance(geom, dict):
        return False, 'la geometría debe ser un objeto GeoJSON'

    if geom.get('type') != 'Polygon':
        return False, 'el tipo de geometría debe ser Polygon'

    coords = geom.get('coordinates')
    if not isinstance(coords, list) or not coords:
        return False, 'las coordenadas deben ser un array no vacío'

    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < 4:
        return False, 'el polígono debe tener al menos 4 puntos (anillo cerrado)'

    if ring[0] != ring[-1]:
        return False, 'el anillo exterior del polígono debe estar cerrado'

    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return False, 'cada coordenada debe ser [lon, lat]'
        lon, lat = pt[0], pt[1]
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            return False, 'las coordenadas deben ser numéricas'
        if abs(lat) > 90:
            return False, f'latitud {lat} fuera de rango [-90, 90]'
        if abs(lon) > 180:
            return False, f'longitud {lon} fuera de rango [-180, 180]'

    return True, ''


def _generate_id():
    """Generate a short hex entity ID."""
    return os.urandom(8).hex()


def _get_iuws_endpoint(codigo_provincia):
    """Resolve IUWS endpoint URL for a given province code."""
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT iuws_base_url, sandbox_url, comunidad "
            "FROM cue_endpoints_autonomicos "
            "WHERE codigo_provincia = %s AND activo = true",
            (codigo_provincia,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error resolving IUWS endpoint for provincia {codigo_provincia}: {e}")
        return None


# ===========================================================================
# AgriFarm routes
# ===========================================================================

@cue_bp.route('/explotaciones', methods=['GET'])
@require_auth
def list_explotaciones():
    """List AgriFarm entities for current tenant with optional filters."""
    tenant = get_current_tenant()
    q_parts = [_tenant_filter(), 'isActive!=false']

    municipio = request.args.get('municipio')
    if municipio:
        q_parts.append(f'address.addressLocality=="{municipio}"')

    nombre = request.args.get('nombre')
    if nombre:
        q_parts.append(f'name~="{nombre}"')

    q = ';'.join(q_parts)
    status, data = query_entities('AgriFarm', tenant, {'q': q})
    if status != 200:
        return jsonify({'error': data}), status
    return jsonify(data)


# ===========================================================================
# IUWS endpoint routing (infrastructure configuration)
# ===========================================================================


@cue_bp.route('/endpoints-autonomicos', methods=['GET'])
@require_auth
def list_endpoints_autonomicos():
    """List all configured IUWS endpoints."""
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT codigo_provincia, comunidad, iuws_base_url, sandbox_url, activo "
            "FROM cue_endpoints_autonomicos "
            "ORDER BY codigo_provincia"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        logger.error(f"Error listing autonomic endpoints: {e}")
        return jsonify({'error': 'Error al consultar endpoints autonómicos'}), 500


@cue_bp.route('/endpoints-autonomicos/<codigo_provincia>', methods=['GET'])
@require_auth
def get_endpoint_autonomico(codigo_provincia):
    """Get IUWS endpoint for a specific province code."""
    result = _get_iuws_endpoint(codigo_provincia)
    if result:
        return jsonify(result), 200
    return jsonify({'error': f'No hay endpoint configurado para la provincia {codigo_provincia}'}), 404


@cue_bp.route('/explotaciones', methods=['POST'])
@require_auth
def create_explotacion():
    """Create AgriFarm entity in Orion-LD."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    farm_id = _generate_id()
    attributes = {
        'name': _property(body.get('nombre', '')),
        'description': _property(body.get('descripcion', '')),
        'contactPoint': _property(body.get('contacto', '')),
        'address': _property(body.get('direccion', '')),
        'version': _property(1),
        'isActive': _property(True),
    }

    if body.get('regepa'):
        attributes['regepa'] = _property(body['regepa'])
    if body.get('cif_entidad_habilitada'):
        attributes['cifEntidadHabilitada'] = _property(body['cif_entidad_habilitada'])

    attributes['tenantId'] = _property(tenant)

    municipio = body.get('municipio', '')
    provincia = body.get('provincia', '')
    partes = [p for p in [municipio, provincia] if p]
    if partes:
        attributes['address'] = _property(', '.join(partes))

    coordenadas = body.get('coordenadas')
    if coordenadas and len(coordenadas) == 2:
        attributes['location'] = _geo_property({
            'type': 'Point',
            'coordinates': [coordenadas[0], coordenadas[1]],
        })

    nif = body.get('nif')
    if nif:
        attributes['ownedBy'] = _relationship(
            _entity_uri('Person', tenant, nif)
        )

    status, resp = create_entity('AgriFarm', tenant, farm_id, attributes)
    if status not in (201, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('AgriFarm', tenant, farm_id)
    return jsonify(entity), 201


@cue_bp.route('/explotaciones/<farm_id>', methods=['GET'])
@require_auth
def get_explotacion(farm_id):
    """Get single AgriFarm."""
    tenant = get_current_tenant()
    status, data = get_entity('AgriFarm', tenant, farm_id)
    if status != 200:
        return jsonify({'error': data}), status
    return jsonify(data)


@cue_bp.route('/explotaciones/<farm_id>', methods=['PUT'])
@require_auth
def update_explotacion(farm_id):
    """Update AgriFarm fields."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    attributes = {}

    if 'nombre' in body:
        attributes['name'] = _property(body['nombre'])
    if 'descripcion' in body:
        attributes['description'] = _property(body['descripcion'])
    if 'contacto' in body:
        attributes['contactPoint'] = _property(body['contacto'])

    if 'regepa' in body:
        attributes['regepa'] = _property(body['regepa'])
    if 'cif_entidad_habilitada' in body:
        attributes['cifEntidadHabilitada'] = _property(body['cif_entidad_habilitada'])

    municipio = body.get('municipio')
    provincia = body.get('provincia')
    if municipio is not None or provincia is not None:
        partes = []
        if municipio:
            partes.append(municipio)
        if provincia:
            partes.append(provincia)
        attributes['address'] = _property(', '.join(partes))

    coordenadas = body.get('coordenadas')
    if coordenadas and len(coordenadas) == 2:
        attributes['location'] = _geo_property({
            'type': 'Point',
            'coordinates': [coordenadas[0], coordenadas[1]],
        })

    if 'nif' in body:
        nif = body['nif']
        if nif:
            attributes['ownedBy'] = _relationship(
                _entity_uri('Person', tenant, nif)
            )
        else:
            attributes['ownedBy'] = _relationship('')

    if not attributes:
        return jsonify({'error': 'No hay campos para actualizar'}), 400

    status, resp = update_entity('AgriFarm', tenant, farm_id, attributes)
    if status not in (200, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('AgriFarm', tenant, farm_id)
    return jsonify(entity)


@cue_bp.route('/explotaciones/<farm_id>', methods=['DELETE'])
@require_auth
def delete_explotacion(farm_id):
    """Soft-delete AgriFarm (isActive=false)."""
    tenant = get_current_tenant()
    status, resp = delete_entity('AgriFarm', tenant, farm_id)
    if status not in (200, 204):
        return jsonify({'error': resp}), status
    return jsonify({'status': 'deleted', 'id': farm_id})


# ===========================================================================
# AgriParcel routes
# ===========================================================================

@cue_bp.route('/explotaciones/<farm_id>/parcelas', methods=['GET'])
@require_auth
def list_parcelas_by_farm(farm_id):
    """Query AgriParcel by hasAgriFarm relationship + isActive."""
    tenant = get_current_tenant()
    farm_uri = _entity_uri('AgriFarm', tenant, farm_id)
    q = f'{_tenant_filter()};hasAgriFarm=="{farm_uri}";isActive!=false'
    status, data = query_entities('AgriParcel', tenant, {'q': q})
    if status != 200:
        return jsonify({'error': data}), status
    return jsonify(data)


@cue_bp.route('/parcelas', methods=['POST'])
@require_auth
def create_parcela():
    """Create AgriParcel entity in Orion-LD."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    parcel_id = _generate_id()
    attributes = {
        'name': _property(body.get('nombre', '')),
        'tenantId': _property(tenant),
        'version': _property(1),
        'isActive': _property(True),
    }

    if 'area_ha' in body:
        attributes['area'] = _property(body['area_ha'])
    if 'cultivo' in body:
        attributes['cropType'] = _property(body['cultivo'])
    if 'estado' in body:
        attributes['state'] = _property(body['estado'])
    if 'riego' in body:
        attributes['irrigation'] = _property(body['riego'])

    explotacion_id = body.get('explotacion_id')
    if explotacion_id:
        attributes['hasAgriFarm'] = _relationship(
            _entity_uri('AgriFarm', tenant, explotacion_id)
        )

    status, resp = create_entity('AgriParcel', tenant, parcel_id, attributes)
    if status not in (201, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('AgriParcel', tenant, parcel_id)
    return jsonify(entity), 201


@cue_bp.route('/parcelas/<parcel_id>', methods=['GET'])
@require_auth
def get_parcela(parcel_id):
    """Get single AgriParcel."""
    tenant = get_current_tenant()
    status, data = get_entity('AgriParcel', tenant, parcel_id)
    if status != 200:
        return jsonify({'error': data}), status
    return jsonify(data)


@cue_bp.route('/parcelas/<parcel_id>', methods=['PUT'])
@require_auth
def update_parcela(parcel_id):
    """Update AgriParcel fields."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    attributes = {}

    field_map = {
        'nombre': 'name',
        'area_ha': 'area',
        'cultivo': 'cropType',
        'estado': 'state',
        'riego': 'irrigation',
    }

    for client_key, ld_key in field_map.items():
        if client_key in body:
            attributes[ld_key] = _property(body[client_key])

    if 'explotacion_id' in body:
        attributes['hasAgriFarm'] = _relationship(
            _entity_uri('AgriFarm', tenant, body['explotacion_id'])
        )

    if not attributes:
        return jsonify({'error': 'No hay campos para actualizar'}), 400

    status, resp = update_entity('AgriParcel', tenant, parcel_id, attributes)
    if status not in (200, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('AgriParcel', tenant, parcel_id)
    return jsonify(entity)


@cue_bp.route('/parcelas/<parcel_id>', methods=['DELETE'])
@require_auth
def delete_parcela(parcel_id):
    """Soft-delete AgriParcel."""
    tenant = get_current_tenant()
    status, resp = delete_entity('AgriParcel', tenant, parcel_id)
    if status not in (200, 204):
        return jsonify({'error': resp}), status
    return jsonify({'status': 'deleted', 'id': parcel_id})


# ===========================================================================
# AgriCropDeclaration routes
# ===========================================================================

@cue_bp.route('/parcelas/<parcel_id>/declaraciones', methods=['GET'])
@require_auth
def list_declaraciones_by_parcela(parcel_id):
    """Query AgriCropDeclaration by hasAgriParcel relationship."""
    tenant = get_current_tenant()
    parcel_uri = _entity_uri('AgriParcel', tenant, parcel_id)
    q = f'{_tenant_filter()};hasAgriParcel=="{parcel_uri}";isActive!=false'
    status, data = query_entities('AgriCropDeclaration', tenant, {'q': q})
    if status != 200:
        return jsonify({'error': data}), status
    return jsonify(data)


@cue_bp.route('/declaraciones', methods=['POST'])
@require_auth
def create_declaracion():
    """Create AgriCropDeclaration entity in Orion-LD."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    decl_id = _generate_id()
    attributes = {
        'campaignYear': _property(body.get('campanya', '')),
        'declaredCrop': _property(body.get('cultivo', '')),
        'tenantId': _property(tenant),
        'version': _property(1),
        'isActive': _property(True),
    }

    superficie = body.get('superficie_ha')
    if superficie is not None:
        attributes['declaredArea'] = _property(superficie)

    parcela_id = body.get('parcela_id')
    if parcela_id:
        attributes['hasAgriParcel'] = _relationship(
            _entity_uri('AgriParcel', tenant, parcela_id)
        )

    status, resp = create_entity('AgriCropDeclaration', tenant, decl_id, attributes)
    if status not in (201, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('AgriCropDeclaration', tenant, decl_id)
    return jsonify(entity), 201


@cue_bp.route('/declaraciones/<decl_id>', methods=['GET'])
@require_auth
def get_declaracion(decl_id):
    """Get single AgriCropDeclaration."""
    tenant = get_current_tenant()
    status, data = get_entity('AgriCropDeclaration', tenant, decl_id)
    if status != 200:
        return jsonify({'error': data}), status
    return jsonify(data)


@cue_bp.route('/declaraciones/<decl_id>', methods=['PUT'])
@require_auth
def update_declaracion(decl_id):
    """Update AgriCropDeclaration fields."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    attributes = {}

    field_map = {
        'campanya': 'campaignYear',
        'cultivo': 'declaredCrop',
        'superficie_ha': 'declaredArea',
    }

    for client_key, ld_key in field_map.items():
        if client_key in body:
            attributes[ld_key] = _property(body[client_key])

    if 'parcela_id' in body:
        attributes['hasAgriParcel'] = _relationship(
            _entity_uri('AgriParcel', tenant, body['parcela_id'])
        )

    if not attributes:
        return jsonify({'error': 'No hay campos para actualizar'}), 400

    status, resp = update_entity('AgriCropDeclaration', tenant, decl_id, attributes)
    if status not in (200, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('AgriCropDeclaration', tenant, decl_id)
    return jsonify(entity)


@cue_bp.route('/declaraciones/<decl_id>', methods=['DELETE'])
@require_auth
def delete_declaracion(decl_id):
    """Soft-delete AgriCropDeclaration."""
    tenant = get_current_tenant()
    status, resp = delete_entity('AgriCropDeclaration', tenant, decl_id)
    if status not in (200, 204):
        return jsonify({'error': resp}), status
    return jsonify({'status': 'deleted', 'id': decl_id})


@cue_bp.route('/declaraciones/<decl_id>/duplicar', methods=['POST'])
@require_auth
def duplicar_declaracion(decl_id):
    """Duplicate a crop declaration for a new campaign year."""
    tenant = get_current_tenant()
    data = request.json or {}

    # Get the original declaration
    status, original = get_entity('AgriCropDeclaration', tenant, decl_id)
    if status != 200:
        return jsonify({'error': f'Declaración no encontrada (status {status})'}), 404

    # Determine target campaign year
    nueva_campanya = data.get('campanya')
    if not nueva_campanya:
        campanya_actual = original.get('campaignYear')
        if isinstance(campanya_actual, dict):
            campanya_actual = campanya_actual.get('value', 2026)
        nueva_campanya = campanya_actual + 1

    # Build new declaration from original
    new_id = _generate_id()
    attributes = {
        "campaignYear": _property(nueva_campanya),
        "tenantId": _property(tenant),
        "version": _property(1),
        "isActive": _property(True),
    }

    # Copy crop and area if present
    for attr_key, ngsi_key in [
        ('declaredCrop', 'declaredCrop'),
        ('declaredArea', 'declaredArea'),
    ]:
        val = original.get(attr_key)
        if val is not None:
            attributes[ngsi_key] = _property(val if not isinstance(val, dict) else val.get('value', val))

    # Copy relationship to the same AgriParcel
    parcel_rel = original.get('hasAgriParcel')
    if parcel_rel:
        attributes['hasAgriParcel'] = {
            "type": "Relationship",
            "object": parcel_rel.get('object') if isinstance(parcel_rel, dict) else parcel_rel
        }

    status, result = create_entity('AgriCropDeclaration', tenant, new_id, attributes)
    if status in (200, 201):
        return jsonify({
            'id': new_id,
            'campanya': nueva_campanya,
            'duplicado_de': decl_id,
            'status': 'created'
        }), 201
    return jsonify({'error': f'Error al duplicar: {result}'}), status


# ===========================================================================
# SigpacEnclosure routes (spatial — PostGIS cache + Orion-LD)
# ===========================================================================

@cue_bp.route('/declaraciones/<decl_id>/recintos', methods=['GET'])
@require_auth
def list_recintos_by_declaracion(decl_id):
    """
    Query Orion-LD SigpacEnclosure by hasAgriCropDeclaration relationship
    and enrich each result with GeoJSON geometry from PostGIS cache.
    """
    tenant = get_current_tenant()
    decl_uri = _entity_uri('AgriCropDeclaration', tenant, decl_id)
    q = f'{_tenant_filter()};hasAgriCropDeclaration=="{decl_uri}";isActive!=false'
    status, data = query_entities('SigpacEnclosure', tenant, {'q': q})
    if status != 200:
        return jsonify({'error': data}), status

    if not data:
        return jsonify([])

    orion_ids = [e.get('id', '') for e in data if e.get('id')]
    if not orion_ids:
        return jsonify(data)

    conn = None
    cur = None
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        placeholders = ','.join('%s' for _ in orion_ids)
        cur.execute(f"""
            SELECT orion_entity_id, ST_AsGeoJSON(geometria) AS geometria_geojson
            FROM cue_recinto_sigpac
            WHERE orion_entity_id IN ({placeholders})
              AND tenant_id = %s
        """, (*orion_ids, tenant))
        geo_rows = cur.fetchall()

        geo_map = {}
        for row in geo_rows:
            oid = row['orion_entity_id']
            geojson_str = row['geometria_geojson']
            if geojson_str:
                geo_map[oid] = json.loads(geojson_str)

        for entity in data:
            eid = entity.get('id', '')
            if eid in geo_map:
                entity['geometria'] = geo_map[eid]

        return jsonify(data)

    except psycopg2.Error as e:
        logger.error(f"PostGIS query error for recintos: {e}")
        return jsonify(data)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@cue_bp.route('/recintos/batch', methods=['POST'])
@require_auth
def create_recintos_batch():
    """Create multiple SigpacEnclosure entities in one request."""
    data = request.json or {}
    recintos = data.get('recintos', [])
    if not recintos or not isinstance(recintos, list):
        return jsonify({'error': 'Se requiere un array "recintos" con al menos un elemento'}), 400

    tenant = get_current_tenant()
    results = []
    errors = []

    for i, recinto_data in enumerate(recintos):
        recinto_id = recinto_data.get('id') or _generate_id()
        geo = recinto_data.get('geometria', {})

        valid, err = _validate_polygon(geo)
        if not valid:
            errors.append({'index': i, 'error': f'Geometría inválida: {err}'})
            continue

        attributes = {
            "sigpacReference": _property(recinto_data.get('referencia_sigpac', '')),
            "eligibleArea": _property({
                "value": recinto_data.get('superficie_admisible_ha', 0),
                "unitCode": "HA"
            }),
            "location": _geo_property(geo),
            "tenantId": _property(tenant),
            "version": _property(1),
            "isActive": _property(True),
        }

        decl_id = recinto_data.get('declaracion_id')
        if decl_id:
            decl_uri = _entity_uri('AgriCropDeclaration', tenant, decl_id)
            attributes['hasAgriCropDeclaration'] = _relationship(decl_uri)

        status, result = create_entity('SigpacEnclosure', tenant, recinto_id, attributes)
        if status in (200, 201):
            results.append({'id': recinto_id, 'status': 'created'})
        else:
            errors.append({'index': i, 'id': recinto_id, 'error': str(result)})

    return jsonify({
        'total': len(recintos),
        'created': len(results),
        'errors': len(errors),
        'results': results,
        'error_details': errors if errors else None,
    }), 201 if results else 400


@cue_bp.route('/recintos', methods=['POST'])
@require_auth
def create_recinto():
    """
    Create SigpacEnclosure entity with GeoJSON Polygon in location.
    Also syncs geometry to PostGIS cache.
    """
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    location = body.get('location') or body.get('geometria')
    if not location:
        return jsonify({'error': 'Se requiere location o geometria (GeoJSON Polygon)'}), 400

    if not isinstance(location, dict):
        return jsonify({'error': 'location debe ser un objeto GeoJSON'}), 400

    valid, err = _validate_polygon(location)
    if not valid:
        return jsonify({'error': f'Geometría inválida: {err}'}), 400

    enclosure_id = _generate_id()
    attributes = {
        'sigpacReference': _property(body.get('referencia_sigpac', '')),
        'eligibleArea': _property(body.get('superficie_elegible', 0)),
        'location': _geo_property(location),
        'tenantId': _property(tenant),
        'version': _property(1),
        'isActive': _property(True),
    }

    declaracion_id = body.get('declaracion_id')
    if declaracion_id:
        attributes['hasAgriCropDeclaration'] = _relationship(
            _entity_uri('AgriCropDeclaration', tenant, declaracion_id)
        )

    status, resp = create_entity('SigpacEnclosure', tenant, enclosure_id, attributes)
    if status not in (201, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('SigpacEnclosure', tenant, enclosure_id)
    return jsonify(entity), 201


@cue_bp.route('/recintos/<enclosure_id>', methods=['GET'])
@require_auth
def get_recinto(enclosure_id):
    """
    Get SigpacEnclosure geometry from PostGIS cache.
    Falls back to Orion-LD if not found in PostGIS.
    """
    tenant = get_current_tenant()
    entity_uri = _entity_uri('SigpacEnclosure', tenant, enclosure_id)

    conn = None
    cur = None
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                orion_entity_id,
                tenant_id,
                ST_AsGeoJSON(geometria) AS geometria_geojson,
                created_at,
                updated_at
            FROM cue_recinto_sigpac
            WHERE orion_entity_id = %s
        """, (entity_uri,))
        row = cur.fetchone()

        if row:
            result = dict(row)
            geojson_str = result.pop('geometria_geojson', None)
            if geojson_str:
                result['geometria'] = json.loads(geojson_str)
            result['id'] = result.pop('orion_entity_id', entity_uri)
            return jsonify(result)

    except psycopg2.Error as e:
        logger.error(f"PostGIS query error for recinto {enclosure_id}: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

    # Fallback: get entity metadata from Orion-LD
    status, entity = get_entity('SigpacEnclosure', tenant, enclosure_id)
    if status != 200:
        return jsonify({'error': entity}), status
    return jsonify(entity)


@cue_bp.route('/recintos/<enclosure_id>', methods=['PUT'])
@require_auth
def update_recinto(enclosure_id):
    """Update SigpacEnclosure fields. Validates Polygon if geometria provided."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'El cuerpo de la solicitud es obligatorio'}), 400

    attributes = {}

    if 'referencia_sigpac' in body:
        attributes['sigpacReference'] = _property(body['referencia_sigpac'])

    if 'superficie_elegible' in body:
        attributes['eligibleArea'] = _property(body['superficie_elegible'])

    location = body.get('location') or body.get('geometria')
    if location is not None:
        if not isinstance(location, dict):
            return jsonify({'error': 'location debe ser un objeto GeoJSON'}), 400
        valid, err = _validate_polygon(location)
        if not valid:
            return jsonify({'error': f'Geometría inválida: {err}'}), 400
        attributes['location'] = _geo_property(location)

    if 'declaracion_id' in body:
        attributes['hasAgriCropDeclaration'] = _relationship(
            _entity_uri('AgriCropDeclaration', tenant, body['declaracion_id'])
        )

    if not attributes:
        return jsonify({'error': 'No hay campos para actualizar'}), 400

    status, resp = update_entity('SigpacEnclosure', tenant, enclosure_id, attributes)
    if status not in (200, 204):
        return jsonify({'error': resp}), status

    _, entity = get_entity('SigpacEnclosure', tenant, enclosure_id)
    return jsonify(entity)


@cue_bp.route('/recintos/<enclosure_id>', methods=['DELETE'])
@require_auth
def delete_recinto(enclosure_id):
    """Soft-delete SigpacEnclosure."""
    tenant = get_current_tenant()
    status, resp = delete_entity('SigpacEnclosure', tenant, enclosure_id)
    if status not in (200, 204):
        return jsonify({'error': resp}), status
    return jsonify({'status': 'deleted', 'id': enclosure_id})


# =========================================================================
# AGRIPESTTREATMENT ROUTES (mandatory since 1-ene-2026)
# =========================================================================

@cue_bp.route('/tratamientos', methods=['GET'])
@require_auth
def list_tratamientos():
    """List AgriPestTreatment entities for current tenant with optional filters."""
    tenant = get_current_tenant()
    parcela_id = request.args.get('parcela_id')
    q_parts = [_tenant_filter(), 'isActive!=false']
    if parcela_id:
        parcela_uri = _entity_uri('AgriParcel', tenant, parcela_id)
        q_parts.append(f'hasAgriParcel=="{parcela_uri}"')
    q = ';'.join(q_parts)
    status, result = query_entities('AgriPestTreatment', tenant, {'q': q})
    if status == 200:
        return jsonify(result), 200
    return jsonify(result), status


@cue_bp.route('/tratamientos', methods=['POST'])
@require_auth
def create_tratamiento():
    """Create an AgriPestTreatment entity in Orion-LD."""
    data = request.json or {}
    tenant = get_current_tenant()
    tratamiento_id = data.get('id') or _generate_id()

    attributes = {
        "name": _property(data.get('nombre', '')),
        "productoROPORef": _property(data.get('producto_ropo', '')),
        "dosisAplicada": _property({
            "value": data.get('dosis', 0),
            "unitCode": data.get('unidad_dosis', 'L/ha')
        }),
        "plagaObjeto": _property(data.get('plaga', '')),
        "equipoAplicacion": _property(data.get('equipo', '')),
        "aplicador": _property(data.get('aplicador', '')),
        "horaAplicacion": _property(data.get('hora', '')),
        "dateObserved": _property(data.get('fecha', '')),
        "tenantId": _property(tenant),
        "version": _property(1),
        "isActive": _property(True),
    }

    parcela_id = data.get('parcela_id')
    if parcela_id:
        parcela_uri = _entity_uri('AgriParcel', tenant, parcela_id)
        attributes['hasAgriParcel'] = _relationship(parcela_uri)

    # Validate against rules engine before creating
    if data.get('validar', True):
        from rules.engine import validate_tratamiento as validate_tratamiento_rules
        try:
            fecha_app = date.fromisoformat(data.get('fecha', '')) if data.get('fecha') else date.today()
        except (ValueError, TypeError):
            fecha_app = date.today()

        validation = validate_tratamiento_rules(
            numero_registro=data.get('producto_ropo', ''),
            dosis=float(data.get('dosis', 0)),
            cultivo=data.get('cultivo', ''),
            plaga=data.get('plaga', ''),
            fecha_aplicacion=fecha_app,
        )

        if data.get('validacion_estricta', True) and not validation['valid']:
            return jsonify({
                'error': 'El tratamiento no supera las validaciones SIEX',
                'validation': validation,
            }), 422

    status, result = create_entity('AgriPestTreatment', tenant, tratamiento_id, attributes)
    return jsonify(result), status if status in (200, 201) else status


@cue_bp.route('/tratamientos/<tratamiento_id>', methods=['GET'])
@require_auth
def get_tratamiento(tratamiento_id):
    """Get an AgriPestTreatment entity by ID."""
    tenant = get_current_tenant()
    status, result = get_entity('AgriPestTreatment', tenant, tratamiento_id)
    return jsonify(result), status


@cue_bp.route('/tratamientos/<tratamiento_id>', methods=['PUT'])
@require_auth
def update_tratamiento(tratamiento_id):
    """Update an AgriPestTreatment entity."""
    data = request.json or {}
    tenant = get_current_tenant()
    attributes = {}

    for key, ngsi_key in [
        ('nombre', 'name'),
        ('producto_ropo', 'productoROPORef'),
        ('plaga', 'plagaObjeto'),
        ('equipo', 'equipoAplicacion'),
        ('aplicador', 'aplicador'),
        ('hora', 'horaAplicacion'),
        ('fecha', 'dateObserved'),
    ]:
        if key in data:
            attributes[ngsi_key] = _property(data[key])

    if 'dosis' in data:
        attributes['dosisAplicada'] = _property({
            "value": data['dosis'],
            "unitCode": data.get('unidad_dosis', 'L/ha')
        })

    status, result = update_entity('AgriPestTreatment', tenant, tratamiento_id, attributes)
    if status == 204:
        return jsonify({'status': 'updated'}), 200
    return jsonify(result), status


@cue_bp.route('/tratamientos/<tratamiento_id>', methods=['DELETE'])
@require_auth
def delete_tratamiento(tratamiento_id):
    """Soft-delete an AgriPestTreatment."""
    tenant = get_current_tenant()
    status, result = delete_entity('AgriPestTreatment', tenant, tratamiento_id)
    if status == 204:
        return jsonify({'status': 'deleted'}), 200
    return jsonify(result), status


# =========================================================================
# AGRIFERTILIZERAPPLICATION ROUTES (mandatory since 1-ene-2026)
# =========================================================================

@cue_bp.route('/fertilizaciones', methods=['GET'])
@require_auth
def list_fertilizaciones():
    """List AgriFertilizerApplication entities for current tenant."""
    tenant = get_current_tenant()
    parcela_id = request.args.get('parcela_id')
    q_parts = [_tenant_filter(), 'isActive!=false']
    if parcela_id:
        parcela_uri = _entity_uri('AgriParcel', tenant, parcela_id)
        q_parts.append(f'hasAgriParcel=="{parcela_uri}"')
    q = ';'.join(q_parts)
    status, result = query_entities('AgriFertilizerApplication', tenant, {'q': q})
    if status == 200:
        return jsonify(result), 200
    return jsonify(result), status


@cue_bp.route('/fertilizaciones', methods=['POST'])
@require_auth
def create_fertilizacion():
    """Create an AgriFertilizerApplication entity in Orion-LD."""
    data = request.json or {}
    tenant = get_current_tenant()
    fertilizacion_id = data.get('id') or _generate_id()

    attributes = {
        "name": _property(data.get('nombre', '')),
        "tipoFertilizante": _property(data.get('tipo', '')),
        "dosisFertilizante": _property({
            "value": data.get('dosis_kg_ha', 0),
            "unitCode": "kg/ha"
        }),
        "contenidoN": _property({
            "value": data.get('contenido_n_pct', 0),
            "unitCode": "%"
        }),
        "contenidoP": _property({
            "value": data.get('contenido_p_pct', 0),
            "unitCode": "%"
        }),
        "dateObserved": _property(data.get('fecha', '')),
        "tenantId": _property(tenant),
        "version": _property(1),
        "isActive": _property(True),
    }

    parcela_id = data.get('parcela_id')
    if parcela_id:
        parcela_uri = _entity_uri('AgriParcel', tenant, parcela_id)
        attributes['hasAgriParcel'] = _relationship(parcela_uri)

    status, result = create_entity('AgriFertilizerApplication', tenant, fertilizacion_id, attributes)
    return jsonify(result), status if status in (200, 201) else status


@cue_bp.route('/fertilizaciones/<fertilizacion_id>', methods=['GET'])
@require_auth
def get_fertilizacion(fertilizacion_id):
    """Get an AgriFertilizerApplication entity by ID."""
    tenant = get_current_tenant()
    status, result = get_entity('AgriFertilizerApplication', tenant, fertilizacion_id)
    return jsonify(result), status


@cue_bp.route('/fertilizaciones/<fertilizacion_id>', methods=['PUT'])
@require_auth
def update_fertilizacion(fertilizacion_id):
    """Update an AgriFertilizerApplication entity."""
    data = request.json or {}
    tenant = get_current_tenant()
    attributes = {}

    for key, ngsi_key in [
        ('nombre', 'name'),
        ('tipo', 'tipoFertilizante'),
        ('fecha', 'dateObserved'),
    ]:
        if key in data:
            attributes[ngsi_key] = _property(data[key])

    if 'dosis_kg_ha' in data:
        attributes['dosisFertilizante'] = _property({
            "value": data['dosis_kg_ha'],
            "unitCode": "kg/ha"
        })
    if 'contenido_n_pct' in data:
        attributes['contenidoN'] = _property({
            "value": data['contenido_n_pct'],
            "unitCode": "%"
        })
    if 'contenido_p_pct' in data:
        attributes['contenidoP'] = _property({
            "value": data['contenido_p_pct'],
            "unitCode": "%"
        })

    status, result = update_entity('AgriFertilizerApplication', tenant, fertilizacion_id, attributes)
    if status == 204:
        return jsonify({'status': 'updated'}), 200
    return jsonify(result), status


@cue_bp.route('/fertilizaciones/<fertilizacion_id>', methods=['DELETE'])
@require_auth
def delete_fertilizacion(fertilizacion_id):
    """Soft-delete an AgriFertilizerApplication."""
    tenant = get_current_tenant()
    status, result = delete_entity('AgriFertilizerApplication', tenant, fertilizacion_id)
    if status == 204:
        return jsonify({'status': 'deleted'}), 200
    return jsonify(result), status


# =========================================================================
# PRODUCT CATALOG ROUTES (ROPO + Fertilizantes master data)
# =========================================================================


@cue_bp.route('/productos-ropo', methods=['GET'])
@require_auth
def list_productos_ropo():
    """List/search ROPO products with SCD Type 2 temporal validity."""
    tenant = get_current_tenant()
    try:
        conn = get_pg_conn()
        cur = conn.cursor()

        query = request.args.get('q')
        cultivo = request.args.get('cultivo')
        estado = request.args.get('estado', 'autorizado')

        sql = """
            SELECT numero_registro, nombre_comercial, ingrediente_activo,
                   tipo, estado, cultivos_autorizados, plagas_autorizadas,
                   dosis_maxima, unidad_dosis, plazo_seguridad_dias,
                   fecha_inicio_validez, fecha_fin_validez
            FROM cue_producto_ropo
            WHERE estado = %s AND fecha_fin_validez IS NULL
        """
        params = [estado]

        if query:
            sql += (" AND (nombre_comercial ILIKE %s OR ingrediente_activo ILIKE %s "
                    "OR numero_registro ILIKE %s)")
            params.extend([f'%{query}%', f'%{query}%', f'%{query}%'])

        if cultivo:
            sql += " AND %s = ANY(cultivos_autorizados)"
            params.append(cultivo)

        sql += " ORDER BY nombre_comercial LIMIT 200"

        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        logger.error(f"Error querying ROPO products: {e}")
        return jsonify({'error': 'Error al consultar productos ROPO'}), 500


@cue_bp.route('/productos-ropo/<numero_registro>', methods=['GET'])
@require_auth
def get_producto_ropo(numero_registro):
    """Get a specific ROPO product by registration number."""
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM cue_producto_ropo "
            "WHERE numero_registro = %s AND fecha_fin_validez IS NULL "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (numero_registro,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return jsonify(dict(row)), 200
        return jsonify({'error': 'Producto ROPO no encontrado'}), 404
    except Exception as e:
        logger.error(f"Error getting ROPO product: {e}")
        return jsonify({'error': 'Error al consultar producto ROPO'}), 500


@cue_bp.route('/productos-fertilizantes', methods=['GET'])
@require_auth
def list_productos_fertilizantes():
    """List/search fertilizer products with SCD Type 2 temporal validity."""
    try:
        conn = get_pg_conn()
        cur = conn.cursor()

        query = request.args.get('q')
        tipo = request.args.get('tipo')
        estado = request.args.get('estado', 'autorizado')

        sql = """
            SELECT numero_registro, nombre_comercial, tipo,
                   composicion_n_pct, composicion_p_pct, composicion_k_pct,
                   fabricante, estado, cultivos_autorizados, dosis_maxima_kg_ha,
                   fecha_inicio_validez, fecha_fin_validez
            FROM cue_producto_fertilizante
            WHERE estado = %s AND fecha_fin_validez IS NULL
        """
        params = [estado]

        if query:
            sql += (" AND (nombre_comercial ILIKE %s OR numero_registro ILIKE %s)")
            params.extend([f'%{query}%', f'%{query}%'])

        if tipo:
            sql += " AND tipo = %s"
            params.append(tipo)

        sql += " ORDER BY nombre_comercial LIMIT 200"

        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        logger.error(f"Error querying fertilizer products: {e}")
        return jsonify({'error': 'Error al consultar productos fertilizantes'}), 500


@cue_bp.route('/productos-fertilizantes/<numero_registro>', methods=['GET'])
@require_auth
def get_producto_fertilizante(numero_registro):
    """Get a specific fertilizer product by registration number."""
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM cue_producto_fertilizante "
            "WHERE numero_registro = %s AND fecha_fin_validez IS NULL "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (numero_registro,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return jsonify(dict(row)), 200
        return jsonify({'error': 'Producto fertilizante no encontrado'}), 404
    except Exception as e:
        logger.error(f"Error getting fertilizer product: {e}")
        return jsonify({'error': 'Error al consultar producto fertilizante'}), 500


# =========================================================================
# VALIDATION ROUTE
# =========================================================================

@cue_bp.route('/validate', methods=['POST'])
@require_auth
def validate_tratamiento_endpoint():
    """
    Validate a phytosanitary treatment against SIEX rules before creating.
    Does NOT create the entity — only validates.
    """
    from rules.engine import validate_tratamiento as validate_tratamiento_rules

    data = request.json or {}
    tenant = get_current_tenant()

    required = ['numero_registro', 'dosis', 'cultivo', 'plaga', 'fecha_aplicacion']
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({'error': f'Faltan campos obligatorios: {", ".join(missing)}'}), 400

    try:
        fecha_aplicacion = date.fromisoformat(data['fecha_aplicacion'])
    except (ValueError, TypeError):
        return jsonify({'error': 'fecha_aplicacion debe ser una fecha ISO (YYYY-MM-DD)'}), 400

    fecha_cosecha = None
    if data.get('fecha_cosecha'):
        try:
            fecha_cosecha = date.fromisoformat(data['fecha_cosecha'])
        except (ValueError, TypeError):
            return jsonify({'error': 'fecha_cosecha debe ser una fecha ISO (YYYY-MM-DD)'}), 400

    result = validate_tratamiento_rules(
        numero_registro=data['numero_registro'],
        dosis=float(data['dosis']),
        cultivo=data['cultivo'],
        plaga=data.get('plaga', ''),
        fecha_aplicacion=fecha_aplicacion,
        fecha_cosecha=fecha_cosecha,
    )

    status_code = 200 if result['valid'] else 422
    return jsonify(result), status_code


# ===========================================================================
# Register blueprint
# ===========================================================================

app.register_blueprint(cue_bp)


# ===========================================================================
# Entrypoint
# ===========================================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
