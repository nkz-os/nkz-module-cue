#!/usr/bin/env python3
# =============================================================================
# CUE Business Rules Engine — SIEX Validation
# =============================================================================
# Chainable boolean rules for validating agricultural treatments.
# All product queries use SCD Type 2 temporal validity.

import os
import logging
from datetime import date, timedelta
from typing import Tuple, Optional

import psycopg2

from ..common.db import get_postgres_url

logger = logging.getLogger(__name__)


class ProductoRevocadoError(Exception):
    """Product was revoked at the time of application."""
    pass


class DosisExcedidaError(Exception):
    """Applied dose exceeds legal maximum."""
    pass


class ProductoNoAutorizadoError(Exception):
    """Product is not authorized for the specified crop/pest."""
    pass


class PlazoSeguridadError(Exception):
    """Safety period between treatment and harvest not met."""
    pass


class PlazoRegistroWarning(Exception):
    """Registration was made after the 30-day legal window."""
    pass


def _get_pg_conn():
    conn = psycopg2.connect(get_postgres_url())
    return conn


def producto_autorizado(numero_registro: str, fecha_aplicacion: date) -> Tuple[bool, str]:
    """
    Rule 1: Verify the product was authorized on the application date.
    Uses SCD Type 2 temporal query.

    Returns (is_valid, error_message).
    """
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, estado, nombre_comercial FROM cue_producto_ropo "
            "WHERE numero_registro = %s "
            "AND fecha_inicio_validez <= %s "
            "AND (fecha_fin_validez IS NULL OR fecha_fin_validez > %s) "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (numero_registro, fecha_aplicacion, fecha_aplicacion)
        )
        row = cur.fetchone()
        if not row:
            return False, f'Producto ROPO {numero_registro} no encontrado en la fecha {fecha_aplicacion}'

        estado = row[1]
        nombre = row[2]
        if estado != 'autorizado':
            return False, f'El producto "{nombre}" ({numero_registro}) no estaba autorizado en {fecha_aplicacion} (estado: {estado})'

        return True, ''
    except Exception as e:
        logger.error(f"Error in producto_autorizado rule: {e}")
        return False, f'Error al validar autorización del producto: {e}'
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def producto_autorizado_cultivo(
    numero_registro: str, cultivo: str, plaga: str, fecha_aplicacion: date
) -> Tuple[bool, str]:
    """
    Rule 2: Verify the product is authorized for the specific crop and pest.
    Uses SCD Type 2 temporal query.
    """
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT cultivos_autorizados, plagas_autorizadas, nombre_comercial "
            "FROM cue_producto_ropo "
            "WHERE numero_registro = %s "
            "AND fecha_inicio_validez <= %s "
            "AND (fecha_fin_validez IS NULL OR fecha_fin_validez > %s) "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (numero_registro, fecha_aplicacion, fecha_aplicacion)
        )
        row = cur.fetchone()
        if not row:
            return False, f'Producto ROPO {numero_registro} no encontrado'

        cultivos = row[0] or []
        plagas = row[1] or []
        nombre = row[2]

        if cultivo not in cultivos:
            return False, (
                f'"{nombre}" no está autorizado para el cultivo "{cultivo}". '
                f'Cultivos autorizados: {", ".join(cultivos[:10])}'
            )

        if plaga and plaga not in plagas:
            return False, (
                f'"{nombre}" no está autorizado para la plaga "{plaga}". '
                f'Plagas autorizadas: {", ".join(plagas[:10])}'
            )

        return True, ''
    except Exception as e:
        logger.error(f"Error in producto_autorizado_cultivo rule: {e}")
        return False, f'Error al validar autorización cultivo/plaga: {e}'
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def dosis_legal(
    numero_registro: str,
    dosis_aplicada: float,
    fecha_aplicacion: date,
    cultivo: str = '',
    plaga: str = '',
) -> Tuple[bool, str]:
    """
    Rule 3: Verify the applied dose does not exceed the legal maximum.
    Checks per-use (product x crop x pest) authorization first, then falls back
    to product-level dosis_maxima in cue_producto_ropo (SCD Type 2).
    """
    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        uso = _lookup_per_use_authorization(cur, numero_registro, cultivo, plaga, fecha_aplicacion)
        if uso and uso[0] is not None:
            max_dosis, unidad = float(uso[0]), uso[1] or 'L/ha'
            if dosis_aplicada > max_dosis:
                return False, (
                    f'La dosis aplicada ({dosis_aplicada} {unidad}) supera la dosis máxima legal '
                    f'para {cultivo}/{plaga or "uso general"} ({max_dosis} {unidad})'
                )
            return True, ''

        cur.execute(
            "SELECT dosis_maxima, unidad_dosis, nombre_comercial "
            "FROM cue_producto_ropo "
            "WHERE numero_registro = %s "
            "AND fecha_inicio_validez <= %s "
            "AND (fecha_fin_validez IS NULL OR fecha_fin_validez > %s) "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (numero_registro, fecha_aplicacion, fecha_aplicacion)
        )
        row = cur.fetchone()
        if not row:
            return False, f'Producto ROPO {numero_registro} no encontrado'

        max_dosis = row[0]
        unidad = row[1]
        nombre = row[2]

        if max_dosis and dosis_aplicada > max_dosis:
            return False, (
                f'La dosis aplicada ({dosis_aplicada} {unidad}) supera la dosis máxima legal '
                f'({max_dosis} {unidad}) para "{nombre}"'
            )

        return True, ''
    except Exception as e:
        logger.error(f"Error in dosis_legal rule: {e}")
        return False, f'Error al validar dosis: {e}'
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def plazo_seguridad(
    numero_registro: str,
    fecha_aplicacion: date,
    fecha_cosecha: Optional[date] = None,
    cultivo: str = '',
    plaga: str = '',
) -> Tuple[bool, str]:
    """
    Rule 4: Verify the safety period between treatment and harvest.
    Checks per-use (product x crop x pest) safety period first, then product default.
    If fecha_cosecha is not provided, returns True (no harvest date to check against).
    """
    if not fecha_cosecha:
        return True, ''

    conn = None
    cur = None
    try:
        conn = _get_pg_conn()
        cur = conn.cursor()
        uso = _lookup_per_use_authorization(cur, numero_registro, cultivo, plaga, fecha_aplicacion)
        if uso and uso[2] is not None:
            plazo_dias = int(uso[2])
            dias_restantes = (fecha_cosecha - fecha_aplicacion).days
            if dias_restantes < plazo_dias:
                return False, (
                    f'El producto ({numero_registro}) requiere {plazo_dias} días de seguridad '
                    f'para {cultivo}. Quedan {dias_restantes} días (insuficiente)'
                )
            return True, ''

        cur.execute(
            "SELECT plazo_seguridad_dias, nombre_comercial "
            "FROM cue_producto_ropo "
            "WHERE numero_registro = %s "
            "AND fecha_inicio_validez <= %s "
            "AND (fecha_fin_validez IS NULL OR fecha_fin_validez > %s) "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (numero_registro, fecha_aplicacion, fecha_aplicacion)
        )
        row = cur.fetchone()
        if not row:
            return False, f'Producto ROPO {numero_registro} no encontrado'

        plazo_dias = row[0]
        nombre = row[1]

        if plazo_dias:
            dias_restantes = (fecha_cosecha - fecha_aplicacion).days
            if dias_restantes < plazo_dias:
                return False, (
                    f'"{nombre}" requiere {plazo_dias} días de seguridad entre tratamiento y cosecha. '
                    f'Quedan {dias_restantes} días (insuficiente)'
                )

        return True, ''
    except Exception as e:
        logger.error(f"Error in plazo_seguridad rule: {e}")
        return False, f'Error al validar plazo de seguridad: {e}'
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def plazo_registro(
    fecha_aplicacion: date, fecha_registro: Optional[date] = None
) -> Tuple[bool, str]:
    """
    Rule 5: Check if registration is within the 30-day legal window.
    Returns warning (not error) if exceeded — SIEX allows rectification via versioning.
    """
    if not fecha_registro:
        fecha_registro = date.today()

    dias_transcurridos = (fecha_registro - fecha_aplicacion).days
    if dias_transcurridos > 30:
        return True, (
            f'Advertencia: Han transcurrido {dias_transcurridos} días desde la aplicación. '
            f'El plazo legal es de 30 días. Se permite el registro con versionado.'
        )
    return True, ''


