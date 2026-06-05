import React, { useState, useEffect } from 'react';

interface GestorDashboardProps {
  onSelectSubmission?: (submission: any) => void;
  onManageFarm?: () => void;
}

export const GestorDashboard: React.FC<GestorDashboardProps> = ({ onSelectSubmission, onManageFarm }) => {
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [estadoFilter, setEstadoFilter] = useState('');
  const [farmerFilter, setFarmerFilter] = useState('');

  const fetchSubmissions = () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (estadoFilter) params.set('estado', estadoFilter);
    if (farmerFilter) params.set('farmer_tenant', farmerFilter);

    const url = `${(window as any).__ENV__?.VITE_API_URL || 'https://nkz.robotika.cloud'}/api/modules/cue/gestor/submissions?${params}`;
    fetch(url, { credentials: 'include' })
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => { setSubmissions(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  };

  useEffect(() => { fetchSubmissions(); }, [estadoFilter, farmerFilter]);

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'aceptado': return 'bg-green-100 text-green-700';
      case 'rechazado_con_errores': return 'bg-red-100 text-red-700';
      case 'pendiente': return 'bg-yellow-100 text-yellow-700';
      case 'procesando': return 'bg-blue-100 text-blue-700';
      case 'firmado': return 'bg-purple-100 text-purple-700';
      case 'borrador': case 'validado': return 'bg-gray-100 text-gray-600';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  // Loading state
  if (loading && submissions.length === 0) {
    return React.createElement('div', { className: 'p-4 text-center text-gray-400 text-sm' }, 'Cargando envíos...');
  }

  // Error state
  if (error) {
    return React.createElement('div', { className: 'p-4' },
      React.createElement('div', { className: 'bg-red-50 text-red-600 p-3 rounded text-sm' }, 'Error: ' + error),
      React.createElement('button', {
        onClick: fetchSubmissions,
        className: 'mt-2 text-sm text-blue-600 hover:underline'
      }, 'Reintentar')
    );
  }

  return React.createElement('div', { className: 'space-y-4' },
    // Header
    React.createElement('div', { className: 'flex items-center justify-between' },
      React.createElement('div', { className: 'flex items-center gap-3' },
        React.createElement('h3', { className: 'text-lg font-bold text-gray-900' }, 'Envíos a IUWS'),
        React.createElement('span', { className: 'text-sm text-gray-500' }, submissions.length + ' envíos')
      ),
      React.createElement('button', {
        onClick: function () { onManageFarm?.(); },
        className: 'px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 font-medium'
      }, 'Gestionar explotación')
    ),

    // Filters
    React.createElement('div', { className: 'flex gap-2' },
      React.createElement('select', {
        value: estadoFilter,
        onChange: (e) => setEstadoFilter(e.target.value),
        className: 'border border-gray-300 rounded px-2 py-1 text-xs'
      },
        React.createElement('option', { value: '' }, 'Todos los estados'),
        React.createElement('option', { value: 'pendiente' }, 'Pendiente'),
        React.createElement('option', { value: 'procesando' }, 'Procesando'),
        React.createElement('option', { value: 'firmado' }, 'Firmado'),
        React.createElement('option', { value: 'aceptado' }, 'Aceptado'),
        React.createElement('option', { value: 'rechazado_con_errores' }, 'Rechazado'),
        React.createElement('option', { value: 'borrador' }, 'Borrador'),
        React.createElement('option', { value: 'validado' }, 'Validado')
      ),
      React.createElement('button', {
        onClick: fetchSubmissions,
        className: 'px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300'
      }, 'Actualizar')
    ),

    // Empty state
    !loading && submissions.length === 0 &&
      React.createElement('div', { className: 'p-4 text-center text-gray-400 text-sm' },
        'No hay envíos registrados para sus explotaciones autorizadas'
      ),

    // Table
    submissions.length > 0 && React.createElement('div', { className: 'overflow-x-auto' },
      React.createElement('table', { className: 'w-full text-sm' },
        React.createElement('thead', null,
          React.createElement('tr', { className: 'border-b bg-gray-50' },
            React.createElement('th', { className: 'text-left p-2 font-medium text-gray-600' }, 'Explotación'),
            React.createElement('th', { className: 'text-left p-2 font-medium text-gray-600' }, 'Fecha'),
            React.createElement('th', { className: 'text-left p-2 font-medium text-gray-600' }, 'Tipo'),
            React.createElement('th', { className: 'text-left p-2 font-medium text-gray-600' }, 'Estado'),
            React.createElement('th', { className: 'text-left p-2 font-medium text-gray-600' }, 'Ticket')
          )
        ),
        React.createElement('tbody', null,
          submissions.map(function (s: any, i: number) {
            return React.createElement('tr', {
              key: s.id || i,
              className: 'border-b hover:bg-gray-50 cursor-pointer',
              onClick: function () { onSelectSubmission?.(s); }
            },
              React.createElement('td', { className: 'p-2' },
                React.createElement('div', { className: 'font-medium' }, s.farmer_name || s.tenant_id || 'Sin nombre'),
                React.createElement('div', { className: 'text-xs text-gray-400' }, s.tenant_id)
              ),
              React.createElement('td', { className: 'p-2 text-xs' },
                s.fecha_presentacion ? new Date(s.fecha_presentacion).toLocaleDateString('es-ES') : (s.created_at ? new Date(s.created_at).toLocaleDateString('es-ES') : '—')
              ),
              React.createElement('td', { className: 'p-2 text-xs' }, s.payload_type || 'Alta'),
              React.createElement('td', { className: 'p-2' },
                React.createElement('span', { className: 'px-2 py-0.5 rounded-full text-xs font-medium ' + getEstadoColor(s.estado) }, s.estado)
              ),
              React.createElement('td', { className: 'p-2 text-xs font-mono' }, s.id_ticket || '—')
            );
          })
        )
      )
    )
  );
};
