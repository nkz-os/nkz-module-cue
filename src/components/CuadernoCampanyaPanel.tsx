import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Loader2,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Download,
  FileSpreadsheet,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { cuadernoApi } from '../services/cueApi';

type SectionId = 'fitosanitarios' | 'fertilizacion' | 'riegos' | 'labores' | 'parcelas' | 'incidencias';

export const CuadernoCampanyaPanel: React.FC = () => {
  const { t } = useTranslation('cue');
  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 6 }, (_, i) => currentYear - i);

  const [campaign, setCampaign] = useState<number>(currentYear);
  const [zvn, setZvn] = useState<boolean>(false);
  const [notebook, setNotebook] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [exporting, setExporting] = useState<'pdf' | 'xlsx' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<SectionId>('fitosanitarios');

  const loadNotebook = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await cuadernoApi.getCampaign(campaign, zvn);
      setNotebook(data);
    } catch (err: any) {
      setError(err?.error || err?.message || t('notebook.loadError'));
    } finally {
      setLoading(false);
    }
  }, [campaign, zvn, t]);

  useEffect(() => {
    loadNotebook();
  }, [loadNotebook]);

  const handleExport = async (fmt: 'pdf' | 'xlsx') => {
    setExporting(fmt);
    setError(null);
    try {
      await cuadernoApi.downloadExport(campaign, fmt, zvn);
    } catch (err: any) {
      setError(err?.error || err?.message || t('notebook.exportError'));
    } finally {
      setExporting(null);
    }
  };

  const res = notebook?.resumen || {};
  const incidencias: any[] = notebook?.incidencias || [];
  const planesFast: Record<string, any> = notebook?.planes_abonado_fast || {};

  return (
    <div className="space-y-4">
      {/* Single-source-of-truth info banner */}
      <div className="bg-cyan-50 border border-cyan-200 rounded-lg p-3 text-xs text-cyan-800 flex items-start gap-2">
        <ShieldCheck className="h-4 w-4 text-cyan-600 mt-0.5 flex-shrink-0" />
        <span>{t('notebook.singleSourceNotice')}</span>
      </div>

      {/* Controls: campaign selector, ZVN toggle, refresh, export */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white border border-gray-200 rounded-lg p-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-700">{t('notebook.campaign')}</label>
            <select
              value={campaign}
              onChange={(e) => setCampaign(Number(e.target.value))}
              className="border border-gray-300 rounded px-2.5 py-1.5 text-sm bg-white"
            >
              {years.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          <label className="flex items-center gap-1.5 text-xs text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={zvn}
              onChange={(e) => setZvn(e.target.checked)}
              className="rounded border-gray-300"
            />
            {t('notebook.zvnToggle')}
          </label>

          <button
            type="button"
            onClick={loadNotebook}
            disabled={loading}
            className="px-2.5 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-50 flex items-center gap-1 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            {t('notebook.refresh')}
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleExport('pdf')}
            disabled={loading || exporting !== null}
            className="px-3 py-1.5 text-xs font-medium bg-cyan-700 text-white rounded hover:bg-cyan-800 flex items-center gap-1.5 disabled:opacity-50"
          >
            {exporting === 'pdf' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            {t('notebook.exportPdf')}
          </button>
          <button
            type="button"
            onClick={() => handleExport('xlsx')}
            disabled={loading || exporting !== null}
            className="px-3 py-1.5 text-xs font-medium bg-emerald-700 text-white rounded hover:bg-emerald-800 flex items-center gap-1.5 disabled:opacity-50"
          >
            {exporting === 'xlsx' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileSpreadsheet className="h-3.5 w-3.5" />}
            {t('notebook.exportXlsx')}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="flex justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-cyan-700" />
        </div>
      )}

      {!loading && notebook && (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            <div className="bg-white border border-gray-200 rounded-lg p-2.5">
              <div className="text-[11px] text-gray-500">{t('notebook.kpiParcels')}</div>
              <div className="text-base font-bold text-gray-900">
                {res.total_parcelas ?? 0} <span className="text-xs font-normal text-gray-500">({res.superficie_total_ha ?? 0} ha)</span>
              </div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-2.5">
              <div className="text-[11px] text-gray-500">{t('notebook.kpiSpraying')}</div>
              <div className="text-base font-bold text-gray-900">{res.tratamientos ?? 0}</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-2.5">
              <div className="text-[11px] text-gray-500">{t('notebook.kpiFertilization')}</div>
              <div className="text-base font-bold text-gray-900">{res.fertilizaciones ?? 0}</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-2.5">
              <div className="text-[11px] text-gray-500">{t('notebook.kpiIrrigation')}</div>
              <div className="text-base font-bold text-gray-900">{res.riegos ?? 0}</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-2.5">
              <div className="text-[11px] text-gray-500">{t('notebook.kpiFastPlans')}</div>
              <div className="text-base font-bold text-cyan-700">{res.planes_fast_firmados ?? 0}</div>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-2.5">
              <div className="text-[11px] text-gray-500">{t('notebook.kpiIssues')}</div>
              <div className="text-base font-bold flex items-center gap-2">
                <span className={(res.errores_inspeccion ?? 0) > 0 ? 'text-red-600' : 'text-emerald-600'}>
                  {res.errores_inspeccion ?? 0} E
                </span>
                <span className="text-amber-600 text-xs">{res.advertencias_inspeccion ?? 0} W</span>
              </div>
            </div>
          </div>

          {/* Section pills */}
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                ['fitosanitarios', t('notebook.secSpraying'), (notebook.tratamientos_fitosanitarios || []).length],
                ['fertilizacion', t('notebook.secFertilization'), (notebook.fertilizaciones || []).length],
                ['riegos', t('notebook.secIrrigation'), (notebook.riegos || []).length],
                ['labores', t('notebook.secTillageHarvest'), (notebook.siembras_y_labores || []).length + (notebook.cosechas || []).length],
                ['parcelas', t('notebook.secParcels'), (notebook.parcelas || []).length],
                ['incidencias', t('notebook.secIssues'), incidencias.length],
              ] as [SectionId, string, number][]
            ).map(([id, label, count]) => (
              <button
                key={id}
                type="button"
                onClick={() => setSection(id)}
                className={
                  'px-3 py-1.5 rounded-full text-xs font-medium transition-colors ' +
                  (section === id
                    ? 'bg-cyan-700 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200')
                }
              >
                {label} ({count})
              </button>
            ))}
          </div>

          {/* Section tables */}
          <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
            {section === 'fitosanitarios' && (
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left p-2">{t('notebook.colDate')}</th>
                    <th className="text-left p-2">{t('notebook.colParcel')}</th>
                    <th className="text-left p-2">{t('notebook.colProduct')}</th>
                    <th className="text-left p-2">{t('notebook.colRegNo')}</th>
                    <th className="text-left p-2">{t('notebook.colDose')}</th>
                    <th className="text-left p-2">{t('notebook.colPest')}</th>
                    <th className="text-left p-2">ROMA / ROPO</th>
                  </tr>
                </thead>
                <tbody>
                  {(notebook.tratamientos_fitosanitarios || []).length === 0 ? (
                    <tr><td colSpan={7} className="p-4 text-center text-gray-400">{t('common.noData')}</td></tr>
                  ) : (
                    (notebook.tratamientos_fitosanitarios || []).map((row: any, i: number) => (
                      <tr key={row.operation_id || i} className="border-b hover:bg-gray-50">
                        <td className="p-2 whitespace-nowrap">{row.fecha}</td>
                        <td className="p-2">{row.parcela_nombre}</td>
                        <td className="p-2 font-medium">{row.producto}</td>
                        <td className="p-2 font-mono">{row.numero_registro || '—'}</td>
                        <td className="p-2">{row.dosis != null ? `${row.dosis} ${row.unidad_dosis}` : '—'}</td>
                        <td className="p-2">{row.plaga_objeto || '—'}</td>
                        <td className="p-2 font-mono">{[row.equipo_roma, row.aplicador_ropo].filter(Boolean).join(' · ') || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}

            {section === 'fertilizacion' && (
              <div className="space-y-3 p-2">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="text-left p-2">{t('notebook.colDate')}</th>
                      <th className="text-left p-2">{t('notebook.colParcel')}</th>
                      <th className="text-left p-2">{t('notebook.colProduct')}</th>
                      <th className="text-left p-2">{t('notebook.colDose')}</th>
                      <th className="text-left p-2">N / P₂O₅ / K₂O (kg/ha)</th>
                      <th className="text-left p-2">{t('notebook.colIncorporation')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(notebook.fertilizaciones || []).length === 0 ? (
                      <tr><td colSpan={6} className="p-4 text-center text-gray-400">{t('common.noData')}</td></tr>
                    ) : (
                      (notebook.fertilizaciones || []).map((row: any, i: number) => (
                        <tr key={row.operation_id || i} className="border-b hover:bg-gray-50">
                          <td className="p-2 whitespace-nowrap">{row.fecha}</td>
                          <td className="p-2">{row.parcela_nombre}</td>
                          <td className="p-2 font-medium">
                            {row.producto}{' '}
                            {row.organico && <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded">Org.</span>}
                          </td>
                          <td className="p-2">{row.dosis_kg_ha} kg/ha</td>
                          <td className="p-2 font-mono">
                            {row.n_aplicado_kg_ha} / {row.p2o5_aplicado_kg_ha} / {row.k2o_aplicado_kg_ha}
                          </td>
                          <td className="p-2">{row.metodo_incorporacion || '—'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>

                {Object.keys(planesFast).length > 0 && (
                  <div className="bg-emerald-50 border border-emerald-200 rounded p-2.5 text-xs space-y-1">
                    <div className="font-semibold text-emerald-900">{t('notebook.fastPlansTitle')}</div>
                    {Object.entries(planesFast).map(([pid, plan]: [string, any]) => (
                      <div key={pid} className="text-emerald-800 flex flex-wrap gap-2">
                        <span className="font-medium">{pid.split(':').pop()}</span>
                        <span>v{plan.version}</span>
                        <span>{plan.signature?.name || ''}</span>
                        <span className="font-mono text-[11px] text-emerald-700">SHA-256: {(plan.snapshot_sha256 || '').slice(0, 14)}…</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {section === 'riegos' && (
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left p-2">{t('notebook.colDate')}</th>
                    <th className="text-left p-2">{t('notebook.colParcel')}</th>
                    <th className="text-left p-2">{t('notebook.colVolume')}</th>
                    <th className="text-left p-2">{t('notebook.colSystem')}</th>
                    <th className="text-left p-2">{t('notebook.colSource')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(notebook.riegos || []).length === 0 ? (
                    <tr><td colSpan={5} className="p-4 text-center text-gray-400">{t('common.noData')}</td></tr>
                  ) : (
                    (notebook.riegos || []).map((row: any, i: number) => (
                      <tr key={row.operation_id || i} className="border-b hover:bg-gray-50">
                        <td className="p-2 whitespace-nowrap">{row.fecha}</td>
                        <td className="p-2">{row.parcela_nombre}</td>
                        <td className="p-2">{row.volumen_m3_ha} m³/ha</td>
                        <td className="p-2">{row.sistema_riego || '—'}</td>
                        <td className="p-2">{row.origen_dato}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}

            {section === 'labores' && (
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left p-2">{t('notebook.colDate')}</th>
                    <th className="text-left p-2">{t('notebook.colParcel')}</th>
                    <th className="text-left p-2">{t('notebook.colType')}</th>
                    <th className="text-left p-2">{t('notebook.colDetail')}</th>
                    <th className="text-left p-2">{t('notebook.colAmount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {[...(notebook.siembras_y_labores || []), ...(notebook.cosechas || [])].length === 0 ? (
                    <tr><td colSpan={5} className="p-4 text-center text-gray-400">{t('common.noData')}</td></tr>
                  ) : (
                    [...(notebook.siembras_y_labores || []), ...(notebook.cosechas || [])].map((row: any, i: number) => (
                      <tr key={row.operation_id || i} className="border-b hover:bg-gray-50">
                        <td className="p-2 whitespace-nowrap">{row.fecha}</td>
                        <td className="p-2">{row.parcela_nombre}</td>
                        <td className="p-2">{row.tipo}</td>
                        <td className="p-2">{row.detalle || row.cultivo || '—'}</td>
                        <td className="p-2">
                          {row.cantidad_kg != null
                            ? `${row.cantidad_kg} kg`
                            : row.dosis_siembra != null
                              ? `${row.dosis_siembra} kg/ha`
                              : row.profundidad_cm != null
                                ? `${row.profundidad_cm} cm`
                                : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}

            {section === 'parcelas' && (
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left p-2">{t('notebook.colParcel')}</th>
                    <th className="text-left p-2">SIGPAC</th>
                    <th className="text-left p-2">{t('notebook.colCrop')}</th>
                    <th className="text-left p-2">{t('notebook.colArea')}</th>
                    <th className="text-left p-2">{t('notebook.colSystem')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(notebook.parcelas || []).length === 0 ? (
                    <tr><td colSpan={5} className="p-4 text-center text-gray-400">{t('common.noData')}</td></tr>
                  ) : (
                    (notebook.parcelas || []).map((row: any, i: number) => (
                      <tr key={row.id || i} className="border-b hover:bg-gray-50">
                        <td className="p-2 font-medium">{row.nombre}</td>
                        <td className="p-2 font-mono">{row.sigpac || '—'}</td>
                        <td className="p-2">{row.cultivo || '—'}</td>
                        <td className="p-2">{row.superficie_ha} ha</td>
                        <td className="p-2">{row.riego || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}

            {section === 'incidencias' && (
              <div className="p-3 space-y-2">
                {incidencias.length === 0 ? (
                  <div className="flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded p-3">
                    <CheckCircle className="h-4 w-4 text-emerald-600" />
                    <span>{t('notebook.noIssues')}</span>
                  </div>
                ) : (
                  incidencias.map((inc: any, i: number) => {
                    const isErr = inc.severidad === 'error';
                    return (
                      <div
                        key={i}
                        className={
                          'rounded p-2.5 text-xs flex items-start gap-2 border ' +
                          (isErr
                            ? 'bg-red-50 border-red-200 text-red-800'
                            : 'bg-amber-50 border-amber-200 text-amber-800')
                        }
                      >
                        {isErr ? (
                          <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
                        )}
                        <div>
                          <span className="font-semibold">{inc.codigo || inc.rule}: </span>
                          <span>{inc.mensaje || inc.message}</span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