def _lookup_per_use_authorization(
    cur, numero_registro: str, cultivo: str, plaga: str, fecha_aplicacion: date
):
    """Look up per-use MAPA authorization (product x crop x pest) with SCD Type 2.

    Returns row tuple (dosis_maxima, unidad_dosis, plazo_seguridad_dias, max_aplicaciones)
    or None if no per-use record exists (caller falls back to cue_producto_ropo).
    """
    if not cultivo:
        return None
    try:
        cur.execute(
            "SELECT dosis_maxima, unidad_dosis, plazo_seguridad_dias, max_aplicaciones "
            "FROM cue_producto_ropo_uso "
            "WHERE numero_registro = %s "
            "AND lower(unaccent(cultivo)) = lower(unaccent(%s)) "
            "AND (%s = '' OR plaga = '' OR lower(unaccent(plaga)) = lower(unaccent(%s))) "
            "AND fecha_inicio_validez <= %s "
            "AND (fecha_fin_validez IS NULL OR fecha_fin_validez > %s) "
            "ORDER BY (plaga != '') DESC, fecha_inicio_validez DESC LIMIT 1",
            (numero_registro, cultivo, plaga or '', plaga or '', fecha_aplicacion, fecha_aplicacion),
        )
        return cur.fetchone()
    except Exception:
        return None


