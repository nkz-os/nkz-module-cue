#!/usr/bin/env python3
# =============================================================================
# Authentication Middleware for CUE Module
# =============================================================================
# Trusts API Gateway validation — decodes token without signature verification.
# Extracts tenant from X-Tenant-ID header (set by API Gateway).
# Integrated gestor cross-tenant support — transparent to all routes.

import os
import hmac
import hashlib
import time
import logging
from functools import wraps
from flask import request, jsonify, g
import jwt
import psycopg2

from .common.db import get_postgres_url

logger = logging.getLogger(__name__)

GESTOR_ROLE = 'GestorCUE'
HMAC_WINDOW_SECONDS = 300

# Internal-service-secret may bypass JWT for read-only reference GETs, plus an
# explicit allowlist of internal write endpoints (SIEX registration from
# field-operations and scheduled IUWS polling). It MUST NOT cover arbitrary mutations.
_INTERNAL_WRITE_PATHS = frozenset({
    '/api/modules/cue/tratamientos',
    '/api/modules/cue/fertilizaciones',
    '/api/modules/cue/poll-iuws',
})


def _require_hmac() -> bool:
    # Fail-closed by default: require HMAC unless explicitly opted out for local dev/tests.
    return os.getenv('REQUIRE_HMAC_SIGNATURE', 'true').lower() not in ('0', 'false', 'no', 'off')


def verify_hmac_signature(
    secret: str,
    signature_header: str,
    token: str,
    tenant_id: str,
    window_seconds: int = HMAC_WINDOW_SECONDS,
) -> bool:
    """Verify canonical platform HMAC signature ({hexdigest}:{timestamp}).

    Payload format: '{token}|{tenant_id}|{timestamp}'.
    Fail-closed when secret or header is missing/malformed/expired.
    """
    if not secret or not signature_header:
        return False
    parts = signature_header.split(':')
    if len(parts) != 2:
        return False
    provided_sig, timestamp_str = parts
    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False
    if abs(int(time.time()) - timestamp) > window_seconds:
        return False
    payload = f'{token}|{tenant_id}|{timestamp}'
    expected_sig = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


def _validate_gestor_access(gestor_sub, farmer_tenant):
    """Check gestor authorization record for a farmer tenant. Returns bool."""
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(get_postgres_url())
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
        internal_method_ok = request.method == "GET" or (
            request.method == "POST" and request.path in _INTERNAL_WRITE_PATHS
        )
        if (
            internal_method_ok
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

        if _require_hmac():
            hmac_secret = os.getenv('HMAC_SECRET', '')
            sig_header = request.headers.get('X-Auth-Signature', '')
            if not tenant_id or not verify_hmac_signature(hmac_secret, sig_header, token, tenant_id):
                logger.warning("Rejected request with missing or invalid X-Auth-Signature")
                return jsonify({'error': 'Firma de autenticación inválida o ausente'}), 401

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

            # Identity and roles come strictly from the HMAC-bound JWT payload,
            # never from unsigned X-User-ID / X-User-Roles headers.
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
