import React, { useState } from 'react';
import { ExplotacionList } from './ExplotacionList';
import { ExplotacionForm } from './ExplotacionForm';
import { TratamientoList } from './TratamientoList';
import { TratamientoForm } from './TratamientoForm';
import { FertilizacionList } from './FertilizacionList';
import { FertilizacionForm } from './FertilizacionForm';
import { CatalogoPanel } from './CatalogoPanel';

type TabId = 'explotaciones' | 'tratamientos' | 'fertilizaciones' | 'catalogos';
type ViewMode = 'list' | 'create' | 'edit';

const TABS: { id: TabId; label: string }[] = [
  { id: 'explotaciones', label: 'Explotaciones' },
  { id: 'tratamientos', label: 'Tratamientos' },
  { id: 'fertilizaciones', label: 'Fertilizaciones' },
  { id: 'catalogos', label: 'Catálogos' },
];

export const CUEMainPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('explotaciones');
  const [selectedEntity, setSelectedEntity] = useState<any>(null);
  const [mode, setMode] = useState<ViewMode>('list');

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
  };

  const renderTabContent = () => {
    // If in create or edit mode, show the form for the current tab
    if (mode !== 'list' && activeTab !== 'catalogos') {
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

    // List mode or catalogos tab
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
