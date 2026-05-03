#!/usr/bin/env python3
# =============================================================================
# SIEX Anti-Corruption Layer -- NGSI-LD -> XML Serializer
# =============================================================================
# Translates NGSI-LD entity graphs into SIEX-compliant XML validated
# against FEGA XSD schemas (Anexo VI, v3.11.4).
#
# Supports 3 payload types:
#   - Alta: new submission
#   - Modificacion: amendment (references original csv_trace_id)
#   - Anulacion: cancellation (references original csv_trace_id + motivo)
#
# NGSI-LD is a graph model (JSON-LD with Relationships).
# FEGA requires hierarchical XML with strict element ordering.
# This is NOT a 1:1 mapping. The serializer resolves NGSI-LD
# Relationships and produces XML matching XSD sequences exactly.

import os
import logging
from datetime import date
from typing import Optional, Dict, Any, List, Tuple
import xmlschema

logger = logging.getLogger(__name__)

# XSD schema directory
XSD_DIR = os.path.join(os.path.dirname(__file__), 'xsd')

# Orion-LD client URL (for resolving relationships)
ORION_URL = os.getenv('ORION_URL', 'http://orion-ld-service:1026')

# ---------------------------------------------------------------------------
# Ordered field maps -- dict is insertion-ordered (Python 3.7+), so each map
# MUST list elements in the exact XSD sequence order.
# ---------------------------------------------------------------------------

# ExplotacionType (farm section in the root, not Cabecera)
# XSD sequence: Nombre, Municipio, Provincia, Parcelas
FIELD_MAP_FARM: List[Tuple[str, str]] = [
    ('address.addressLocality', 'Municipio'),
    ('address.addressRegion', 'Provincia'),
]

# ParcelaType
# XSD sequence: Nombre, Cultivo, SuperficieHA, SistemaRiego, Recintos
FIELD_MAP_PARCEL: List[Tuple[str, str]] = [
    ('name', 'Nombre'),
    ('hasCrop', 'Cultivo'),
    ('area', 'SuperficieHA'),
    ('irrigationSystem', 'SistemaRiego'),
]

# RecintoType
# XSD sequence: ReferenciaSIGPAC, SuperficieAdmisibleHA, Geometria
FIELD_MAP_ENCLOSURE: List[Tuple[str, str]] = [
    ('sigpacReference', 'ReferenciaSIGPAC'),
    ('eligibleArea', 'SuperficieAdmisibleHA'),
]

# TratamientoFitoType -- EXACT XSD order (every element must be in sequence)
# FechaAplicacion, ProductoROPORef, Dosis, UnidadDosis, Plaga,
# Equipo?, Aplicador?, Hora?, ParcelaRef
FIELD_MAP_TREATMENT: List[Tuple[str, str]] = [
    ('dateObserved', 'FechaAplicacion'),
    ('productoROPORef', 'ProductoROPORef'),
    ('plagaObjeto', 'Plaga'),
    ('equipoAplicacion', 'Equipo'),
    ('aplicador', 'Aplicador'),
    ('horaAplicacion', 'Hora'),
]

# FertilizacionType -- EXACT XSD order
# FechaAplicacion, TipoFertilizante, DosisKGHA, ContenidoNPCT?,
# ContenidoPPCT?, ParcelaRef
FIELD_MAP_FERTILIZATION: List[Tuple[str, str]] = [
    ('dateObserved', 'FechaAplicacion'),
    ('tipoFertilizante', 'TipoFertilizante'),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ngsi_value(attr: Any) -> Any:
    """Extract the actual value from an NGSI-LD attribute dict.

    NGSI-LD attributes are wrapped in Property objects:
        {'type': 'Property', 'value': actual_value}

    Relationships have:
        {'type': 'Relationship', 'object': 'urn:ngsi-ld:...'}

    This function recursively unwraps until it finds a plain value.
    """
    if isinstance(attr, dict):
        if 'value' in attr:
            return _get_ngsi_value(attr['value'])
        if 'object' in attr:
            return attr['object']
    return attr


def _text(element_name: str, value: Any) -> str:
    """Build an XML text element: <Name>value</Name>."""
    return f'<{element_name}>{value}</{element_name}>'


def _element(element_name: str, children: List[str]) -> str:
    """Build an XML element with children, filtering out empty strings."""
    inner = '\n'.join(c for c in children if c)
    return f'<{element_name}>\n{inner}\n</{element_name}>'


def _resolve_nested_attr(entity: dict, dotted_key: str) -> Any:
    """Resolve a dotted key like 'address.addressLocality' on an entity dict."""
    parts = dotted_key.split('.')
    current = entity
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, {})
        else:
            return None
    return current


