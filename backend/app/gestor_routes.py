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
    list_gestor_authorized_tenants, _validate_gestor_autorizacion,
    POSTGRES_URL,
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


@gestor_bp.route('/switch-tenant', methods=['POST'])
@require_auth
@require_gestor_mode
def switch_tenant():
    """Validate gestor can access a farmer tenant."""
    data = request.json or {}
    target_tenant = data.get('tenant_id')
    if not target_tenant:
        return jsonify({'error': 'Se requiere tenant_id'}), 400
    gestor_sub = getattr(g, 'user_id', None)
    if not gestor_sub:
        return jsonify({'error': 'Usuario no identificado'}), 401
    if not _validate_gestor_autorizacion(gestor_sub, target_tenant):
        return jsonify({'error': 'No autorizado'}), 403
    return jsonify({'tenant_id': target_tenant, 'gestor_mode': True}), 200


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
    Body: { gestor_sub, gestor_username, gestor_tenant }

    Creates or updates the authorization record with autorizado=true.
    Only non-gestor users (farmers) can call this.
    """
    roles = getattr(g, 'roles', [])
    if GESTOR_ROLE in roles:
        return jsonify({'error': 'Los gestores no pueden auto-autorizarse'}), 403

    farmer_tenant = get_current_tenant()
    data = request.json or {}

    gestor_sub = data.get('gestor_sub')
    gestor_username = data.get('gestor_username')
    gestor_tenant = data.get('gestor_tenant')

    if not gestor_sub or not gestor_username:
        return jsonify({'error': 'Se requiere gestor_sub y gestor_username'}), 400

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
                'error': f'Este tenant ya tiene un gestor autorizado: {existing["gestor_username"]}',
                'existing_gestor': dict(existing),
            }), 409

        # Upsert the authorization record
        farmer_sub = getattr(g, 'user_id', None)
        cur.execute(
            "INSERT INTO cue_gestor_autorizaciones "
            "(gestor_sub, gestor_username, gestor_tenant, farmer_tenant, farmer_sub, autorizado, autorizado_at) "
            "VALUES (%s,%s,%s,%s,%s,true,NOW()) "
            "ON CONFLICT (gestor_sub, farmer_tenant) DO UPDATE SET "
            "autorizado = true, autorizado_at = NOW(), "
            "gestor_username = EXCLUDED.gestor_username, "
            "gestor_tenant = EXCLUDED.gestor_tenant "
            "RETURNING id",
            (gestor_sub, gestor_username, gestor_tenant, farmer_tenant, farmer_sub)
        )
        row = cur.fetchone()
        conn.commit()

        logger.info(f"Farmer {farmer_tenant} authorized gestor {gestor_sub}")
        return jsonify({'status': 'authorized', 'id': row['id']}), 201
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
