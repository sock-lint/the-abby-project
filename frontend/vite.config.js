import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import { VitePWA } from 'vite-plugin-pwa'

// In production builds, assets live under Django's STATIC_URL (/static/) so
// the built index.html can be served as-is from the SPA catch-all view and
// still resolve its bundled JS/CSS through WhiteNoise. In dev the Vite server
// serves from / and proxies /api to the Django dev server on :8000.
export default defineConfig(({ command }) => {
  const plugins = [
    react(),
    tailwindcss(),
    VitePWA({
      base: '/',
      scope: '/',
      registerType: 'prompt',
      injectRegister: false,
      filename: 'sw.js',
      manifestFilename: 'manifest.webmanifest',
      // Emit the SW + manifest at dist root (not under /static/) so they
      // serve from / via the explicit Django routes in config/urls.py. The
      // SW needs root scope; the manifest needs application/manifest+json.
      manifest: {
        name: 'The Abby Project',
        short_name: 'Abby',
        description:
          'Keep your memories, grow your story, and share little adventures with your family.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        // Deliberately NOT 'portrait'. Android enforces the manifest
        // orientation in standalone mode (iOS ignores it), so a portrait
        // lock left a kid with an Android tablet in a kickstand or keyboard
        // case stuck sideways while the same device on iOS rotated freely.
        // Nothing in the layout needs portrait — JournalShell already has a
        // wide arrangement (sidebar at lg) that landscape viewports use.
        orientation: 'any',
        background_color: '#FFF8EE',
        theme_color: '#FFF8EE',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/maskable-icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
