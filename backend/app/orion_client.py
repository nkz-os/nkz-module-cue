#!/usr/bin/env python3
# =============================================================================
# Orion-LD Client — NGSI-LD CRUD Operations
# =============================================================================
# Wrapper for Orion-LD entity operations.
# All writes go through Orion-LD (SOTA architecture).

import os
import re
import logging
import requests
from typing import Optional, Dict, Any, List
from app.common.tenant_utils import normalize_tenant_id

logger = logging.getLogger(__name__)

ORION_URL = os.getenv('ORION_URL', 'http://orion-ld-service:1026')
NGSI_LD_CONTEXT_URL = os.getenv(
    'CONTEXT_URL',
    'http://api-gateway-service:5000/ngsi-ld-context.jsonld'
)
CUE_CONTEXT_URL = os.getenv(
    'CUE_CONTEXT_URL',
    'http://api-gateway-service:5000/ngsi-ld/cue-context.jsonld'
)

DEFAULT_CONTEXTS = [
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
]

SDM_CONTEXTS = {
    'AgriFarm': "https://smart-data-models.github.io/dataModel.Agrifood/AgriFarm/context.jsonld",
    'AgriParcel': "https://smart-data-models.github.io/dataModel.Agrifood/AgriParcel/context.jsonld",
    'AgriPestTreatment': "https://smart-data-models.github.io/dataModel.Agrifood/AgriPestTreatment/context.jsonld",
    'AgriFertilizerApplication': "https://smart-data-models.github.io/dataModel.Agrifood/AgriFertilizerApplication/context.jsonld",
}

# Allowed characters in entity IDs: alphanumeric, hyphens, underscores.
# Restricts to safe chars to prevent NGSI-LD query injection via the 'q' parameter.
_SAFE_ENTITY_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')

# Safe entity type: alphabetic only (SDM convention)
_SAFE_ENTITY_TYPE_RE = re.compile(r'[^a-zA-Z]')

# Safe tenant ID: alphanumeric, hyphens, underscores, dots (FIWARE convention)
_SAFE_TENANT_RE = re.compile(r'[^a-zA-Z0-9_\-.]')


def _entity_uri(entity_type: str, tenant_id: str, entity_id: str) -> str:
    """Build NGSI-LD entity URN with input validation.

    Entity IDs are validated to contain only safe characters
    (alphanumeric, hyphens, underscores) to prevent NGSI-LD query injection
    via the 'q' parameter. Tenant and type are sanitized.

    Raises ValueError if entity_id contains unsafe characters or is empty.
    """
    if not entity_id:
        raise ValueError("entity_id must not be empty")
    if not _SAFE_ENTITY_ID_RE.match(entity_id):
        raise ValueError(
            f"entity_id contains invalid characters: {entity_id!r}. "
            f"Only alphanumeric, hyphens, and underscores are allowed."
        )
    # Sanitize tenant_id and entity_type (defense in depth)
    safe_tenant = _SAFE_TENANT_RE.sub('_', tenant_id)
    safe_type = _SAFE_ENTITY_TYPE_RE.sub('', entity_type)
    return f"urn:ngsi-ld:{safe_type}:{safe_tenant}:{entity_id}"


def _build_context(entity_type: str) -> list:
    """Build @context array for an entity type."""
    contexts = list(DEFAULT_CONTEXTS)
    sdm_ctx = SDM_CONTEXTS.get(entity_type)
    if sdm_ctx:
        contexts.append(sdm_ctx)
    else:
        contexts.append(CUE_CONTEXT_URL)
    return contexts


def _ngsi_ld_headers(tenant_id: str, with_content_type: bool = True) -> Dict[str, str]:
    """Build canonical NGSI-LD headers with tenant normalization.

    Applies FIWARE multi-tenant conventions: lowercase, underscores,
    alphanumeric-only normalized tenant value for both NGSILD-Tenant
    and Fiware-Service headers. Includes Link header when CONTEXT_URL is set.
    """
    n = normalize_tenant_id(tenant_id)
    h: Dict[str, str] = {
        'NGSILD-Tenant': n,
        'Fiware-Service': n,
        'Fiware-ServicePath': '/',
        'Accept': 'application/ld+json',
    }
    if with_content_type:
        # Writes carry @context in the body, so the mode is ld+json and a Link
        # header alongside it is the combination ETSI GS CIM 009 forbids.
        h['Content-Type'] = 'application/ld+json'
        return h
    ctx = os.getenv('CONTEXT_URL', '')
    if ctx:
        h['Link'] = (
            f'<{ctx}>; '
            f'rel="http://www.w3.org/ns/json-ld#context"; '
            f'type="application/ld+json"'
        )
    return h


def _property(value) -> Dict[str, Any]:
    """Build NGSI-LD Property."""
    if isinstance(value, dict):
        return {"type": "Property", "value": value}
    return {"type": "Property", "value": value}


def _relationship(object_urn: str) -> Dict[str, Any]:
    """Build NGSI-LD Relationship."""
    return {"type": "Relationship", "object": object_urn}


