#!/usr/bin/env python3
# =============================================================================
# ETL — ROPO Master Catalog Sync (SCD Type 2)
# =============================================================================
# Downloads official ROPO dump from MAPA, transforms, and loads into
# cue_producto_ropo with Slowly Changing Dimension Type 2.

import os
import logging
import hashlib
import csv
import io
from datetime import date
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv(
    'POSTGRES_URL',
    'postgresql://postgres:postgres@postgresql-service:5432/nekazari'
)

# Official MAPA ROPO dump URL (CSV format)
ROPO_DUMP_URL = os.getenv(
    'ROPO_DUMP_URL',
    'https://www.mapa.gob.es/app/ropo/descarga/ropo_completo.csv'
)


def compute_hash(content: bytes) -> str:
    """Compute SHA-256 hash of source content for audit trail."""
    return hashlib.sha256(content).hexdigest()


def download_ropo_dump() -> bytes:
    """Download the official ROPO CSV dump from MAPA."""
    import requests
    r = requests.get(ROPO_DUMP_URL, timeout=60)
    r.raise_for_status()
    return r.content


def parse_ropo_csv(content: bytes) -> list[dict]:
    """Parse ROPO CSV into list of product dicts."""
    text = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    products = []
    for row in reader:
        products.append({
            'numero_registro': row.get('NumeroRegistro', '').strip(),
            'nombre_comercial': row.get('NombreComercial', '').strip(),
            'ingrediente_activo': row.get('IngredienteActivo', '').strip(),
            'titular': row.get('Titular', '').strip(),
            'tipo': row.get('Tipo', '').strip(),
            'estado': row.get('Estado', 'autorizado').strip().lower(),
            'cultivos': [c.strip() for c in row.get('Cultivos', '').split(',') if c.strip()],
            'plagas': [p.strip() for p in row.get('Plagas', '').split(',') if p.strip()],
            'dosis_maxima': float(row.get('DosisMaxima', 0) or 0),
            'unidad_dosis': row.get('UnidadDosis', 'L/ha').strip(),
            'plazo_seguridad_dias': int(row.get('PlazoSeguridad', 0) or 0),
        })
    return products


def sync_ropo_products(products: list[dict], source_hash: str) -> dict:
    """
    Sync ROPO products to PostgreSQL with SCD Type 2.

    For each product:
    - If new (numero_registro not in DB): INSERT with fecha_inicio_validez=today
    - If existing and changed (estado/cultivos/dosis differ): close current row
      (fecha_fin_validez=today) and INSERT new row
    - If existing and unchanged: skip
    """
    conn = psycopg2.connect(POSTGRES_URL)
    cur = conn.cursor()

    inserted = 0
    closed = 0
    skipped = 0

    for p in products:
        nr = p['numero_registro']

        # Find current active row for this product
        cur.execute(
            "SELECT id, estado, cultivos_autorizados, plagas_autorizadas, "
            "dosis_maxima, plazo_seguridad_dias "
            "FROM cue_producto_ropo "
            "WHERE numero_registro = %s AND fecha_fin_validez IS NULL "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (nr,)
        )
        current = cur.fetchone()

        if current is None:
            # New product: insert
            cur.execute(
                "INSERT INTO cue_producto_ropo (numero_registro, nombre_comercial, "
                "ingrediente_activo, titular, tipo, estado, cultivos_autorizados, "
                "plagas_autorizadas, dosis_maxima, unidad_dosis, plazo_seguridad_dias, "
                "fuente_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (nr, p['nombre_comercial'], p['ingrediente_activo'], p['titular'],
                 p['tipo'], p['estado'], p['cultivos'], p['plagas'],
                 p['dosis_maxima'], p['unidad_dosis'], p['plazo_seguridad_dias'],
                 source_hash)
            )
            inserted += 1
        else:
            cur_id, cur_estado, cur_cultivos, cur_plagas, cur_dosis, cur_plazo = current
            # Check for changes
            changed = (
                cur_estado != p['estado']
                or cur_cultivos != p['cultivos']
                or cur_plagas != p['plagas']
                or cur_dosis != p['dosis_maxima']
                or cur_plazo != p['plazo_seguridad_dias']
            )
            if changed:
                # SCD Type 2: close current row
                cur.execute(
                    "UPDATE cue_producto_ropo SET fecha_fin_validez = %s "
                    "WHERE id = %s",
                    (date.today(), cur_id)
                )
                closed += 1
                # Insert new row
                cur.execute(
                    "INSERT INTO cue_producto_ropo (numero_registro, nombre_comercial, "
                    "ingrediente_activo, titular, tipo, estado, cultivos_autorizados, "
                    "plagas_autorizadas, dosis_maxima, unidad_dosis, plazo_seguridad_dias, "
                    "fecha_inicio_validez, fuente_hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (nr, p['nombre_comercial'], p['ingrediente_activo'], p['titular'],
                     p['tipo'], p['estado'], p['cultivos'], p['plagas'],
                     p['dosis_maxima'], p['unidad_dosis'], p['plazo_seguridad_dias'],
                     date.today(), source_hash)
                )
                inserted += 1
            else:
                skipped += 1

    conn.commit()
    cur.close()
    conn.close()

    return {'inserted': inserted, 'closed': closed, 'skipped': skipped, 'total': len(products)}


def run_ropo_sync() -> dict:
    """Run the full ROPO ETL pipeline."""
    logger.info("Starting ROPO ETL sync")

    content = download_ropo_dump()
    source_hash = compute_hash(content)
    products = parse_ropo_csv(content)

    if not products:
        logger.warning("ROPO dump contained no products")
        return {'status': 'empty', 'products': 0}

    result = sync_ropo_products(products, source_hash)
    logger.info(f"ROPO sync complete: {result}")

    return {'status': 'ok', 'source_hash': source_hash, **result}
