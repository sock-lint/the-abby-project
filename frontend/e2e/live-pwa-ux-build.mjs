import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { build } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const destination = process.argv[2];
if (!destination) throw new Error('Offline fixture build requires an explicit output directory');
// A production-mode build is required: Vite dev deliberately skips the PWA
// provider registration. Do not load app environment files or build plugins
// that contact deployment/Sentry services, and do not generate a real worker.
await build({
  configFile: false,
  envDir: false,
  root: frontendRoot,
  mode: 'production',
  base: '/',
  publicDir: false,
  plugins: [react(), tailwindcss()],
  build: {
    outDir: resolve(destination), emptyOutDir: false, sourcemap: false,
    rollupOptions: { input: resolve(frontendRoot, 'e2e/live-pwa-ux-fixture.html') },
  },
});
