#!/usr/bin/env python3
# =============================================================================
# CUE API — Cuaderno de Campo (SIEX Spain) — NGSI-LD CRUD + PostGIS Spatial
# =============================================================================
# Phase 1 backend-only. Orion-LD source of truth, PostGIS spatial cache.
# Flask + psycopg2 + Orion-LD client wrappers.

import os
import logging
import json
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

            "campaignYear": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:AgriCropDeclaration:campaignYear"
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
            "tenantId": {
                "@type": "Property",
                "@id": "urn:ngsi-ld:tenantId"
            },

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
        return jsonify({'status': 'error', 'message': 'Invalid notification body'}), 400

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
        return False, 'geometry must be a GeoJSON object'

    if geom.get('type') != 'Polygon':
        return False, 'geometry type must be Polygon'

    coords = geom.get('coordinates')
    if not isinstance(coords, list) or not coords:
        return False, 'coordinates must be a non-empty array'

    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < 4:
        return False, 'Polygon must have at least 4 points (closed ring)'

    if ring[0] != ring[-1]:
        return False, 'Polygon exterior ring must be closed'

    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return False, 'each coordinate must be [lon, lat]'
        lon, lat = pt[0], pt[1]
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            return False, 'coordinates must be numeric'
        if abs(lat) > 90:
            return False, f'latitude {lat} out of range [-90, 90]'
        if abs(lon) > 180:
            return False, f'longitude {lon} out of range [-180, 180]'

    return True, ''


def _generate_id():
    """Generate a short hex entity ID."""
    return os.urandom(8).hex()


# ===========================================================================
# AgriFarm routes
# ===========================================================================

@cue_bp.route('/explotaciones', methods=['GET'])
@require_auth
def list_explotaciones():
    """Query Orion-LD AgriFarm by tenant, filter isActive!=false."""
    tenant = get_current_tenant()
    q = f'{_tenant_filter()};isActive!=false'
    status, data = query_entities('AgriFarm', tenant, {'q': q})
    if status != 200:
        return jsonify({'error': data}), status
    return jsonify(data)


@cue_bp.route('/explotaciones', methods=['POST'])
@require_auth
def create_explotacion():
    """Create AgriFarm entity in Orion-LD."""
    tenant = get_current_tenant()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body is required'}), 400

    farm_id = _generate_id()
    attributes = {
        'name': _property(body.get('nombre', '')),
        'description': _property(body.get('descripcion', '')),
        'contactPoint': _property(body.get('contacto', '')),
        'address': _property(body.get('direccion', '')),
        'tenantId': _property(tenant),
        'version': _property(1),
        'isActive': _property(True),
    }

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
        return jsonify({'error': 'Request body is required'}), 400

    attributes = {}

    if 'nombre' in body:
        attributes['name'] = _property(body['nombre'])
    if 'descripcion' in body:
        attributes['description'] = _property(body['descripcion'])
    if 'contacto' in body:
        attributes['contactPoint'] = _property(body['contacto'])

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
        return jsonify({'error': 'No fields to update'}), 400

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
        return jsonify({'error': 'Request body is required'}), 400

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
        return jsonify({'error': 'Request body is required'}), 400

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
        return jsonify({'error': 'No fields to update'}), 400

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
        return jsonify({'error': 'Request body is required'}), 400

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
        return jsonify({'error': 'Request body is required'}), 400

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
        return jsonify({'error': 'No fields to update'}), 400

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
        return jsonify({'error': 'Request body is required'}), 400

    location = body.get('location') or body.get('geometria')
    if not location:
        return jsonify({'error': 'location or geometria (GeoJSON Polygon) is required'}), 400

    if not isinstance(location, dict):
        return jsonify({'error': 'location must be a GeoJSON object'}), 400

    valid, err = _validate_polygon(location)
    if not valid:
        return jsonify({'error': f'Geometria invalida: {err}'}), 400

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
        return jsonify({'error': 'Request body is required'}), 400

    attributes = {}

    if 'referencia_sigpac' in body:
        attributes['sigpacReference'] = _property(body['referencia_sigpac'])

    if 'superficie_elegible' in body:
        attributes['eligibleArea'] = _property(body['superficie_elegible'])

    location = body.get('location') or body.get('geometria')
    if location is not None:
        if not isinstance(location, dict):
            return jsonify({'error': 'location must be a GeoJSON object'}), 400
        valid, err = _validate_polygon(location)
        if not valid:
            return jsonify({'error': f'Geometria invalida: {err}'}), 400
        attributes['location'] = _geo_property(location)

    if 'declaracion_id' in body:
        attributes['hasAgriCropDeclaration'] = _relationship(
            _entity_uri('AgriCropDeclaration', tenant, body['declaracion_id'])
        )

    if not attributes:
        return jsonify({'error': 'No fields to update'}), 400

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


# ===========================================================================
# Register blueprint
# ===========================================================================

app.register_blueprint(cue_bp)


# ===========================================================================
# Entrypoint
# ===========================================================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
