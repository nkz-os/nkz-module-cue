#!/usr/bin/env python3
"""
Gestor authentication decorator for cross-tenant CUE access.
Requires @require_auth to have run first (populates g.roles, g.user_id).
"""
import os
import logging
from functools import wraps
from flask import request, jsonify, g
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

GESTOR_ROLE = 'GestorCUE'
POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
)


def _get_pg_conn():
    conn = psycopg2.connect(POSTGRES_URL)
    conn.cursor_factory = RealDictCursor
    return conn


def _validate_gestor_autorizacion(gestor_sub, farmer_tenant):
    """Check if gestor is authorized for a given farmer tenant."""
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM cue_gestor_autorizaciones "
            "WHERE gestor_sub = %s AND farmer_tenant = %s AND autorizado = true",
            (gestor_sub, farmer_tenant)
        )
        row = cur.fetchone()
        return row is not None
    except Exception as e:
        logger.error(f"Error validating gestor authorization: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def list_gestor_authorized_tenants(gestor_sub):
    """List all authorized farmer tenants for a gestor."""
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT farmer_tenant, farmer_name, autorizado_at "
            "FROM cue_gestor_autorizaciones "
            "WHERE gestor_sub = %s AND autorizado = true "
            "ORDER BY farmer_name",
            (gestor_sub,)
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error listing gestor tenants: {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def require_gestor_mode(f):
    """
    Decorator that enables gestor cross-tenant mode.

    If user has GestorCUE role AND X-Gestor-Target-Tenant header/query param,
    validates authorization and overrides g.tenant with the farmer tenant.

    Must be stacked BELOW @require_auth.
    Uses query param as fallback if header not present (avoids CORS preflight for GET).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        roles = getattr(g, 'roles', [])
        if GESTOR_ROLE not in roles:
            return f(*args, **kwargs)

        # Accept target tenant from header OR query param (for GET without preflight)
        target_tenant = (
            request.headers.get('X-Gestor-Target-Tenant')
            or request.args.get('gestor_tenant')
        )

        if not target_tenant:
            # Gestor without target — still in gestor mode, route handles it
            g.gestor_mode = True
            return f(*args, **kwargs)

        gestor_sub = getattr(g, 'user_id', None)
        if not gestor_sub:
            return jsonify({'error': 'No se pudo identificar al gestor'}), 401

        if not _validate_gestor_autorizacion(gestor_sub, target_tenant):
            return jsonify({
                'error': 'No está autorizado para gestionar este tenant',
                'gestor_sub': gestor_sub,
                'target_tenant': target_tenant,
            }), 403

        g.tenant = target_tenant
        g.tenant_id = target_tenant
        g.gestor_mode = True
        g.gestor_sub = gestor_sub

        return f(*args, **kwargs)

    return decorated_function
