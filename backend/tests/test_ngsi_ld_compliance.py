"""NGSI-LD compliance for the CUE write path.

Two independent defects covered here:

1. @context delivery mode. ETSI GS CIM 009 makes the two modes mutually exclusive:
   @context in the body means application/ld+json and NO Link header. The client
   sent both at once whenever CONTEXT_URL was set.

2. unitCode values must be UN/CEFACT Recommendation 20 common codes, not the
   symbols they abbreviate: hectare is HAR (not "HA"), percent is P1 (not "%").
"""

import importlib
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client_mod():
    os.environ["CONTEXT_URL"] = "http://api-gateway-service:5000/ngsi-ld-context.json"
    from app import orion_client

    importlib.reload(orion_client)
    return orion_client


class TestContextDeliveryMode:
    def test_ld_json_writes_carry_no_link_header(self, client_mod):
        """@context in the body plus a Link header is the forbidden combination."""
        h = client_mod._ngsi_ld_headers("montiko", with_content_type=True)
        assert h["Content-Type"] == "application/ld+json"
        assert "Link" not in h, "ld+json body context must not also send a Link header"

    def test_reads_still_get_the_link_header(self, client_mod):
        """GETs carry no body, so the context has to travel in the Link header."""
        h = client_mod._ngsi_ld_headers("montiko", with_content_type=False)
        assert "Link" in h
        assert "json-ld#context" in h["Link"]

    def test_tenant_headers_present(self, client_mod):
        h = client_mod._ngsi_ld_headers("montiko")
        assert h["NGSILD-Tenant"] == h["Fiware-Service"]
        assert h["Fiware-ServicePath"] == "/"

    def test_create_entity_sends_context_in_body_only(self, client_mod):
        resp = MagicMock(status_code=201, text="")
        resp.json.return_value = {}
        with patch.object(client_mod.requests, "post", return_value=resp) as m:
            client_mod.create_entity("AgriIrrigation", "montiko", "r1", {})
        assert "@context" in m.call_args.kwargs["json"]
        assert "Link" not in m.call_args.kwargs["headers"]


class TestUnitCodes:
    """UN/CEFACT Rec 20 common codes, verified against the published code list."""

    def test_no_bare_hectare_symbol_in_payloads(self):
        src = _payload_source()
        assert '"unitCode": "HA"' not in src, 'hectare is HAR in UN/CEFACT, not "HA"'

    def test_no_bare_percent_symbol_in_payloads(self):
        src = _payload_source()
        assert '"unitCode": "%"' not in src, 'percent is P1 in UN/CEFACT, not "%"'

    def test_hectare_uses_har(self):
        assert '"unitCode": "HAR"' in _payload_source()

    def test_percent_uses_p1(self):
        assert '"unitCode": "P1"' in _payload_source()


def _payload_source() -> str:
    """cue_api source.

    The module no longer serves its own @context document, so every unitCode left
    in this file belongs to an entity payload.
    """
    from app import cue_api

    with open(cue_api.__file__, encoding="utf-8") as fh:
        return fh.read()