def _map_fields(entity: dict, field_map: List[Tuple[str, str]]) -> List[str]:
    """Apply a field map to an entity, returning a list of XML text elements.

    Only produces elements for non-empty values. Handles nested attributes
    via dotted keys and NGSI-LD Property/Relationship unwrapping.
    """
    children: List[str] = []
    for ngsi_key, xml_key in field_map:
        if '.' in ngsi_key:
            val = _resolve_nested_attr(entity, ngsi_key)
        else:
            val = entity.get(ngsi_key, '')
        val = _get_ngsi_value(val)
        if val:
            children.append(_text(xml_key, str(val)))
    return children


def _get_dosis_value(dosis_field: Any) -> Tuple[Optional[str], Optional[str]]:
    """Extract (dosis, unitCode) from an NGSI-LD dosis attribute.

    NGSI-LD pattern for measured values:
        {'type': 'Property', 'value': {'value': 2.5, 'unitCode': 'L/ha'}}

    The outer 'type'/'value' is the NGSI-LD Property wrapper.
    The inner dict is the "value container" holding both the
    numeric value and metadata like unitCode.

    To avoid _get_ngsi_value collapsing the inner dict (it sees
    the nested 'value' key and recurses), we handle the Property
    wrapper directly.
    """
    if not isinstance(dosis_field, dict) or 'value' not in dosis_field:
        return None, None

    container = dosis_field['value']
    if not isinstance(container, dict):
        # Simple scalar value, no unitCode
        return str(container), None

    # Structured container: {'value': 2.5, 'unitCode': 'L/ha'}
    dosis = container.get('value')
    unit = container.get('unitCode')
    return (str(dosis) if dosis is not None else None,
            str(unit) if unit else None)


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_farm_xml(farm: dict) -> str:
    """Build XML for an AgriFarm entity (Explotacion section).

    NOTE: This is a standalone builder for use outside the main pipeline.
    The main pipeline (serialize_explotacion_to_xml) builds Explotacion
    directly with Cabecera fields in the header and only Nombre, Municipio,
    Provincia in the farm block.
    """
    children: List[str] = []
    # Nombre first
    name = _get_ngsi_value(farm.get('name', ''))
    if name:
        children.append(_text('Nombre', str(name)))

    # Municipio, Provincia from address
    for ngsi_key, xml_key in FIELD_MAP_FARM:
        if '.' in ngsi_key:
            parts = ngsi_key.split('.')
            val = farm.get(parts[0], {})
            if isinstance(val, dict):
                val = val.get(parts[1], '')
        else:
            val = farm.get(ngsi_key, '')
        val = _get_ngsi_value(val)
        if val:
            children.append(_text(xml_key, str(val)))

    return _element('Explotacion', children)


