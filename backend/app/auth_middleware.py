#!/usr/bin/env python3
# =============================================================================
# Authentication Middleware for CUE Module
# =============================================================================
# Trusts API Gateway validation — decodes token without signature verification.
# Extracts tenant from X-Tenant-ID header (set by API Gateway).
# Integrated gestor cross-tenant support — transparent to all routes.

import os
import hmac
import logging
from functools import wraps
from flask import request, jsonify, g
import jwt
import psycopg2

logger = logging.getLogger(__name__)

TRUST_API_GATEWAY = os.getenv('TRUST_API_GATEWAY', 'true').lower() == 'true'
GESTOR_ROLE = 'GestorCUE'
POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
)


def _validate_gestor_access(gestor_sub, farmer_tenant):
    """Check gestor authorization record for a farmer tenant. Returns bool."""
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(POSTGRES_URL)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM cue_gestor_autorizaciones "
            "WHERE gestor_sub = %s AND farmer_tenant = %s AND autorizado = true",
            (gestor_sub, farmer_tenant)
        )
        return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Error validating gestor access: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_request_token():
    """Extract JWT token from Authorization header or httpOnly cookie (fallback)."""
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]
    return request.cookies.get('nkz_token')


def require_auth(f):
    """
    Authentication decorator for Flask routes.

    Trusts API Gateway validation:
    - If X-Tenant-ID header is present, uses it (API Gateway already validated)
    - Only decodes token to extract user info (no signature verification)
    - Stores user info in Flask g for access in route handlers
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        internal_secret = os.getenv("INTERNAL_SERVICE_SECRET", "")
        provided = request.headers.get("X-Internal-Service-Secret", "")
        if (
            request.method == "GET"
            and internal_secret
            and provided
            and hmac.compare_digest(provided, internal_secret)
        ):
            g.current_user = {}
            g.tenant = request.headers.get("X-Tenant-ID", "")
            g.tenant_id = g.tenant
            g.user_id = "internal-service"
            g.username = "internal-service"
            g.email = ""
            g.roles = []
            return f(*args, **kwargs)
        token = get_request_token()
        if not token:
            return jsonify({'error': 'Falta cabecera de autorización o es inválida'}), 401

        tenant_id = request.headers.get('X-Tenant-ID')

        try:
            payload = jwt.decode(token, options={
                "verify_signature": False,
                "verify_exp": True
            })

            if not tenant_id:
                tenant_id = (
                    payload.get('tenant_id')
                    or payload.get('tenant-id')
                    or payload.get('tenant')
                )

            if not tenant_id:
                logger.warning("No tenant_id found in token or X-Tenant-ID header")
                return jsonify({'error': 'No se encontró el ID del tenant'}), 401

            g.current_user = payload
            g.tenant = tenant_id
            g.tenant_id = tenant_id
            g.user_id = payload.get('sub')
            g.username = payload.get('preferred_username')
            g.email = payload.get('email')
            g.roles = payload.get('realm_access', {}).get('roles', [])

            # ── Gestor cross-tenant support ──
            if GESTOR_ROLE in g.roles:
                g.gestor_mode = True
                g.gestor_sub = g.user_id
                target_tenant = (
                    request.headers.get('X-Gestor-Target-Tenant')
                    or request.args.get('gestor_tenant')
                )
                if target_tenant and target_tenant != g.tenant:
                    if _validate_gestor_access(g.user_id, target_tenant):
                        g.tenant = target_tenant
                        g.tenant_id = target_tenant
                        g.gestor_target_tenant = target_tenant
                    else:
                        return jsonify({
                            'error': 'No está autorizado para gestionar este tenant',
                            'gestor_sub': g.user_id,
                            'target_tenant': target_tenant,
                        }), 403

            return f(*args, **kwargs)

        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return jsonify({'error': 'El token ha expirado'}), 401
        except Exception as e:
            logger.error(f"Error in auth decorator: {e}")
            return jsonify({'error': 'Error de autenticación'}), 500

    return decorated_function


def get_current_user():
    """Get current user from Flask request context."""
    return getattr(g, 'current_user', None)


def get_current_tenant():
    """Get current tenant from Flask request context."""
    return getattr(g, 'tenant', None) or getattr(g, 'tenant_id', None)
