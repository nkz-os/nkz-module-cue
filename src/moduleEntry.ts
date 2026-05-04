import App from './App';
import { moduleSlots } from './slots/index';
import pkg from '../package.json';

const MODULE_ID = 'cue';

if (window.__NKZ__) {
  window.__NKZ__.register({
    id: MODULE_ID,
    viewerSlots: moduleSlots,
    main: App,
    version: pkg.version,
  });
}
