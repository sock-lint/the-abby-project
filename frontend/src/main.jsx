import * as Sentry from '@sentry/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { AuthProvider } from './hooks/useApi'

// Chrome fires beforeinstallprompt very early after page load — often before
// React has mounted InstallPromptProvider and its useEffect has run. Capture
// it at module-load time and stash it on window so the provider can pick it
// up on mount. Without this, the event is dropped and the Install card
// falls through to the "browser doesn't support" message on Chrome Android.
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    window.__deferredInstallPrompt = event
  })
  window.addEventListener('appinstalled', () => {
    window.__deferredInstallPrompt = null
  })
}

Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN || '',
  environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || 'development',
  release: import.meta.env.VITE_SENTRY_RELEASE || undefined,
  enabled: !!import.meta.env.VITE_SENTRY_DSN,
  tracesSampleRate: parseFloat(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || '0.2'),
  tracePropagationTargets: [/^\/api\//],
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
)
