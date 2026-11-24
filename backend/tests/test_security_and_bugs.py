#!/usr/bin/env python3
"""Regression tests for Block A security hardening and bug fixes."""

import hashlib
import hmac
import os
import sys
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.cue_api import app, _parse_cors_origins, _normalize_entity_id
from app.common.db import get_postgres_url
from app.serializers.siex_serializer import (
    serialize_explotacion_to_xml,
    validate_against_xsd,
)


def _make_jwt(tenant: str = 'acme', sub: str = 'user-1', roles=None) -> str:
    payload = {
        'sub': sub,
        'preferred_username': 'farmer1',
        'tenant_id': tenant,
        'realm_access': {'roles': roles or ['Farmer']},
        'exp': int(time.time()) + 3600,
    }
    return jwt.encode(payload, 'unused', algorithm='HS256')


def _sign_hmac(secret: str, token: str, tenant: str, ts: int | None = None) -> str:
    t = ts if ts is not None else int(time.time())
    sig = hmac.new(
        secret.encode('utf-8'),
        f'{token}|{tenant}|{t}'.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return f'{sig}:{t}'


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestHmacEnforcement:
    def test_missing_signature_rejected_when_required(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'true')
        monkeypatch.setenv('HMAC_SECRET', 'super-secret')
        token = _make_jwt('acme')
        r = client.get(
            '/api/modules/cue/explotaciones',
            headers={'Authorization': f'Bearer {token}', 'X-Tenant-ID': 'acme'},
        )
        assert r.status_code == 401

    def test_empty_secret_fails_closed(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'true')
        monkeypatch.delenv('HMAC_SECRET', raising=False)
        token = _make_jwt('acme')
        r = client.get(
            '/api/modules/cue/explotaciones',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant-ID': 'acme',
                'X-Auth-Signature': 'deadbeef:9999999999',
            },
        )
        assert r.status_code == 401

    def test_expired_signature_rejected(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'true')
        monkeypatch.setenv('HMAC_SECRET', 'super-secret')
        token = _make_jwt('acme')
        sig = _sign_hmac('super-secret', token, 'acme', ts=int(time.time()) - 600)
        r = client.get(
            '/api/modules/cue/explotaciones',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Tenant-ID': 'acme',
                'X-Auth-Signature': sig,
            },
        )
        assert r.status_code == 401

    def test_valid_signature_accepted(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'true')
        monkeypatch.setenv('HMAC_SECRET', 'super-secret')
        token = _make_jwt('acme')
        sig = _sign_hmac('super-secret', token, 'acme')
        with patch('app.cue_api.query_entities', return_value=(200, [])):
            r = client.get(
                '/api/modules/cue/explotaciones',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant-ID': 'acme',
                    'X-Auth-Signature': sig,
                },
            )
        assert r.status_code == 200


class TestFailFastAndCors:
    def test_postgres_url_required(self, monkeypatch):
        monkeypatch.delenv('POSTGRES_URL', raising=False)
        monkeypatch.delenv('DATABASE_URL', raising=False)
        with pytest.raises(RuntimeError, match='POSTGRES_URL'):
            get_postgres_url()

    def test_database_url_alias_supported(self, monkeypatch):
        monkeypatch.delenv('POSTGRES_URL', raising=False)
        monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@host:5432/db')
        assert get_postgres_url() == 'postgresql://u:p@host:5432/db'

    def test_cors_never_allows_wildcard(self):
        assert _parse_cors_origins('*') == []
        assert _parse_cors_origins('') == []
        assert _parse_cors_origins('["https://example.org", "*"]') == ['https://example.org']
        assert _parse_cors_origins('https://a.example.org, https://b.example.org') == [
            'https://a.example.org',
            'https://b.example.org',
        ]


