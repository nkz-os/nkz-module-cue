import React, { useState, useEffect, useCallback } from 'react';
import { Search, Loader2, AlertCircle, Plus } from 'lucide-react';
import { tratamientosApi } from '../services/cueApi';

interface TratamientoListProps {
  onSelect: (tratamiento: any) => void;
  onNew: () => void;
}

export const TratamientoList: React.FC<TratamientoListProps> = ({ onSelect, onNew }) => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchParcela, setSearchParcela] = useState('');
  const [showDeleted, setShowDeleted] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const filters: Record<string, string> = {};
      if (searchParcela.trim()) filters.parcela_id = searchParcela.trim();
      if (showDeleted) filters.incluir_inactivos = 'true';
      const data = await tratamientosApi.list(filters);
      setItems(Array.isArray(data) ? data : data?.data || []);
    } catch (err: any) {
      setError(err?.error || err?.message || 'Error al cargar tratamientos');
    } finally {
      setLoading(false);
    }
  }, [searchParcela, showDeleted, refreshKey]);

  const handleRestore = (item: any) => {
    const id = item.id || item.orion_entity_id;
    tratamientosApi.restore(id)
      .then(() => setRefreshKey(k => k + 1))
      .catch((err: any) => alert('Error: ' + (err.error || 'No se pudo restaurar')));
  };

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const formatDate = (d: string) => {
    if (!d) return '';
    try { return new Date(d).toLocaleDateString('es-ES'); } catch { return d; }
  };

  return React.createElement('div', { className: 'space-y-4' },
    // Search and action bar
    React.createElement('div', { className: 'flex gap-2 items-end flex-wrap' },
      React.createElement('div', { className: 'flex-1 min-w-[200px]' },
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Filtrar por parcela'),
        React.createElement('div', { className: 'relative' },
          React.createElement(Search, { className: 'absolute left-2 top-2.5 h-4 w-4 text-gray-400' }),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded pl-8 pr-3 py-2 w-full',
            placeholder: 'ID de parcela...',
            value: searchParcela,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => setSearchParcela(e.target.value),
          })
        )
      ),
      React.createElement('button', {
        className: 'bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 flex items-center gap-1 h-[38px]',
        onClick: onNew,
      },
        React.createElement(Plus, { className: 'h-4 w-4' }),
        React.createElement('span', null, 'Nuevo')
      ),
      React.createElement('button', {
        onClick: () => setShowDeleted(!showDeleted),
        className: `px-3 py-1 text-xs rounded h-[38px] ${showDeleted ? 'bg-red-100 text-red-700 border border-red-300' : 'bg-gray-100 text-gray-600 border border-gray-200'}`,
      }, showDeleted ? 'Papelera' : 'Ver papelera')
    ),

    // Content
    loading
      ? React.createElement('div', { className: 'flex justify-center py-8' },
          React.createElement(Loader2, { className: 'h-6 w-6 animate-spin text-green-600' })
        )
      : error
        ? React.createElement('div', { className: 'bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2' },
            React.createElement(AlertCircle, { className: 'h-5 w-5 text-red-500 flex-shrink-0' }),
            React.createElement('span', { className: 'text-red-700 text-sm' }, error)
          )
        : items.length === 0
          ? React.createElement('div', { className: 'text-center py-12 text-gray-400' },
              React.createElement('p', { className: 'text-sm' }, 'No hay tratamientos registrados')
            )
          : React.createElement('div', { className: 'space-y-2 max-h-[500px] overflow-y-auto' },
              items.map((item: any) => {
                const isInactive = item.isActive === false || item.is_active === false;
                return React.createElement('div', {
                  key: item.id || item.entityId,
                  className: `${isInactive ? 'bg-red-50 border-red-200' : 'bg-white border-gray-100'} rounded-lg shadow p-4 cursor-pointer hover:shadow-md transition-shadow border`,
                  onClick: () => onSelect(item),
                },
                  React.createElement('div', { className: 'flex justify-between items-start' },
                    React.createElement('h3', { className: 'font-semibold text-gray-900' },
                      item.producto_ropo || 'Tratamiento'
                    ),
                    React.createElement('div', { className: 'flex items-center gap-2' },
                      isInactive
                        ? React.createElement('span', { className: 'text-xs text-red-500 font-medium bg-red-100 px-2 py-0.5 rounded' }, 'Inactivo')
                        : null,
                      item.fecha
                        ? React.createElement('span', { className: 'text-xs text-gray-500' }, formatDate(item.fecha))
                        : null
                    )
                  ),
                  React.createElement('div', { className: 'text-sm text-gray-500 mt-1' },
                    [item.parcela_id ? `Parcela: ${item.parcela_id}` : null, item.plaga ? `Plaga: ${item.plaga}` : null].filter(Boolean).join(' | ')
                  ),
                  item.dosis
                    ? React.createElement('div', { className: 'text-xs text-gray-400 mt-1' },
                        'Dosis: ', item.dosis, item.unidad_dosis ? ` ${item.unidad_dosis}` : ''
                      )
                    : null,
                  isInactive
                    ? React.createElement('button', {
                        onClick: (e: React.MouseEvent) => { e.stopPropagation(); handleRestore(item); },
                        className: 'text-xs text-green-600 hover:text-green-800 underline mt-2',
                      }, 'Restaurar')
                    : null
                );
              })
            )
  );
};
