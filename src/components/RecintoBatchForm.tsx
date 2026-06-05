import React, { useState } from 'react';
import { recintosApi } from '../services/cueApi';

interface RecintoBatchFormProps {
  declaracionId: string;
  onSaved: () => void;
}

export const RecintoBatchForm: React.FC<RecintoBatchFormProps> = ({ declaracionId, onSaved }) => {
  const [rows, setRows] = useState([{ referencia_sigpac: '', superficie_admisible_ha: '', geometria: '' }]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const addRow = () => setRows([...rows, { referencia_sigpac: '', superficie_admisible_ha: '', geometria: '' }]);
  const removeRow = (i: number) => setRows(rows.filter((_, idx) => idx !== i));

  const updateRow = (i: number, field: string, value: string) => {
    const updated = [...rows];
    (updated[i] as any)[field] = value;
    setRows(updated);
  };

  const handleSubmit = () => {
    const recintos = rows.map(r => {
      const data: any = {
        declaracion_id: declaracionId,
        referencia_sigpac: r.referencia_sigpac,
        superficie_admisible_ha: parseFloat(r.superficie_admisible_ha) || 0,
      };
      if (r.geometria.trim()) {
        try { data.geometria = JSON.parse(r.geometria); }
        catch { /* invalid JSON, skip */ }
      }
      return data;
    });

    setLoading(true);
    setError(null);
    recintosApi.createBatch(recintos)
      .then(res => { setResult(res); setLoading(false); onSaved(); })
      .catch(err => { setError(err?.error || 'Error en lote'); setLoading(false); });
  };

  // Result state
  if (result && !loading) {
    return React.createElement('div', { className: 'space-y-2' },
      React.createElement('div', { className: 'bg-green-50 text-green-700 p-3 rounded text-sm' },
        'Lote completado: ' + result.created + ' creados, ' + result.errors + ' errores de ' + result.total
      ),
      result.error_details && result.error_details.length > 0 &&
        React.createElement('div', { className: 'bg-red-50 text-red-600 p-2 rounded text-xs' },
          result.error_details.map((e: any, i: number) =>
            React.createElement('div', { key: i }, 'Fila ' + (e.index + 1) + ': ' + e.error)
          )
        ),
      React.createElement('button', {
        onClick: () => { setResult(null); setRows([{ referencia_sigpac: '', superficie_admisible_ha: '', geometria: '' }]); },
        className: 'text-sm text-blue-600 hover:underline',
      }, 'Nuevo lote')
    );
  }

  // Form state
  return React.createElement('div', { className: 'space-y-3' },
    error && React.createElement('div', { className: 'bg-red-50 text-red-600 p-2 rounded text-sm' }, error),

    // Header
    React.createElement('div', { className: 'flex items-center justify-between' },
      React.createElement('span', { className: 'text-sm font-medium' }, rows.length + ' recinto(s)'),
      React.createElement('div', { className: 'space-x-2' },
        React.createElement('button', {
          onClick: addRow,
          className: 'px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700',
        }, '+ Añadir fila'),
        React.createElement('button', {
          onClick: handleSubmit,
          disabled: loading || rows.length === 0,
          className: 'px-3 py-1 text-xs rounded text-white ' + (loading ? 'bg-gray-400' : 'bg-green-600 hover:bg-green-700'),
        }, loading ? 'Creando...' : 'Crear lote')
      )
    ),

    // Table
    React.createElement('div', { className: 'overflow-x-auto' },
      React.createElement('table', { className: 'w-full text-xs' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'border-b' },
            React.createElement('th', { className: 'text-left p-1' }, 'Ref SIGPAC'),
            React.createElement('th', { className: 'text-left p-1' }, 'Sup. Adm. (ha)'),
            React.createElement('th', { className: 'text-left p-1' }, 'GeoJSON'),
            React.createElement('th', { className: 'p-1 w-8' }, '')
          )
        ),
        React.createElement('tbody', null,
          rows.map((r, i) =>
            React.createElement('tr', { key: i, className: 'border-b' },
              React.createElement('td', { className: 'p-1' },
                React.createElement('input', {
                  type: 'text',
                  value: r.referencia_sigpac,
                  onChange: (e) => updateRow(i, 'referencia_sigpac', e.target.value),
                  placeholder: '31:230:0:0:0:243:9003',
                  className: 'border rounded px-1 py-0.5 w-full text-xs',
                })
              ),
              React.createElement('td', { className: 'p-1' },
                React.createElement('input', {
                  type: 'number',
                  step: '0.01',
                  value: r.superficie_admisible_ha,
                  onChange: (e) => updateRow(i, 'superficie_admisible_ha', e.target.value),
                  className: 'border rounded px-1 py-0.5 w-20 text-xs',
                })
              ),
              React.createElement('td', { className: 'p-1' },
                React.createElement('input', {
                  type: 'text',
                  value: r.geometria,
                  onChange: (e) => updateRow(i, 'geometria', e.target.value),
                  placeholder: '{"type":"Polygon",...}',
                  className: 'border rounded px-1 py-0.5 w-full text-xs font-mono',
                })
              ),
              React.createElement('td', { className: 'p-1' },
                rows.length > 1 && React.createElement('button', {
                  onClick: () => removeRow(i),
                  className: 'text-red-500 hover:text-red-700 text-xs',
                }, '✕')
              )
            )
          )
        )
      )
    )
  );
};
