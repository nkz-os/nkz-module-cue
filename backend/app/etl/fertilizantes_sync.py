#!/usr/bin/env python3
# =============================================================================
# ETL — Fertilizantes Master Catalog Sync (SCD Type 2)
# =============================================================================
# Downloads official fertilizer registry dump from MAPA, transforms, and loads
# into cue_producto_fertilizante with Slowly Changing Dimension Type 2.

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

# Official MAPA fertilizer registry dump URL (CSV format)
FERTILIZANTES_DUMP_URL = os.getenv(
    'FERTILIZANTES_DUMP_URL',
    'https://www.mapa.gob.es/app/fertilizantes/descarga/fertilizantes_completo.csv'
)


def compute_hash(content: bytes) -> str:
    """Compute SHA-256 hash of source content for audit trail."""
    return hashlib.sha256(content).hexdigest()


def download_fertilizantes_dump() -> bytes:
    """Download the official fertilizer registry CSV dump from MAPA."""
    import requests
    r = requests.get(FERTILIZANTES_DUMP_URL, timeout=60)
    r.raise_for_status()
    return r.content


def parse_fertilizantes_csv(content: bytes) -> list[dict]:
    """Parse fertilizer registry CSV into list of product dicts."""
    text = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    products = []
    for row in reader:
        products.append({
            'numero_registro': row.get('NumeroRegistro', '').strip(),
            'nombre_comercial': row.get('NombreComercial', '').strip(),
            'tipo': row.get('Tipo', '').strip(),
            'composicion_n_pct': float(row.get('ComposicionN', 0) or 0),
            'composicion_p_pct': float(row.get('ComposicionP', 0) or 0),
            'composicion_k_pct': float(row.get('ComposicionK', 0) or 0),
            'fabricante': row.get('Fabricante', '').strip(),
            'estado': row.get('Estado', 'autorizado').strip().lower(),
            'cultivos': [c.strip() for c in row.get('Cultivos', '').split(',') if c.strip()],
            'dosis_maxima_kg_ha': float(row.get('DosisMaxima', 0) or 0),
        })
    return products


def sync_fertilizantes_products(products: list[dict], source_hash: str) -> dict:
    """
    Sync fertilizer products to PostgreSQL with SCD Type 2.

    For each product:
    - If new (numero_registro not in DB): INSERT with fecha_inicio_validez=today
    - If existing and changed (estado/composicion/cultivos differ): close current
      row (fecha_fin_validez=today) and INSERT new row
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
            "SELECT id, estado, composicion_n_pct, composicion_p_pct, "
            "composicion_k_pct, cultivos_autorizados, dosis_maxima_kg_ha "
            "FROM cue_producto_fertilizante "
            "WHERE numero_registro = %s AND fecha_fin_validez IS NULL "
            "ORDER BY fecha_inicio_validez DESC LIMIT 1",
            (nr,)
        )
        current = cur.fetchone()

        if current is None:
            # New product: insert
            cur.execute(
                "INSERT INTO cue_producto_fertilizante (numero_registro, nombre_comercial, "
                "tipo, composicion_n_pct, composicion_p_pct, composicion_k_pct, "
                "fabricante, estado, cultivos_autorizados, dosis_maxima_kg_ha, "
                "fuente_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (nr, p['nombre_comercial'], p['tipo'],
                 p['composicion_n_pct'], p['composicion_p_pct'], p['composicion_k_pct'],
                 p['fabricante'], p['estado'], p['cultivos'], p['dosis_maxima_kg_ha'],
                 source_hash)
            )
            inserted += 1
        else:
            (cur_id, cur_estado, cur_n, cur_p, cur_k,
             cur_cultivos, cur_dosis) = current
            # Check for changes
            changed = (
                cur_estado != p['estado']
                or float(cur_n or 0) != p['composicion_n_pct']
                or float(cur_p or 0) != p['composicion_p_pct']
                or float(cur_k or 0) != p['composicion_k_pct']
                or cur_cultivos != p['cultivos']
                or float(cur_dosis or 0) != p['dosis_maxima_kg_ha']
            )
            if changed:
                # SCD Type 2: close current row
                cur.execute(
                    "UPDATE cue_producto_fertilizante SET fecha_fin_validez = %s "
                    "WHERE id = %s",
                    (date.today(), cur_id)
                )
                closed += 1
                # Insert new row
                cur.execute(
                    "INSERT INTO cue_producto_fertilizante (numero_registro, nombre_comercial, "
                    "tipo, composicion_n_pct, composicion_p_pct, composicion_k_pct, "
                    "fabricante, estado, cultivos_autorizados, dosis_maxima_kg_ha, "
                    "fecha_inicio_validez, fuente_hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (nr, p['nombre_comercial'], p['tipo'],
                     p['composicion_n_pct'], p['composicion_p_pct'], p['composicion_k_pct'],
                     p['fabricante'], p['estado'], p['cultivos'], p['dosis_maxima_kg_ha'],
                     date.today(), source_hash)
                )
                inserted += 1
            else:
                skipped += 1

    conn.commit()
    cur.close()
    conn.close()

    return {'inserted': inserted, 'closed': closed, 'skipped': skipped, 'total': len(products)}


def run_fertilizantes_sync() -> dict:
    """Run the full fertilizer registry ETL pipeline."""
    logger.info("Starting Fertilizantes ETL sync")

    content = download_fertilizantes_dump()
    source_hash = compute_hash(content)
    products = parse_fertilizantes_csv(content)

    if not products:
        logger.warning("Fertilizantes dump contained no products")
        return {'status': 'empty', 'products': 0}

    result = sync_fertilizantes_products(products, source_hash)
    logger.info(f"Fertilizantes sync complete: {result}")

    return {'status': 'ok', 'source_hash': source_hash, **result}
