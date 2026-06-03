#!/usr/bin/env python3
"""Tests for iuws_client ephemeral certificate handling."""

import pytest
import os
import sys
import threading
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.integration.iuws_client import (
    set_ephemeral_cert,
    purge_ephemeral_cert,
    _get_mtls_kwargs,
)

FAKE_CERT = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKl7V8xqN9UwMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkVTMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMjQwMTAxMDAwMDAwWhcNMjUxMjMxMjM1OTU5WjBF
MQswCQYDVQQGEwJFUzETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50
ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB
CgKCAQEA0Z3VS5JJcB5G5F6Xa8Lq2m7U4k1V8wR3tYxZ6bN2cF4hJ7L0aS5D3mK
8wP2tV4xY6bN0cF3aS5D2mK7wP1tV4xZ6bN0cF3aS5D2mK7wP1tV4xZ6bN0cF3
-----END CERTIFICATE-----"""

FAKE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC0tLS0dGVzdCBr
ZXkgc2ltdWxhdGlvbiBmb3IgdmVyaWZpY2F0aW9uIHB1cnBvc2VzIG9ubHkK
-----END PRIVATE KEY-----"""


class TestEphemeralCert:
    """Tests for ephemeral certificate flow."""

    def test_ephemeral_cert_returns_temp_file_paths(self):
        """After set_ephemeral_cert, _get_mtls_kwargs returns file paths (not PEM strings)."""
        set_ephemeral_cert(FAKE_CERT, FAKE_KEY)
        kwargs = _get_mtls_kwargs()
        assert 'cert' in kwargs
        cert_tuple = kwargs['cert']
        assert isinstance(cert_tuple, tuple)
        assert len(cert_tuple) == 2
        cert_path, key_path = cert_tuple
        # Must be file paths that exist (not PEM strings)
        assert os.path.isfile(cert_path), f"cert_path is not a file: {cert_path}"
        assert os.path.isfile(key_path), f"key_path is not a file: {key_path}"
        # Content must match
        with open(cert_path) as f:
            assert f.read() == FAKE_CERT
        with open(key_path) as f:
            assert f.read() == FAKE_KEY
        purge_ephemeral_cert()

    def test_purge_removes_temp_files(self):
        """purge_ephemeral_cert must delete temp files."""
        set_ephemeral_cert(FAKE_CERT, FAKE_KEY)
        kwargs_before = _get_mtls_kwargs()
        cert_path = kwargs_before['cert'][0]
        key_path = kwargs_before['cert'][1]
        assert os.path.isfile(cert_path)
        assert os.path.isfile(key_path)

        purge_ephemeral_cert()
        assert not os.path.isfile(cert_path), "cert temp file not deleted"
        assert not os.path.isfile(key_path), "key temp file not deleted"

    def test_no_ephemeral_falls_back_to_persistent(self, monkeypatch):
        """Without ephemeral cert, persistent K8s cert is used (if paths exist)."""
        purge_ephemeral_cert()
        with tempfile.NamedTemporaryFile(suffix='.crt', delete=False) as cf:
            cf.write(b"fake-cert-content")
            cert_path = cf.name
        with tempfile.NamedTemporaryFile(suffix='.key', delete=False) as kf:
            kf.write(b"fake-key-content")
            key_path = kf.name
        try:
            monkeypatch.setenv('MTLS_CERT_PATH', cert_path)
            monkeypatch.setenv('MTLS_KEY_PATH', key_path)
            # Reload module globals
            import app.integration.iuws_client as mod
            mod.MTLS_CERT_PATH = cert_path
            mod.MTLS_KEY_PATH = key_path
            mod.MTLS_CA_PATH = '/nonexistent/ca.crt'
            kwargs = mod._get_mtls_kwargs()
            assert kwargs['cert'] == (cert_path, key_path)
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)
