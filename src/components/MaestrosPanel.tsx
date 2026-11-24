import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, Trash2, AlertCircle } from 'lucide-react';
import { maestrosApi } from '../services/cueApi';

type SubTab = 'roma' | 'ropo';

export const MaestrosPanel: React.FC = () => {
  const { t } = useTranslation('cue');
  const [subTab, setSubTab] = useState<SubTab>('roma');
  const [equipos, setEquipos] = useState<any[]>([]);
  const [aplicadores, setAplicadores] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ROMA form
  const [eqNombre, setEqNombre] = useState('');
  const [eqRoma, setEqRoma] = useState('');
  const [eqTipo, setEqTipo] = useState('pulverizador_hidraulico');
  const [eqIteaf, setEqIteaf] = useState('');

  // ROPO form
  const [apNombre, setApNombre] = useState('');
  const [apNif, setApNif] = useState('');
  const [apCarne, setApCarne] = useState('');
  const [apNivel, setApNivel] = useState('cualificado');
  const [apCaducidad, setApCaducidad] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [eq, ap] = await Promise.all([
        maestrosApi.listEquipos(),
        maestrosApi.listAplicadores(),
      ]);
      setEquipos(Array.isArray(eq) ? eq : []);
      setAplicadores(Array.isArray(ap) ? ap : []);
    } catch (err: any) {
      setError(err?.error || err?.message || t('common.error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleAddEquipo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!eqNombre.trim() || !eqRoma.trim()) return;
    setError(null);
    try {
      await maestrosApi.createEquipo({
        nombre: eqNombre.trim(),
        numero_roma: eqRoma.trim(),
        tipo_equipo: eqTipo,
        fecha_proxima_iteaf: eqIteaf || undefined,
      });
      setEqNombre('');
      setEqRoma('');
      setEqIteaf('');
      loadAll();
    } catch (err: any) {
      setError(err?.error || t('common.error'));
    }
  };

  const handleAddAplicador = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apNombre.trim() || !apCarne.trim()) return;
    setError(null);
    try {
      await maestrosApi.createAplicador({
        nombre: apNombre.trim(),
        nif: apNif.trim() || undefined,
        numero_carne_ropo: apCarne.trim(),
        nivel_capacitacion: apNivel,
        fecha_caducidad: apCaducidad || undefined,
      });
      setApNombre('');
      setApNif('');
      setApCarne('');
      setApCaducidad('');
      loadAll();
    } catch (err: any) {
      setError(err?.error || t('common.error'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setSubTab('roma')}
          className={
            'px-3 py-1.5 rounded text-xs font-medium ' +
            (subTab === 'roma' ? 'bg-cyan-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200')
          }
        >
          {t('masters.romaTab')} ({equipos.length})
        </button>
        <button
          type="button"
          onClick={() => setSubTab('ropo')}
          className={
            'px-3 py-1.5 rounded text-xs font-medium ' +
            (subTab === 'ropo' ? 'bg-cyan-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200')
          }
        >
          {t('masters.ropoTab')} ({aplicadores.length})
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-2.5 flex items-center gap-2 text-xs text-red-700">
          <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="flex justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-cyan-700" />
        </div>
      )}

      {!loading && subTab === 'roma' && (
        <div className="space-y-4">
          <form onSubmit={handleAddEquipo} className="bg-gray-50 border border-gray-200 rounded-lg p-3 grid grid-cols-1 sm:grid-cols-5 gap-2">
            <input
              type="text"
              value={eqNombre}
              onChange={(e) => setEqNombre(e.target.value)}
              placeholder={t('masters.equipmentName')}
              className="border border-gray-300 rounded px-2.5 py-1.5 text-xs"
              required
            />
            <input
              type="text"
              value={eqRoma}
              onChange={(e) => setEqRoma(e.target.value)}
              placeholder={t('masters.romaNumber')}
              className="border border-gray-300 rounded px-2.5 py-1.5 text-xs"
              required
            />
            <select
              value={eqTipo}
              onChange={(e) => setEqTipo(e.target.value)}
              className="border border-gray-300 rounded px-2 py-1.5 text-xs bg-white"
            >
              <option value="pulverizador_hidraulico">Pulverizador hidráulico</option>
              <option value="atomizador">Atomizador</option>
              <option value="espolvoreador">Espolvoreador</option>
              <option value="abonadora">Abonadora</option>
            </select>
            <input
              type="date"
              value={eqIteaf}
              onChange={(e) => setEqIteaf(e.target.value)}
              title={t('masters.nextIteaf')}
              className="border border-gray-300 rounded px-2 py-1.5 text-xs"
            />
            <button
              type="submit"
              className="px-3 py-1.5 bg-cyan-700 text-white rounded text-xs font-medium hover:bg-cyan-800 flex items-center justify-center gap-1"
            >
              <Plus className="h-3.5 w-3.5" />
              {t('common.create')}
            </button>
          </form>

          <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left p-2">{t('masters.equipmentName')}</th>
                  <th className="text-left p-2">{t('masters.romaNumber')}</th>
                  <th className="text-left p-2">{t('masters.nextIteaf')}</th>
                  <th className="text-left p-2">{t('masters.status')}</th>
                  <th className="p-2 w-10" />
                </tr>
              </thead>
              <tbody>
                {equipos.length === 0 ? (
                  <tr><td colSpan={5} className="p-4 text-center text-gray-400">{t('common.noData')}</td></tr>
                ) : (
                  equipos.map((eq) => (
                    <tr key={eq.id} className="border-b hover:bg-gray-50">
                      <td className="p-2 font-medium">{eq.nombre}</td>
                      <td className="p-2 font-mono">{eq.numero_roma}</td>
                      <td className="p-2">{eq.fecha_proxima_iteaf || '—'}</td>
                      <td className="p-2">
                        {eq.iteaf_vigente === true && (
                          <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{t('masters.valid')}</span>
                        )}
                        {eq.iteaf_vigente === false && (
                          <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700">{t('masters.expired')}</span>
                        )}
                        {eq.iteaf_vigente == null && <span className="text-gray-400">—</span>}
                      </td>
                      <td className="p-2 text-right">
                        <button
                          type="button"
                          onClick={() => maestrosApi.deleteEquipo(eq.id).then(loadAll)}
                          className="text-gray-400 hover:text-red-600 p-1"
                          title={t('common.delete')}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && subTab === 'ropo' && (
        <div className="space-y-4">
          <form onSubmit={handleAddAplicador} className="bg-gray-50 border border-gray-200 rounded-lg p-3 grid grid-cols-1 sm:grid-cols-6 gap-2">
            <input
              type="text"
              value={apNombre}
              onChange={(e) => setApNombre(e.target.value)}
              placeholder={t('masters.personName')}
              className="border border-gray-300 rounded px-2.5 py-1.5 text-xs"
              required
            />
            <input
              type="text"
              value={apNif}
              onChange={(e) => setApNif(e.target.value)}
              placeholder="NIF"
              className="border border-gray-300 rounded px-2.5 py-1.5 text-xs"
            />
            <input
              type="text"
              value={apCarne}
              onChange={(e) => setApCarne(e.target.value)}
              placeholder={t('masters.ropoCard')}
              className="border border-gray-300 rounded px-2.5 py-1.5 text-xs"
              required
            />
            <select
              value={apNivel}
              onChange={(e) => setApNivel(e.target.value)}
              className="border border-gray-300 rounded px-2 py-1.5 text-xs bg-white"
            >
              <option value="basico">Básico</option>
              <option value="cualificado">Cualificado</option>
              <option value="fumigador">Fumigador</option>
              <option value="piloto">Piloto</option>
              <option value="asesor_gip">Asesor GIP</option>
            </select>
            <input
              type="date"
              value={apCaducidad}
              onChange={(e) => setApCaducidad(e.target.value)}
              title={t('masters.expiry')}
              className="border border-gray-300 rounded px-2 py-1.5 text-xs"
            />
            <button
              type="submit"
              className="px-3 py-1.5 bg-cyan-700 text-white rounded text-xs font-medium hover:bg-cyan-800 flex items-center justify-center gap-1"
            >
              <Plus className="h-3.5 w-3.5" />
              {t('common.create')}
            </button>
          </form>

          <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left p-2">{t('masters.personName')}</th>
                  <th className="text-left p-2">NIF</th>
                  <th className="text-left p-2">{t('masters.ropoCard')}</th>
                  <th className="text-left p-2">{t('masters.level')}</th>
                  <th className="text-left p-2">{t('masters.expiry')}</th>
                  <th className="p-2 w-10" />
                </tr>
              </thead>
              <tbody>
                {aplicadores.length === 0 ? (
                  <tr><td colSpan={6} className="p-4 text-center text-gray-400">{t('common.noData')}</td></tr>
                ) : (
                  aplicadores.map((ap) => (
                    <tr key={ap.id} className="border-b hover:bg-gray-50">
                      <td className="p-2 font-medium">{ap.nombre}</td>
                      <td className="p-2 font-mono">{ap.nif || '—'}</td>
                      <td className="p-2 font-mono">{ap.numero_carne_ropo}</td>
                      <td className="p-2">{ap.nivel_capacitacion}</td>
                      <td className="p-2">
                        {ap.fecha_caducidad || '—'}{' '}
                        {ap.carne_vigente === false && (
                          <span className="ml-1 px-1.5 py-0.5 rounded-full bg-red-100 text-red-700">{t('masters.expired')}</span>
                        )}
                      </td>
                      <td className="p-2 text-right">
                        <button
                          type="button"
                          onClick={() => maestrosApi.deleteAplicador(ap.id).then(loadAll)}
                          className="text-gray-400 hover:text-red-600 p-1"
                          title={t('common.delete')}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
