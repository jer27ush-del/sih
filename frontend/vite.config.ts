import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Development: the app runs at http://localhost:5173 and forwards /api to Django on :8000.
// Production build: assets are served by Django (WhiteNoise) under /static/.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/static/' : '/',
  server: { proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } } },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts' },
}));