def _geo_property(geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Build NGSI-LD GeoProperty."""
    return {"type": "GeoProperty", "value": geometry}


def create_entity(
    entity_type: str,
    tenant_id: str,
    entity_id: str,
    attributes: Dict[str, Any],
    extra_contexts: Optional[List[str]] = None,
) -> tuple[int, Dict[str, Any]]:
    """
    Create an NGSI-LD entity in Orion-LD.

    Returns (status_code, response_body).
    """
    uri = _entity_uri(entity_type, tenant_id, entity_id)
    contexts = _build_context(entity_type)
    if extra_contexts:
        contexts.extend(extra_contexts)

    body = {
        "id": uri,
        "type": entity_type,
        "@context": contexts,
    }
    body.update(attributes)

    try:
        r = requests.post(
            f"{ORION_URL}/ngsi-ld/v1/entities",
            json=body,
            headers=_ngsi_ld_headers(tenant_id),
            timeout=10,
        )
        return r.status_code, r.json() if r.text else {}
    except requests.RequestException as e:
        logger.error(f"Orion-LD create_entity error: {e}")
        return 502, {"error": f"Orion-LD inaccesible: {e}"}


def get_entity(
    entity_type: str,
    tenant_id: str,
    entity_id: str,
    expand: Optional[str] = None,
) -> tuple[int, Dict[str, Any]]:
    """
    Get an NGSI-LD entity by ID.

    Args:
        expand: Relationships to expand (e.g. 'hasAgriParcel').
    """
    uri = _entity_uri(entity_type, tenant_id, entity_id)
    params = {}
    if expand:
        params['options'] = 'keyValues'
    else:
        params['options'] = 'keyValues'

    try:
        r = requests.get(
            f"{ORION_URL}/ngsi-ld/v1/entities/{uri}",
            params=params,
            headers=_ngsi_ld_headers(tenant_id, with_content_type=False),
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if expand and expand in data:
                rel = data.get(expand, {})
                if isinstance(rel, dict) and rel.get('type') == 'Relationship':
                    rel_uri = rel.get('object', '')
                    _, rel_obj = get_entity_by_uri(tenant_id, rel_uri)
                    if rel_obj:
                        data[expand] = rel_obj
            return r.status_code, data
        return r.status_code, r.json() if r.text else {}
    except requests.RequestException as e:
        logger.error(f"Orion-LD get_entity error: {e}")
        return 502, {"error": f"Orion-LD inaccesible: {e}"}


def get_entity_by_uri(
    tenant_id: str,
    uri: str,
) -> tuple[int, Dict[str, Any]]:
    """Get entity by full URI."""
    try:
        r = requests.get(
            f"{ORION_URL}/ngsi-ld/v1/entities/{uri}",
            params={'options': 'keyValues'},
            headers=_ngsi_ld_headers(tenant_id, with_content_type=False),
            timeout=10,
        )
        return r.status_code, r.json() if r.text else {}
    except requests.RequestException as e:
        logger.error(f"Orion-LD get_entity_by_uri error: {e}")
        return 502, {"error": f"Orion-LD inaccesible: {e}"}


def query_entities(
    entity_type: str,
    tenant_id: str,
    query_params: Optional[Dict[str, str]] = None,
) -> tuple[int, List[Dict[str, Any]]]:
    """
    Query NGSI-LD entities by type.

    Additional query_params are passed as NGSI-LD query parameters (q, georel, etc.).
    """
    params = {
        'type': entity_type,
        'options': 'keyValues',
    }
    if query_params:
        params.update(query_params)

    try:
        r = requests.get(
            f"{ORION_URL}/ngsi-ld/v1/entities",
            params=params,
            headers=_ngsi_ld_headers(tenant_id, with_content_type=False),
            timeout=10,
        )
        return r.status_code, r.json() if r.text else []
    except requests.RequestException as e:
        logger.error(f"Orion-LD query_entities error: {e}")
        return 502, {"error": f"Orion-LD inaccesible: {e}"}


def update_entity(
    entity_type: str,
    tenant_id: str,
    entity_id: str,
    attributes: Dict[str, Any],
) -> tuple[int, Dict[str, Any]]:
    """
    Update NGSI-LD entity attributes (partial update via PATCH).
    """
    uri = _entity_uri(entity_type, tenant_id, entity_id)
    contexts = _build_context(entity_type)

    body = {
        "@context": contexts,
    }
    body.update(attributes)

    try:
        r = requests.patch(
            f"{ORION_URL}/ngsi-ld/v1/entities/{uri}/attrs",
            json=body,
            headers=_ngsi_ld_headers(tenant_id),
            timeout=10,
        )
        return r.status_code, {}
    except requests.RequestException as e:
        logger.error(f"Orion-LD update_entity error: {e}")
        return 502, {"error": f"Orion-LD inaccesible: {e}"}


def delete_entity(
    entity_type: str,
    tenant_id: str,
    entity_id: str,
) -> tuple[int, Dict[str, Any]]:
    """
    Soft-delete: set isActive=False instead of actual deletion.
    Uses PATCH to preserve audit trail.
    """
    return update_entity(
        entity_type, tenant_id, entity_id,
        {"isActive": _property(False)}
    )