def build_parcel_xml(parcel: dict) -> str:
    """Build XML for an AgriParcel entity (Parcela section).

    XSD sequence: Nombre, Cultivo, SuperficieHA, SistemaRiego, Recintos
    """
    children: List[str] = []
    for ngsi_key, xml_key in FIELD_MAP_PARCEL:
        if '.' in ngsi_key:
            val = _resolve_nested_attr(parcel, ngsi_key)
        else:
            val = parcel.get(ngsi_key, '')
        val = _get_ngsi_value(val)
        if val:
            if ngsi_key == 'area' and isinstance(val, dict):
                val = val.get('value', val)
            children.append(_text(xml_key, str(val)))
    return _element('Parcela', children)


def build_enclosure_xml(enclosure: dict) -> str:
    """Build XML for a SigpacEnclosure entity (Recinto section).

    XSD sequence: ReferenciaSIGPAC, SuperficieAdmisibleHA, Geometria
    """
    children: List[str] = []
    for ngsi_key, xml_key in FIELD_MAP_ENCLOSURE:
        val = _get_ngsi_value(enclosure.get(ngsi_key, ''))
        if val:
            if isinstance(val, dict):
                val = val.get('value', val)
            children.append(_text(xml_key, str(val)))

    # Geometry (GeoJSON location) -- last in RecintoType XSD sequence
    location = enclosure.get('location', {})
    geom = _get_ngsi_value(location)
    if geom and isinstance(geom, dict):
        geo_type = geom.get('type', 'Polygon')
        coords = str(geom.get('coordinates', ''))
        children.append(_element('Geometria', [
            _text('Tipo', geo_type),
            _text('Coordenadas', coords),
        ]))

    return _element('Recinto', children)


def build_treatment_xml(treatment: dict) -> str:
    """Build XML for an AgriPestTreatment entity.

    XSD sequence (TratamientoFitoType):
      FechaAplicacion, ProductoROPORef, [Dosis, UnidadDosis], Plaga,
      [Equipo?, Aplicador?, Hora?], ParcelaRef

    Dosis/UnidadDosis are computed from the NGSI-LD dosisAplicada attribute.
    ParcelaRef is resolved from the hasAgriParcel Relationship.
    """
    children: List[str] = []

    # FechaAplicacion, ProductoROPORef
    for key in ('dateObserved', 'productoROPORef'):
        val = _get_ngsi_value(treatment.get(key, ''))
        xml_key = 'FechaAplicacion' if key == 'dateObserved' else 'ProductoROPORef'
        if val:
            children.append(_text(xml_key, str(val)))

    # Dosis + UnidadDosis (computed, position 3-4 in XSD sequence)
    dosis_val, unit_val = _get_dosis_value(treatment.get('dosisAplicada', {}))
    if dosis_val:
        children.append(_text('Dosis', dosis_val))
    if unit_val:
        children.append(_text('UnidadDosis', unit_val))

    # Plaga (plagaObjeto), then optional fields
    plaga = _get_ngsi_value(treatment.get('plagaObjeto', ''))
    if plaga:
        children.append(_text('Plaga', str(plaga)))

    for key in ('equipoAplicacion', 'aplicador', 'horaAplicacion'):
        val = _get_ngsi_value(treatment.get(key, ''))
        xml_key = {
            'equipoAplicacion': 'Equipo',
            'aplicador': 'Aplicador',
            'horaAplicacion': 'Hora',
        }[key]
        if val:
            children.append(_text(xml_key, str(val)))

    # ParcelaRef -- last in XSD sequence
    parcela_urn = _get_ngsi_value(treatment.get('hasAgriParcel', {}))
    if parcela_urn:
        children.append(_text('ParcelaRef', str(parcela_urn)))

    return _element('TratamientoFitosanitario', children)


def _extract_value_container(ngsi_field: Any) -> Optional[dict]:
    """Extract the inner value container from an NGSI-LD Property.

    NGSI-LD pattern:
        {'type': 'Property', 'value': {'value': 46}}

    Returns the inner dict {'value': 46}, or None if the field
    is missing/empty. This avoids _get_ngsi_value() collapsing
    nested value containers.
    """
    if not isinstance(ngsi_field, dict):
        return None
    container = ngsi_field.get('value')
    if isinstance(container, dict):
        return container
    return None


