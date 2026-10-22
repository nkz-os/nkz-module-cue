import React, { useState, useEffect } from 'react';
import { Loader2, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react';
import { explotacionesApi } from '../services/cueApi';

interface ExplotacionFormProps {
  onSaved: () => void;
  explotacion?: any;
}

interface FormData {
  nombre: string;
  descripcion: string;
  municipio: string;
  provincia: string;
  nif: string;
  regepa: string;
  cif_entidad_habilitada: string;
  coordenadas: { lng: string; lat: string };
}

const emptyForm: FormData = {
  nombre: '',
  descripcion: '',
  municipio: '',
  provincia: '',
  nif: '',
  regepa: '',
  cif_entidad_habilitada: '',
  coordenadas: { lng: '', lat: '' },
};

export const ExplotacionForm: React.FC<ExplotacionFormProps> = ({ onSaved, explotacion }) => {
  const [formData, setFormData] = useState<FormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const isEdit = !!explotacion;

  useEffect(() => {
    if (explotacion) {
      const coords = explotacion.coordenadas || explotacion.location || {};
      setFormData({
        nombre: explotacion.nombre || '',
        descripcion: explotacion.descripcion || '',
        municipio: explotacion.municipio || '',
        provincia: explotacion.provincia || '',
        nif: explotacion.nif || '',
        regepa: explotacion.regepa || '',
        cif_entidad_habilitada: explotacion.cif_entidad_habilitada || explotacion.cifEntidadHabilitada || '',
        coordenadas: {
          lng: coords.lng !== undefined ? String(coords.lng) : coords.coordinates?.[0] !== undefined ? String(coords.coordinates[0]) : '',
          lat: coords.lat !== undefined ? String(coords.lat) : coords.coordinates?.[1] !== undefined ? String(coords.coordinates[1]) : '',
        },
      });
    }
  }, [explotacion]);

  const updateField = (field: keyof Omit<FormData, 'coordenadas'>, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const updateCoord = (axis: 'lng' | 'lat', value: string) => {
    setFormData(prev => ({
      ...prev,
      coordenadas: { ...prev.coordenadas, [axis]: value },
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    if (!formData.nombre.trim()) {
      setError('El campo "Nombre" es obligatorio');
      return;
    }

    setSaving(true);
    try {
      const payload: Record<string, any> = {
        nombre: formData.nombre,
        descripcion: formData.descripcion,
        municipio: formData.municipio,
        provincia: formData.provincia,
        nif: formData.nif,
        regepa: formData.regepa,
        cif_entidad_habilitada: formData.cif_entidad_habilitada,
      };
      if (formData.coordenadas.lng && formData.coordenadas.lat) {
        payload.coordenadas = {
          type: 'Point',
          coordinates: [parseFloat(formData.coordenadas.lng), parseFloat(formData.coordenadas.lat)],
        };
        payload.location = {
          lng: parseFloat(formData.coordenadas.lng),
          lat: parseFloat(formData.coordenadas.lat),
        };
      }

      if (isEdit && explotacion?.id) {
        await explotacionesApi.update(explotacion.id, payload);
      } else {
        await explotacionesApi.create(payload);
      }

      setSuccess(true);
      setTimeout(() => onSaved(), 1500);
    } catch (err: any) {
      setError(err?.error || err?.message || (err?.detail && typeof err.detail === 'string' ? err.detail : null) || 'Error al guardar la explotación');
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
        isEdit ? 'Editar Explotación' : 'Nueva Explotación'
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
          React.createElement('span', { className: 'text-green-700 text-sm' }, 'Explotación guardada correctamente')
        )
      : null,

    // Form
    React.createElement('form', { onSubmit: handleSubmit, className: 'space-y-3' },
      // nombre
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' },
          'Nombre ', React.createElement('span', { className: 'text-red-500' }, '*')
        ),
        React.createElement('input', {
          type: 'text',
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.nombre,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('nombre', e.target.value),
          placeholder: 'Nombre de la explotación',
          required: true,
        })
      ),

      // descripcion
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Descripción'),
        React.createElement('textarea', {
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.descripcion,
          onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => updateField('descripcion', e.target.value),
          placeholder: 'Descripción opcional',
          rows: 3,
        })
      ),

      // municipio + provincia (row)
      React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Municipio'),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.municipio,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('municipio', e.target.value),
            placeholder: 'Municipio',
          })
        ),
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Provincia'),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.provincia,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('provincia', e.target.value),
            placeholder: 'Provincia',
          })
        )
      ),

      // nif + regepa (row)
      React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'NIF'),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.nif,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('nif', e.target.value),
            placeholder: '12345678A',
          })
        ),
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'REGEPA'),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.regepa,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('regepa', e.target.value),
            placeholder: 'Número REGEPA',
          })
        )
      ),

      // cif_entidad_habilitada
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'CIF Entidad Habilitada'),
        React.createElement('input', {
          type: 'text',
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.cif_entidad_habilitada,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('cif_entidad_habilitada', e.target.value),
          placeholder: 'CIF de la entidad habilitada',
        })
      ),

      // coordenadas
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Coordenadas'),
        React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
          React.createElement('div', null,
            React.createElement('label', { className: 'block text-xs text-gray-500 mb-1' }, 'Longitud'),
            React.createElement('input', {
              type: 'number',
              step: 'any',
              className: 'border border-gray-300 rounded px-3 py-2 w-full',
              value: formData.coordenadas.lng,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateCoord('lng', e.target.value),
              placeholder: '-3.7038',
            })
          ),
          React.createElement('div', null,
            React.createElement('label', { className: 'block text-xs text-gray-500 mb-1' }, 'Latitud'),
            React.createElement('input', {
              type: 'number',
              step: 'any',
              className: 'border border-gray-300 rounded px-3 py-2 w-full',
              value: formData.coordenadas.lat,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateCoord('lat', e.target.value),
              placeholder: '40.4168',
            })
          )
        )
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