class TestTenantIsolationAndPollGuard:
    def test_get_submission_passes_tenant_id(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'false')
        token = _make_jwt('tenant-a')
        with patch('app.cue_api.get_submission', return_value=None) as mock_get:
            r = client.get(
                '/api/modules/cue/submissions/42',
                headers={'Authorization': f'Bearer {token}', 'X-Tenant-ID': 'tenant-a'},
            )
        assert r.status_code == 404
        mock_get.assert_called_once_with(42, tenant_id='tenant-a')

    def test_transition_submission_passes_tenant_id(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'false')
        token = _make_jwt('tenant-a')
        with patch('app.cue_api.transition_state', return_value=(False, 'Envio 42 no encontrado')) as mock_tr:
            r = client.post(
                '/api/modules/cue/submissions/42/transition',
                json={'estado': 'validado'},
                headers={'Authorization': f'Bearer {token}', 'X-Tenant-ID': 'tenant-a'},
            )
        assert r.status_code == 422
        mock_tr.assert_called_once_with(42, 'validado', None, tenant_id='tenant-a')

    def test_poll_iuws_forbidden_for_farmer(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'false')
        token = _make_jwt('tenant-a', roles=['Farmer'])
        r = client.post(
            '/api/modules/cue/poll-iuws',
            headers={'Authorization': f'Bearer {token}', 'X-Tenant-ID': 'tenant-a'},
        )
        assert r.status_code == 403

    def test_poll_iuws_allowed_for_internal_secret(self, client, monkeypatch):
        monkeypatch.setenv('INTERNAL_SERVICE_SECRET', 's3cr3t')
        with patch('app.cue_api.run_polling_cycle', return_value={'polled': 0}):
            r = client.post(
                '/api/modules/cue/poll-iuws',
                headers={'X-Internal-Service-Secret': 's3cr3t', 'X-Tenant-ID': 'tenant-a'},
            )
        assert r.status_code == 200


