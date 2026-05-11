import type { SlotWidgetDefinition, ModuleViewerSlots } from '@nekazari/sdk';
import { CUEEnclosureLayer } from '../components/CUEEnclosureLayer';
import { CUEMainPanel } from '../components/CUEMainPanel';

const MODULE_ID = 'cue';

export const moduleSlots: ModuleViewerSlots = {
  'context-panel': [
    {
      id: 'cue-main-panel',
      moduleId: MODULE_ID,
      component: 'CUEMainPanel',
      priority: 100,
      localComponent: CUEMainPanel,
    },
  ],
  'map-layer': [
    {
      id: 'cue-enclosure-layer',
      moduleId: MODULE_ID,
      component: 'CUEEnclosureLayer',
      priority: 90,
      localComponent: CUEEnclosureLayer,
    },
  ],
};

/** Alias for host integration */
export const viewerSlots = moduleSlots;
