#!/usr/bin/env python3
"""Tests for Block B: ROMA/ROPO masters, campaign notebook aggregator, RD 1051/2022 rules, and PDF/XLSX export."""

import io
import os
import sys
import zipfile
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.cue_api import app
from app.exporters import export_notebook_html, export_notebook_pdf, export_notebook_xlsx
from app.notebook_aggregator import build_campaign_notebook
from app.rules.engine import validate_fertilizacion_campanya


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sample_orion_data():
    farms = [{
        'id': 'urn:ngsi-ld:AgriFarm:acme:f1',
        'name': 'Finca El Prado',
        'regepa': '31-00123',
        'ownedBy': 'urn:ngsi-ld:Person:acme:12345678Z',
        'address': {'addressLocality': 'Tudela', 'addressRegion': 'Navarra'},
    }]
    parcels = [{
        'id': 'urn:ngsi-ld:AgriParcel:acme:p1',
        'name': 'Parcela Norte',
        'cropType': 'Trigo',
        'area': 10.0,
        'irrigation': 'secano',
    }]
    ops = [
        {
            'id': 'urn:ngsi-ld:AgriParcelOperation:acme:op-spray',
            'operationType': 'spraying',
            'status': 'completed',
            'hasAgriParcel': 'urn:ngsi-ld:AgriParcel:acme:p1',
            'startedAt': {'@value': '2026-04-15T08:00:00Z'},
            'productName': 'Fungicida Pro',
            'productRegistryRef': 'ES-00123',
            'productRate': 1.2,
            'productRateUnit': 'L/ha',
            'target': 'Roya parda',
            'treatedAreaHa': 10.0,
            'sprayVolumeLHa': 250.0,
            'equipmentRoma': '31/12345',
            'applicatorRopo': 'NA-9988',
        },
        {
            'id': 'urn:ngsi-ld:AgriParcelOperation:acme:op-fert',
            'operationType': 'fertilization',
            'status': 'completed',
            'hasAgriParcel': 'urn:ngsi-ld:AgriParcel:acme:p1',
            'startedAt': {'@value': '2026-03-10T09:00:00Z'},
            'fertilizerType': 'Purín porcino',
            'organicFertilizer': True,
            'fertilizerRate': 40000.0,
            'nitrogenContent': 0.5,
            'phosphorusPentoxideContent': 0.2,
            'potassiumOxideContent': 0.4,
            'incorporationMethod': 'enterrado_24h',
            'organicOriginRega': 'ES310000012345',
        },
        {
            'id': 'urn:ngsi-ld:AgriParcelOperation:acme:op-irr',
            'operationType': 'irrigation',
            'status': 'completed',
            'hasAgriParcel': 'urn:ngsi-ld:AgriParcel:acme:p1',
            'startedAt': {'@value': '2026-05-20T06:00:00Z'},
            'waterPerHectare': 350.0,
            'dataSource': 'sensor',
        },
        {
            'id': 'urn:ngsi-ld:AgriParcelOperation:acme:op-harv',
            'operationType': 'harvesting',
            'status': 'completed',
            'hasAgriParcel': 'urn:ngsi-ld:AgriParcel:acme:p1',
            'startedAt': {'@value': '2026-07-12T10:00:00Z'},
            'harvestedWeight': 62000.0,
            'harvestBatch': 'LOTE-2026-01',
        },
        # Different campaign year — must be excluded
        {
            'id': 'urn:ngsi-ld:AgriParcelOperation:acme:op-old',
            'operationType': 'spraying',
            'status': 'completed',
            'hasAgriParcel': 'urn:ngsi-ld:AgriParcel:acme:p1',
            'startedAt': {'@value': '2025-04-15T08:00:00Z'},
            'productName': 'Viejo',
        },
    ]
    return farms, parcels, ops


