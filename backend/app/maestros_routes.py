#!/usr/bin/env python3
"""Legal masters CRUD for CUE: ROMA application equipment and ROPO applicators/advisors.

Tenant-scoped tables owned by nkz_module_cue. Read endpoints also accept
X-Internal-Service-Secret so field-operations can populate dropdowns without
duplicating master data.
"""

import logging
from datetime import date
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Blueprint, jsonify, request

from .auth_middleware import require_auth, get_current_tenant
from .common.db import get_postgres_url

logger = logging.getLogger(__name__)

maestros_bp = Blueprint('maestros', __name__, url_prefix='/api/modules/cue')

VALID_ROPO_LEVELS = frozenset({'basico', 'cualificado', 'fumigador', 'piloto', 'asesor_gip'})


def _get_pg_conn():
    conn = psycopg2.connect(get_postgres_url())
    conn.cursor_factory = RealDictCursor
    return conn


def _serialize_row(row: dict) -> dict:
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, 'isoformat'):
            out[k] = v.isoformat()
    return out


def _parse_iso_date(raw, field_name: str):
    if raw in (None, ''):
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError as exc:
        raise ValueError(f'{field_name} debe ser una fecha ISO (YYYY-MM-DD)') from exc


# =========================================================================
# EQUIPOS ROMA (Machinery / Application Equipment)
# =========================================================================

