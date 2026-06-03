#!/usr/bin/env python3
# =============================================================================
# IUWS Client — FEGA SIEX Interfaz Único Común (Anexo VI, v3.11.4)
# =============================================================================
# Communicates with autonomous community IUWS endpoints for:
#   1. REA download: GET /IUWS/exportarREA/{NIF}_{CIF}
#   2. CUE submission: POST /IUWS/... (XML payload)
#   3. Status polling: GET /IUWS/estado/{idTicket}
#
# Authentication: mTLS with client certificate (from K8s Secrets).
# Certificates are loaded into RAM, never written to disk.

import os
import logging
import tempfile
import atexit
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

# Certificate paths from K8s Secrets (mounted as files)
MTLS_CERT_PATH = os.getenv('MTLS_CERT_PATH', '/etc/cue/certs/client.crt')
MTLS_KEY_PATH = os.getenv('MTLS_KEY_PATH', '/etc/cue/certs/client.key')
MTLS_CA_PATH = os.getenv('MTLS_CA_PATH', '/etc/cue/certs/ca.crt')

# For ephemeral cert flow (AutoFirma): cert loaded from request, not env
# PEM strings are written to temp files because requests library requires
# file paths, not inline PEM content.
_ephemeral_cert = None
_ephemeral_key = None
_ephemeral_cert_file = None  # Path to temp cert file (AutoFirma flow)
_ephemeral_key_file = None   # Path to temp key file (AutoFirma flow)


def _write_ephemeral_to_tempfiles():
    """Write ephemeral cert/key PEM strings to temporary files.

    The requests library requires cert/key as FILE PATHS, not PEM strings.
    We write to temp files (tmpfs in K8s, never persists to disk).
    Files are created with 0o600 permissions for security.
    """
    global _ephemeral_cert_file, _ephemeral_key_file
    if _ephemeral_cert and _ephemeral_key and not _ephemeral_cert_file:
        # Write cert to temp file
        cert_fd, _ephemeral_cert_file = tempfile.mkstemp(
            suffix='.pem', prefix='cue_cert_'
        )
        with os.fdopen(cert_fd, 'w') as f:
            f.write(_ephemeral_cert)
        os.chmod(_ephemeral_cert_file, 0o600)

        # Write key to temp file
        key_fd, _ephemeral_key_file = tempfile.mkstemp(
            suffix='.pem', prefix='cue_key_'
        )
        with os.fdopen(key_fd, 'w') as f:
            f.write(_ephemeral_key)
        os.chmod(_ephemeral_key_file, 0o600)


def _get_mtls_kwargs() -> dict:
    """
    Build mTLS kwargs for requests library.

    Priority:
    1. Ephemeral cert (AutoFirma flow -- loaded from user request into RAM,
       written to temp files for requests library compatibility)
    2. Persistent cert from K8s Secrets (Sello de Empresa flow)
    """
    global _ephemeral_cert, _ephemeral_key, _ephemeral_cert_file, _ephemeral_key_file

    if _ephemeral_cert and _ephemeral_key:
        # Write PEM strings to temp files (requests requires file paths)
        _write_ephemeral_to_tempfiles()
        if _ephemeral_cert_file and _ephemeral_key_file:
            return {'cert': (_ephemeral_cert_file, _ephemeral_key_file)}

    if os.path.exists(MTLS_CERT_PATH) and os.path.exists(MTLS_KEY_PATH):
        ca = MTLS_CA_PATH if os.path.exists(MTLS_CA_PATH) else None
        kwargs = {'cert': (MTLS_CERT_PATH, MTLS_KEY_PATH)}
        if ca:
            kwargs['verify'] = ca
        return kwargs

    logger.warning("No mTLS certificate available -- requests will fail against IUWS")
    return {}


def set_ephemeral_cert(cert_pem: str, key_pem: str):
    """
    Set ephemeral certificate for AutoFirma flow.

    These are loaded into RAM and must be purged after use.
    NEVER written to disk. NEVER logged.
    """
    global _ephemeral_cert, _ephemeral_key
    _ephemeral_cert = cert_pem
    _ephemeral_key = key_pem
    logger.info("Ephemeral certificate loaded into RAM")


