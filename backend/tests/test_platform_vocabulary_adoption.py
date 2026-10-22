"""CUE writes against the platform vocabulary, not a private one.

The module used to ship a second @context served from its own backend, and told
Orion to fetch it from the api-gateway — a path the gateway does not route. The
platform context URL it sent was wrong too (.jsonld; the gateway serves .json).
Both @context references Orion was asked to resolve were 404s.

It also declared two entity types that do not exist in Smart Data Models,
AgriPestTreatment and AgriFertilizerApplication, pointed at SDM URLs that 404.
Agrifood has AgriPest and AgriFertilize, and both were already in the platform
context with the right IRIs.
"""

import importlib

import pytest


@pytest.fixture
def client_mod(monkeypatch):
    monkeypatch.delenv("CONTEXT_URL", raising=False)
    monkeypatch.delenv("CUE_CONTEXT_URL", raising=False)
    from app import orion_client

    importlib.reload(orion_client)
    return orion_client


class TestSingleContext:
    def test_default_context_url_matches_what_the_gateway_serves(self, client_mod):
        assert client_mod.NGSI_LD_CONTEXT_URL.endswith("/ngsi-ld-context.json")
        assert not client_mod.NGSI_LD_CONTEXT_URL.endswith(".jsonld")

    def test_no_private_cue_context(self, client_mod):
        assert not hasattr(client_mod, "CUE_CONTEXT_URL")

    def test_no_per_type_sdm_context_map(self, client_mod):
        """Every per-type SDM context URL in that map returned 404."""
        assert not hasattr(client_mod, "SDM_CONTEXTS")

    @pytest.mark.parametrize(
        "entity_type",
        ["AgriParcel", "AgriFarm", "AgriPest", "AgriFertilize", "AgriCropDeclaration"],
    )
    def test_every_type_uses_the_platform_context(self, client_mod, entity_type):
        ctx = client_mod._build_context(entity_type)
        assert ctx[-1] == client_mod.NGSI_LD_CONTEXT_URL
        assert not any("github.io" in c for c in ctx)

    def test_core_context_comes_first(self, client_mod):
        ctx = client_mod._build_context("AgriParcel")
        assert ctx[0].startswith("https://uri.etsi.org/ngsi-ld/")


class TestSdmTypeNames:
    def test_invented_types_are_gone(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "app"
        offenders = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in ("AgriPestTreatment", "AgriFertilizerApplication"):
                if name in text:
                    offenders.append(f"{path.name}: {name}")
        assert not offenders, offenders

    def test_official_types_are_used(self):
        import pathlib

        text = (pathlib.Path(__file__).resolve().parents[1] / "app" / "cue_api.py").read_text()
        assert "AgriPest" in text
        assert "AgriFertilize" in text


class TestServedContextRemoved:
    def test_module_no_longer_serves_its_own_context(self):
        from app import cue_api

        routes = {r.rule for r in cue_api.app.url_map.iter_rules()}
        assert "/ngsi-ld/cue-context.jsonld" not in routes
