// ModuleViewerSlots type — defined locally as it's not yet exported from @nekazari/sdk
import type React from 'react';

interface SlotWidgetDefinition {
  id: string;
  moduleId: string;
  component: string;
  priority: number;
}

interface ModuleViewerSlots {
  'context-panel'?: SlotWidgetDefinition[];
  'map-layer'?: SlotWidgetDefinition[];
  'layer-toggle'?: SlotWidgetDefinition[];
  'bottom-panel'?: SlotWidgetDefinition[];
  'entity-tree'?: SlotWidgetDefinition[];
  moduleProvider?: React.ComponentType<any>;
}

const MODULE_ID = 'cue';

export const moduleSlots: ModuleViewerSlots = {
  'context-panel': [
    {
      id: 'cue-main-panel',
      moduleId: MODULE_ID,
      component: 'CUEMainPanel',
      priority: 100,
    },
  ],
  'map-layer': [
    {
      id: 'cue-enclosure-layer',
      moduleId: MODULE_ID,
      component: 'CUEEnclosureLayer',
      priority: 90,
    },
  ],
};
