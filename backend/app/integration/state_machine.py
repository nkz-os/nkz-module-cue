#!/usr/bin/env python3
# =============================================================================
# CUE Submission State Machine -- SIEX IUWS Tracking
# =============================================================================
# Tracks submission lifecycle through 10 states.
# Stores state in PostgreSQL (infrastructure data, not NGSI-LD).

import os
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
)

# Valid states and their order
STATES = [
    'borrador',
    'validado',
    'firmado',
    'pendiente',
    'procesando',
    'aceptado',
    'aceptado_con_advertencias',
    'pendiente_de_subsanacion',
    'rechazado_con_errores',
    'subsanado',
]

# Allowed transitions
TRANSITIONS = {
    'borrador': ['validado'],
    'validado': ['firmado'],
    'firmado': ['pendiente'],
    'pendiente': ['procesando', 'rechazado_con_errores'],
    'procesando': ['aceptado', 'aceptado_con_advertencias', 'pendiente_de_subsanacion', 'rechazado_con_errores'],
    'aceptado': [],  # Terminal
    'aceptado_con_advertencias': ['subsanado'],
    'pendiente_de_subsanacion': ['subsanado'],
    'rechazado_con_errores': ['subsanado'],
    'subsanado': ['pendiente'],  # Re-submit after correction
}


def _get_conn():
    conn = psycopg2.connect(POSTGRES_URL)
    conn.cursor_factory = RealDictCursor
    return conn


def create_submission(
    tenant_id: str,
    farm_id: str,
    payload_type: str = 'Alta',
    provincia: Optional[str] = None,
    iuws_url: Optional[str] = None,
    xml_payload: Optional[str] = None,
    xsd_valid: Optional[bool] = None,
) -> int:
    """Create a new submission in 'borrador' state. Returns submission ID."""
    conn = None
    cur = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO cue_estado_envio "
            "(tenant_id, farm_id, payload_type, provincia, iuws_url, xml_payload, xsd_valid) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (tenant_id, farm_id, payload_type, provincia, iuws_url, xml_payload, xsd_valid)
        )
        row_id = cur.fetchone()['id']
        conn.commit()
        logger.info(f"Submission {row_id} created for farm {farm_id}")
        return row_id
    except Exception as e:
        logger.error(f"Error creating submission: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def transition_state(submission_id: int, new_state: str, metadata: Optional[Dict] = None) -> Tuple[bool, str]:
    """
    Transition a submission to a new state.

    Returns (success, message).
    Validates that the transition is allowed.
    """
    if new_state not in STATES:
        return False, f'Estado invalido: {new_state}. Estados validos: {STATES}'

    conn = None
    cur = None
    try:
        conn = _get_conn()
        cur = conn.cursor()

        # Get current state
        cur.execute("SELECT estado FROM cue_estado_envio WHERE id = %s", (submission_id,))
        row = cur.fetchone()
        if not row:
            return False, f'Envio {submission_id} no encontrado'

        current = row['estado']
        allowed = TRANSITIONS.get(current, [])

        if new_state not in allowed and current != new_state:
            return False, (
                f'Transicion no permitida: {current} -> {new_state}. '
                f'Transiciones validas desde {current}: {allowed}'
            )

        # Update state
        updates = ["estado = %s"]
        params = [new_state]

        # Set timestamp on certain transitions
        if new_state in ('pendiente', 'firmado'):
            updates.append("fecha_presentacion = %s")
            params.append(datetime.now())

        # Merge response detail
        if metadata:
            updates.append("detalle_respuesta = COALESCE(detalle_respuesta, '{}'::jsonb) || %s::jsonb")
            params.append(json.dumps(metadata))

        params.append(submission_id)
        cur.execute(
            f"UPDATE cue_estado_envio SET {', '.join(updates)} WHERE id = %s",
            params
        )
        conn.commit()
        logger.info(f"Submission {submission_id}: {current} -> {new_state}")
        return True, ''
    except Exception as e:
        logger.error(f"Error in transition_state: {e}")
        if conn:
            conn.rollback()
        return False, str(e)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def set_ticket(submission_id: int, id_ticket: str, csv_trace_id: Optional[str] = None):
    """Record the IUWS ticket ID after submission."""
    conn = None
    cur = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE cue_estado_envio SET id_ticket = %s, csv_trace_id = COALESCE(%s, csv_trace_id) "
            "WHERE id = %s",
            (id_ticket, csv_trace_id, submission_id)
        )
        conn.commit()
        logger.info(f"Ticket {id_ticket} assigned to submission {submission_id}")
    except Exception as e:
        logger.error(f"Error setting ticket: {e}")
        if conn:
            conn.rollback()
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_submission(submission_id: int) -> Optional[Dict]:
    """Get a submission by ID."""
    conn = None
    cur = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM cue_estado_envio WHERE id = %s", (submission_id,))
        row = cur.fetchone()
        if row:
            result = dict(row)
            # Convert datetime objects to ISO strings
            for k in ('created_at', 'updated_at', 'fecha_presentacion'):
                if result.get(k):
                    result[k] = result[k].isoformat()
            return result
        return None
    except Exception as e:
        logger.error(f"Error getting submission: {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def list_submissions(tenant_id: str, farm_id: Optional[str] = None, estado: Optional[str] = None) -> List[Dict]:
    """List submissions for a tenant, optionally filtered by farm and state."""
    conn = None
    cur = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        sql = "SELECT * FROM cue_estado_envio WHERE tenant_id = %s"
        params = [tenant_id]
        if farm_id:
            sql += " AND farm_id = %s"
            params.append(farm_id)
        if estado:
            sql += " AND estado = %s"
            params.append(estado)
        sql += " ORDER BY created_at DESC LIMIT 100"
        cur.execute(sql, params)
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            for k in ('created_at', 'updated_at', 'fecha_presentacion'):
                if d.get(k):
                    d[k] = d[k].isoformat()
            results.append(d)
        return results
    except Exception as e:
        logger.error(f"Error listing submissions: {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
