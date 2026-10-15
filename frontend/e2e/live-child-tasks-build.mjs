import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { build } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const frontendRoot = fileURLToPath(new URL('..', import.meta.url));
const destination = process.argv[2];
if (!destination) throw new Error('Child Tasks fixture requires an explicit output directory');
// Use real production React components, without deployment plugins, .env
// loading, public assets or service-worker generation.
await build({
  configFile: false, envDir: false, root: frontendRoot, mode: 'production',
  base: '/', publicDir: false, plugins: [react(), tailwindcss()],
  build: {
    outDir: resolve(destination), emptyOutDir: false, sourcemap: false,
    rollupOptions: { input: resolve(frontendRoot, 'e2e/live-child-tasks-fixture.html') },
  },
});