@maestros_bp.route('/equipos-roma', methods=['GET'])
@require_auth
def list_equipos_roma():
    tenant = get_current_tenant()
    incluir_inactivos = request.args.get('incluir_inactivos', 'false').lower() == 'true'
    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        sql = "SELECT * FROM cue_equipo_aplicacion WHERE tenant_id = %s"
        params = [tenant]
        if not incluir_inactivos:
            sql += " AND activo = true"
        sql += " ORDER BY nombre"
        cur.execute(sql, params)
        today = date.today()
        rows = []
        for r in cur.fetchall():
            item = _serialize_row(r)
            prox = r.get('fecha_proxima_iteaf')
            item['iteaf_vigente'] = (prox >= today) if prox else None
            rows.append(item)
        return jsonify(rows), 200
    except Exception as e:
        logger.error(f"Error listing equipos ROMA: {e}")
        return jsonify({'error': 'Error al consultar equipos ROMA'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@maestros_bp.route('/equipos-roma', methods=['POST'])
@require_auth
def create_equipo_roma():
    tenant = get_current_tenant()
    data = request.get_json(silent=True) or {}
    nombre = (data.get('nombre') or '').strip()
    numero_roma = (data.get('numero_roma') or '').strip()
    if not nombre or not numero_roma:
        return jsonify({'error': 'Los campos nombre y numero_roma son obligatorios'}), 400
    try:
        ultima = _parse_iso_date(data.get('fecha_ultima_iteaf'), 'fecha_ultima_iteaf')
        proxima = _parse_iso_date(data.get('fecha_proxima_iteaf'), 'fecha_proxima_iteaf')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cue_equipo_aplicacion
                (tenant_id, nombre, numero_roma, tipo_equipo, capacidad_litros,
                 fecha_ultima_iteaf, fecha_proxima_iteaf, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, true)
            RETURNING *
            """,
            (
                tenant,
                nombre,
                numero_roma,
                (data.get('tipo_equipo') or 'pulverizador_hidraulico').strip(),
                data.get('capacidad_litros'),
                ultima,
                proxima,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return jsonify(_serialize_row(row)), 201
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({'error': f'Ya existe un equipo con numero_roma {numero_roma}'}), 409
    except Exception as e:
        logger.error(f"Error creating equipo ROMA: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': 'Error al crear equipo ROMA'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@maestros_bp.route('/equipos-roma/<int:equipo_id>', methods=['PUT'])
@require_auth
def update_equipo_roma(equipo_id):
    tenant = get_current_tenant()
    data = request.get_json(silent=True) or {}
    updates = []
    params = []
    for key in ('nombre', 'numero_roma', 'tipo_equipo', 'capacidad_litros', 'activo'):
        if key in data:
            updates.append(f"{key} = %s")
            params.append(data[key])
    try:
        for dkey in ('fecha_ultima_iteaf', 'fecha_proxima_iteaf'):
            if dkey in data:
                updates.append(f"{dkey} = %s")
                params.append(_parse_iso_date(data[dkey], dkey))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not updates:
        return jsonify({'error': 'No hay campos para actualizar'}), 400

    params.extend([equipo_id, tenant])
    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE cue_equipo_aplicacion SET {', '.join(updates)} "
            "WHERE id = %s AND tenant_id = %s RETURNING *",
            params,
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Equipo ROMA no encontrado'}), 404
        conn.commit()
        return jsonify(_serialize_row(row)), 200
    except Exception as e:
        logger.error(f"Error updating equipo ROMA: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': 'Error al actualizar equipo ROMA'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@maestros_bp.route('/equipos-roma/<int:equipo_id>', methods=['DELETE'])
@require_auth
def delete_equipo_roma(equipo_id):
    tenant = get_current_tenant()
    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE cue_equipo_aplicacion SET activo = false "
            "WHERE id = %s AND tenant_id = %s RETURNING id",
            (equipo_id, tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Equipo ROMA no encontrado'}), 404
        conn.commit()
        return jsonify({'status': 'deleted', 'id': equipo_id}), 200
    except Exception as e:
        logger.error(f"Error deleting equipo ROMA: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': 'Error al eliminar equipo ROMA'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =========================================================================
# APLICADORES Y ASESORES ROPO
# =========================================================================

@maestros_bp.route('/aplicadores-ropo', methods=['GET'])
@require_auth
def list_aplicadores_ropo():
    tenant = get_current_tenant()
    incluir_inactivos = request.args.get('incluir_inactivos', 'false').lower() == 'true'
    nivel = request.args.get('nivel')
    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        sql = "SELECT * FROM cue_aplicador_ropo WHERE tenant_id = %s"
        params = [tenant]
        if not incluir_inactivos:
            sql += " AND activo = true"
        if nivel:
            sql += " AND nivel_capacitacion = %s"
            params.append(nivel)
        sql += " ORDER BY nombre"
        cur.execute(sql, params)
        today = date.today()
        rows = []
        for r in cur.fetchall():
            item = _serialize_row(r)
            cad = r.get('fecha_caducidad')
            item['carne_vigente'] = (cad >= today) if cad else None
            rows.append(item)
        return jsonify(rows), 200
    except Exception as e:
        logger.error(f"Error listing aplicadores ROPO: {e}")
        return jsonify({'error': 'Error al consultar aplicadores ROPO'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@maestros_bp.route('/aplicadores-ropo', methods=['POST'])
@require_auth
def create_aplicador_ropo():
    tenant = get_current_tenant()
    data = request.get_json(silent=True) or {}
    nombre = (data.get('nombre') or '').strip()
    carne = (data.get('numero_carne_ropo') or '').strip()
    nivel = (data.get('nivel_capacitacion') or 'cualificado').strip()
    if not nombre or not carne:
        return jsonify({'error': 'Los campos nombre y numero_carne_ropo son obligatorios'}), 400
    if nivel not in VALID_ROPO_LEVELS:
        return jsonify({'error': f'nivel_capacitacion debe ser uno de: {sorted(VALID_ROPO_LEVELS)}'}), 400
    try:
        caducidad = _parse_iso_date(data.get('fecha_caducidad'), 'fecha_caducidad')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cue_aplicador_ropo
                (tenant_id, nombre, nif, numero_carne_ropo, nivel_capacitacion,
                 fecha_caducidad, activo)
            VALUES (%s, %s, %s, %s, %s, %s, true)
            RETURNING *
            """,
            (tenant, nombre, (data.get('nif') or '').strip() or None, carne, nivel, caducidad),
        )
        row = cur.fetchone()
        conn.commit()
        return jsonify(_serialize_row(row)), 201
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({'error': f'Ya existe un aplicador con numero_carne_ropo {carne}'}), 409
    except Exception as e:
        logger.error(f"Error creating aplicador ROPO: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': 'Error al crear aplicador ROPO'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@maestros_bp.route('/aplicadores-ropo/<int:aplicador_id>', methods=['PUT'])
@require_auth
def update_aplicador_ropo(aplicador_id):
    tenant = get_current_tenant()
    data = request.get_json(silent=True) or {}
    if 'nivel_capacitacion' in data and data['nivel_capacitacion'] not in VALID_ROPO_LEVELS:
        return jsonify({'error': f'nivel_capacitacion debe ser uno de: {sorted(VALID_ROPO_LEVELS)}'}), 400
    updates = []
    params = []
    for key in ('nombre', 'nif', 'numero_carne_ropo', 'nivel_capacitacion', 'activo'):
        if key in data:
            updates.append(f"{key} = %s")
            params.append(data[key])
    try:
        if 'fecha_caducidad' in data:
            updates.append("fecha_caducidad = %s")
            params.append(_parse_iso_date(data['fecha_caducidad'], 'fecha_caducidad'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not updates:
        return jsonify({'error': 'No hay campos para actualizar'}), 400

    params.extend([aplicador_id, tenant])
    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            f"UPDATE cue_aplicador_ropo SET {', '.join(updates)} "
            "WHERE id = %s AND tenant_id = %s RETURNING *",
            params,
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Aplicador ROPO no encontrado'}), 404
        conn.commit()
        return jsonify(_serialize_row(row)), 200
    except Exception as e:
        logger.error(f"Error updating aplicador ROPO: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': 'Error al actualizar aplicador ROPO'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@maestros_bp.route('/aplicadores-ropo/<int:aplicador_id>', methods=['DELETE'])
@require_auth
def delete_aplicador_ropo(aplicador_id):
    tenant = get_current_tenant()
    conn = cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE cue_aplicador_ropo SET activo = false "
            "WHERE id = %s AND tenant_id = %s RETURNING id",
            (aplicador_id, tenant),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Aplicador ROPO no encontrado'}), 404
        conn.commit()
        return jsonify({'status': 'deleted', 'id': aplicador_id}), 200
    except Exception as e:
        logger.error(f"Error deleting aplicador ROPO: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': 'Error al eliminar aplicador ROPO'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
