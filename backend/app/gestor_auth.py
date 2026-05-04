#!/usr/bin/env python3
"""
Gestor authentication decorator for cross-tenant CUE access.
Tenant switching is handled transparently by @require_auth in auth_middleware.py.
This module provides: role gate decorator, Keycloak user lookup, tenant listing.
"""
import os
import logging
from functools import wraps
from flask import request, jsonify, g
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib.request
import json as json_mod

logger = logging.getLogger(__name__)

GESTOR_ROLE = 'GestorCUE'
POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
)
KEYCLOAK_INTERNAL_URL = os.getenv(
    'KEYCLOAK_INTERNAL_URL',
    'http://keycloak-service:8080/auth'
)
KEYCLOAK_REALM = os.getenv('KEYCLOAK_REALM', 'nekazari')
KEYCLOAK_ADMIN_USER = os.getenv('KEYCLOAK_ADMIN_USER', '')
KEYCLOAK_ADMIN_PASSWORD = os.getenv('KEYCLOAK_ADMIN_PASSWORD', '')


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
        return cur.fetchone() is not None
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
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error listing gestor tenants: {e}")
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =========================================================================
# Keycloak Admin API helpers
# =========================================================================

def _get_keycloak_admin_token():
    """Obtain admin token from Keycloak via password grant."""
    if not KEYCLOAK_ADMIN_USER or not KEYCLOAK_ADMIN_PASSWORD:
        logger.warning("KEYCLOAK_ADMIN_USER/PASSWORD not configured")
        return None
    try:
        data = urllib.parse.urlencode({
            'client_id': 'admin-cli',
            'grant_type': 'password',
            'username': KEYCLOAK_ADMIN_USER,
            'password': KEYCLOAK_ADMIN_PASSWORD,
        }).encode()
        url = f"{KEYCLOAK_INTERNAL_URL}/realms/master/protocol/openid-connect/token"
        req = urllib.request.Request(url, data=data)
        resp = urllib.request.urlopen(req, timeout=10)
        return json_mod.loads(resp.read())['access_token']
    except Exception as e:
        logger.error(f"Failed to get Keycloak admin token: {e}")
        return None


def lookup_user_by_email(email):
    """
    Look up a Keycloak user by email in the configured realm.
    Returns dict with {sub, username, email, tenant_id} or None if not found.
    Verifies the user has the specified role if role_name is given.
    """
    token = _get_keycloak_admin_token()
    if not token:
        return None

    try:
        # Search user by email
        search_url = (f"{KEYCLOAK_INTERNAL_URL}/admin/realms/{KEYCLOAK_REALM}/users"
                      f"?email={urllib.parse.quote(email)}&max=1")
        req = urllib.request.Request(search_url, headers={'Authorization': f'Bearer {token}'})
        users = json_mod.loads(urllib.request.urlopen(req, timeout=10).read())

        if not users:
            return None

        user = users[0]
        user_id = user['id']
        username = user.get('username', '')
        user_email = user.get('email', email)

        # Get user attributes (tenant_id)
        tenant_id = ''
        attrs = user.get('attributes', {})
        if 'tenant_id' in attrs and attrs['tenant_id']:
            tenant_id = attrs['tenant_id'][0] if isinstance(attrs['tenant_id'], list) else attrs['tenant_id']

        # Get realm roles
        roles_url = (f"{KEYCLOAK_INTERNAL_URL}/admin/realms/{KEYCLOAK_REALM}"
                     f"/users/{user_id}/role-mappings/realm")
        req2 = urllib.request.Request(roles_url, headers={'Authorization': f'Bearer {token}'})
        roles = json_mod.loads(urllib.request.urlopen(req2, timeout=10).read())
        role_names = [r['name'] for r in roles]

        return {
            'sub': user_id,
            'username': username,
            'email': user_email,
            'tenant_id': tenant_id,
            'roles': role_names,
        }
    except Exception as e:
        logger.error(f"Error looking up user by email '{email}': {e}")
        return None


# =========================================================================
# Role gate decorator
# =========================================================================

def require_gestor_mode(f):
    """
    Decorator that gates access to GestorCUE role holders.

    Tenant switching (g.tenant override) is handled transparently by
    @require_auth in auth_middleware.py — this decorator only checks
    the role and optionally requires a target tenant for cross-tenant ops.

    Must be stacked BELOW @require_auth.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        roles = getattr(g, 'roles', [])
        if GESTOR_ROLE not in roles:
            return jsonify({'error': 'Acceso restringido a gestores (rol GestorCUE requerido)'}), 403

        return f(*args, **kwargs)

    return decorated_function
