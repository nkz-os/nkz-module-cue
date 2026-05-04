import React, { useState, useEffect } from 'react';

interface GestorFarmSelectorProps {
  onSelectFarm: (tenantId: string, farmerName: string) => void;
}

export const GestorFarmSelector: React.FC<GestorFarmSelectorProps> = ({ onSelectFarm }) => {
  const [tenants, setTenants] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState('');

  useEffect(() => {
    const apiUrl = (window as any).__ENV__?.VITE_API_URL || 'https://nkz.robotika.cloud';
    fetch(apiUrl + '/api/modules/cue/gestor/tenants', { credentials: 'include' })
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => { setTenants(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, []);

  const handleSelect = (e: any) => {
    const idx = e.target.selectedIndex;
    const tenantId = e.target.value;
    const farmerName = idx > 0 && tenants[idx - 1] ? (tenants[idx - 1].farmer_name || tenants[idx - 1].farmer_tenant) : tenantId;
    setSelected(tenantId);
    if (tenantId) onSelectFarm(tenantId, farmerName);
  };

  if (loading) {
    return React.createElement('div', { className: 'p-4 text-center text-gray-400 text-sm' }, 'Cargando explotaciones...');
  }

  if (error) {
    return React.createElement('div', { className: 'p-4 bg-red-50 text-red-600 text-sm rounded' }, 'Error: ' + error);
  }

  if (tenants.length === 0) {
    return React.createElement('div', { className: 'p-4 text-center' },
      React.createElement('div', { className: 'text-gray-400 text-sm mb-2' }, 'No tiene explotaciones autorizadas'),
      React.createElement('div', { className: 'text-gray-400 text-xs' }, 'Solicite a sus clientes que le autoricen desde la pestaña "Gestoría"')
    );
  }

  return React.createElement('div', { className: 'p-2' },
    React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Seleccionar explotación'),
    React.createElement('select', {
      value: selected,
      onChange: handleSelect,
      className: 'border border-gray-300 rounded px-3 py-2 w-full text-sm'
    },
      React.createElement('option', { value: '' }, '-- Seleccionar --'),
      tenants.map(function (t: any) {
        return React.createElement('option', { key: t.farmer_tenant, value: t.farmer_tenant },
          (t.farmer_name || t.farmer_tenant)
        );
      })
    )
  );
};
