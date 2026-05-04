#!/usr/bin/env python3
"""
Gestor-specific routes for the CUE module.
Farmer authorization management + gestor tenant listing + consolidated dashboard.
"""
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Blueprint, jsonify, request, g
from .auth_middleware import require_auth, get_current_tenant
from .gestor_auth import (
    require_gestor_mode, GESTOR_ROLE,
    list_gestor_authorized_tenants,
    lookup_user_by_email, POSTGRES_URL,
)

logger = logging.getLogger(__name__)

gestor_bp = Blueprint('gestor', __name__, url_prefix='/api/modules/cue/gestor')


def _get_pg_conn():
    conn = psycopg2.connect(POSTGRES_URL)
    conn.cursor_factory = RealDictCursor
    return conn


# =========================================================================
# GESTOR ROUTES (require GestorCUE role)
# =========================================================================

@gestor_bp.route('/tenants', methods=['GET'])
@require_auth
@require_gestor_mode
def list_authorized_tenants():
    """List farmer tenants this gestor can manage."""
    gestor_sub = getattr(g, 'user_id', None)
    if not gestor_sub:
        return jsonify({'error': 'Usuario no identificado'}), 401
    tenants = list_gestor_authorized_tenants(gestor_sub)
    return jsonify(tenants), 200


@gestor_bp.route('/submissions', methods=['GET'])
@require_auth
@require_gestor_mode
def list_gestor_submissions():
    """
    Consolidated view: all submissions across all farmers this gestor manages.
    Query params: estado, farmer_tenant, desde, hasta
    """
    gestor_sub = getattr(g, 'user_id', None)
    if not gestor_sub:
        return jsonify({'error': 'Usuario no identificado'}), 401

    estado = request.args.get('estado')
    farmer_tenant = request.args.get('farmer_tenant')
    desde = request.args.get('desde')
    hasta = request.args.get('hasta')
    limit = min(int(request.args.get('limit', 200)), 500)

    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()

        sql = """
            SELECT e.*, ga.farmer_name
            FROM cue_estado_envio e
            JOIN cue_gestor_autorizaciones ga ON e.tenant_id = ga.farmer_tenant
            WHERE ga.gestor_sub = %s AND ga.autorizado = true
        """
        params = [gestor_sub]

        if estado:
            sql += " AND e.estado = %s"
            params.append(estado)
        if farmer_tenant:
            sql += " AND e.tenant_id = %s"
            params.append(farmer_tenant)
        if desde:
            sql += " AND e.created_at >= %s"
            params.append(desde)
        if hasta:
            sql += " AND e.created_at <= %s"
            params.append(hasta)

        sql += " ORDER BY e.created_at DESC LIMIT %s"
        params.append(limit)

        cur.execute(sql, params)
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            for k in ('created_at', 'updated_at', 'fecha_presentacion', 'autorizado_at'):
                if d.get(k):
                    d[k] = d[k].isoformat()
            results.append(d)

        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error listing gestor submissions: {e}")
        return jsonify({'error': 'Error al consultar envíos'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =========================================================================
# FARMER AUTHORIZATION ROUTES (require Farmer role, NOT GestorCUE)
# =========================================================================

@gestor_bp.route('/mis-autorizaciones', methods=['GET'])
@require_auth
def list_mis_autorizaciones():
    """List all gestor authorizations for the current farmer tenant."""
    roles = getattr(g, 'roles', [])
    if GESTOR_ROLE in roles:
        return jsonify({'error': 'Los gestores no pueden gestionar autorizaciones desde esta ruta'}), 403

    farmer_tenant = get_current_tenant()
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, gestor_sub, gestor_username, gestor_tenant, autorizado, "
            "autorizado_at, created_at "
            "FROM cue_gestor_autorizaciones "
            "WHERE farmer_tenant = %s "
            "ORDER BY created_at DESC",
            (farmer_tenant,)
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            for k in ('created_at', 'updated_at', 'autorizado_at'):
                if d.get(k):
                    d[k] = d[k].isoformat()
            results.append(d)
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error listing autorizaciones: {e}")
        return jsonify({'error': 'Error al consultar autorizaciones'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@gestor_bp.route('/solicitar', methods=['POST'])
@require_auth
def solicitar_autorizacion():
    """
    Farmer authorizes a gestor for their tenant.

    Accepts: { gestor_email } — the gestor's email address.
    Backend resolves the email against Keycloak, verifies the user has
    GestorCUE role, and auto-fills gestor_sub/gestor_username/gestor_tenant.
    """
    roles = getattr(g, 'roles', [])
    if GESTOR_ROLE in roles:
        return jsonify({'error': 'Los gestores no pueden auto-autorizarse'}), 403

    farmer_tenant = get_current_tenant()
    data = request.json or {}

    gestor_email = (data.get('gestor_email') or '').strip().lower()
    if not gestor_email:
        return jsonify({'error': 'Se requiere el email del gestor'}), 400

    # Resolve gestor via Keycloak
    gestor_info = lookup_user_by_email(gestor_email)
    if not gestor_info:
        return jsonify({'error': f'No se encontró ningún usuario con email {gestor_email}'}), 404

    if GESTOR_ROLE not in gestor_info.get('roles', []):
        return jsonify({
            'error': f'El usuario {gestor_email} no tiene el rol GestorCUE. '
                     'Solo los usuarios con rol de gestor pueden gestionar cuadernos de campo.'
        }), 422

    gestor_sub = gestor_info['sub']
    gestor_username = gestor_info['username'] or gestor_email
    gestor_tenant = gestor_info['tenant_id'] or ''

    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()

        # Check no other gestor is already authorized for this farmer
        cur.execute(
            "SELECT id, gestor_sub, gestor_username FROM cue_gestor_autorizaciones "
            "WHERE farmer_tenant = %s AND autorizado = true",
            (farmer_tenant,)
        )
        existing = cur.fetchone()
        if existing:
            return jsonify({
                'error': f'Este tenant ya tiene un gestor autorizado: {existing["gestor_username"]}. '
                         'Revóquelo antes de autorizar a otro.',
                'existing_gestor': dict(existing),
            }), 409

        # Get farmer name from JWT or use tenant as fallback
        farmer_name = getattr(g, 'username', None) or farmer_tenant
        farmer_sub = getattr(g, 'user_id', None)

        # Upsert the authorization record
        cur.execute(
            "INSERT INTO cue_gestor_autorizaciones "
            "(gestor_sub, gestor_username, gestor_tenant, farmer_tenant, farmer_name, farmer_sub, autorizado, autorizado_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,true,NOW()) "
            "ON CONFLICT (gestor_sub, farmer_tenant) DO UPDATE SET "
            "autorizado = true, autorizado_at = NOW(), "
            "gestor_username = EXCLUDED.gestor_username, "
            "gestor_tenant = EXCLUDED.gestor_tenant, "
            "farmer_name = EXCLUDED.farmer_name "
            "RETURNING id",
            (gestor_sub, gestor_username, gestor_tenant, farmer_tenant, farmer_name, farmer_sub)
        )
        row = cur.fetchone()
        conn.commit()

        logger.info(f"Farmer {farmer_tenant} authorized gestor {gestor_sub} ({gestor_email})")
        return jsonify({
            'status': 'authorized',
            'id': row['id'],
            'gestor_username': gestor_username,
            'gestor_email': gestor_email,
        }), 201
    except Exception as e:
        logger.error(f"Error in solicitar_autorizacion: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': f'Error al autorizar: {str(e)}'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@gestor_bp.route('/autorizar/<int:autorizacion_id>', methods=['DELETE'])
@require_auth
def revocar_autorizacion(autorizacion_id):
    """
    Farmer revokes a gestor's authorization.
    Sets autorizado=false instead of deleting (audit trail).
    """
    roles = getattr(g, 'roles', [])
    if GESTOR_ROLE in roles:
        return jsonify({'error': 'Los gestores no pueden modificar autorizaciones'}), 403

    farmer_tenant = get_current_tenant()
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE cue_gestor_autorizaciones SET autorizado = false "
            "WHERE id = %s AND farmer_tenant = %s "
            "RETURNING id, gestor_username",
            (autorizacion_id, farmer_tenant)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Autorización no encontrada'}), 404
        conn.commit()

        logger.info(f"Farmer {farmer_tenant} revoked gestor {row['gestor_username']}")
        return jsonify({'status': 'revoked', 'id': row['id']}), 200
    except Exception as e:
        logger.error(f"Error in revocar_autorizacion: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': f'Error al revocar: {str(e)}'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =========================================================================
# GESTOR-INITIATED ACCESS REQUEST
# =========================================================================

@gestor_bp.route('/solicitar-acceso', methods=['POST'])
@require_auth
@require_gestor_mode
def solicitar_acceso():
    """
    Gestor requests access to a farmer's tenant.

    Accepts: { farmer_email } — the farmer's email address.
    Creates a pending authorization record (autorizado=false) that the farmer
    can approve or reject from their 'Gestoría' tab.
    """
    gestor_sub = getattr(g, 'user_id', None)
    if not gestor_sub:
        return jsonify({'error': 'Usuario no identificado'}), 401

    data = request.json or {}
    farmer_email = (data.get('farmer_email') or '').strip().lower()
    if not farmer_email:
        return jsonify({'error': 'Se requiere el email del agricultor'}), 400

    # Resolve farmer via Keycloak
    farmer_info = lookup_user_by_email(farmer_email)
    if not farmer_info:
        return jsonify({'error': f'No se encontró ningún usuario con email {farmer_email}'}), 404

    farmer_tenant = farmer_info.get('tenant_id', '')
    if not farmer_tenant:
        return jsonify({'error': f'El usuario {farmer_email} no tiene un tenant asignado'}), 422

    farmer_name = farmer_info.get('username') or farmer_email

    # Check if gestor is already authorized for this tenant
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, autorizado FROM cue_gestor_autorizaciones "
            "WHERE gestor_sub = %s AND farmer_tenant = %s",
            (gestor_sub, farmer_tenant)
        )
        existing = cur.fetchone()
        if existing:
            if existing['autorizado']:
                return jsonify({'error': 'Ya está autorizado para gestionar este agricultor'}), 409
            else:
                return jsonify({'status': 'pending', 'message': 'Ya existe una solicitud pendiente para este agricultor'}), 200

        gestor_username = getattr(g, 'username', None) or getattr(g, 'email', None) or ''
        gestor_tenant = get_current_tenant() or ''

        cur.execute(
            "INSERT INTO cue_gestor_autorizaciones "
            "(gestor_sub, gestor_username, gestor_tenant, farmer_tenant, farmer_name, autorizado) "
            "VALUES (%s,%s,%s,%s,%s,false) "
            "RETURNING id",
            (gestor_sub, gestor_username, gestor_tenant, farmer_tenant, farmer_name)
        )
        row = cur.fetchone()
        conn.commit()

        logger.info(f"Gestor {gestor_sub} requested access to farmer {farmer_tenant}")
        return jsonify({
            'status': 'requested',
            'id': row['id'],
            'farmer_name': farmer_name,
            'message': 'Solicitud enviada. El agricultor debe aprobarla desde la pestaña Gestoría.'
        }), 201
    except Exception as e:
        logger.error(f"Error in solicitar_acceso: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': f'Error al solicitar acceso: {str(e)}'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@gestor_bp.route('/autorizar/<int:autorizacion_id>/aprobar', methods=['PUT'])
@require_auth
def aprobar_autorizacion(autorizacion_id):
    """Farmer approves a pending gestor access request."""
    roles = getattr(g, 'roles', [])
    if GESTOR_ROLE in roles:
        return jsonify({'error': 'Los gestores no pueden aprobar autorizaciones'}), 403

    farmer_tenant = get_current_tenant()
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE cue_gestor_autorizaciones SET autorizado = true, autorizado_at = NOW() "
            "WHERE id = %s AND farmer_tenant = %s AND autorizado = false "
            "RETURNING id, gestor_username",
            (autorizacion_id, farmer_tenant)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Solicitud no encontrada o ya procesada'}), 404
        conn.commit()
        logger.info(f"Farmer {farmer_tenant} approved gestor {row['gestor_username']}")
        return jsonify({'status': 'approved', 'id': row['id']}), 200
    except Exception as e:
        logger.error(f"Error in aprobar_autorizacion: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': f'Error al aprobar: {str(e)}'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@gestor_bp.route('/autorizar/<int:autorizacion_id>/rechazar', methods=['PUT'])
@require_auth
def rechazar_autorizacion(autorizacion_id):
    """Farmer rejects a pending gestor access request."""
    roles = getattr(g, 'roles', [])
    if GESTOR_ROLE in roles:
        return jsonify({'error': 'Los gestores no pueden rechazar autorizaciones'}), 403

    farmer_tenant = get_current_tenant()
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM cue_gestor_autorizaciones "
            "WHERE id = %s AND farmer_tenant = %s AND autorizado = false "
            "RETURNING id, gestor_username",
            (autorizacion_id, farmer_tenant)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Solicitud no encontrada o ya procesada'}), 404
        conn.commit()
        logger.info(f"Farmer {farmer_tenant} rejected gestor {row['gestor_username']}")
        return jsonify({'status': 'rejected', 'id': row['id']}), 200
    except Exception as e:
        logger.error(f"Error in rechazar_autorizacion: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': f'Error al rechazar: {str(e)}'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
