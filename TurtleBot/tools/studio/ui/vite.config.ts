import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

// Dev only: the proxy forwards /api to a running Studio, for example
//   python studio.py --fake --no-browser --stay-open --port 8790
// Open http://localhost:5173/v2/?token=<token printed by Studio> to use it.
// Another Studio port: set STUDIO_PORT (and optionally DEV_PORT for the dev server).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const STUDIO = 'http://127.0.0.1:' + (env.STUDIO_PORT || '8790');
  return {
    base: '/v2/',
    plugins: [react()],
    build: {
      outDir: '../web/v2',
      emptyOutDir: true,
      target: 'es2020',
      sourcemap: false,
      chunkSizeWarningLimit: 700,
    },
    server: {
      port: Number(env.DEV_PORT || 5173),
      strictPort: false,
      proxy: {
        '/api': {
          target: STUDIO,
          changeOrigin: true,
          configure: (proxy) => {
            // Studio only accepts requests whose Origin is its own address.
            proxy.on('proxyReq', (proxyReq) => {
              if (proxyReq.getHeader('origin')) proxyReq.setHeader('origin', STUDIO);
            });
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      restoreMocks: true,
    },
  };
});
