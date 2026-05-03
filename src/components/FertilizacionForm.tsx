import React, { useState, useEffect } from 'react';
import { Loader2, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react';
import { fertilizacionesApi, explotacionesApi } from '../services/cueApi';

interface FertilizacionFormProps {
  onSaved: () => void;
  fertilizacion?: any;
}

interface FormData {
  parcela_id: string;
  tipo: string;
  dosis_kg_ha: string;
  contenido_n_pct: string;
  contenido_p_pct: string;
  fecha: string;
}

const emptyForm: FormData = {
  parcela_id: '',
  tipo: 'mineral',
  dosis_kg_ha: '',
  contenido_n_pct: '',
  contenido_p_pct: '',
  fecha: '',
};

const TIPOS = [
  { value: 'mineral', label: 'Mineral' },
  { value: 'orgánico', label: 'Orgánico' },
  { value: 'estiércol', label: 'Estiércol' },
  { value: 'purín', label: 'Purín' },
  { value: 'compost', label: 'Compost' },
];

export const FertilizacionForm: React.FC<FertilizacionFormProps> = ({ onSaved, fertilizacion }) => {
  const [formData, setFormData] = useState<FormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [parcelas, setParcelas] = useState<any[]>([]);
  const [loadingParcelas, setLoadingParcelas] = useState(false);

  const isEdit = !!fertilizacion;

  useEffect(() => {
    if (fertilizacion) {
      setFormData({
        parcela_id: fertilizacion.parcela_id || '',
        tipo: fertilizacion.tipo || 'mineral',
        dosis_kg_ha: fertilizacion.dosis_kg_ha !== undefined ? String(fertilizacion.dosis_kg_ha) : '',
        contenido_n_pct: fertilizacion.contenido_n_pct !== undefined ? String(fertilizacion.contenido_n_pct) : '',
        contenido_p_pct: fertilizacion.contenido_p_pct !== undefined ? String(fertilizacion.contenido_p_pct) : '',
        fecha: fertilizacion.fecha || '',
      });
    }
  }, [fertilizacion]);

  useEffect(() => {
    setLoadingParcelas(true);
    explotacionesApi.list()
      .then(farms => {
        const allParcelas: any[] = [];
        Promise.all(farms.map(f => explotacionesApi.listParcelas(f.id)))
          .then(results => {
            results.forEach(parcelas => allParcelas.push(...(Array.isArray(parcelas) ? parcelas : [])));
            setParcelas(allParcelas);
            setLoadingParcelas(false);
          });
      })
      .catch(() => setLoadingParcelas(false));
  }, []);

  const updateField = (field: keyof FormData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    if (!formData.parcela_id.trim()) {
      setError('El campo "Parcela ID" es obligatorio');
      return;
    }

    setSaving(true);
    try {
      const payload: Record<string, any> = {
        parcela_id: formData.parcela_id,
        tipo: formData.tipo,
        dosis_kg_ha: formData.dosis_kg_ha ? parseFloat(formData.dosis_kg_ha) : undefined,
        contenido_n_pct: formData.contenido_n_pct ? parseFloat(formData.contenido_n_pct) : undefined,
        contenido_p_pct: formData.contenido_p_pct ? parseFloat(formData.contenido_p_pct) : undefined,
        fecha: formData.fecha || undefined,
      };

      // Clean up undefined values
      Object.keys(payload).forEach(k => { if (payload[k] === undefined) delete payload[k]; });

      if (isEdit && fertilizacion?.id) {
        await fertilizacionesApi.update(fertilizacion.id, payload);
      } else {
        await fertilizacionesApi.create(payload);
      }

      setSuccess(true);
      setTimeout(() => onSaved(), 1500);
    } catch (err: any) {
      setError(err?.error || err?.message || (err?.detail && typeof err.detail === 'string' ? err.detail : null) || 'Error al guardar la fertilización');
    } finally {
      setSaving(false);
    }
  };

  return React.createElement('div', { className: 'space-y-4' },
    // Header
    React.createElement('div', { className: 'flex items-center gap-2' },
      React.createElement('button', {
        onClick: onSaved,
        className: 'text-gray-500 hover:text-gray-700 p-1',
      },
        React.createElement(ArrowLeft, { className: 'h-5 w-5' })
      ),
      React.createElement('h3', { className: 'text-lg font-semibold text-gray-900' },
        isEdit ? 'Editar Fertilización' : 'Nueva Fertilización'
      )
    ),

    // Error
    error
      ? React.createElement('div', { className: 'bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2' },
          React.createElement(AlertCircle, { className: 'h-5 w-5 text-red-500 flex-shrink-0' }),
          React.createElement('span', { className: 'text-red-700 text-sm' }, error)
        )
      : null,

    // Success
    success
      ? React.createElement('div', { className: 'bg-green-50 border border-green-200 rounded p-3 flex items-center gap-2' },
          React.createElement(CheckCircle, { className: 'h-5 w-5 text-green-500 flex-shrink-0' }),
          React.createElement('span', { className: 'text-green-700 text-sm' }, 'Fertilización guardada correctamente')
        )
      : null,

    // Form
    React.createElement('form', { onSubmit: handleSubmit, className: 'space-y-3' },
      // parcela_id — dropdown from explotaciones
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' },
          'Parcela ID ', React.createElement('span', { className: 'text-red-500' }, '*')
        ),
        React.createElement('select', {
          value: formData.parcela_id,
          onChange: (e: React.ChangeEvent<HTMLSelectElement>) => updateField('parcela_id', e.target.value),
          className: 'border border-gray-300 rounded px-3 py-2 w-full text-sm',
          disabled: loadingParcelas,
        },
          React.createElement('option', { value: '' }, loadingParcelas ? 'Cargando parcelas...' : '-- Seleccionar parcela --'),
          ...parcelas.map(p =>
            React.createElement('option', {
              key: p.id || p.orion_entity_id,
              value: p.id
            }, `${p.name || p.nombre || 'Sin nombre'} (${p.hasCrop || p.cultivo || 'sin cultivo'})`)
          )
        )
      ),

      // tipo
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Tipo de fertilizante'),
        React.createElement('select', {
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.tipo,
          onChange: (e: React.ChangeEvent<HTMLSelectElement>) => updateField('tipo', e.target.value),
        },
          TIPOS.map(t => React.createElement('option', { key: t.value, value: t.value }, t.label))
        )
      ),

      // dosis_kg_ha
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Dosis (kg/ha)'),
        React.createElement('input', {
          type: 'number',
          step: '0.01',
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.dosis_kg_ha,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('dosis_kg_ha', e.target.value),
          placeholder: '0.00',
        })
      ),

      // contenido_n_pct + contenido_p_pct (row)
      React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Contenido N (%)'),
          React.createElement('input', {
            type: 'number',
            step: '0.1',
            min: '0',
            max: '100',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.contenido_n_pct,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('contenido_n_pct', e.target.value),
            placeholder: '0.0',
          })
        ),
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Contenido P (%)'),
          React.createElement('input', {
            type: 'number',
            step: '0.1',
            min: '0',
            max: '100',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.contenido_p_pct,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('contenido_p_pct', e.target.value),
            placeholder: '0.0',
          })
        )
      ),

      // fecha
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Fecha de aplicación'),
        React.createElement('input', {
          type: 'date',
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.fecha,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('fecha', e.target.value),
        })
      ),

      // Submit
      React.createElement('div', { className: 'flex gap-2 pt-2' },
        React.createElement('button', {
          type: 'button',
          onClick: onSaved,
          className: 'border border-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-50',
          disabled: saving,
        }, 'Cancelar'),
        React.createElement('button', {
          type: 'submit',
          className: 'bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 flex items-center gap-2 disabled:opacity-50',
          disabled: saving || success,
        },
          saving ? React.createElement(Loader2, { className: 'h-4 w-4 animate-spin' }) : null,
          saving ? 'Guardando...' : (isEdit ? 'Actualizar' : 'Guardar')
        )
      )
    )
  );
};
