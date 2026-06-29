import React, { useState, useEffect, useRef } from 'react';
import { useViewerOptional } from '@nekazari/sdk';

interface CUEEnclosureLayerProps {
  viewer?: any;
  cesium?: any;
  declarationId?: string;
  onEnclosureSelect?: (enclosure: any) => void;
}

interface RecintosUpdatedDetail {
  enclosures: any[];
  selectedId?: string | null;
}

export const CUEEnclosureLayer: React.FC<CUEEnclosureLayerProps> = () => {
  const viewerCtx = useViewerOptional();
  const viewer = viewerCtx?.cesiumViewer ?? null;
  const isViewerReady = viewerCtx?.isViewerReady !== false;
  const [enclosures, setEnclosures] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const entitiesRef = useRef<any[]>([]);

  useEffect(() => {
    const onRecintosUpdated = (e: CustomEvent<RecintosUpdatedDetail>) => {
      setEnclosures(Array.isArray(e.detail?.enclosures) ? e.detail.enclosures : []);
      setSelectedId(e.detail?.selectedId ?? null);
    };
    const onRecintosCleared = () => {
      setEnclosures([]);
      setSelectedId(null);
    };
    const onRecintoSelected = (e: CustomEvent<{ selectedId?: string | null }>) => {
      setSelectedId(e.detail?.selectedId ?? null);
    };

    window.addEventListener('cue:recintos-updated', onRecintosUpdated as EventListener);
    window.addEventListener('cue:recintos-cleared', onRecintosCleared);
    window.addEventListener('cue:recinto-selected', onRecintoSelected as EventListener);
    return () => {
      window.removeEventListener('cue:recintos-updated', onRecintosUpdated as EventListener);
      window.removeEventListener('cue:recintos-cleared', onRecintosCleared);
      window.removeEventListener('cue:recinto-selected', onRecintoSelected as EventListener);
    };
  }, []);

  useEffect(() => {
    if (!viewer || viewer.isDestroyed?.() || !isViewerReady || enclosures.length === 0) {
      entitiesRef.current.forEach((entity: any) => {
        try {
          viewer?.entities?.remove(entity);
        } catch { /* viewer torn down */ }
      });
      entitiesRef.current = [];
      return;
    }

    const cesium = (window as any).Cesium;
    if (!cesium) return;

    entitiesRef.current.forEach((entity: any) => {
      viewer.entities.remove(entity);
    });
    entitiesRef.current = [];

    enclosures.forEach((enc: any) => {
      const geom = enc.geometria || enc.geometry;
      if (!geom?.coordinates) return;

      const isSelected = enc.id === selectedId || enc.orion_entity_id === selectedId;

      try {
        const entity = viewer.entities.add({
          polygon: {
            hierarchy: cesium.Cartesian3.fromDegreesArray(
              geom.coordinates[0].flatMap((c: number[]) => [c[0], c[1]])
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

        if (entity) {
          entity._nkzData = enc;
          entitiesRef.current.push(entity);
        }
      } catch (err) {
        console.warn('[CUEEnclosureLayer] Error rendering polygon:', err);
      }
    });

    return () => {
      entitiesRef.current.forEach((entity: any) => {
        try {
          viewer.entities.remove(entity);
        } catch { /* viewer torn down */ }
      });
      entitiesRef.current = [];
    };
  }, [viewer, isViewerReady, enclosures, selectedId]);

  return null;
};
