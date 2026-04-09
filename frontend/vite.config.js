import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In production builds, assets live under Django's STATIC_URL (/static/) so
// the built index.html can be served as-is from the SPA catch-all view and
// still resolve its bundled JS/CSS through WhiteNoise. In dev the Vite server
// serves from / and proxies /api to the Django dev server on :8000.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/' : '/',
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: ['abby.bos.lol', '.sslip.io', 'localhost'],
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
}))
