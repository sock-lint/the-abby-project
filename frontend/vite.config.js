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
          'Track projects, chores, and homework — earn money, coins, and badges.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#f4ecd8',
        theme_color: '#f4ecd8',
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
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [
          /^\/api\//,
          /^\/admin\//,
          /^\/static\//,
          /^\/media\//,
          /^\/\.well-known\//,
        ],
        runtimeCaching: [
          // Same-origin GET /api/ reads: network first with a short timeout,
          // falling back to the last cached response so flaky-wifi and
          // fully-offline boots still show recent data. NOTE: the Cache
          // Storage entries are per-browser-profile (each family member's
          // own device/profile only sees responses their own token fetched)
          // — this is a family app on trusted devices, so a same-profile
          // stale read is acceptable. Non-GET requests are never cached.
          {
            urlPattern: ({ sameOrigin, url }) =>
              sameOrigin && url.pathname.startsWith('/api/'),
            method: 'GET',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-reads',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 60, maxAgeSeconds: 86400 },
              cacheableResponse: { statuses: [200] },
            },
          },
          // Google Fonts: the stylesheet (fonts.googleapis.com) and the font
          // binaries (fonts.gstatic.com) are immutable-in-practice — cache
          // first for a year so typography survives offline boots. One route
          // for both hosts: two entries sharing a cacheName would register
          // duplicate ExpirationPlugins on the same cache.
          {
            urlPattern: /^https:\/\/fonts\.(?:googleapis|gstatic)\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts',
              expiration: { maxEntries: 30, maxAgeSeconds: 31536000 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
        cleanupOutdatedCaches: true,
      },
    }),
  ]

  // Upload source maps to self-hosted Sentry during production builds.
  // Requires SENTRY_AUTH_TOKEN — gracefully skipped in local dev.
  if (command === 'build' && process.env.SENTRY_AUTH_TOKEN) {
    plugins.push(
      sentryVitePlugin({
        url: 'https://logs.neato.digital',
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT,
        authToken: process.env.SENTRY_AUTH_TOKEN,
        release: {
          name: process.env.VITE_SENTRY_RELEASE,
        },
        sourcemaps: {
          filesToDeleteAfterUpload: ['./dist/assets/*.map'],
        },
        telemetry: false,
      }),
    )
  }

  return {
    base: command === 'build' ? '/static/' : '/',
    plugins,
    build: {
      sourcemap: 'hidden',
      rollupOptions: {
        output: {
          // Stable long-lived vendor chunks so a deploy that only touches app
          // code doesn't invalidate the React/motion/Sentry bytes the SW has
          // already precached. Page chunks come from React.lazy in App.jsx.
          // Function form: Vite 8 (rolldown) doesn't accept the object form.
          // Each group also captures its own internal deps (scheduler,
          // motion-dom/utils, @sentry-internal) so the graph stays acyclic.
          manualChunks(id) {
            if (/[\\/]node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom)[\\/]/.test(id)) {
              return 'vendor'
            }
            if (/[\\/]node_modules[\\/](framer-motion|motion-dom|motion-utils)[\\/]/.test(id)) {
              return 'motion'
            }
            if (/[\\/]node_modules[\\/]@sentry(-internal)?[\\/]/.test(id)) {
              return 'sentry'
            }
            return undefined
          },
        },
      },
    },
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
  }
})