class TestCampaignNotebookAggregator:
    def test_aggregates_all_sources_and_flags_zvn_and_expired_iteaf(self):
        farms, parcels, ops = _sample_orion_data()

        def _fake_query(etype, tenant, params=None):
            if etype == 'AgriFarm':
                return 200, farms
            if etype == 'AgriParcel':
                return 200, parcels
            if etype == 'AgriParcelOperation':
                return 200, ops
            return 200, []

        expired = date.today() - timedelta(days=10)
        equipos = [{'id': 1, 'nombre': 'Pulverizador 1', 'numero_roma': '31/12345', 'fecha_proxima_iteaf': expired}]
        aplicadores = [{'id': 1, 'nombre': 'Ana', 'numero_carne_ropo': 'NA-9988', 'nivel_capacitacion': 'cualificado', 'fecha_caducidad': date.today() + timedelta(days=365)}]
        fast_plan = {
            'plan_id': 'plan-1',
            'version': 2,
            'campaign': 2026,
            'signed_at': '2026-02-01T10:00:00Z',
            'snapshot_sha256': 'abcdef1234567890abcdef',
            'signature': {'kind': 'advisor', 'name': 'Técnico Competente'},
            'sheets': [],
        }

        with patch('app.notebook_aggregator.query_entities', side_effect=_fake_query), \
             patch('app.notebook_aggregator._fetch_legal_masters', return_value=(equipos, aplicadores)), \
             patch('app.notebook_aggregator.fetch_fast_plan_summary', return_value=fast_plan):
            nb = build_campaign_notebook('acme', 2026, vulnerable_zone=True)

        assert nb['resumen']['total_parcelas'] == 1
        assert nb['resumen']['tratamientos'] == 1
        assert nb['resumen']['fertilizaciones'] == 1
        assert nb['resumen']['riegos'] == 1
        assert nb['resumen']['cosechas'] == 1
        assert nb['resumen']['planes_fast_firmados'] == 1
        # 40000 kg/ha * 0.5% N = 200 kg N orgánico/ha > 170 kg/ha ZVN limit
        assert nb['fertilizaciones'][0]['n_aplicado_kg_ha'] == 200.0
        assert nb['fertilizaciones'][0]['k2o_aplicado_kg_ha'] == 160.0
        codes = {i.get('codigo') for i in nb['incidencias']}
        assert 'ITEAF_CADUCADA' in codes
        assert 'ZVN_LIMITE_N_ORGANICO_EXCEDIDO' in codes
        assert 'SIN_PLAN_ABONADO_FIRMADO' not in codes

    def test_exports_html_xlsx_and_pdf(self):
        farms, parcels, ops = _sample_orion_data()
        with patch('app.notebook_aggregator.query_entities', side_effect=lambda t, *a: (200, {'AgriFarm': farms, 'AgriParcel': parcels, 'AgriParcelOperation': ops}.get(t, []))), \
             patch('app.notebook_aggregator._fetch_legal_masters', return_value=([], [])), \
             patch('app.notebook_aggregator.fetch_fast_plan_summary', return_value=None):
            nb = build_campaign_notebook('acme', 2026, vulnerable_zone=False)

        html = export_notebook_html(nb)
        assert 'Cuaderno de Explotación Agrícola' in html
        assert 'Fungicida Pro' in html
        assert 'LOTE-2026-01' in html

        xlsx_bytes = export_notebook_xlsx(nb)
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes), 'r') as zf:
            names = set(zf.namelist())
            assert 'xl/workbook.xml' in names
            assert 'xl/worksheets/sheet4.xml' in names
            sheet4 = zf.read('xl/worksheets/sheet4.xml').decode('utf-8')
            assert 'Fungicida Pro' in sheet4

        pdf_bytes = export_notebook_pdf(nb)
        assert pdf_bytes.startswith(b'%PDF-')


class TestFertilizationCampaignRules:
    def test_warns_missing_incorporation_and_missing_fast_plan(self):
        res = validate_fertilizacion_campanya(
            [{
                'parcela_id': 'p1',
                'parcela_nombre': 'Norte',
                'fecha': '2026-03-01',
                'organico': True,
                'n_aplicado_kg_ha': 120.0,
                'metodo_incorporacion': '',
            }],
            vulnerable_zone=True,
            signed_plan_parcels=set(),
        )
        assert res['valid'] is True
        warn_codes = {w['codigo'] for w in res['warnings']}
        assert 'INCORPORACION_ORGANICO_SIN_REGISTRAR' in warn_codes
        assert 'SIN_PLAN_ABONADO_FIRMADO' in warn_codes


class TestMaestrosAndExportEndpoints:
    def test_maestros_equipos_roma_internal_read(self, client, monkeypatch):
        monkeypatch.setenv('INTERNAL_SERVICE_SECRET', 's3cr3t')
        fake_cur = MagicMock()
        fake_cur.fetchall.return_value = [
            {'id': 1, 'nombre': 'Pulverizador', 'numero_roma': '31/100', 'fecha_proxima_iteaf': date.today() + timedelta(days=30)}
        ]
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        with patch('app.maestros_routes._get_pg_conn', return_value=fake_conn):
            r = client.get(
                '/api/modules/cue/equipos-roma',
                headers={'X-Internal-Service-Secret': 's3cr3t', 'X-Tenant-ID': 'acme'},
            )
        assert r.status_code == 200
        data = r.get_json()
        assert data[0]['numero_roma'] == '31/100'
        assert data[0]['iteaf_vigente'] is True

    def test_cuaderno_export_endpoint_xlsx(self, client, monkeypatch):
        monkeypatch.setenv('INTERNAL_SERVICE_SECRET', 's3cr3t')
        with patch('app.notebook_aggregator.build_campaign_notebook', return_value={
            'campanya': 2026, 'generado_en': '2026-11-24T00:00:00Z', 'tenant_id': 'acme',
            'zona_vulnerable_nitratos': False, 'explotaciones': [], 'resumen': {},
            'parcelas': [], 'equipos_roma': [], 'personal_ropo': [],
            'tratamientos_fitosanitarios': [], 'fertilizaciones': [], 'planes_abonado_fast': {},
            'riegos': [], 'siembras_y_labores': [], 'cosechas': [], 'observaciones': [], 'incidencias': [],
        }):
            r = client.get(
                '/api/modules/cue/cuaderno/2026/export?format=xlsx',
                headers={'X-Internal-Service-Secret': 's3cr3t', 'X-Tenant-ID': 'acme'},
            )
        assert r.status_code == 200
        assert 'spreadsheetml' in r.content_type
        assert r.data[:2] == b'PK'
