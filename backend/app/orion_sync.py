#!/usr/bin/env python3
# =============================================================================
# Orion-LD → PostGIS Sync for SigpacEnclosure geometries
# =============================================================================
# Receives NGSI-LD notifications via /notify webhook.
# Extracts GeoJSON geometry from SigpacEnclosure entities.
# Upserts into cue_recinto_sigpac (PostGIS spatial cache).

import os
import logging
import json
import psycopg2
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
)


def extract_ngsi_ld_value(attribute: Any) -> Any:
    """
    Extract value from NGSI-LD attribute format.

    NGSI-LD format: {"type": "Property", "value": "actual_value"}
    or {"type": "Relationship", "object": "urn:ngsi-ld:..."}
    or {"type": "GeoProperty", "value": {...}}
    """
    if isinstance(attribute, dict):
        if 'value' in attribute:
            return attribute['value']
        elif 'object' in attribute:
            return attribute['object']
    return attribute


def extract_tenant_from_entity(entity: Dict[str, Any]) -> Optional[str]:
    """
    Extract tenant_id from a NGSI-LD entity.

    Checks: tenantId → tenant_id → tenant → entity ID parsing.
    """
    if 'tenantId' in entity:
        return extract_ngsi_ld_value(entity['tenantId'])

    if 'tenant_id' in entity:
        return extract_ngsi_ld_value(entity['tenant_id'])

    if 'tenant' in entity:
        return extract_ngsi_ld_value(entity['tenant'])

    entity_id = entity.get('id', '')
    parts = entity_id.split(':')
    if len(parts) >= 4:
        return parts[3]

    logger.warning(f"Could not extract tenant from entity {entity.get('id', 'unknown')}")
    return None


def sync_enclosure_to_postgres(
    entity_id: str,
    tenant_id: str,
    location: Dict[str, Any],
) -> bool:
    """
    Upsert a SigpacEnclosure geometry into the PostGIS cache.

    Args:
        entity_id: NGSI-LD entity ID (urn:ngsi-ld:SigpacEnclosure:...)
        tenant_id: Tenant identifier
        location: GeoJSON geometry dict with type and coordinates

    Returns:
        True if sync successful, False otherwise.
    """
    conn = None
    cur = None

    try:
        geometry_type = location.get('type')

        if geometry_type != 'Polygon':
            logger.warning(
                f"Skipping non-Polygon geometry for {entity_id}: {geometry_type}"
            )
            return False

        coordinates = location.get('coordinates')
        if not coordinates:
            logger.error(f"Missing coordinates for {entity_id}")
            return False

        geometry_json = json.dumps({
            'type': 'Polygon',
            'coordinates': coordinates,
        })

        conn = psycopg2.connect(POSTGRES_URL)
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO cue_recinto_sigpac (orion_entity_id, tenant_id, geometria)
            VALUES (%s, %s, ST_GeomFromGeoJSON(%s))
            ON CONFLICT (orion_entity_id) DO UPDATE SET
                geometria = EXCLUDED.geometria,
                updated_at = NOW()
            RETURNING id
        """, (entity_id, tenant_id, geometry_json))

        result = cur.fetchone()
        conn.commit()

        row_id = result[0] if result else None
        logger.info(f"Synced enclosure {entity_id} to PostGIS (row: {row_id})")
        return True

    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error syncing {entity_id}: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        logger.error(f"Error syncing {entity_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def process_notification(notification: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process an Orion-LD notification and sync SigpacEnclosure geometries.

    Returns a summary dict with processed, synced, and error counts.
    """
    entities = notification.get('data', [])
    summary = {'processed': len(entities), 'synced': 0, 'errors': 0}

    for entity in entities:
        entity_type = entity.get('type', '')
        if entity_type != 'SigpacEnclosure':
            continue

        entity_id = entity.get('id', '')
        tenant_id = extract_tenant_from_entity(entity)

        if not tenant_id:
            logger.warning(f"Skipping {entity_id}: no tenant")
            summary['errors'] += 1
            continue

        location = extract_ngsi_ld_value(entity.get('location', {}))
        if not location:
            logger.warning(f"Skipping {entity_id}: no location GeoProperty")
            summary['errors'] += 1
            continue

        if sync_enclosure_to_postgres(entity_id, tenant_id, location):
            summary['synced'] += 1
        else:
            summary['errors'] += 1

    return summary
