#!/usr/bin/env python3
# =============================================================================
# IUWS Polling Worker — cron job for checking submission status
# =============================================================================
# Periodically polls IUWS endpoints for pending submissions and updates
# their state in cue_estado_envio.
#
# Run: python -m app.integration.iuws_poller
# Cron: */5 * * * * (every 5 minutes)

import os
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor

from .iuws_client import (
    check_submission_status,
    resolve_iuws_url,
    translate_siex_error,
)
from .state_machine import transition_state

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
)

# States to poll (active submissions)
POLLABLE_STATES = ['pendiente', 'procesando']

# Max age for polling (skip submissions older than 30 days)
MAX_POLL_AGE_DAYS = 30


def _get_conn():
    conn = psycopg2.connect(POSTGRES_URL)
    conn.cursor_factory = RealDictCursor
    return conn


def get_pending_submissions() -> list:
    """Fetch all submissions that need status polling."""
    conn = None
    cur = None
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cutoff = datetime.now() - timedelta(days=MAX_POLL_AGE_DAYS)
        cur.execute(
            "SELECT id, id_ticket, provincia, estado, tenant_id, farm_id "
            "FROM cue_estado_envio "
            "WHERE estado = ANY(%s) "
            "AND id_ticket IS NOT NULL "
            "AND provincia IS NOT NULL "
            "AND created_at > %s "
            "ORDER BY created_at",
            (POLLABLE_STATES, cutoff)
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error fetching pending submissions: {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def poll_submission(sub: Dict[str, Any]) -> Dict[str, Any]:
    """
    Poll a single submission's status from IUWS.

    Returns poll result summary.
    """
    sub_id = sub['id']
    id_ticket = sub['id_ticket']
    provincia = sub['provincia']

    iuws_url = resolve_iuws_url(provincia)
    if not iuws_url:
        logger.warning(f"Skipping submission {sub_id}: no IUWS URL for provincia {provincia}")
        return {'submission_id': sub_id, 'status': 'skipped', 'reason': 'no_iuws_url'}

    status, result = check_submission_status(iuws_url, id_ticket)
    estado = result.get('estado', 'unknown')

    if status != 200:
        logger.warning(f"Submission {sub_id}: IUWS returned {status}, keeping current state")
        return {'submission_id': sub_id, 'status': 'error', 'http_status': status}

    # Map IUWS state to state machine state
    state_map = {
        'pendiente': 'pendiente',
        'en_proceso': 'procesando',
        'procesando': 'procesando',
        'aceptado': 'aceptado',
        'aceptada': 'aceptado',
        'aceptado_con_advertencias': 'aceptado_con_advertencias',
        'pendiente_de_subsanacion': 'pendiente_de_subsanacion',
        'rechazado': 'rechazado_con_errores',
        'rechazado_con_errores': 'rechazado_con_errores',
    }

    new_state = state_map.get(estado.lower() if estado else '', '')
    if not new_state:
        logger.info(f"Submission {sub_id}: estado='{estado}' (no mapping), keeping current")
        return {'submission_id': sub_id, 'status': 'unchanged', 'estado': estado}

    if new_state == sub['estado']:
        return {'submission_id': sub_id, 'status': 'unchanged', 'estado': estado}

    # Transition state
    metadata = {}
    if new_state == 'rechazado_con_errores':
        error_codes = result.get('detail', {}).get('errores', [])
        metadata['errores'] = error_codes
        metadata['errores_traducidos'] = [translate_siex_error(e) for e in error_codes]

    ok, msg = transition_state(sub_id, new_state, metadata)
    if ok:
        logger.info(f"Submission {sub_id}: {sub['estado']} → {new_state}")
        return {
            'submission_id': sub_id,
            'status': 'transitioned',
            'from_state': sub['estado'],
            'to_state': new_state,
        }
    else:
        logger.error(f"Submission {sub_id}: transition failed: {msg}")
        return {'submission_id': sub_id, 'status': 'error', 'reason': msg}


def run_polling_cycle() -> Dict[str, Any]:
    """
    Run a full polling cycle: fetch pending submissions, poll each one,
    transition states. Returns summary.
    """
    start_time = time.time()
    logger.info("Starting IUWS polling cycle")

    pending = get_pending_submissions()
    summary = {
        'total_pending': len(pending),
        'polled': 0,
        'transitioned': 0,
        'unchanged': 0,
        'skipped': 0,
        'errors': 0,
        'details': [],
    }

    for sub in pending:
        result = poll_submission(sub)
        summary['polled'] += 1

        status = result.get('status', 'error')
        if status == 'transitioned':
            summary['transitioned'] += 1
        elif status == 'unchanged':
            summary['unchanged'] += 1
        elif status == 'skipped':
            summary['skipped'] += 1
        else:
            summary['errors'] += 1

        summary['details'].append(result)

    elapsed = time.time() - start_time
    summary['elapsed_seconds'] = round(elapsed, 2)
    logger.info(f"Polling cycle complete: {summary['polled']} polled, "
                f"{summary['transitioned']} transitioned, "
                f"{summary['errors']} errors in {elapsed:.1f}s")

    return summary


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    summary = run_polling_cycle()
    print(f"Polled: {summary['polled']}")
    print(f"Transitioned: {summary['transitioned']}")
    print(f"Errors: {summary['errors']}")
