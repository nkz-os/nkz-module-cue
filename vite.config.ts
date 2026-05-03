import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const MODULE_ID = 'cue';
const ENTRY = 'src/moduleEntry.ts';
const OUTPUT_FILE = 'nkz-module.js';

const NKZ_EXTERNALS: Record<string, string> = {
  'react': 'React',
  'react-dom': 'ReactDOM',
  'react-dom/client': 'ReactDOM',
  'react-router-dom': 'ReactRouterDOM',
  '@nekazari/sdk': '__NKZ_SDK__',
  '@nekazari/ui-kit': '__NKZ_UI__',
};

export default defineConfig({
  plugins: [
    react({ jsxRuntime: 'classic' }),
    {
      name: 'nkz-module-banner',
      generateBundle(_options, bundle) {
        for (const chunk of Object.values(bundle)) {
          if (chunk.type === 'chunk' && chunk.isEntry) {
            chunk.code = `/* NKZ Module: ${MODULE_ID} | Built: ${new Date().toISOString()} */\n${chunk.code}`;
          }
        }
      },
    },
  ],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
    '__NKZ_MODULE_ID__': JSON.stringify(MODULE_ID),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5005,
    proxy: {
      '/api': {
        target: 'https://nkz.robotika.cloud',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    lib: {
      entry: ENTRY,
      name: `NKZModule_${MODULE_ID}`,
      formats: ['iife'],
      fileName: () => OUTPUT_FILE,
    },
    rollupOptions: {
      external: Object.keys(NKZ_EXTERNALS),
      output: {
        globals: NKZ_EXTERNALS,
        inlineDynamicImports: true,
      },
    },
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
    minify: 'esbuild',
    copyPublicDir: false,
  },
});
