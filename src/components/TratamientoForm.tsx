import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, AlertCircle, CheckCircle, ArrowLeft, AlertTriangle, Search as SearchIcon } from 'lucide-react';
import { tratamientosApi, catalogosApi, explotacionesApi } from '../services/cueApi';

interface TratamientoFormProps {
  onSaved: () => void;
  tratamiento?: any;
}

interface FormData {
  parcela_id: string;
  producto_ropo: string;
  producto_ropo_nombre: string;
  dosis: string;
  unidad_dosis: string;
  plaga: string;
  equipo: string;
  aplicador: string;
  hora: string;
  fecha: string;
  fecha_cosecha: string;
}

interface ValidationIssue {
  rule?: string;
  severity?: string;
  message?: string;
  field?: string;
  msg?: string;
}

const emptyForm: FormData = {
  parcela_id: '',
  producto_ropo: '',
  producto_ropo_nombre: '',
  dosis: '',
  unidad_dosis: 'L/ha',
  plaga: '',
  equipo: '',
  aplicador: '',
  hora: '',
  fecha: '',
  fecha_cosecha: '',
};

export const TratamientoForm: React.FC<TratamientoFormProps> = ({ onSaved, tratamiento }) => {
  const [formData, setFormData] = useState<FormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [parcelas, setParcelas] = useState<any[]>([]);
  const [loadingParcelas, setLoadingParcelas] = useState(false);

  // Validation state
  const [validationErrors, setValidationErrors] = useState<ValidationIssue[]>([]);
  const [validationWarnings, setValidationWarnings] = useState<ValidationIssue[]>([]);

  // ROPO autocomplete state
  const [ropoSearchTerm, setRopoSearchTerm] = useState('');
  const [ropoResults, setRopoResults] = useState<any[]>([]);
  const [ropoSearching, setRopoSearching] = useState(false);
  const [showRopoDropdown, setShowRopoDropdown] = useState(false);

  const isEdit = !!tratamiento;

  useEffect(() => {
    if (tratamiento) {
      setFormData({
        parcela_id: tratamiento.parcela_id || '',
        producto_ropo: tratamiento.producto_ropo || '',
        producto_ropo_nombre: tratamiento.producto_ropo_nombre || '',
        dosis: tratamiento.dosis !== undefined ? String(tratamiento.dosis) : '',
        unidad_dosis: tratamiento.unidad_dosis || 'L/ha',
        plaga: tratamiento.plaga || '',
        equipo: tratamiento.equipo || '',
        aplicador: tratamiento.aplicador || '',
        hora: tratamiento.hora || '',
        fecha: tratamiento.fecha || '',
        fecha_cosecha: tratamiento.fecha_cosecha || '',
      });
      if (tratamiento.producto_ropo) {
        setRopoSearchTerm(tratamiento.producto_ropo_nombre || tratamiento.producto_ropo);
      }
    }
  }, [tratamiento]);

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

  // Debounced ROPO search
  useEffect(() => {
    if (ropoSearchTerm.length < 2) {
      setRopoResults([]);
      setShowRopoDropdown(false);
      return;
    }
    const timer = setTimeout(async () => {
      setRopoSearching(true);
      try {
        const data = await catalogosApi.productosRopo({ nombre: ropoSearchTerm });
        const results = Array.isArray(data) ? data : data?.data || [];
        setRopoResults(results);
        setShowRopoDropdown(results.length > 0);
      } catch {
        setRopoResults([]);
      } finally {
        setRopoSearching(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [ropoSearchTerm]);

  const selectRopoProduct = useCallback((product: any) => {
    const regNum = product.numero_registro || '';
    const displayName = product.nombre_comercial || product.nombre || '';
    setFormData(prev => ({ ...prev, producto_ropo: regNum, producto_ropo_nombre: displayName }));
    setRopoSearchTerm(`${displayName} (${regNum})`);
    setShowRopoDropdown(false);
  }, []);

  const clearValidation = () => {
    setValidationErrors([]);
    setValidationWarnings([]);
  };

  const handleSave = async (force: boolean = false) => {
    setError(null);
    setSuccess(false);
    clearValidation();

    if (!formData.parcela_id.trim()) {
      setError('El campo "Parcela ID" es obligatorio');
      return;
    }

    setSaving(true);
    try {
      const payload: Record<string, any> = {
        parcela_id: formData.parcela_id,
        producto_ropo: formData.producto_ropo,
        dosis: formData.dosis ? parseFloat(formData.dosis) : undefined,
        unidad_dosis: formData.unidad_dosis,
        plaga: formData.plaga,
        equipo: formData.equipo,
        aplicador: formData.aplicador,
        hora: formData.hora || undefined,
        fecha: formData.fecha || undefined,
        fecha_cosecha: formData.fecha_cosecha || undefined,
      };
      if (force) {
        payload.validacion_estricta = false;
      }

      // If not force-saving, run validation first
      if (!force) {
        try {
          await tratamientosApi.validate(payload);
          // Validation passed, no errors
        } catch (validateErr: any) {
          // Parse validation errors
          const detail = validateErr?.detail || validateErr?.errors || validateErr;
          const issues = Array.isArray(detail) ? detail : (detail?.errors || [detail]);
          const errs: ValidationIssue[] = [];
          const warns: ValidationIssue[] = [];
          issues.forEach((iss: any) => {
            const issue: ValidationIssue = {
              rule: iss.rule || iss.loc?.join('.') || '',
              severity: iss.severity || 'error',
              message: iss.message || iss.msg || iss.type || '',
              field: iss.field || '',
            };
            if (issue.severity === 'warning') {
              warns.push(issue);
            } else {
              errs.push(issue);
            }
          });

          if (errs.length > 0 || warns.length > 0) {
            setValidationErrors(errs);
            setValidationWarnings(warns);
            setSaving(false);
            if (errs.length > 0) {
              setError('Corrija los errores de validación o use "Guardar de todas formas"');
            }
            return;
          }
        }
      }

      // Save
      if (isEdit && tratamiento?.id) {
        await tratamientosApi.update(tratamiento.id, payload);
      } else {
        await tratamientosApi.create(payload);
      }

      setSuccess(true);
      setTimeout(() => onSaved(), 1500);
    } catch (err: any) {
      setError(err?.error || err?.message || (err?.detail && typeof err.detail === 'string' ? err.detail : null) || 'Error al guardar el tratamiento');
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSave(false);
  };

  const handleForceSave = () => {
    handleSave(true);
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
        isEdit ? 'Editar Tratamiento' : 'Nuevo Tratamiento'
      )
    ),

    // Error
    error
      ? React.createElement('div', { className: 'bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2' },
          React.createElement(AlertCircle, { className: 'h-5 w-5 text-red-500 flex-shrink-0' }),
          React.createElement('span', { className: 'text-red-700 text-sm' }, error)
        )
      : null,

    // Validation errors
    validationErrors.length > 0
      ? React.createElement('div', { className: 'space-y-1' },
          validationErrors.map((ve, i) =>
            React.createElement('div', { key: i, className: 'bg-red-50 border border-red-200 rounded p-2 flex items-start gap-2' },
              React.createElement(AlertCircle, { className: 'h-4 w-4 text-red-500 mt-0.5 flex-shrink-0' }),
              React.createElement('div', { className: 'text-xs text-red-700' },
                ve.rule ? React.createElement('span', { className: 'font-medium' }, ve.rule, ': ') : null,
                ve.message
              )
            )
          )
        )
      : null,

    // Validation warnings
    validationWarnings.length > 0
      ? React.createElement('div', { className: 'space-y-1' },
          validationWarnings.map((vw, i) =>
            React.createElement('div', { key: i, className: 'bg-yellow-50 border border-yellow-200 rounded p-2 flex items-start gap-2' },
              React.createElement(AlertTriangle, { className: 'h-4 w-4 text-yellow-500 mt-0.5 flex-shrink-0' }),
              React.createElement('div', { className: 'text-xs text-yellow-700' },
                vw.rule ? React.createElement('span', { className: 'font-medium' }, vw.rule, ': ') : null,
                vw.message
              )
            )
          )
        )
      : null,

    // Success
    success
      ? React.createElement('div', { className: 'bg-green-50 border border-green-200 rounded p-3 flex items-center gap-2' },
          React.createElement(CheckCircle, { className: 'h-5 w-5 text-green-500 flex-shrink-0' }),
          React.createElement('span', { className: 'text-green-700 text-sm' }, 'Tratamiento guardado correctamente')
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

      // producto_ropo with autocomplete
      React.createElement('div', { className: 'relative' },
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Producto ROPO'),
        React.createElement('div', { className: 'relative' },
          React.createElement(SearchIcon, { className: 'absolute left-2 top-2.5 h-4 w-4 text-gray-400' }),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded pl-8 pr-3 py-2 w-full',
            value: ropoSearchTerm,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
              setRopoSearchTerm(e.target.value);
              if (!e.target.value) {
                updateField('producto_ropo', '');
                updateField('producto_ropo_nombre', '');
              }
            },
            placeholder: 'Buscar producto ROPO (nombre o nº registro)',
            onFocus: () => {
              if (ropoResults.length > 0) setShowRopoDropdown(true);
            },
            onBlur: () => setTimeout(() => setShowRopoDropdown(false), 200),
          }),
          ropoSearching
            ? React.createElement(Loader2, { className: 'absolute right-2 top-2.5 h-4 w-4 animate-spin text-gray-400' })
            : null
        ),
        // Dropdown
        showRopoDropdown && ropoResults.length > 0
          ? React.createElement('div', { className: 'absolute z-10 mt-1 w-full bg-white border border-gray-300 rounded shadow-lg max-h-48 overflow-y-auto' },
              ropoResults.map((prod: any, i: number) =>
                React.createElement('div', {
                  key: prod.numero_registro || prod.id || i,
                  className: 'px-3 py-2 hover:bg-green-50 cursor-pointer text-sm border-b border-gray-100 last:border-b-0',
                  onMouseDown: () => selectRopoProduct(prod),
                },
                  React.createElement('div', { className: 'font-medium text-gray-800' },
                    prod.nombre_comercial || prod.nombre || '—'
                  ),
                  React.createElement('div', { className: 'text-xs text-gray-500' },
                    prod.numero_registro || '', prod.sustancia_activa ? ` — ${prod.sustancia_activa}` : ''
                  )
                )
              )
            )
          : null,
        // Selected product tag
        formData.producto_ropo && formData.producto_ropo_nombre
          ? React.createElement('div', { className: 'mt-1 text-xs text-green-700 bg-green-50 rounded px-2 py-1 inline-block' },
              'Seleccionado: ', formData.producto_ropo_nombre, ' (', formData.producto_ropo, ')'
            )
          : formData.producto_ropo && !formData.producto_ropo_nombre
            ? React.createElement('div', { className: 'mt-1 text-xs text-gray-500' },
                'Nº registro: ', formData.producto_ropo
              )
            : null
      ),

      // dosis + unidad_dosis (row)
      React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Dosis'),
          React.createElement('input', {
            type: 'number',
            step: '0.01',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.dosis,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('dosis', e.target.value),
            placeholder: '0.00',
          })
        ),
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Unidad'),
          React.createElement('select', {
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.unidad_dosis,
            onChange: (e: React.ChangeEvent<HTMLSelectElement>) => updateField('unidad_dosis', e.target.value),
          },
            React.createElement('option', { value: 'L/ha' }, 'L/ha'),
            React.createElement('option', { value: 'kg/ha' }, 'kg/ha')
          )
        )
      ),

      // plaga
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Plaga / Enfermedad'),
        React.createElement('input', {
          type: 'text',
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.plaga,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('plaga', e.target.value),
          placeholder: 'Nombre de la plaga o enfermedad',
        })
      ),

      // equipo + aplicador (row)
      React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Equipo'),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.equipo,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('equipo', e.target.value),
            placeholder: 'Equipo de aplicación',
          })
        ),
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Aplicador'),
          React.createElement('input', {
            type: 'text',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.aplicador,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('aplicador', e.target.value),
            placeholder: 'Nombre del aplicador',
          })
        )
      ),

      // fecha + hora (row)
      React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Fecha'),
          React.createElement('input', {
            type: 'date',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.fecha,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('fecha', e.target.value),
          })
        ),
        React.createElement('div', null,
          React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Hora'),
          React.createElement('input', {
            type: 'time',
            className: 'border border-gray-300 rounded px-3 py-2 w-full',
            value: formData.hora,
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('hora', e.target.value),
          })
        )
      ),

      // fecha_cosecha
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' },
          'Fecha de cosecha (plazo de seguridad)'
        ),
        React.createElement('input', {
          type: 'date',
          className: 'border border-gray-300 rounded px-3 py-2 w-full',
          value: formData.fecha_cosecha,
          onChange: (e: React.ChangeEvent<HTMLInputElement>) => updateField('fecha_cosecha', e.target.value),
        })
      ),

      // Submit buttons
      React.createElement('div', { className: 'flex gap-2 pt-2 flex-wrap' },
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
          saving ? 'Validando...' : (isEdit ? 'Actualizar' : 'Guardar')
        ),
        // Force save button (visible when there are validation issues)
        (validationErrors.length > 0 || validationWarnings.length > 0)
          ? React.createElement('button', {
              type: 'button',
              onClick: handleForceSave,
              className: 'bg-yellow-500 text-white px-4 py-2 rounded hover:bg-yellow-600 flex items-center gap-2 disabled:opacity-50',
              disabled: saving || success,
            },
              saving ? React.createElement(Loader2, { className: 'h-4 w-4 animate-spin' }) : null,
              'Guardar de todas formas'
            )
          : null
      )
    )
  );
};
