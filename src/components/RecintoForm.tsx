import React, { useState } from 'react';
import { recintosApi } from '../services/cueApi';
import { Loader2, AlertCircle, CheckCircle, ArrowLeft, MapPin } from 'lucide-react';

interface RecintoFormProps {
  declaracionId: string;
  onSaved: () => void;
  recinto?: any;
}

export const RecintoForm: React.FC<RecintoFormProps> = ({ declaracionId, onSaved, recinto }) => {
  const [referenciaSigpac, setReferenciaSigpac] = useState(
    recinto?.sigpacReference || recinto?.referencia_sigpac || ''
  );
  const [superficieAdmisible, setSuperficieAdmisible] = useState(
    recinto?.eligibleArea?.value != null
      ? String(recinto.eligibleArea.value)
      : recinto?.superficie_admisible_ha != null
        ? String(recinto.superficie_admisible_ha)
        : ''
  );
  const [geometria, setGeometria] = useState(
    recinto?.geometria || recinto?.geometry || null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [geoText, setGeoText] = useState('');

  const isEdit = !!recinto;

  const handleGeoPaste = function () {
    try {
      var parsed = JSON.parse(geoText);
      if (parsed.type === 'Polygon') {
        setGeometria(parsed);
        setGeoText('');
        setError(null);
      } else {
        setError('Solo se admiten polígonos GeoJSON (type: Polygon)');
      }
    } catch (_e) {
      setError('JSON inválido. Pegue un polígono GeoJSON válido.');
    }
  };

  const handleSubmit = function (e: any) {
    if (e && e.preventDefault) e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    var data: Record<string, any> = {
      declaracion_id: declaracionId,
      referencia_sigpac: referenciaSigpac,
      superficie_admisible_ha: parseFloat(superficieAdmisible) || 0,
    };
    if (geometria) data.geometria = geometria;

    var promise = recinto
      ? recintosApi.update(recinto.id || recinto.orion_entity_id, data)
      : recintosApi.create(data);

    promise
      .then(function () {
        setSuccess(isEdit ? 'Recinto actualizado' : 'Recinto creado');
        setLoading(false);
        if (!isEdit) {
          setReferenciaSigpac('');
          setSuperficieAdmisible('');
          setGeometria(null);
        }
        setTimeout(function () { onSaved(); }, 1500);
      })
      .catch(function (err: any) {
        setError(err?.error || err?.message || 'Error al guardar recinto');
        setLoading(false);
      });
  };

  return React.createElement('div', { className: 'space-y-3' },
    // Header
    React.createElement('div', { className: 'flex items-center gap-2' },
      React.createElement('button', {
        onClick: onSaved,
        className: 'text-gray-500 hover:text-gray-700 p-1',
      },
        React.createElement(ArrowLeft, { className: 'h-5 w-5' })
      ),
      React.createElement('h3', { className: 'text-lg font-semibold text-gray-900' },
        isEdit ? 'Editar Recinto' : 'Nuevo Recinto'
      )
    ),

    // Success
    success
      ? React.createElement('div', { className: 'bg-green-50 border border-green-200 rounded p-3 flex items-center gap-2' },
          React.createElement(CheckCircle, { className: 'h-5 w-5 text-green-500 flex-shrink-0' }),
          React.createElement('span', { className: 'text-green-700 text-sm' }, success)
        )
      : null,

    // Error
    error
      ? React.createElement('div', { className: 'bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2' },
          React.createElement(AlertCircle, { className: 'h-5 w-5 text-red-500 flex-shrink-0' }),
          React.createElement('span', { className: 'text-red-700 text-sm' }, error)
        )
      : null,

    // Form
    React.createElement('form', { onSubmit: handleSubmit, className: 'space-y-3' },
      // Referencia SIGPAC
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' },
          'Referencia SIGPAC'
        ),
        React.createElement('input', {
          type: 'text',
          value: referenciaSigpac,
          onChange: function (e: React.ChangeEvent<HTMLInputElement>) {
            setReferenciaSigpac(e.target.value);
          },
          placeholder: '31:230:0:0:0:243:9003',
          className: 'border border-gray-300 rounded px-3 py-2 w-full text-sm font-mono',
        })
      ),

      // Superficie admisible
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' },
          'Superficie Admisible (ha)'
        ),
        React.createElement('input', {
          type: 'number',
          step: '0.01',
          min: '0',
          value: superficieAdmisible,
          onChange: function (e: React.ChangeEvent<HTMLInputElement>) {
            setSuperficieAdmisible(e.target.value);
          },
          className: 'border border-gray-300 rounded px-3 py-2 w-full text-sm',
        })
      ),

      // GeoJSON paste area
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' },
          'Geometría (GeoJSON Polygon)'
        ),
        React.createElement('div', { className: 'relative' },
          React.createElement('textarea', {
            value: geoText,
            onChange: function (e: React.ChangeEvent<HTMLTextAreaElement>) {
              setGeoText(e.target.value);
            },
            placeholder: 'Pegue aquí un polígono GeoJSON...',
            rows: 4,
            className: 'border border-gray-300 rounded px-3 py-2 w-full text-sm font-mono resize-vertical',
          }),
        ),
        React.createElement('div', { className: 'flex items-center gap-2 mt-1' },
          React.createElement('button', {
            type: 'button',
            onClick: handleGeoPaste,
            disabled: !geoText.trim(),
            className: 'px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1',
          },
            React.createElement(MapPin, { className: 'h-3.5 w-3.5' }),
            'Usar geometría'
          ),
          geometria
            ? React.createElement('span', { className: 'text-green-600 text-xs flex items-center gap-1' },
                React.createElement(CheckCircle, { className: 'h-3 w-3' }),
                'Geometría cargada'
              )
            : null
        )
      ),

      // Submit
      React.createElement('div', { className: 'flex gap-2 pt-2' },
        React.createElement('button', {
          type: 'button',
          onClick: onSaved,
          className: 'border border-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-50 text-sm',
          disabled: loading,
        }, 'Cancelar'),
        React.createElement('button', {
          type: 'submit',
          disabled: loading || !!success,
          className: 'bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 text-sm flex items-center gap-2 disabled:opacity-50',
        },
          loading
            ? React.createElement(Loader2, { className: 'h-4 w-4 animate-spin' })
            : null,
          loading
            ? 'Guardando...'
            : (isEdit ? 'Actualizar Recinto' : 'Crear Recinto')
        )
      )
    )
  );
};
