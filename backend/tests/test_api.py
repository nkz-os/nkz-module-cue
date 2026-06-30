#!/usr/bin/env python3
# =============================================================================
# CUE API Tests
# =============================================================================

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.cue_api import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get('/health')
        assert r.status_code == 200
        data = r.get_json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'cue-api'


class TestContext:
    def test_context_returns_200(self, client):
        r = client.get('/ngsi-ld/cue-context.jsonld')
        assert r.status_code == 200
        ctx = r.get_json()['@context']
        assert 'AgriCropDeclaration' in ctx
        assert 'SigpacEnclosure' in ctx
        assert 'campaignYear' in ctx
        assert 'sigpacReference' in ctx


class TestNotifyWebhook:
    def test_empty_notification(self, client):
        r = client.post('/notify', json={'data': []})
        assert r.status_code == 200
        assert r.get_json()['status'] == 'ok'

    def test_no_entities(self, client):
        r = client.post('/notify', json={
            'id': 'test-notif-1',
            'subscriptionId': 'sub-1',
            'data': []
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['processed'] == 0

    def test_non_enclosure_entity_skipped(self, client):
        r = client.post('/notify', json={
            'id': 'test-notif-2',
            'subscriptionId': 'sub-2',
            'data': [
                {
                    'id': 'urn:ngsi-ld:AgriFarm:test:1',
                    'type': 'AgriFarm',
                    'name': {'type': 'Property', 'value': 'Test Farm'},
                    'tenantId': {'type': 'Property', 'value': 'test'},
                }
            ]
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data['synced'] == 0


class TestAuthRequired:
    def test_list_explotaciones_requires_auth(self, client):
        r = client.get('/api/modules/cue/explotaciones')
        assert r.status_code == 401

    def test_create_explotacion_requires_auth(self, client):
        r = client.post('/api/modules/cue/explotaciones', json={'nombre': 'Finca'})
        assert r.status_code == 401


from unittest.mock import MagicMock, patch


class TestInternalAuth:
    def test_internal_secret_bypasses_jwt(self, client, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s3cr3t")
        fake_conn = MagicMock()
        fake_conn.cursor.return_value.fetchall.return_value = []
        with patch("app.cue_api.get_pg_conn", return_value=fake_conn):
            r = client.get(
                "/api/modules/cue/productos-ropo?cultivo=trigo",
                headers={"X-Internal-Service-Secret": "s3cr3t", "X-Tenant-ID": "montiko"},
            )
        assert r.status_code == 200

    def test_no_secret_no_token_is_401(self, client):
        r = client.get("/api/modules/cue/productos-ropo?cultivo=trigo", headers={"X-Tenant-ID": "montiko"})
        assert r.status_code == 401

    def test_internal_secret_does_not_bypass_post(self, client, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s3cr3t")
        r = client.post(
            "/api/modules/cue/explotaciones",
            json={},
            headers={"X-Internal-Service-Secret": "s3cr3t", "X-Tenant-ID": "montiko"},
        )
        assert r.status_code == 401


class TestCultivoMatch:
    def test_cultivo_filter_is_accent_case_insensitive(self, client, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s3cr3t")
        captured = {}
        fake_cur = MagicMock()
        fake_cur.fetchall.return_value = []
        def _exec(sql, params):
            captured["sql"] = sql
            captured["params"] = params
        fake_cur.execute.side_effect = _exec
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        with patch("app.cue_api.get_pg_conn", return_value=fake_conn):
            r = client.get(
                "/api/modules/cue/productos-ropo?cultivo=Ma%C3%ADz",
                headers={"X-Internal-Service-Secret": "s3cr3t", "X-Tenant-ID": "montiko"},
            )
        assert r.status_code == 200
        assert "unnest(cultivos_autorizados)" in captured["sql"]
        assert "unaccent" in captured["sql"]
        assert "Maíz" in captured["params"]
