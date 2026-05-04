import React, { useState, useEffect, useCallback, useRef } from 'react';
import { SlotShellCompact } from '@nekazari/viewer-kit';
import { recintosApi } from '../services/cueApi';
import { Loader2, AlertCircle } from 'lucide-react';

const cueAccent = { base: '#EF4444', soft: '#FEE2E2', strong: '#B91C1C' };

interface CUEEnclosureLayerProps {
  viewer?: any;
  cesium?: any;
  declarationId?: string;
  onEnclosureSelect?: (enclosure: any) => void;
}

export const CUEEnclosureLayer: React.FC<CUEEnclosureLayerProps> = (props) => {
  const { viewer, cesium, declarationId, onEnclosureSelect } = props;
  const [enclosures, setEnclosures] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const entitiesRef = useRef<any[]>([]);

  // Load enclosures
  useEffect(() => {
    if (!declarationId) {
      setEnclosures([]);
      return;
    }
    setLoading(true);
    setError(null);
    recintosApi.listByDeclaracion(declarationId)
      .then(data => {
        const list = Array.isArray(data) ? data : [];
        setEnclosures(list);
        setLoading(false);
      })
      .catch(err => {
        setError(err?.error || 'Error al cargar recintos');
        setLoading(false);
      });
  }, [declarationId]);

  // Render polygons on Cesium
  useEffect(() => {
    if (!viewer || !cesium || enclosures.length === 0) return;

    // Clean up previous entities
    entitiesRef.current.forEach(function (e: any) {
      viewer.entities.remove(e);
    });
    entitiesRef.current = [];

    enclosures.forEach(function (enc: any) {
      var geom = enc.geometria || enc.geometry;
      if (!geom || !geom.coordinates) return;

      var isSelected = enc.id === selectedId || enc.orion_entity_id === selectedId;

      try {
        var entity = viewer.entities.add({
          polygon: {
            hierarchy: cesium.Cartesian3.fromDegreesArray(
              geom.coordinates[0].flatMap(function (c: number[]) { return [c[0], c[1]]; })
            ),
            material: isSelected
              ? cesium.Color.BLUE.withAlpha(0.4)
              : cesium.Color.GREEN.withAlpha(0.3),
            outline: true,
            outlineColor: isSelected ? cesium.Color.BLUE : cesium.Color.DARKGREEN,
            outlineWidth: isSelected ? 3 : 1,
          },
          name: enc.sigpacReference || enc.referencia_sigpac || 'Recinto',
          description: JSON.stringify(enc),
        });

        // Click handler via entity properties
        if (entity) {
          entity._nkzData = enc;
          entitiesRef.current.push(entity);
        }
      } catch (e) {
        console.warn('[CUEEnclosureLayer] Error rendering polygon:', e);
      }
    });

    return function cleanup() {
      entitiesRef.current.forEach(function (e: any) {
        viewer.entities.remove(e);
      });
      entitiesRef.current = [];
    };
  }, [viewer, cesium, enclosures, selectedId]);

  // Loading state
  if (loading) {
    return React.createElement(SlotShellCompact, { moduleId: 'cue', accent: cueAccent },
      React.createElement('div', { className: 'p-2 text-gray-500 text-sm flex items-center gap-2' },
        React.createElement(Loader2, { className: 'h-4 w-4 animate-spin text-green-600' }),
        'Cargando recintos...'
      )
    );
  }

  // Error state
  if (error) {
    return React.createElement(SlotShellCompact, { moduleId: 'cue', accent: cueAccent },
      React.createElement('div', { className: 'p-2 text-red-500 text-sm flex items-center gap-2' },
        React.createElement(AlertCircle, { className: 'h-5 w-5 text-red-500 flex-shrink-0' }),
        error
      )
    );
  }

  // Empty state — no declaration selected
  if (!declarationId) {
    return React.createElement(SlotShellCompact, { moduleId: 'cue', accent: cueAccent },
      React.createElement('div', { className: 'p-2 text-gray-400 text-sm' },
        'Seleccione una línea de declaración para ver sus recintos'
      )
    );
  }

  // Empty state — declaration selected but no recintos
  if (enclosures.length === 0) {
    return React.createElement(SlotShellCompact, { moduleId: 'cue', accent: cueAccent },
      React.createElement('div', { className: 'p-2 text-gray-400 text-sm' },
        'No hay recintos para esta declaración'
      )
    );
  }

  // Normal state: show summary with recinto list
  return React.createElement(SlotShellCompact, { moduleId: 'cue', accent: cueAccent },
    React.createElement('div', { className: 'p-2 text-sm' },
    React.createElement('div', { className: 'font-medium text-gray-800' },
      enclosures.length + ' recintos'
    ),
    React.createElement('div', { className: 'text-gray-500 mt-1 space-y-0.5 max-h-[300px] overflow-y-auto' },
      enclosures.map(function (e: any, i: number) {
        var isSelected = e.id === selectedId || e.orion_entity_id === selectedId;
        return React.createElement('div', {
          key: e.id || e.orion_entity_id || i,
          className: 'cursor-pointer py-1 px-2 rounded flex items-center gap-2 ' +
            (isSelected ? 'bg-blue-100' : 'hover:bg-gray-100'),
          onClick: function () {
            var id = e.id || e.orion_entity_id;
            setSelectedId(id);
            onEnclosureSelect?.(e);
          },
        },
          // Color indicator dot
          React.createElement('span', {
            className: 'inline-block w-2.5 h-2.5 rounded-full flex-shrink-0',
            style: { backgroundColor: isSelected ? '#3B82F6' : '#22C55E' },
          }),
          React.createElement('span', { className: 'truncate flex-1' },
            e.sigpacReference || e.referencia_sigpac || 'Recinto ' + (i + 1)
          ),
          e.area_ha != null
            ? React.createElement('span', { className: 'text-gray-400 text-xs flex-shrink-0' },
                e.area_ha.toFixed(2) + ' ha'
              )
            : null
        );
      })
    )
  )
);
};