class TestBackendBugFixes:
    def test_validate_endpoint_imports_rules_engine(self, client, monkeypatch):
        monkeypatch.setenv('REQUIRE_HMAC_SIGNATURE', 'false')
        token = _make_jwt('acme')
        with patch(
            'app.rules.engine.validate_tratamiento',
            return_value={'valid': True, 'errors': [], 'warnings': []},
        ) as mock_val:
            r = client.post(
                '/api/modules/cue/validate',
                json={
                    'numero_registro': 'ES-001',
                    'dosis': 1.5,
                    'cultivo': 'trigo',
                    'plaga': 'roya',
                    'fecha_aplicacion': '2026-05-01',
                },
                headers={'Authorization': f'Bearer {token}', 'X-Tenant-ID': 'acme'},
            )
        assert r.status_code == 200
        mock_val.assert_called_once()

    def test_create_tratamiento_accepts_full_parcel_urn_and_returns_id(self, client, monkeypatch):
        monkeypatch.setenv('INTERNAL_SERVICE_SECRET', 's3cr3t')
        with patch('app.cue_api.create_entity', return_value=(201, {})) as mock_create:
            r = client.post(
                '/api/modules/cue/tratamientos',
                json={
                    'parcela_id': 'urn:ngsi-ld:AgriParcel:acme:p-123',
                    'producto_ropo': 'ES-001',
                    'dosis': 1.5,
                    'fecha': '2026-05-01',
                    'validar': False,
                },
                headers={'X-Internal-Service-Secret': 's3cr3t', 'X-Tenant-ID': 'acme'},
            )
        assert r.status_code == 201
        body = r.get_json()
        assert body['id'].startswith('urn:ngsi-ld:AgriPest:acme:')
        attrs = mock_create.call_args[0][3]
        assert attrs['hasAgriParcel']['object'] == 'urn:ngsi-ld:AgriParcel:acme:p-123'

    def test_normalize_entity_id(self):
        assert _normalize_entity_id('urn:ngsi-ld:AgriParcel:acme:p-123') == 'p-123'
        assert _normalize_entity_id('p-123') == 'p-123'

    def test_siex_serializer_matches_cue_fields_and_validates_xsd(self):
        farm = {
            'id': 'urn:ngsi-ld:AgriFarm:acme:f1',
            'name': {'type': 'Property', 'value': 'Finca Test'},
            'regepa': {'type': 'Property', 'value': '31-00001'},
            'ownedBy': {'type': 'Relationship', 'object': 'urn:ngsi-ld:Person:acme:12345678Z'},
            'address': {'type': 'Property', 'value': {'addressLocality': 'Tudela', 'addressRegion': 'Navarra'}},
        }
        p1 = {
            'id': 'urn:ngsi-ld:AgriParcel:acme:p1',
            'name': {'type': 'Property', 'value': 'Parcela 1'},
            'cropType': {'type': 'Property', 'value': 'Trigo'},
            'area': {'type': 'Property', 'value': 5.25},
            'irrigation': {'type': 'Property', 'value': 'secano'},
        }
        p2 = {
            'id': 'urn:ngsi-ld:AgriParcel:acme:p2',
            'name': {'type': 'Property', 'value': 'Parcela 2'},
            'cropType': {'type': 'Property', 'value': 'Cebada'},
            'area': {'type': 'Property', 'value': 3.5},
        }
        e1 = {
            'id': 'urn:ngsi-ld:SigpacEnclosure:acme:e1',
            '_parcel_uri': 'urn:ngsi-ld:AgriParcel:acme:p1',
            'sigpacReference': {'type': 'Property', 'value': '31:230:0:0:1:2:3'},
            'eligibleArea': {'type': 'Property', 'value': 5.25},
            'location': {'type': 'GeoProperty', 'value': {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
        }
        xml_str = serialize_explotacion_to_xml(farm, [p1, p2], [e1], [], [], payload_type='Alta')
        valid, err = validate_against_xsd(xml_str, 'Alta')
        assert valid, f'XSD validation failed: {err}\n{xml_str}'
        assert xml_str.count('31:230:0:0:1:2:3') == 1
        assert '<Cultivo>Trigo</Cultivo>' in xml_str
        assert '<Provincia>Navarra</Provincia>' in xml_str

    def test_extract_pkcs12_in_memory_without_openssl(self):
        import base64
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID
        from app.cue_api import _extract_pkcs12_pem

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'test-cue')])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
            .sign(key, hashes.SHA256())
        )
        p12_bytes = pkcs12.serialize_key_and_certificates(
            b'test', key, cert, None, serialization.BestAvailableEncryption(b's3cr3t-pwd')
        )
        cert_pem, key_pem = _extract_pkcs12_pem(base64.b64encode(p12_bytes).decode(), 's3cr3t-pwd')
        assert 'BEGIN CERTIFICATE' in cert_pem
        assert 'BEGIN PRIVATE KEY' in key_pem
        with pytest.raises(ValueError, match='contrasena'):
            _extract_pkcs12_pem(base64.b64encode(p12_bytes).decode(), 'wrong-pwd')


class TestKeycloakServiceAccountToken:
    def test_prefers_client_credentials_over_admin_password(self, monkeypatch):
        from app import gestor_auth

        monkeypatch.setenv('KEYCLOAK_CLIENT_ID', 'cue-user-lookup')
        monkeypatch.setenv('KEYCLOAK_CLIENT_SECRET', 'sa-secret')
        monkeypatch.setenv('KEYCLOAK_REALM', 'test-realm')
        monkeypatch.setenv('KEYCLOAK_INTERNAL_URL', 'http://keycloak-service:8080/auth')
        monkeypatch.delenv('KEYCLOAK_ADMIN_USER', raising=False)
        monkeypatch.delenv('KEYCLOAK_ADMIN_PASSWORD', raising=False)

        captured = {}

        class _FakeResp:
            def read(self):
                return b'{"access_token": "sa-token-123"}'

        def _fake_urlopen(req, timeout=10):
            captured['url'] = req.full_url
            captured['body'] = req.data.decode('utf-8')
            return _FakeResp()

        with patch('app.gestor_auth.urllib.request.urlopen', side_effect=_fake_urlopen):
            tok = gestor_auth._get_keycloak_admin_token()

        assert tok == 'sa-token-123'
        assert captured['url'] == 'http://keycloak-service:8080/auth/realms/test-realm/protocol/openid-connect/token'
        assert 'grant_type=client_credentials' in captured['body']
        assert 'client_id=cue-user-lookup' in captured['body']