def _extract_scalar_or_container(ngsi_field: Any) -> Any:
    """Extract a scalar value from an NGSI-LD Property.

    Handles both simple values:
        {'type': 'Property', 'value': 150}
    and value containers:
        {'type': 'Property', 'value': {'value': 150}}

    Returns the scalar value if available, else None.
    """
    if not isinstance(ngsi_field, dict):
        return None
    container = ngsi_field.get('value')
    if isinstance(container, dict):
        return container.get('value')
    return container


def build_fertilization_xml(fertilization: dict) -> str:
    """Build XML for an AgriFertilizerApplication entity.

    XSD sequence (FertilizacionType):
      FechaAplicacion, TipoFertilizante, DosisKGHA,
      [ContenidoNPCT?, ContenidoPPCT?], ParcelaRef

    DosisKGHA is computed from dosisFertilizante.
    NP content from contenidoN / contenidoP.
    ParcelaRef from hasAgriParcel Relationship.
    """
    children: List[str] = []

    # FechaAplicacion, TipoFertilizante (simple string properties)
    for key in ('dateObserved', 'tipoFertilizante'):
        val = _get_ngsi_value(fertilization.get(key, ''))
        if val:
            xml_key = 'FechaAplicacion' if key == 'dateObserved' else 'TipoFertilizante'
            children.append(_text(xml_key, str(val)))

    # DosisKGHA (computed from dosisFertilizante Property)
    dosis_val = _extract_scalar_or_container(fertilization.get('dosisFertilizante', {}))
    if dosis_val is not None:
        children.append(_text('DosisKGHA', str(dosis_val)))

    # NP content (optional, in XSD order)
    for src_key in ('contenidoN', 'contenidoP'):
        container = _extract_value_container(fertilization.get(src_key, {}))
        if container is not None:
            xml_key = 'ContenidoNPCT' if src_key == 'contenidoN' else 'ContenidoPPCT'
            val = container.get('value')
            if val is not None:
                children.append(_text(xml_key, str(val)))

    # ParcelaRef -- last in XSD sequence
    parcela_urn = _get_ngsi_value(fertilization.get('hasAgriParcel', {}))
    if parcela_urn:
        children.append(_text('ParcelaRef', str(parcela_urn)))

    return _element('AplicacionFertilizante', children)


# ---------------------------------------------------------------------------
# Main serialization entry point
# ---------------------------------------------------------------------------

