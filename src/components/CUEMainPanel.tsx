import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, AlertCircle, Plus, Search } from 'lucide-react';
import { ExplotacionList } from './ExplotacionList';
import { ExplotacionForm } from './ExplotacionForm';
import { TratamientoList } from './TratamientoList';
import { TratamientoForm } from './TratamientoForm';
import { FertilizacionList } from './FertilizacionList';
import { FertilizacionForm } from './FertilizacionForm';
import { CatalogoPanel } from './CatalogoPanel';
import { RecintoForm } from './RecintoForm';
import { recintosApi } from '../services/cueApi';

type TabId = 'explotaciones' | 'tratamientos' | 'fertilizaciones' | 'catalogos' | 'recintos';
type ViewMode = 'list' | 'create' | 'edit';

const TABS: { id: TabId; label: string }[] = [
  { id: 'explotaciones', label: 'Explotaciones' },
  { id: 'tratamientos', label: 'Tratamientos' },
  { id: 'fertilizaciones', label: 'Fertilizaciones' },
  { id: 'catalogos', label: 'Catálogos' },
  { id: 'recintos', label: 'Recintos' },
];

export const CUEMainPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('explotaciones');
  const [selectedEntity, setSelectedEntity] = useState<any>(null);
  const [mode, setMode] = useState<ViewMode>('list');

  // Recintos tab state
  const [declarationId, setDeclarationId] = useState('');
  const [recintoList, setRecintoList] = useState<any[]>([]);
  const [recintoListLoading, setRecintoListLoading] = useState(false);
  const [recintoListError, setRecintoListError] = useState<string | null>(null);
  const [selectedRecinto, setSelectedRecinto] = useState<any>(null);
  const [recintoMode, setRecintoMode] = useState<'list' | 'create' | 'edit'>('list');

  const handleSelect = (entity: any) => {
    setSelectedEntity(entity);
    setMode('edit');
  };

  const handleNew = () => {
    setSelectedEntity(null);
    setMode('create');
  };

  const handleSaved = () => {
    setSelectedEntity(null);
    setMode('list');
  };

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    setSelectedEntity(null);
    setMode('list');
    // Reset recintos tab state
    if (tabId !== 'recintos') {
      setRecintoMode('list');
      setSelectedRecinto(null);
    }
  };

  // Fetch recintos when declarationId changes
  const fetchRecintos = useCallback(function () {
    if (!declarationId.trim()) {
      setRecintoList([]);
      return;
    }
    setRecintoListLoading(true);
    setRecintoListError(null);
    recintosApi.listByDeclaracion(declarationId.trim())
      .then(function (data: any) {
        var list = Array.isArray(data) ? data : (data?.data || []);
        setRecintoList(list);
        setRecintoListLoading(false);
      })
      .catch(function (err: any) {
        setRecintoListError(err?.error || err?.message || 'Error al cargar recintos');
        setRecintoListLoading(false);
      });
  }, [declarationId]);

  useEffect(function () {
    if (activeTab === 'recintos' && declarationId.trim()) {
      fetchRecintos();
    }
  }, [activeTab, declarationId, fetchRecintos]);

  const handleRecintoNew = function () {
    setSelectedRecinto(null);
    setRecintoMode('create');
  };

  const handleRecintoSelect = function (recinto: any) {
    setSelectedRecinto(recinto);
    setRecintoMode('edit');
  };

  const handleRecintoSaved = function () {
    setSelectedRecinto(null);
    setRecintoMode('list');
    fetchRecintos();
  };

  const renderRecintosTab = function () {
    if (recintoMode === 'create' || recintoMode === 'edit') {
      if (!declarationId.trim()) {
        return React.createElement('div', { className: 'p-4 text-center text-gray-400 text-sm' },
          'Seleccione una declaración primero'
        );
      }
      return React.createElement(RecintoForm, {
        key: selectedRecinto?.id || 'new',
        declaracionId: declarationId.trim(),
        onSaved: handleRecintoSaved,
        recinto: recintoMode === 'edit' ? selectedRecinto : undefined,
      });
    }

    return React.createElement('div', { className: 'space-y-4' },
      // Declaration ID input
      React.createElement('div', null,
        React.createElement('label', { className: 'block text-sm font-medium text-gray-700 mb-1' },
          'ID de Declaración'
        ),
        React.createElement('div', { className: 'flex gap-2' },
          React.createElement('input', {
            type: 'text',
            value: declarationId,
            onChange: function (e: React.ChangeEvent<HTMLInputElement>) {
              setDeclarationId(e.target.value);
            },
            placeholder: 'UUID de la declaración...',
            className: 'border border-gray-300 rounded px-3 py-2 w-full text-sm flex-1',
          }),
          React.createElement('button', {
            onClick: fetchRecintos,
            disabled: !declarationId.trim() || recintoListLoading,
            className: 'px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm flex items-center gap-1 disabled:opacity-50',
          },
            React.createElement(Search, { className: 'h-4 w-4' }),
            'Buscar'
          )
        )
      ),

      // Content area
      !declarationId.trim()
        ? React.createElement('div', { className: 'text-center py-12 text-gray-400' },
            React.createElement('p', { className: 'text-sm' }, 'Seleccione una línea de declaración primero')
          )
        : recintoListLoading
          ? React.createElement('div', { className: 'flex justify-center py-8' },
              React.createElement(Loader2, { className: 'h-6 w-6 animate-spin text-green-600' })
            )
          : recintoListError
            ? React.createElement('div', { className: 'bg-red-50 border border-red-200 rounded p-3 flex items-center gap-2' },
                React.createElement(AlertCircle, { className: 'h-5 w-5 text-red-500 flex-shrink-0' }),
                React.createElement('span', { className: 'text-red-700 text-sm' }, recintoListError)
              )
            : recintoList.length === 0
              ? React.createElement('div', { className: 'text-center py-12 text-gray-400' },
                  React.createElement('p', { className: 'text-sm' }, 'No hay recintos para esta declaración')
                )
              : React.createElement('div', { className: 'space-y-2' },
                  React.createElement('div', { className: 'flex items-center justify-between' },
                    React.createElement('span', { className: 'text-sm font-medium text-gray-700' },
                      recintoList.length + ' recinto(s)'
                    ),
                    React.createElement('button', {
                      onClick: handleRecintoNew,
                      className: 'bg-green-600 text-white px-3 py-1.5 rounded text-sm hover:bg-green-700 flex items-center gap-1',
                    },
                      React.createElement(Plus, { className: 'h-3.5 w-3.5' }),
                      'Nuevo'
                    )
                  ),
                  React.createElement('div', { className: 'space-y-1 max-h-[400px] overflow-y-auto' },
                    recintoList.map(function (recinto: any, i: number) {
                      return React.createElement('div', {
                        key: recinto.id || recinto.orion_entity_id || i,
                        className: 'bg-white rounded-lg shadow p-3 cursor-pointer hover:shadow-md transition-shadow border border-gray-100',
                        onClick: function () { handleRecintoSelect(recinto); },
                      },
                        React.createElement('div', { className: 'flex items-center justify-between' },
                          React.createElement('div', null,
                            React.createElement('h4', { className: 'font-medium text-gray-900 text-sm' },
                              recinto.sigpacReference || recinto.referencia_sigpac || 'Recinto ' + (i + 1)
                            ),
                            React.createElement('div', { className: 'text-xs text-gray-500 mt-0.5' },
                              recinto.area_ha != null
                                ? recinto.area_ha.toFixed(2) + ' ha'
                                : recinto.superficie_admisible_ha != null
                                  ? recinto.superficie_admisible_ha.toFixed(2) + ' ha admisibles'
                                  : 'Sin superficie'
                            )
                          ),
                          recinto.geometria || recinto.geometry
                            ? React.createElement('span', { className: 'text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded' }, 'MAP')
                            : null
                        )
                      );
                    })
                  )
                )
    );
  };

  const renderTabContent = () => {
    // If in create or edit mode, show the form for the current tab
    if (mode !== 'list' && activeTab !== 'catalogos' && activeTab !== 'recintos') {
      switch (activeTab) {
        case 'explotaciones':
          return React.createElement(ExplotacionForm, {
            key: selectedEntity?.id || 'new',
            onSaved: handleSaved,
            explotacion: mode === 'edit' ? selectedEntity : undefined,
          });
        case 'tratamientos':
          return React.createElement(TratamientoForm, {
            key: selectedEntity?.id || 'new',
            onSaved: handleSaved,
            tratamiento: mode === 'edit' ? selectedEntity : undefined,
          });
        case 'fertilizaciones':
          return React.createElement(FertilizacionForm, {
            key: selectedEntity?.id || 'new',
            onSaved: handleSaved,
            fertilizacion: mode === 'edit' ? selectedEntity : undefined,
          });
        default:
          return null;
      }
    }

    // List mode or catalogos/recintos tab
    switch (activeTab) {
      case 'explotaciones':
        return React.createElement(ExplotacionList, {
          key: 'list',
          onSelect: handleSelect,
          onNew: handleNew,
        });
      case 'tratamientos':
        return React.createElement(TratamientoList, {
          key: 'list',
          onSelect: handleSelect,
          onNew: handleNew,
        });
      case 'fertilizaciones':
        return React.createElement(FertilizacionList, {
          key: 'list',
          onSelect: handleSelect,
          onNew: handleNew,
        });
      case 'catalogos':
        return React.createElement(CatalogoPanel, null);
      case 'recintos':
        return renderRecintosTab();
      default:
        return null;
    }
  };

  return React.createElement('div', { className: 'space-y-4' },
    // Module header
    React.createElement('div', { className: 'bg-white rounded-lg shadow p-4' },
      React.createElement('h2', { className: 'text-lg font-bold text-gray-900' }, 'CUE — Cuaderno de Campo'),
      React.createElement('p', { className: 'text-sm text-gray-500 mt-1' }, 'SIEX (RD 1054/2022)')
    ),

    // Tab navigation
    React.createElement('div', { className: 'border-b border-gray-200' },
      React.createElement('nav', { className: 'flex gap-0 -mb-px overflow-x-auto' },
        TABS.map(tab =>
          React.createElement('button', {
            key: tab.id,
            onClick: () => handleTabChange(tab.id),
            className: 'px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ' +
              (activeTab === tab.id
                ? 'border-green-600 text-green-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'),
          }, tab.label)
        )
      )
    ),

    // Tab content
    React.createElement('div', { className: 'min-h-[200px]' },
      renderTabContent()
    )
  );
};
