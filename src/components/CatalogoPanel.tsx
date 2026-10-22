import React, { useState, useEffect, useCallback } from 'react';
import { Search, Loader2, AlertCircle } from 'lucide-react';
import { catalogosApi } from '../services/cueApi';

export const CatalogoPanel: React.FC = () => {
  // ROPO search
  const [ropoTerm, setRopoTerm] = useState('');
  const [ropoResults, setRopoResults] = useState<any[]>([]);
  const [ropoLoading, setRopoLoading] = useState(false);
  const [ropoError, setRopoError] = useState<string | null>(null);
  const [ropoSearched, setRopoSearched] = useState(false);

  // Fertilizer search
  const [fertTerm, setFertTerm] = useState('');
  const [fertResults, setFertResults] = useState<any[]>([]);
  const [fertLoading, setFertLoading] = useState(false);
  const [fertError, setFertError] = useState<string | null>(null);
  const [fertSearched, setFertSearched] = useState(false);

  const searchRopo = useCallback(async () => {
    if (!ropoTerm.trim()) return;
    setRopoLoading(true);
    setRopoError(null);
    setRopoSearched(true);
    try {
      const data = await catalogosApi.productosRopo({ nombre: ropoTerm.trim() });
      setRopoResults(Array.isArray(data) ? data : data?.data || []);
    } catch (err: any) {
      setRopoError(err?.error || err?.message || 'Error al buscar productos ROPO');
      setRopoResults([]);
    } finally {
      setRopoLoading(false);
    }
  }, [ropoTerm]);

  const searchFert = useCallback(async () => {
    if (!fertTerm.trim()) return;
    setFertLoading(true);
    setFertError(null);
    setFertSearched(true);
    try {
      const data = await catalogosApi.productosFertilizantes({ nombre: fertTerm.trim() });
      setFertResults(Array.isArray(data) ? data : data?.data || []);
    } catch (err: any) {
      setFertError(err?.error || err?.message || 'Error al buscar fertilizantes');
      setFertResults([]);
    } finally {
      setFertLoading(false);
    }
  }, [fertTerm]);

  // Auto-search on enter
  const handleRopoKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); searchRopo(); } };
  const handleFertKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter') { e.preventDefault(); searchFert(); } };

  const renderRopoTable = () => {
    if (ropoLoading) {
      return React.createElement('div', { className: 'flex justify-center py-6' },
        React.createElement(Loader2, { className: 'h-5 w-5 animate-spin text-green-600' })
      );
    }
    if (ropoError) {
      return React.createElement('div', { className: 'bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2' },
        React.createElement(AlertCircle, { className: 'h-4 w-4 text-red-500 flex-shrink-0' }),
        React.createElement('span', { className: 'text-red-700 text-xs' }, ropoError)
      );
    }
    if (ropoSearched && ropoResults.length === 0) {
      return React.createElement('div', { className: 'text-center py-6 text-gray-400 text-sm' }, 'No se encontraron productos ROPO');
    }
    if (ropoResults.length === 0) {
      return null;
    }
    return React.createElement('div', { className: 'overflow-x-auto' },
      React.createElement('table', { className: 'w-full text-sm' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'bg-gray-50' },
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'Nº Registro'),
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'Nombre Comercial'),
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'Sustancia Activa'),
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'Estado')
          )
        ),
        React.createElement('tbody', null,
          ropoResults.map((prod: any, i: number) =>
            React.createElement('tr', {
              key: prod.numero_registro || prod.id || i,
              className: 'border-b border-gray-100 hover:bg-gray-50',
            },
              React.createElement('td', { className: 'px-3 py-2 font-mono text-xs' }, prod.numero_registro || '—'),
              React.createElement('td', { className: 'px-3 py-2' }, prod.nombre_comercial || prod.nombre || '—'),
              React.createElement('td', { className: 'px-3 py-2 text-gray-500' }, prod.sustancia_activa || '—'),
              React.createElement('td', { className: 'px-3 py-2' },
                React.createElement('span', {
                  className: 'inline-block px-2 py-0.5 rounded text-xs font-medium ' +
                    (prod.estado === 'Autorizado' ? 'bg-green-100 text-green-700' :
                     prod.estado === 'Revocado' ? 'bg-red-100 text-red-700' :
                     'bg-yellow-100 text-yellow-700')
                }, prod.estado || '—')
              )
            )
          )
        )
      )
    );
  };

  const renderFertTable = () => {
    if (fertLoading) {
      return React.createElement('div', { className: 'flex justify-center py-6' },
        React.createElement(Loader2, { className: 'h-5 w-5 animate-spin text-green-600' })
      );
    }
    if (fertError) {
      return React.createElement('div', { className: 'bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2' },
        React.createElement(AlertCircle, { className: 'h-4 w-4 text-red-500 flex-shrink-0' }),
        React.createElement('span', { className: 'text-red-700 text-xs' }, fertError)
      );
    }
    if (fertSearched && fertResults.length === 0) {
      return React.createElement('div', { className: 'text-center py-6 text-gray-400 text-sm' }, 'No se encontraron fertilizantes');
    }
    if (fertResults.length === 0) {
      return null;
    }
    return React.createElement('div', { className: 'overflow-x-auto' },
      React.createElement('table', { className: 'w-full text-sm' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'bg-gray-50' },
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'Nº Registro'),
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'Nombre Comercial'),
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'NPK'),
            React.createElement('th', { className: 'text-left px-3 py-2 font-medium text-gray-600 text-xs uppercase' }, 'Estado')
          )
        ),
        React.createElement('tbody', null,
          fertResults.map((prod: any, i: number) =>
            React.createElement('tr', {
              key: prod.numero_registro || prod.id || i,
              className: 'border-b border-gray-100 hover:bg-gray-50',
            },
              React.createElement('td', { className: 'px-3 py-2 font-mono text-xs' }, prod.numero_registro || '—'),
              React.createElement('td', { className: 'px-3 py-2' }, prod.nombre_comercial || prod.nombre || '—'),
              React.createElement('td', { className: 'px-3 py-2 text-gray-500' }, prod.npk || prod.formulacion || '—'),
              React.createElement('td', { className: 'px-3 py-2' },
                React.createElement('span', {
                  className: 'inline-block px-2 py-0.5 rounded text-xs font-medium ' +
                    (prod.estado === 'Autorizado' ? 'bg-green-100 text-green-700' :
                     prod.estado === 'Revocado' ? 'bg-red-100 text-red-700' :
                     'bg-yellow-100 text-yellow-700')
                }, prod.estado || '—')
              )
            )
          )
        )
      )
    );
  };

  return React.createElement('div', { className: 'space-y-6' },
    // Section 1: ROPO Products
    React.createElement('div', { className: 'bg-white rounded-lg shadow p-4' },
      React.createElement('h3', { className: 'text-md font-semibold text-gray-900 mb-3' }, 'Productos ROPO (Fitosanitarios)'),
      React.createElement('div', { className: 'flex gap-2 mb-3' },
        React.createElement('div', { className: 'relative flex-1' },
          React.createElement(Search, { className: 'absolute left-2 top-2.5 h-4 w-4 text-gray-400' }),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded pl-8 pr-3 py-2 w-full',
            placeholder: 'Buscar por nombre, ingrediente o nº registro...',
            value: ropoTerm,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setRopoTerm(e.target.value),
            onKeyDown: handleRopoKeyDown,
          })
        ),
        React.createElement('button', {
          onClick: searchRopo,
          className: 'bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm',
        }, 'Buscar')
      ),
      renderRopoTable()
    ),

    // Section 2: Fertilizer Products
    React.createElement('div', { className: 'bg-white rounded-lg shadow p-4' },
      React.createElement('h3', { className: 'text-md font-semibold text-gray-900 mb-3' }, 'Productos Fertilizantes'),
      React.createElement('div', { className: 'flex gap-2 mb-3' },
        React.createElement('div', { className: 'relative flex-1' },
          React.createElement(Search, { className: 'absolute left-2 top-2.5 h-4 w-4 text-gray-400' }),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded pl-8 pr-3 py-2 w-full',
            placeholder: 'Buscar por nombre o nº registro...',
            value: fertTerm,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setFertTerm(e.target.value),
            onKeyDown: handleFertKeyDown,
          })
        ),
        React.createElement('button', {
          onClick: searchFert,
          className: 'bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm',
        }, 'Buscar')
      ),
      renderFertTable()
    )
  );
};