def serialize_explotacion_to_xml(
    farm: dict,
    parcelas: List[dict],
    enclosures: List[dict],
    treatments: List[dict],
    fertilizations: List[dict],
    payload_type: str = 'Alta',
    original_trace_id: Optional[str] = None,
    motivo_anulacion: Optional[str] = None,
) -> str:
    """Serialize a complete explotacion into a SIEX-compliant XML document.

    Builds the full XML tree from entity data:
      1. Cabecera (header -- NIF, REGEPA, operation type, date)
      2. Explotacion (farm info + parcels + enclosures)
      3. Actividades (treatments + fertilizations)

    Supports three payload types:
      - 'Alta': new submission (no reference required)
      - 'Modificacion': amendment (original_trace_id required)
      - 'Anulacion': cancellation (original_trace_id + motivo_anulacion required)

    Args:
        farm: AgriFarm entity dict from NGSI-LD
        parcelas: List of AgriParcel entity dicts
        enclosures: List of SigpacEnclosure entity dicts
        treatments: List of AgriPestTreatment entity dicts
        fertilizations: List of AgriFertilizerApplication entity dicts
        payload_type: 'Alta', 'Modificacion', or 'Anulacion'
        original_trace_id: csv_trace_id of the original submission (required for
            Modificacion and Anulacion)
        motivo_anulacion: Reason for cancellation (required for Anulacion)

    Returns:
        XML string

    Raises:
        ValueError: If required parameters are missing for the payload type
    """
    # Validate required parameters
    if payload_type in ('Modificacion', 'Anulacion') and not original_trace_id:
        raise ValueError(
            f'original_trace_id is required for payload type "{payload_type}"'
        )
    if payload_type == 'Anulacion' and not motivo_anulacion:
        raise ValueError(
            'motivo_anulacion is required for payload type "Anulacion"'
        )

    # -----------------------------------------------------------------------
    # 1. Cabecera (Header) -- XSD sequence: NIFTitular, CIFEntidadHabilitada?,
    #    REGEPA, TipoOperacion, FechaEnvio, [ReferenciaEnvioOriginal],
    #    [MotivoAnulacion]
    # -----------------------------------------------------------------------
    cabecera_children: List[str] = []

    # NIFTitular from ownedBy Relationship
    nif = _get_ngsi_value(farm.get('ownedBy', ''))
    if nif:
        nif_str = str(nif).split(':')[-1] if ':' in str(nif) else str(nif)
        cabecera_children.append(_text('NIFTitular', nif_str))
    else:
        cabecera_children.append(_text('NIFTitular', ''))

    # CIFEntidadHabilitada (optional)
    cif = _get_ngsi_value(farm.get('cifEntidadHabilitada', ''))
    if cif:
        cabecera_children.append(_text('CIFEntidadHabilitada', str(cif)))

    # REGEPA (always present for an active farm)
    regepa = _get_ngsi_value(farm.get('regepa', ''))
    if regepa:
        cabecera_children.append(_text('REGEPA', str(regepa)))
    else:
        cabecera_children.append(_text('REGEPA', ''))

    cabecera_children.append(_text('TipoOperacion', payload_type))
    cabecera_children.append(_text('FechaEnvio', date.today().isoformat()))

    # ReferenciaEnvioOriginal (Modificacion / Anulacion only)
    if original_trace_id:
        cabecera_children.append(_text('ReferenciaEnvioOriginal', original_trace_id))

    # MotivoAnulacion (Anulacion only)
    if motivo_anulacion:
        cabecera_children.append(_text('MotivoAnulacion', motivo_anulacion))

    cabecera = _element('Cabecera', cabecera_children)

    # -----------------------------------------------------------------------
    # 2. Explotacion (Farm) -- XSD sequence: Nombre, Municipio, Provincia,
    #    Parcelas?
    # -----------------------------------------------------------------------
    farm_children: List[str] = []

    # Nombre
    farm_name = _get_ngsi_value(farm.get('name', ''))
    farm_children.append(_text('Nombre', str(farm_name) if farm_name else ''))

    # Municipio from address.addressLocality
    addr = _get_ngsi_value(farm.get('address', {}))
    if isinstance(addr, dict):
        farm_children.append(
            _text('Municipio', str(addr.get('addressLocality', '')))
        )
        farm_children.append(
            _text('Provincia', str(addr.get('addressRegion', '')))
        )
    else:
        farm_children.append(_text('Municipio', str(addr) if addr else ''))
        farm_children.append(_text('Provincia', ''))

    # Parcelas (optional, after Provincia)
    if parcelas:
        parcelas_xml: List[str] = []
        for parcela in parcelas:
            parcela_children = _map_fields(parcela, FIELD_MAP_PARCEL)

            # Recintos for this parcel -- after SistemaRiego
            parcela_enclosures = _match_enclosures_to_parcel(parcela, enclosures)
            if parcela_enclosures:
                recintos_xml = [build_enclosure_xml(e) for e in parcela_enclosures]
                parcela_children.append(_element('Recintos', recintos_xml))

            parcelas_xml.append(_element('Parcela', parcela_children))

        farm_children.append(_element('Parcelas', parcelas_xml))

    explotacion = _element('Explotacion', farm_children)

    # -----------------------------------------------------------------------
    # 3. Actividades (Activities) -- optional
    #    Contains TratamientoFitosanitario* and AplicacionFertilizante*
    # -----------------------------------------------------------------------
    actividades_children: List[str] = []
    for t in treatments:
        actividades_children.append(build_treatment_xml(t))
    for f in fertilizations:
        actividades_children.append(build_fertilization_xml(f))

    if actividades_children:
        actividades = _element('Actividades', actividades_children)
    else:
        actividades = ''

    # -----------------------------------------------------------------------
    # 4. Root element
    # -----------------------------------------------------------------------
    root_name = {
        'Alta': 'SolicitudAlta',
        'Modificacion': 'SolicitudModificacion',
        'Anulacion': 'SolicitudAnulacion',
    }.get(payload_type, 'SolicitudAlta')

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<{root_name} version="3.11.4">',
        cabecera,
        explotacion,
        actividades,
        f'</{root_name}>',
    ]

    return '\n'.join(p for p in xml_parts if p)


