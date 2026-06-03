#!/usr/bin/env python3
"""Tests for Orion-LD client — query injection prevention."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.orion_client import _entity_uri


class TestEntityURISafety:
    """Entity IDs must be validated to prevent NGSI-LD query injection."""

    def test_normal_id_accepted(self):
        uri = _entity_uri('AgriFarm', 'tenant', 'farm123')
        assert uri == 'urn:ngsi-ld:AgriFarm:tenant:farm123'

    def test_id_with_quote_is_rejected(self):
        """Entity IDs containing double quotes must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', 'test" || id==*')

    def test_id_with_semicolon_is_rejected(self):
        """Entity IDs containing semicolons must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', 'test;isActive!=false')

    def test_id_with_equals_is_rejected(self):
        """Entity IDs containing equals signs must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', 'test=inject')

    def test_id_with_spaces_is_rejected(self):
        """Entity IDs containing spaces must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', 'test inject')

    def test_id_with_slash_is_rejected(self):
        """Entity IDs containing slashes must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', 'test/inject')

    def test_valid_alphanumeric_hyphen_underscore(self):
        """Valid entity IDs: alphanumeric, hyphens, underscores."""
        uri = _entity_uri('AgriFarm', 'tenant', 'farm-123_test')
        assert 'farm-123_test' in uri

    def test_valid_uuid_hex(self):
        """Generated hex IDs (8 bytes = 16 chars) are valid."""
        import os as _os
        hex_id = _os.urandom(8).hex()
        uri = _entity_uri('AgriFarm', 'tenant', hex_id)
        assert hex_id in uri

    def test_empty_id_rejected(self):
        """Empty entity IDs must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', '')

    def test_id_with_pipe_rejected(self):
        """Entity IDs containing pipe (OR operator) must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', 'test||bad')

    def test_id_with_parens_rejected(self):
        """Entity IDs containing parentheses must raise ValueError."""
        with pytest.raises(ValueError):
            _entity_uri('AgriFarm', 'tenant', 'test(paren)')

    def test_tenant_with_special_chars_is_sanitized(self):
        """Tenant ID with dangerous special chars is sanitized in URI."""
        uri = _entity_uri('AgriFarm', 'test-tenant_with.mixed', 'farm1')
        assert '"' not in uri
        assert ';' not in uri
        # Dots are safe in tenant IDs (FIWARE convention)
        assert 'test-tenant_with.mixed' in uri

    def test_type_with_special_chars_is_sanitized(self):
        """Entity type is sanitized to alphabetic only."""
        uri = _entity_uri('AgriFarm123!@#', 'tenant', 'farm1')
        # Only alphabetic chars retained in type
        assert '123' not in uri.split(':')[1]
        assert '!' not in uri
        assert 'AgriFarm' in uri
