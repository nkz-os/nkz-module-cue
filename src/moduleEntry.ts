/**
 * CUE (Cuaderno de Campo) — Nekazari Platform Module
 * Uses @nekazari/module-kit for typed module definition.
 */
import { defineModule } from '@nekazari/module-kit';
import App from './App';
import { moduleSlots } from './slots/index';
import pkg from '../package.json';

const MODULE_ID = 'cue';

const moduleConfig = defineModule({
  id: MODULE_ID,
  displayName: 'Cuaderno de Campo (CUE)',
  accent: { base: '#0891B2', soft: '#CFFAFE', strong: '#155E75' },
  hostApiVersion: '^2.0.0',
  api: { basePath: '/api/modules/cue' },
});

if (window.__NKZ__) {
  window.__NKZ__.register({
    id: MODULE_ID,
    viewerSlots: moduleSlots,
    main: App,
    version: pkg.version,
  });
}

export default moduleConfig;
