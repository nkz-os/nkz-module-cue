#!/usr/bin/env python3
"""Official CUE Campaign Notebook Exporters (HTML, PDF via WeasyPrint, XLSX via stdlib)."""

from __future__ import annotations

import io
import zipfile
from html import escape as html_escape
from typing import Any, Dict, List, Sequence
from xml.sax.saxutils import escape as xml_escape


# =========================================================================
# HTML / PDF EXPORT (RD 1054/2022 + RD 1051/2022)
# =========================================================================

def _html_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    if not rows:
        return '<p class="empty">Sin registros en esta campaña.</p>'
    th = ''.join(f'<th>{html_escape(str(h))}</th>' for h in headers)
    body_rows = []
    for row in rows:
        tds = ''.join(f'<td>{html_escape("" if v is None else str(v))}</td>' for v in row)
        body_rows.append(f'<tr>{tds}</tr>')
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'


def export_notebook_html(notebook: Dict[str, Any]) -> str:
    """Render an inspection-ready Spanish HTML report for a campaign CUE notebook."""
    camp = notebook.get('campanya', '')
    res = notebook.get('resumen', {})
    exps = notebook.get('explotaciones', [])
    exp_rows = [
        [e.get('nombre'), e.get('nif_titular'), e.get('regepa'), e.get('cif_entidad_habilitada')]
        for e in exps
    ]
    parcel_rows = [
        [p.get('nombre'), p.get('sigpac'), p.get('cultivo'), p.get('superficie_ha'), p.get('riego')]
        for p in notebook.get('parcelas', [])
    ]
    eq_rows = [
        [e.get('nombre'), e.get('numero_roma'), e.get('tipo_equipo'), e.get('fecha_proxima_iteaf'),
         'Vigente' if e.get('iteaf_vigente') else ('Caducada' if e.get('iteaf_vigente') is False else 'Sin fecha')]
        for e in notebook.get('equipos_roma', [])
    ]
    ap_rows = [
        [a.get('nombre'), a.get('nif'), a.get('numero_carne_ropo'), a.get('nivel_capacitacion'), a.get('fecha_caducidad')]
        for a in notebook.get('personal_ropo', [])
    ]
    tr_rows = [
        [t.get('fecha'), t.get('parcela_nombre'), t.get('cultivo'), t.get('producto'),
         t.get('numero_registro'), f"{t.get('dosis') or ''} {t.get('unidad_dosis') or ''}".strip(),
         t.get('plaga_objeto'), t.get('superficie_tratada_ha'), t.get('volumen_caldo_l_ha'),
         t.get('equipo_roma'), t.get('aplicador_ropo')]
        for t in notebook.get('tratamientos_fitosanitarios', [])
    ]
    ft_rows = [
        [f.get('fecha'), f.get('parcela_nombre'), f.get('producto'),
         'Orgánico' if f.get('organico') else 'Mineral', f.get('dosis_kg_ha'),
         f"{f.get('contenido_n_pct')}/{f.get('contenido_p2o5_pct')}/{f.get('contenido_k2o_pct')}",
         f.get('n_aplicado_kg_ha'), f.get('p2o5_aplicado_kg_ha'), f.get('k2o_aplicado_kg_ha'),
         f.get('metodo_incorporacion'), f.get('origen_organico_rega')]
        for f in notebook.get('fertilizaciones', [])
    ]
    fast_rows = [
        [pid.split(':')[-1], p.get('plan_id'), f"v{p.get('version')}", p.get('signed_at'),
         (p.get('signature') or {}).get('name', ''), (p.get('snapshot_sha256') or '')[:16]]
        for pid, p in (notebook.get('planes_abonado_fast') or {}).items()
    ]
    riego_rows = [
        [r.get('fecha'), r.get('parcela_nombre'), r.get('volumen_m3_ha'),
         r.get('sistema_riego'), r.get('procedencia_agua'), r.get('origen_dato')]
        for r in notebook.get('riegos', [])
    ]
    labor_rows = [
        [l.get('fecha'), l.get('parcela_nombre'), l.get('tipo'), l.get('detalle'),
         l.get('dosis_siembra') or l.get('profundidad_cm') or '', l.get('metodo_siembra')]
        for l in notebook.get('siembras_y_labores', [])
    ]
    cos_rows = [
        [c.get('fecha'), c.get('parcela_nombre'), c.get('tipo'), c.get('cultivo'),
         c.get('cantidad_kg'), c.get('destino_lote')]
        for c in notebook.get('cosechas', [])
    ]
    inc_rows = [
        [i.get('severidad', '').upper(), i.get('bloque'), i.get('codigo') or i.get('rule', ''), i.get('mensaje') or i.get('message', '')]
        for i in notebook.get('incidencias', [])
    ]

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Cuaderno de Explotación (CUE) — Campaña {html_escape(str(camp))}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  body {{ font-family: DejaVu Sans, Arial, sans-serif; font-size: 9pt; color: #111827; }}
  h1 {{ font-size: 15pt; margin: 0 0 4px 0; color: #0f766e; }}
  h2 {{ font-size: 11pt; margin: 14px 0 6px 0; border-bottom: 1px solid #cbd5e1; padding-bottom: 2px; color: #1e293b; }}
  .meta {{ font-size: 8pt; color: #475569; margin-bottom: 10px; }}
  .kpi {{ display: inline-block; margin-right: 16px; padding: 4px 8px; background: #f1f5f9; border-radius: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; font-size: 8pt; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 3px 5px; text-align: left; }}
  th {{ background: #e2e8f0; font-weight: bold; }}
  .empty {{ color: #64748b; font-style: italic; font-size: 8pt; }}
</style>
</head>
<body>
  <h1>Cuaderno de Explotación Agrícola (CUE — RD 1054/2022 · RD 1051/2022)</h1>
  <div class="meta">
    Campaña: <strong>{html_escape(str(camp))}</strong> ·
    Generado: {html_escape(str(notebook.get('generado_en', '')))} ·
    ZVN: {'Sí (límite 170 kg N orgánico/ha·año)' if notebook.get('zona_vulnerable_nitratos') else 'No'}
  </div>
  <div>
    <span class="kpi">Parcelas: {res.get('total_parcelas', 0)} ({res.get('superficie_total_ha', 0)} ha)</span>
    <span class="kpi">Fitosanitarios: {res.get('tratamientos', 0)}</span>
    <span class="kpi">Fertilizaciones: {res.get('fertilizaciones', 0)}</span>
    <span class="kpi">Riegos: {res.get('riegos', 0)}</span>
    <span class="kpi">Planes FaST firmados: {res.get('planes_fast_firmados', 0)}</span>
    <span class="kpi">Errores: {res.get('errores_inspeccion', 0)} · Avisos: {res.get('advertencias_inspeccion', 0)}</span>
  </div>

  <h2>1. Identificación de la Explotación y Parcelas</h2>
  {_html_table(['Explotación', 'NIF Titular', 'REGEPA', 'CIF Entidad Habilitada'], exp_rows)}
  {_html_table(['Parcela', 'Referencia SIGPAC', 'Cultivo', 'Superficie (ha)', 'Sistema Riego'], parcel_rows)}

  <h2>2. Equipos de Aplicación (ROMA / ITEAF) y Personal / Asesores (ROPO)</h2>
  {_html_table(['Equipo', 'Nº ROMA', 'Tipo', 'Próxima ITEAF', 'Estado ITEAF'], eq_rows)}
  {_html_table(['Nombre', 'NIF', 'Nº Carné ROPO', 'Nivel', 'Caducidad'], ap_rows)}

  <h2>3. Tratamientos Fitosanitarios</h2>
  {_html_table(['Fecha', 'Parcela', 'Cultivo', 'Producto', 'Nº Reg.', 'Dosis', 'Plaga', 'Sup. (ha)', 'Caldo (L/ha)', 'ROMA', 'ROPO'], tr_rows)}

  <h2>4. Fertilización (RD 1051/2022) y Plan de Abonado (FaST)</h2>
  {_html_table(['Fecha', 'Parcela', 'Fertilizante', 'Tipo', 'Dosis (kg/ha)', 'N/P₂O₅/K₂O (%)', 'N (kg/ha)', 'P₂O₅ (kg/ha)', 'K₂O (kg/ha)', 'Incorporación', 'Origen REGA'], ft_rows)}
  {_html_table(['Parcela', 'Plan FaST ID', 'Versión', 'Firmado en', 'Asesor / Titular', 'Sello SHA-256'], fast_rows)}

  <h2>5. Riegos</h2>
  {_html_table(['Fecha', 'Parcela', 'Volumen (m³/ha)', 'Sistema', 'Procedencia', 'Fuente'], riego_rows)}

  <h2>6. Siembras, Labores y Cosechas</h2>
  {_html_table(['Fecha', 'Parcela', 'Tipo', 'Detalle', 'Dosis / Prof.', 'Método'], labor_rows)}
  {_html_table(['Fecha', 'Parcela', 'Tipo', 'Cultivo', 'Cantidad (kg)', 'Destino / Lote'], cos_rows)}

  <h2>7. Checklist de Inspección e Incidencias</h2>
  {_html_table(['Severidad', 'Bloque', 'Código', 'Descripción'], inc_rows)}
</body>
</html>"""


def export_notebook_pdf(notebook: Dict[str, Any]) -> bytes:
    """Render official CUE campaign notebook to PDF bytes via WeasyPrint."""
    import weasyprint
    html = export_notebook_html(notebook)
    return weasyprint.HTML(string=html).write_pdf()


# =========================================================================
# XLSX EXPORT (stdlib OOXML — zero external dependencies)
# =========================================================================

def _col_letter(idx: int) -> str:
    res = ''
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(65 + rem) + res
    return res


def _build_sheet_xml(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    all_rows = [list(headers)] + [list(r) for r in rows]
    xml_rows = []
    for r_idx, row in enumerate(all_rows, start=1):
        cells = []
        for c_idx, val in enumerate(row):
            ref = f'{_col_letter(c_idx)}{r_idx}'
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                text = '' if val is None else str(val)
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(text)}</t></is></c>')
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        '</worksheet>'
    )


def export_notebook_xlsx(notebook: Dict[str, Any]) -> bytes:
    """Build a standard multi-sheet .xlsx workbook using Python stdlib only."""
    res = notebook.get('resumen', {})
    sheets = [
        ('Resumen', ['Indicador', 'Valor'], [
            ['Campaña', notebook.get('campanya')],
            ['Generado', notebook.get('generado_en')],
            ['ZVN', 'Sí' if notebook.get('zona_vulnerable_nitratos') else 'No'],
            ['Total parcelas', res.get('total_parcelas', 0)],
            ['Superficie total (ha)', res.get('superficie_total_ha', 0)],
            ['Tratamientos fitosanitarios', res.get('tratamientos', 0)],
            ['Fertilizaciones', res.get('fertilizaciones', 0)],
            ['Riegos', res.get('riegos', 0)],
            ['Siembras y labores', res.get('siembras_y_labores', 0)],
            ['Cosechas', res.get('cosechas', 0)],
            ['Planes FaST firmados', res.get('planes_fast_firmados', 0)],
            ['Errores de inspección', res.get('errores_inspeccion', 0)],
            ['Advertencias de inspección', res.get('advertencias_inspeccion', 0)],
        ]),
        ('Parcelas', ['Parcela', 'SIGPAC', 'Cultivo', 'Superficie_ha', 'Riego'], [
            [p.get('nombre'), p.get('sigpac'), p.get('cultivo'), p.get('superficie_ha'), p.get('riego')]
            for p in notebook.get('parcelas', [])
        ]),
        ('Equipos_Personal', ['Tipo', 'Nombre', 'Registro_ROMA_ROPO', 'Categoria', 'Vigencia_Hasta'], [
            ['Equipo ROMA', e.get('nombre'), e.get('numero_roma'), e.get('tipo_equipo'), e.get('fecha_proxima_iteaf')]
            for e in notebook.get('equipos_roma', [])
        ] + [
            ['Personal ROPO', a.get('nombre'), a.get('numero_carne_ropo'), a.get('nivel_capacitacion'), a.get('fecha_caducidad')]
            for a in notebook.get('personal_ropo', [])
        ]),
        ('Fitosanitarios', ['Fecha', 'Parcela', 'Cultivo', 'Producto', 'Num_Registro', 'Dosis', 'Unidad', 'Plaga', 'Sup_Tratada_ha', 'Caldo_L_ha', 'ROMA', 'ROPO', 'Asesor_GIP', 'Lote'], [
            [t.get('fecha'), t.get('parcela_nombre'), t.get('cultivo'), t.get('producto'),
             t.get('numero_registro'), t.get('dosis'), t.get('unidad_dosis'), t.get('plaga_objeto'),
             t.get('superficie_tratada_ha'), t.get('volumen_caldo_l_ha'), t.get('equipo_roma'),
             t.get('aplicador_ropo'), t.get('asesor_gip'), t.get('lote')]
            for t in notebook.get('tratamientos_fitosanitarios', [])
        ]),
        ('Fertilizacion', ['Fecha', 'Parcela', 'Producto', 'Organico', 'Dosis_kg_ha', 'N_pct', 'P2O5_pct', 'K2O_pct', 'N_kg_ha', 'P2O5_kg_ha', 'K2O_kg_ha', 'Incorporacion', 'Origen_REGA'], [
            [f.get('fecha'), f.get('parcela_nombre'), f.get('producto'), 'Sí' if f.get('organico') else 'No',
             f.get('dosis_kg_ha'), f.get('contenido_n_pct'), f.get('contenido_p2o5_pct'), f.get('contenido_k2o_pct'),
             f.get('n_aplicado_kg_ha'), f.get('p2o5_aplicado_kg_ha'), f.get('k2o_aplicado_kg_ha'),
             f.get('metodo_incorporacion'), f.get('origen_organico_rega')]
            for f in notebook.get('fertilizaciones', [])
        ]),
        ('Riegos', ['Fecha', 'Parcela', 'Volumen_m3_ha', 'Sistema', 'Procedencia', 'Fuente'], [
            [r.get('fecha'), r.get('parcela_nombre'), r.get('volumen_m3_ha'),
             r.get('sistema_riego'), r.get('procedencia_agua'), r.get('origen_dato')]
            for r in notebook.get('riegos', [])
        ]),
        ('Labores_Cosechas', ['Fecha', 'Parcela', 'Tipo', 'Detalle_Cultivo', 'Cantidad_Dosis', 'Metodo_Destino'], [
            [l.get('fecha'), l.get('parcela_nombre'), l.get('tipo'), l.get('detalle'),
             l.get('dosis_siembra') or l.get('profundidad_cm'), l.get('metodo_siembra')]
            for l in notebook.get('siembras_y_labores', [])
        ] + [
            [c.get('fecha'), c.get('parcela_nombre'), c.get('tipo'), c.get('cultivo'),
             c.get('cantidad_kg'), c.get('destino_lote')]
            for c in notebook.get('cosechas', [])
        ]),
        ('Incidencias', ['Severidad', 'Bloque', 'Codigo', 'Mensaje'], [
            [i.get('severidad'), i.get('bloque'), i.get('codigo') or i.get('rule', ''), i.get('mensaje') or i.get('message', '')]
            for i in notebook.get('incidencias', [])
        ]),
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        overrides = ''.join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        zf.writestr(
            '[Content_Types].xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f'{overrides}</Types>',
        )
        zf.writestr(
            '_rels/.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        sheet_tags = ''.join(
            f'<sheet name="{xml_escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, (name, _, _) in enumerate(sheets, start=1)
        )
        zf.writestr(
            'xl/workbook.xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{sheet_tags}</sheets></workbook>',
        )
        rel_tags = ''.join(
            f'<Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        zf.writestr(
            'xl/_rels/workbook.xml.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{rel_tags}</Relationships>',
        )
        for i, (_, headers, rows) in enumerate(sheets, start=1):
            zf.writestr(f'xl/worksheets/sheet{i}.xml', _build_sheet_xml(headers, rows))

    return buf.getvalue()