def purge_ephemeral_cert():
    """Purge ephemeral certificate from RAM and delete temp files after IUWS response."""
    global _ephemeral_cert, _ephemeral_key, _ephemeral_cert_file, _ephemeral_key_file
    _ephemeral_cert = None
    _ephemeral_key = None

    # Delete temp files if they exist
    for fpath in (_ephemeral_cert_file, _ephemeral_key_file):
        if fpath and os.path.exists(fpath):
            try:
                os.unlink(fpath)
            except OSError as e:
                logger.warning(
                    "Failed to delete temp cert file %s: %s", fpath, e
                )

    _ephemeral_cert_file = None
    _ephemeral_key_file = None
    logger.info("Ephemeral certificate purged from RAM and temp files deleted")


def resolve_iuws_url(codigo_provincia: str) -> Optional[str]:
    """
    Resolve the IUWS base URL for a given province code.

    Queries cue_endpoints_autonomicos table.
    """
    import psycopg2
    conn = None
    cur = None
    try:
        postgres_url = os.getenv(
            'POSTGRES_URL',
            'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
        )
        conn = psycopg2.connect(postgres_url)
        cur = conn.cursor()
        cur.execute(
            "SELECT iuws_base_url, comunidad "
            "FROM cue_endpoints_autonomicos "
            "WHERE codigo_provincia = %s AND activo = true",
            (codigo_provincia,)
        )
        row = cur.fetchone()
        if row:
            logger.info(f"IUWS resolved: {codigo_provincia} -> {row[1]} ({row[0]})")
            return row[0]
        logger.warning(f"No IUWS endpoint for provincia {codigo_provincia}")
        return None
    except Exception as e:
        logger.error(f"Error resolving IUWS URL: {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def extract_province_from_regepa(regepa: str) -> str:
    """
    Extract the 2-digit province code from a REGEPA number.

    REGEPA format: PP-XXXXX (PP = province code, XXXXX = farm number)
    Example: '31-00001' -> '31' (Navarra)
    """
    if not regepa:
        return ''
    parts = regepa.split('-')
    if len(parts) >= 1 and len(parts[0]) == 2 and parts[0].isdigit():
        return parts[0]
    return ''


def download_rea(
    iuws_base_url: str,
    nif_titular: str,
    cif_entidad: str,
    timeout: int = 120,
) -> Tuple[int, Any]:
    """
    Download REA (Registro de Explotaciones Agricolas) data from IUWS.

    GET {base_url}/IUWS/exportarREA/{NIF}_{CIF}

    Returns (status_code, response_data).
    The response contains parcel data, crop declarations, SIGPAC enclosures,
    and machinery data for the authorized farm.

    Args:
        iuws_base_url: IUWS endpoint URL (from cue_endpoints_autonomicos)
        nif_titular: NIF of the farm owner
        cif_entidad: CIF of the authorized entity (Nekazari)
        timeout: Request timeout in seconds

    Returns:
        (status_code, dict or str)
    """
    url = urljoin(iuws_base_url, f'/IUWS/exportarREA/{nif_titular}_{cif_entidad}')

    logger.info(f"Downloading REA from: {url}")

    try:
        kwargs = _get_mtls_kwargs()
        r = requests.get(url, timeout=timeout, **kwargs)
        logger.info(f"REA download: HTTP {r.status_code}")

        if r.status_code == 200:
            content_type = r.headers.get('Content-Type', '')
            if 'xml' in content_type or r.text.strip().startswith('<?xml'):
                return r.status_code, {'format': 'xml', 'data': r.text}
            elif 'json' in content_type:
                return r.status_code, r.json()
            else:
                return r.status_code, {'format': 'unknown', 'data': r.text}
        return r.status_code, {'error': r.text[:500]}
    except requests.exceptions.SSLError as e:
        logger.error(f"mTLS error downloading REA: {e}")
        return 502, {'error': f'Error de certificado mTLS: {e}'}
    except requests.exceptions.Timeout:
        logger.error(f"Timeout downloading REA from {url}")
        return 504, {'error': 'Timeout al conectar con la administracion'}
    except requests.RequestException as e:
        logger.error(f"Error downloading REA: {e}")
        return 502, {'error': f'Error de conexion IUWS: {e}'}


def submit_cue(
    iuws_base_url: str,
    xml_payload: str,
    nif_titular: str,
    cif_entidad: str,
    timeout: int = 120,
) -> Tuple[int, Dict[str, Any]]:
    """
    Submit CUE data to the IUWS endpoint.

    POST {base_url}/IUWS/... with XML payload.

    Args:
        iuws_base_url: IUWS endpoint URL
        xml_payload: SIEX-compliant XML document
        nif_titular: NIF of the farm owner
        cif_entidad: CIF of the authorized entity
        timeout: Request timeout

    Returns:
        (status_code, response_dict with idTicket if successful)
    """
    url = urljoin(iuws_base_url, '/IUWS/submit')
    logger.info(f"Submitting CUE to: {url} ({len(xml_payload)} bytes XML)")

    try:
        kwargs = _get_mtls_kwargs()
        headers = {'Content-Type': 'application/xml; charset=utf-8'}
        r = requests.post(
            url,
            data=xml_payload.encode('utf-8'),
            headers=headers,
            timeout=timeout,
            **kwargs,
        )
        logger.info(f"CUE submission: HTTP {r.status_code}")

        if r.status_code in (200, 201, 202):
            try:
                data = r.json() if r.text else {}
            except Exception:
                data = {'raw_response': r.text[:500]}

            # Extract idTicket from response (varies by CCAA)
            ticket = data.get('idTicket') or data.get('ticketId') or data.get('id')
            return r.status_code, {
                'status': 'submitted',
                'idTicket': ticket,
                'response': data,
            }
        return r.status_code, {'error': r.text[:500]}
    except requests.exceptions.SSLError as e:
        logger.error(f"mTLS error submitting CUE: {e}")
        return 502, {'error': f'Error de certificado mTLS: {e}'}
    except requests.exceptions.Timeout:
        logger.error(f"Timeout submitting to {url}")
        return 504, {'error': 'Timeout al enviar a la administracion'}
    except requests.RequestException as e:
        logger.error(f"Error submitting CUE: {e}")
        return 502, {'error': f'Error de conexion IUWS: {e}'}


def check_submission_status(
    iuws_base_url: str,
    id_ticket: str,
    timeout: int = 30,
) -> Tuple[int, Dict[str, Any]]:
    """
    Check the status of a submitted CUE transaction.

    GET {base_url}/IUWS/estado/{idTicket}

    Returns:
        (status_code, dict with estado and optional error details)
    """
    url = urljoin(iuws_base_url, f'/IUWS/estado/{id_ticket}')
    logger.info(f"Checking submission status: {url}")

    try:
        kwargs = _get_mtls_kwargs()
        r = requests.get(url, timeout=timeout, **kwargs)
        logger.info(f"Status check: HTTP {r.status_code}")

        if r.status_code == 200:
            try:
                data = r.json() if r.text else {}
            except Exception:
                data = {'raw_response': r.text[:500]}

            estado = data.get('estado') or data.get('status') or 'unknown'
            return r.status_code, {
                'idTicket': id_ticket,
                'estado': estado,
                'detail': data,
            }
        return r.status_code, {'error': r.text[:500]}
    except requests.RequestException as e:
        logger.error(f"Error checking status: {e}")
        return 502, {'error': f'Error de conexion IUWS: {e}'}


# =============================================================================
# SIEX Error Code Catalog
# =============================================================================
# Maps IUWS normative error codes to Spanish messages.

SIEX_ERROR_CODES = {
    'ERR_001': 'El NIF del titular no esta registrado en el sistema',
    'ERR_002': 'La entidad habilitada no tiene autorizacion para esta explotacion',
    'ERR_003': 'El certificado digital no es valido o ha expirado',
    'ERR_004': 'El XML no cumple el esquema XSD',
    'ERR_005': 'El producto fitosanitario no esta autorizado en la fecha indicada',
    'ERR_006': 'La dosis aplicada supera el maximo legal',
    'ERR_007': 'La parcela de referencia no existe en el REA',
    'ERR_008': 'El recinto SIGPAC no pertenece a la explotacion declarada',
    'ERR_009': 'La fecha de aplicacion es posterior a la fecha de envio',
    'ERR_010': 'El plazo de seguridad no se ha respetado',
    'ERR_011': 'La campana agricola no esta abierta para envios',
    'ERR_099': 'Error interno del servidor de la administracion',
}


def translate_siex_error(error_code: str) -> str:
    """Translate a SIEX IUWS error code to a user-friendly Spanish message."""
    return SIEX_ERROR_CODES.get(
        error_code,
        f'Error del sistema de administracion (codigo: {error_code})'
    )