# ---------------------------------------------------------------------------
# Enclosure-to-parcel matching
# ---------------------------------------------------------------------------

def _match_enclosures_to_parcel(parcel: dict, enclosures: List[dict]) -> List[dict]:
    """Match SIGPAC enclosures to their parent parcel.

    In the NGSI-LD graph:
      SigpacEnclosure -> hasAgriCropDeclaration -> AgriCropDeclaration
      AgriParcel (already matched via crop declaration reference)

    For now, return all enclosures since the full graph traversal requires
    resolving intermediate AgriCropDeclaration entities.
    """
    # TODO: Implement full graph traversal via Orion-LD when the
    # intermediate AgriCropDeclaration entities are resolved.
    return enclosures


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def build_full_xml_from_entity_graph(
    farm: dict,
    parcelas: List[dict],
    enclosures: List[dict],
    treatments: List[dict],
    fertilizations: List[dict],
    payload_type: str = 'Alta',
    original_trace_id: Optional[str] = None,
    motivo_anulacion: Optional[str] = None,
    validate: bool = False,
) -> str:
    """Build and optionally validate a SIEX XML document from NGSI-LD entities.

    Convenience wrapper over serialize_explotacion_to_xml() that adds
    optional XSD validation before returning.

    Args:
        Same as serialize_explotacion_to_xml() plus:
        validate: If True, validate against XSD before returning

    Returns:
        XML string

    Raises:
        ValueError: If validation is enabled and the XML does not validate
    """
    xml_str = serialize_explotacion_to_xml(
        farm=farm,
        parcelas=parcelas,
        enclosures=enclosures,
        treatments=treatments,
        fertilizations=fertilizations,
        payload_type=payload_type,
        original_trace_id=original_trace_id,
        motivo_anulacion=motivo_anulacion,
    )

    if validate:
        valid, error = validate_against_xsd(xml_str, payload_type)
        if not valid:
            raise ValueError(
                f'XML validation failed for {payload_type}: {error}'
            )

    return xml_str


# ---------------------------------------------------------------------------
# XSD validation
# ---------------------------------------------------------------------------

def validate_against_xsd(xml_str: str, payload_type: str = 'Alta') -> tuple:
    """Validate an XML string against the corresponding FEGA XSD schema.

    Loads the XSD schema for the given payload type and validates the
    XML document against it.

    Args:
        xml_str: XML document string
        payload_type: 'Alta', 'Modificacion', or 'Anulacion'

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    xsd_file = os.path.join(XSD_DIR, f'siex_{payload_type.lower()}.xsd')
    if not os.path.exists(xsd_file):
        return False, f'XSD schema not found: {xsd_file}'

    try:
        schema = xmlschema.XMLSchema(xsd_file)
        schema.validate(xml_str)
        return True, ''
    except xmlschema.XMLSchemaValidationError as e:
        return False, str(e)
    except Exception as e:
        return False, f'Validation error: {e}'
