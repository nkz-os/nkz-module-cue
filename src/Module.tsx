import { defineModule } from '@nekazari/module-kit';
import { lazy } from 'react';
import './i18n';
import { moduleSlots } from './slots';
import pkg from '../package.json';

const MainPage = lazy(() => import('./App'));

export default defineModule({
  id: 'cue',
  displayName: 'Cuaderno de Campo (CUE)',
  version: pkg.version,
  hostApiVersion: '^2.0.0',
  description: 'Cuaderno de Campo de Explotación, SIEX compliant (RD 1054/2022) — Nekazari Platform Module',
  accent: { base: '#0891B2', soft: '#CFFAFE', strong: '#155E75' },
  icon: 'notebook',
  main: MainPage,
  api: { basePath: '/api/modules/cue' },
  slots: moduleSlots as never,
});
