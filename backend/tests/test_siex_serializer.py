#!/usr/bin/env python3
"""Tests for SIEX XML serializer — injection prevention."""

import pytest
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.serializers.siex_serializer import (
    _text, _element, _get_ngsi_value,
    build_farm_xml, build_parcel_xml, build_enclosure_xml,
    build_treatment_xml, build_fertilization_xml,
    serialize_explotacion_to_xml,
)


class TestXMLInjectionPrevention:
    """All text values must be XML-escaped to prevent injection."""

    def test_text_escapes_special_chars(self):
        result = _text('Nombre', 'Finca<script>alert(1)</script>&"<>')
        assert '<script>' not in result, f"Unescaped HTML in: {result}"
        assert '&lt;script&gt;' in result, f"Missing escape in: {result}"
        assert '&amp;' in result, "Ampersand not escaped"
        assert '&lt;' in result, "Less-than not escaped"
        assert '&gt;' in result, "Greater-than not escaped"

    def test_element_name_not_escaped(self):
        """Element names should NOT be escaped (they're controlled by code, not user input)."""
        result = _text('Nombre', 'safe_value')
        assert result.startswith('<Nombre>')
        assert result.endswith('</Nombre>')

    def test_farm_xml_escapes_user_input(self):
        farm = {
            'name': {'type': 'Property', 'value': 'Finca</Nombre><Injected>'},
            'address': {
                'type': 'Property',
                'value': {'addressLocality': 'Town</Municipio>', 'addressRegion': 'Region'}
            }
        }
        xml = build_farm_xml(farm)
        # The injected </Nombre> should NOT appear as a raw closing tag
        assert '&lt;/Nombre&gt;' in xml or '&lt;/Municipio&gt;' in xml, (
            f"Injection chars not escaped in farm XML: {xml[:300]}"
        )

    def test_treatment_xml_escapes_product_ref(self):
        treatment = {
            'productoROPORef': {'type': 'Property', 'value': '12345</ProductoROPORef><Dosis>999</Dosis>'},
            'dateObserved': {'type': 'Property', 'value': '2026-01-15'},
            'plagaObjeto': {'type': 'Property', 'value': 'plaga'},
        }
        xml = build_treatment_xml(treatment)
        # The injected </ProductoROPORef> must be escaped
        assert '&lt;/ProductoROPORef&gt;' in xml, (
            f"Injection in product ref not escaped: {xml[:300]}"
        )

    def test_parcel_xml_escapes_name(self):
        parcel = {
            'name': {'type': 'Property', 'value': 'Parcela</Parcela><Injected>'},
            'area': {'type': 'Property', 'value': 5.0},
        }
        xml = build_parcel_xml(parcel)
        assert '&lt;/Parcela&gt;' in xml, (
            f"Injection in parcel name not escaped: {xml[:300]}"
        )

    def test_fertilization_xml_escapes_type(self):
        fert = {
            'tipoFertilizante': {'type': 'Property', 'value': 'Org</TipoFertilizante><Injected>'},
            'dateObserved': {'type': 'Property', 'value': '2026-02-01'},
        }
        xml = build_fertilization_xml(fert)
        assert '&lt;/TipoFertilizante&gt;' in xml, (
            f"Injection in fertilizer type not escaped: {xml[:300]}"
        )

    def test_full_serialization_resists_injection(self):
        """Complete serialization must escape injection in all fields."""
        farm = {
            'name': {'type': 'Property', 'value': 'Test Farm'},
            'ownedBy': {'type': 'Relationship', 'object': 'urn:ngsi-ld:Person:test:12345678A'},
            'regepa': {'type': 'Property', 'value': '31-00001'},
            'address': {'type': 'Property', 'value': {'addressLocality': 'Town', 'addressRegion': 'Navarra'}},
        }
        parcelas = [{
            'name': {'type': 'Property', 'value': 'Parcela</Parcela><Parcela>evil</Parcela>'},
            'area': {'type': 'Property', 'value': 5.0},
        }]
        xml = serialize_explotacion_to_xml(farm, parcelas, [], [], [], payload_type='Alta')
        # Count occurrences of <Parcela> — should be exactly 2 (open + close for one parcel)
        parcela_tags = re.findall(r'</?Parcela\b[^>]*>', xml)
        assert len(parcela_tags) == 2, (
            f"Expected 2 Parcela tags (open+close), got {len(parcela_tags)}: injection likely.\n"
            f"Tags found: {parcela_tags}\nXML[:500]:\n{xml[:500]}"
        )

    def test_ampersand_in_value_escaped(self):
        """Ampersands in values must be escaped to avoid entity reference confusion."""
        result = _text('Nombre', 'Garcia & Gomez')
        assert '&amp;' in result, f"Ampersand not escaped: {result}"
        assert result.count('&amp;') == 1

    def test_enclosure_reference_escaped(self):
        enclosure = {
            'sigpacReference': {'type': 'Property', 'value': '31:1:0:0:1<script>'},
            'eligibleArea': {'type': 'Property', 'value': 2.5},
        }
        xml = build_enclosure_xml(enclosure)
        assert '<script>' not in xml, f"Unescaped script in enclosure: {xml[:300]}"
        assert '&lt;script&gt;' in xml


class TestSerializerNoRegression:
    """Verify normal serialization still works after escaping."""

    def test_normal_farm_serialization(self):
        farm = {
            'name': {'type': 'Property', 'value': 'Finca La Vega'},
            'address': {'addressLocality': 'Tudela', 'addressRegion': 'Navarra'},
        }
        xml = build_farm_xml(farm)
        assert '<Nombre>Finca La Vega</Nombre>' in xml
        assert '<Municipio>Tudela</Municipio>' in xml

    def test_normal_treatment_serialization(self):
        treatment = {
            'productoROPORef': {'type': 'Property', 'value': 'ES-12345'},
            'dateObserved': {'type': 'Property', 'value': '2026-01-15'},
            'dosisAplicada': {
                'type': 'Property',
                'value': {'value': 2.5, 'unitCode': 'L/ha'}
            },
            'plagaObjeto': {'type': 'Property', 'value': 'Oidio'},
            'hasAgriParcel': {
                'type': 'Relationship',
                'object': 'urn:ngsi-ld:AgriParcel:test:parcel1'
            },
        }
        xml = build_treatment_xml(treatment)
        assert '<ProductoROPORef>ES-12345</ProductoROPORef>' in xml
        assert '<Dosis>2.5</Dosis>' in xml
        # Normal values unchanged