def validate_fertilizacion_campanya(
    fertilizaciones: list,
    vulnerable_zone: bool = False,
    signed_plan_parcels: Optional[set] = None,
) -> dict:
    """Validate campaign fertilization records against RD 1051/2022 rules.

    Checks:
      1. ZVN organic nitrogen limit (170 kg N orgánico / ha·año per parcel).
      2. Organic fertilizer incorporation method/timing (Annex V).
      3. Signed FaST fertilization plan coverage per fertilized parcel.
    """
    errors = []
    warnings = []
    organic_n_by_parcel: dict[str, float] = {}
    parcel_names: dict[str, str] = {}

    for f in fertilizaciones:
        pid = f.get('parcela_id') or 'sin_parcela'
        parcel_names[pid] = f.get('parcela_nombre') or pid
        if f.get('organico'):
            n_kg = float(f.get('n_aplicado_kg_ha') or 0.0)
            organic_n_by_parcel[pid] = organic_n_by_parcel.get(pid, 0.0) + n_kg
            if not f.get('metodo_incorporacion'):
                warnings.append({
                    'codigo': 'INCORPORACION_ORGANICO_SIN_REGISTRAR',
                    'parcela_id': pid,
                    'mensaje': f"Abonado orgánico del {f.get('fecha', '')} en {parcel_names[pid]} sin método de incorporación (RD 1051/2022 Anexo V).",
                })

    if vulnerable_zone:
        for pid, total_n in organic_n_by_parcel.items():
            if total_n > 170.0:
                errors.append({
                    'codigo': 'ZVN_LIMITE_N_ORGANICO_EXCEDIDO',
                    'parcela_id': pid,
                    'mensaje': f"Parcela {parcel_names[pid]}: {round(total_n, 2)} kg N orgánico/ha·año supera el límite legal de 170 kg N/ha en ZVN.",
                })

    if signed_plan_parcels is not None:
        fertilized_parcels = {f.get('parcela_id') for f in fertilizaciones if f.get('parcela_id')}
        for pid in sorted(fertilized_parcels - signed_plan_parcels):
            warnings.append({
                'codigo': 'SIN_PLAN_ABONADO_FIRMADO',
                'parcela_id': pid,
                'mensaje': f"Parcela {parcel_names.get(pid, pid)} tiene fertilizaciones registradas pero no consta Plan de Abonado firmado en FaST.",
            })

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
    }


def validate_tratamiento(
    numero_registro: str,
    dosis: float,
    cultivo: str,
    plaga: str,
    fecha_aplicacion: date,
    fecha_cosecha: Optional[date] = None,
    fecha_registro: Optional[date] = None,
) -> dict:
    """
    Run all applicable rules for a phytosanitary treatment.

    Returns:
        {'valid': bool, 'errors': [...], 'warnings': [...]}
    """
    errors = []
    warnings = []

    # Rule 1: Product authorization
    ok, msg = producto_autorizado(numero_registro, fecha_aplicacion)
    if not ok:
        errors.append({'rule': 'producto_autorizado', 'message': msg})

    # Rule 2: Crop/pest authorization
    ok, msg = producto_autorizado_cultivo(numero_registro, cultivo, plaga, fecha_aplicacion)
    if not ok:
        errors.append({'rule': 'producto_autorizado_cultivo', 'message': msg})

    # Rule 3: Dose (per-use product x crop x pest first, then product default)
    ok, msg = dosis_legal(numero_registro, dosis, fecha_aplicacion, cultivo=cultivo, plaga=plaga)
    if not ok:
        errors.append({'rule': 'dosis_legal', 'message': msg})

    # Rule 4: Safety period (per-use product x crop x pest first, then product default)
    ok, msg = plazo_seguridad(numero_registro, fecha_aplicacion, fecha_cosecha, cultivo=cultivo, plaga=plaga)
    if not ok:
        errors.append({'rule': 'plazo_seguridad', 'message': msg})

    # Rule 5: Registration window (warning only)
    ok, msg = plazo_registro(fecha_aplicacion, fecha_registro)
    if msg:
        warnings.append({'rule': 'plazo_registro', 'message': msg})

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
    }
