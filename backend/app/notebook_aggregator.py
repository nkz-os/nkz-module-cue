#!/usr/bin/env python3
"""Campaign CUE Notebook Aggregator (single-source-of-truth reader).

Builds an official RD 1054/2022 + RD 1051/2022 Cuaderno de Explotación for a
tenant and campaign year by reading:
  - Core Orion-LD: AgriFarm, AgriParcel
  - field-operations (Orion-LD): completed AgriParcelOperation entities
  - FaST Navigator (internal API): signed fertilization plans + advisor + SHA-256
  - CUE PostgreSQL: legal masters (ROMA equipment, ROPO applicators/advisors)

Zero operational data duplication: CUE never asks the user to re-enter field work.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

from .common.db import get_postgres_url
from .orion_client import query_entities
from .rules.engine import validate_fertilizacion_campanya

logger = logging.getLogger(__name__)

FAST_API_URL = os.getenv('FAST_API_URL', 'http://fast-navigator-service:8000')
ZVN_ORGANIC_N_LIMIT_KG_HA = 170.0


def _unwrap(val: Any) -> Any:
    if isinstance(val, dict):
        if '@value' in val:
            return val['@value']
        if 'value' in val:
            return _unwrap(val['value'])
        if 'object' in val:
            return val['object']
    return val


def _op_date(op: dict) -> str:
    for key in ('endedAt', 'startedAt', 'dateObserved', 'dateCreated'):
        raw = _unwrap(op.get(key))
        if raw:
            s = str(raw)
            if len(s) >= 10:
                return s[:10]
    return ''


def _in_campaign(op_day: str, campaign: int) -> bool:
    if not op_day:
        return False
    try:
        return int(op_day[:4]) == campaign
    except ValueError:
        return False


def _float_or_none(val: Any) -> Optional[float]:
    v = _unwrap(val)
    if v in (None, ''):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def fetch_fast_plan_summary(
    tenant_id: str,
    parcel_urn: str,
    campaign: int,
    timeout: int = 5,
) -> Optional[dict]:
    """Read signed fertilization plan summary from FaST (fail-open)."""
    secret = os.getenv('INTERNAL_SERVICE_SECRET', '')
    if not secret or not parcel_urn:
        return None
    url = f"{FAST_API_URL.rstrip('/')}/internal/plans/summary"
    try:
        r = requests.get(
            url,
            params={'tenant_id': tenant_id, 'parcel_id': parcel_urn, 'campaign': campaign},
            headers={'X-Internal-Service-Secret': secret},
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except requests.RequestException as exc:
        logger.warning("FaST plan summary unavailable for %s/%s: %s", tenant_id, parcel_urn, exc)
        return None


def _fetch_legal_masters(tenant_id: str) -> tuple[list[dict], list[dict]]:
    """Load active ROMA equipment and ROPO applicators/advisors for tenant."""
    conn = cur = None
    equipos, aplicadores = [], []
    try:
        conn = psycopg2.connect(get_postgres_url())
        conn.cursor_factory = RealDictCursor
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM cue_equipo_aplicacion WHERE tenant_id = %s AND activo = true ORDER BY nombre",
            (tenant_id,),
        )
        equipos = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT * FROM cue_aplicador_ropo WHERE tenant_id = %s AND activo = true ORDER BY nombre",
            (tenant_id,),
        )
        aplicadores = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("Could not load CUE legal masters for %s: %s", tenant_id, exc)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
    return equipos, aplicadores


def _serialize_dates(row: dict) -> dict:
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, 'isoformat'):
            out[k] = v.isoformat()
    return out


def build_campaign_notebook(
    tenant_id: str,
    campaign: int,
    vulnerable_zone: bool = False,
) -> Dict[str, Any]:
    """Assemble the complete campaign CUE notebook from platform sources."""
    today = date.today()
    incidencias: List[Dict[str, Any]] = []

    # 1. Core entities: AgriFarm & AgriParcel
    _, farms_raw = query_entities('AgriFarm', tenant_id, {'q': 'isActive!=false'})
    farms = farms_raw if isinstance(farms_raw, list) else []

    _, parcels_raw = query_entities('AgriParcel', tenant_id, {'q': 'isActive!=false'})
    parcels = parcels_raw if isinstance(parcels_raw, list) else []
    parcel_map: Dict[str, dict] = {}
    parcel_rows: List[dict] = []
    total_area_ha = 0.0

    for p in parcels:
        if not isinstance(p, dict):
            continue
        pid = p.get('id', '')
        area = _float_or_none(p.get('area')) or 0.0
        total_area_ha += area
        row = {
            'id': pid,
            'nombre': _unwrap(p.get('name')) or pid.split(':')[-1],
            'cultivo': _unwrap(p.get('cropType')) or _unwrap(p.get('hasCrop')) or '',
            'superficie_ha': round(area, 4),
            'riego': _unwrap(p.get('irrigation')) or _unwrap(p.get('irrigationSystem')) or '',
            'sigpac': _unwrap(p.get('sigpacReference')) or _unwrap(p.get('category')) or '',
        }
        parcel_map[pid] = row
        parcel_rows.append(row)

    # 2. Legal masters (ROMA + ROPO)
    equipos_raw, aplicadores_raw = _fetch_legal_masters(tenant_id)
    equipos = []
    for eq in equipos_raw:
        prox = eq.get('fecha_proxima_iteaf')
        vigente = (prox >= today) if isinstance(prox, date) else None
        if vigente is False:
            incidencias.append({
                'severidad': 'error',
                'bloque': 'equipos_roma',
                'codigo': 'ITEAF_CADUCADA',
                'mensaje': f"Equipo ROMA {eq.get('numero_roma')} ({eq.get('nombre')}) con ITEAF caducada ({prox.isoformat()}).",
            })
        item = _serialize_dates(eq)
        item['iteaf_vigente'] = vigente
        equipos.append(item)

    aplicadores = []
    for ap in aplicadores_raw:
        cad = ap.get('fecha_caducidad')
        vigente = (cad >= today) if isinstance(cad, date) else None
        if vigente is False:
            incidencias.append({
                'severidad': 'error',
                'bloque': 'personal_ropo',
                'codigo': 'CARNE_ROPO_CADUCADO',
                'mensaje': f"Carné ROPO {ap.get('numero_carne_ropo')} ({ap.get('nombre')}) caducado ({cad.isoformat()}).",
            })
        item = _serialize_dates(ap)
        item['carne_vigente'] = vigente
        aplicadores.append(item)

    # 3. Completed operations from field-operations (AgriParcelOperation)
    _, ops_raw = query_entities('AgriParcelOperation', tenant_id, {'q': 'status=="completed"', 'limit': '1000'})
    ops = ops_raw if isinstance(ops_raw, list) else []

    tratamientos: List[dict] = []
    fertilizaciones: List[dict] = []
    riegos: List[dict] = []
    siembras_labores: List[dict] = []
    cosechas: List[dict] = []
    observaciones: List[dict] = []

    for op in ops:
        if not isinstance(op, dict):
            continue
        day = _op_date(op)
        if not _in_campaign(day, campaign):
            continue
        op_type = _unwrap(op.get('operationType')) or ''
        parcel_urn = _unwrap(op.get('hasAgriParcel')) or _unwrap(op.get('refAgriParcel')) or ''
        p_info = parcel_map.get(parcel_urn, {})
        parcel_name = p_info.get('nombre') or parcel_urn.split(':')[-1]

        if op_type == 'spraying':
            rec = {
                'operation_id': op.get('id', ''),
                'fecha': day,
                'parcela_id': parcel_urn,
                'parcela_nombre': parcel_name,
                'cultivo': p_info.get('cultivo', ''),
                'producto': _unwrap(op.get('productName')) or '',
                'numero_registro': _unwrap(op.get('productRegistryRef')) or '',
                'dosis': _float_or_none(op.get('productRate')),
                'unidad_dosis': _unwrap(op.get('productRateUnit')) or 'L/ha',
                'plaga_objeto': _unwrap(op.get('target')) or _unwrap(op.get('targetPest')) or '',
                'superficie_tratada_ha': _float_or_none(op.get('treatedAreaHa')) or p_info.get('superficie_ha'),
                'volumen_caldo_l_ha': _float_or_none(op.get('sprayVolumeLHa')),
                'equipo_roma': _unwrap(op.get('equipmentRoma')) or _unwrap(op.get('equipmentRef')) or '',
                'aplicador_ropo': _unwrap(op.get('applicatorRopo')) or _unwrap(op.get('operator')) or '',
                'asesor_gip': _unwrap(op.get('advisorRopo')) or '',
                'justificacion_gip': _unwrap(op.get('gipJustification')) or '',
                'lote': _unwrap(op.get('batchNumber')) or '',
                'eficacia': _unwrap(op.get('efficacy')) or '',
                'notas': _unwrap(op.get('notes')) or '',
            }
            missing_legal = [
                k for k in ('numero_registro', 'plaga_objeto', 'equipo_roma', 'aplicador_ropo')
                if not rec.get(k)
            ]
            if missing_legal:
                incidencias.append({
                    'severidad': 'warning',
                    'bloque': 'tratamientos_fitosanitarios',
                    'codigo': 'CAMPOS_LEGALES_INCOMPLETOS',
                    'operation_id': rec['operation_id'],
                    'mensaje': f"Tratamiento {day} en {parcel_name} sin: {', '.join(missing_legal)}.",
                })
            tratamientos.append(rec)

        elif op_type == 'fertilization':
            rate = _float_or_none(op.get('fertilizerRate')) or 0.0
            n_pct = _float_or_none(op.get('nitrogenContent')) or 0.0
            p_pct = _float_or_none(op.get('phosphorusPentoxideContent')) or 0.0
            k_pct = _float_or_none(op.get('potassiumOxideContent')) or 0.0
            rec = {
                'operation_id': op.get('id', ''),
                'fecha': day,
                'parcela_id': parcel_urn,
                'parcela_nombre': parcel_name,
                'cultivo': p_info.get('cultivo', ''),
                'producto': _unwrap(op.get('fertilizerType')) or '',
                'numero_registro': _unwrap(op.get('fertilizerRegistryRef')) or '',
                'organico': bool(_unwrap(op.get('organicFertilizer'))),
                'forma_n': _unwrap(op.get('nitrogenForm')) or '',
                'dosis_kg_ha': round(rate, 3),
                'contenido_n_pct': n_pct,
                'contenido_p2o5_pct': p_pct,
                'contenido_k2o_pct': k_pct,
                'n_aplicado_kg_ha': round(rate * n_pct / 100.0, 2),
                'p2o5_aplicado_kg_ha': round(rate * p_pct / 100.0, 2),
                'k2o_aplicado_kg_ha': round(rate * k_pct / 100.0, 2),
                'metodo_incorporacion': _unwrap(op.get('incorporationMethod')) or '',
                'horas_incorporacion': _float_or_none(op.get('incorporationHours')),
                'origen_organico_rega': _unwrap(op.get('organicOriginRega')) or '',
                'notas': _unwrap(op.get('notes')) or '',
            }
            fertilizaciones.append(rec)

        elif op_type == 'irrigation':
            riegos.append({
                'operation_id': op.get('id', ''),
                'fecha': day,
                'parcela_id': parcel_urn,
                'parcela_nombre': parcel_name,
                'volumen_m3_ha': _float_or_none(op.get('waterPerHectare')),
                'procedencia_agua': _unwrap(op.get('waterSource')) or '',
                'sistema_riego': _unwrap(op.get('irrigationSystem')) or p_info.get('riego', ''),
                'origen_dato': _unwrap(op.get('dataSource')) or 'manual',
                'notas': _unwrap(op.get('notes')) or '',
            })

        elif op_type in ('sowing', 'tillage'):
            siembras_labores.append({
                'operation_id': op.get('id', ''),
                'fecha': day,
                'tipo': op_type,
                'parcela_id': parcel_urn,
                'parcela_nombre': parcel_name,
                'detalle': (
                    f"{_unwrap(op.get('cropType')) or ''} {_unwrap(op.get('variety')) or ''}".strip()
                    if op_type == 'sowing'
                    else (_unwrap(op.get('tillageType')) or '')
                ),
                'dosis_siembra': _float_or_none(op.get('seedingRate')) if op_type == 'sowing' else None,
                'metodo_siembra': _unwrap(op.get('sowingMethod')) or '',
                'profundidad_cm': _float_or_none(op.get('tillageDepth')) if op_type == 'tillage' else None,
                'notas': _unwrap(op.get('notes')) or '',
            })

        elif op_type in ('harvesting', 'haymaking', 'baling'):
            cosechas.append({
                'operation_id': op.get('id', ''),
                'fecha': day,
                'tipo': op_type,
                'parcela_id': parcel_urn,
                'parcela_nombre': parcel_name,
                'cultivo': _unwrap(op.get('cropType')) or p_info.get('cultivo', ''),
                'cantidad_kg': _float_or_none(op.get('harvestedWeight')),
                'pacas': _float_or_none(op.get('baleCount')),
                'destino_lote': _unwrap(op.get('harvestBatch')) or _unwrap(op.get('destination')) or '',
                'notas': _unwrap(op.get('notes')) or '',
            })

        elif op_type == 'scouting':
            observaciones.append({
                'operation_id': op.get('id', ''),
                'fecha': day,
                'parcela_id': parcel_urn,
                'parcela_nombre': parcel_name,
                'plataforma': _unwrap(op.get('platformType')) or 'manual',
                'notas': _unwrap(op.get('notes')) or '',
            })

    # 4. FaST signed fertilization plans (read-only per parcel)
    planes_fast: Dict[str, dict] = {}
    fert_parcel_ids = {f['parcela_id'] for f in fertilizaciones if f.get('parcela_id')}
    for pid in sorted(fert_parcel_ids | set(parcel_map.keys())):
        summary = fetch_fast_plan_summary(tenant_id, pid, campaign)
        if summary:
            planes_fast[pid] = summary

    # 5. RD 1051/2022 fertilization campaign compliance
    fert_check = validate_fertilizacion_campanya(
        fertilizaciones,
        vulnerable_zone=vulnerable_zone,
        signed_plan_parcels=set(planes_fast.keys()),
    )
    for err in fert_check.get('errors', []):
        incidencias.append({'severidad': 'error', 'bloque': 'fertilizacion', **err})
    for warn in fert_check.get('warnings', []):
        incidencias.append({'severidad': 'warning', 'bloque': 'fertilizacion', **warn})

    # Sort all operational tables chronologically
    for lst in (tratamientos, fertilizaciones, riegos, siembras_labores, cosechas, observaciones):
        lst.sort(key=lambda r: (r.get('fecha', ''), r.get('parcela_nombre', '')))

    return {
        'campanya': campaign,
        'generado_en': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'tenant_id': tenant_id,
        'zona_vulnerable_nitratos': vulnerable_zone,
        'explotaciones': [
            {
                'id': f.get('id', ''),
                'nombre': _unwrap(f.get('name')) or '',
                'regepa': _unwrap(f.get('regepa')) or '',
                'nif_titular': str(_unwrap(f.get('ownedBy')) or '').split(':')[-1],
                'cif_entidad_habilitada': _unwrap(f.get('cifEntidadHabilitada')) or '',
                'direccion': _unwrap(f.get('address')) or '',
            }
            for f in farms if isinstance(f, dict)
        ],
        'resumen': {
            'total_parcelas': len(parcel_rows),
            'superficie_total_ha': round(total_area_ha, 4),
            'tratamientos': len(tratamientos),
            'fertilizaciones': len(fertilizaciones),
            'riegos': len(riegos),
            'siembras_y_labores': len(siembras_labores),
            'cosechas': len(cosechas),
            'planes_fast_firmados': len(planes_fast),
            'errores_inspeccion': sum(1 for i in incidencias if i.get('severidad') == 'error'),
            'advertencias_inspeccion': sum(1 for i in incidencias if i.get('severidad') == 'warning'),
        },
        'parcelas': parcel_rows,
        'equipos_roma': equipos,
        'personal_ropo': aplicadores,
        'tratamientos_fitosanitarios': tratamientos,
        'fertilizaciones': fertilizaciones,
        'planes_abonado_fast': planes_fast,
        'riegos': riegos,
        'siembras_y_labores': siembras_labores,
        'cosechas': cosechas,
        'observaciones': observaciones,
        'incidencias': incidencias,
    }
