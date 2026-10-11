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
        globPatterns: ['**/*.{js,css,html,svg,png,woff2,ttf}'],
        // The worker and shell have root URLs, but bundled assets are served
        // by WhiteNoise at /static/assets/. Cache the same URLs index.html
        // requests so the previous release can still boot after a deploy.
        modifyURLPrefix: { 'assets/': '/static/assets/' },
        dontCacheBustURLsMatching: /^\/static\/assets\//,
        // Django serves named PWA root files, not generated workbox-*.js.
        // Inline the runtime so /sw.js never imports the SPA HTML catch-all.
        inlineWorkboxRuntime: true,
        // Web Push handlers live in their own root-served file rather than
        // switching this whole config to injectManifest — see push-sw.js for
        // why generateSW stays in charge.
        importScripts: ['/push-sw.js', '/privacy-sw.js'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [
          /^\/api\//,
          // Product and privacy pages are rendered by Django without the SPA.
          /^\/(?:about|privacy)(?:\/|\?|$)/,
          // The separately built Unity scene is served by its own /play host.
          // Installed PWAs must let this navigation reach that host.
          /^\/play(?:\/|$)/,
          /^\/admin\//,
          /^\/static\//,
          /^\/media\//,
          /^\/\.well-known\//,
        ],
        runtimeCaching: [
          // Private API reads always reach the network. URL-only caches
          // cannot distinguish accounts sharing a browser profile.
          // Images remain available offline. Image fields are presigned Ceph URLs whose
          // signature dies after AWS_QUERYSTRING_EXPIRE (1h), and the media
          // host is cross-origin, so none of it was runtime-cached at all.
          // Sketchbook tiles, pet art, proof thumbnails and avatars therefore
          // collapsed into broken-image icons on exactly the stale/offline
          // boots the SW otherwise supports.
          //
          // ``matchOptions.ignoreSearch`` is the load-bearing bit: the bytes
          // are stored under the full signed URL, but lookups compare paths
          // only, so tomorrow's freshly-signed URL still hits the entry that
          // yesterday's signature downloaded. Opaque cross-origin responses
          // (an <img> with no crossorigin attribute fetches no-cors) arrive
          // as status 0, hence the [0, 200] allowance — same as the fonts
          // route below. /static/ is excluded because the precache route
          // already owns the app's own bundled art.
          {
            urlPattern: ({ request, url }) =>
              request.destination === 'image'
              && !url.pathname.startsWith('/static/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'media-images',
              matchOptions: { ignoreSearch: true },
              expiration: { maxEntries: 120, maxAgeSeconds: 2592000 },
              cacheableResponse: { statuses: [0, 200] },
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
        '/about': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/privacy': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/public/fonts': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
