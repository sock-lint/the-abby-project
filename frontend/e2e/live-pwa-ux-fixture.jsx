import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../src/hooks/useApi';
import { STORAGE_KEYS } from '../src/constants/storage';
import { PwaStatusProvider } from '../src/pwa/PwaStatusProvider';
import { PwaStatusContext, usePwaStatus } from '../src/pwa/pwaStatus.context';
import UpdateBanner from '../src/pwa/UpdateBanner';
import ProjectNew from '../src/pages/ProjectNew';
import Manage from '../src/pages/Manage';
import '../src/index.css';

// Synthetic credential stays on the loopback fixture origin. No real account,
// live configuration or deployed request is involved in these offline checks.
localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'offline-live-pwa-synthetic-token');

export default function FormBoundary({ children }) {
  const status = usePwaStatus();
  // Deliberate fixture damage models missing form guard registration. The
  // real provider, banner and domain form state stay mounted and unmodified.
  const missing = window.__abbyOfflinePwaFault === 'missing-guards'
    || (window.__abbyOfflinePwaFault === 'missing-modal-guard' && location.pathname === '/manage');
  const value = missing
    ? { ...status, registerUpdateGuard: () => {} }
    : status;
  return <PwaStatusContext.Provider value={value}>{children}</PwaStatusContext.Provider>;
}

createRoot(document.getElementById('root')).render(
  <BrowserRouter><AuthProvider><PwaStatusProvider>
    <UpdateBanner />
    <p data-testid="fixture-mode">{import.meta.env.MODE}</p>
    <FormBoundary><Routes>
      <Route path="/projects/new" element={<ProjectNew />} />
      <Route path="/manage" element={<Manage />} />
      <Route path="*" element={<Navigate to="/projects/new" replace />} />
    </Routes></FormBoundary>
  </PwaStatusProvider></AuthProvider></BrowserRouter>,
);
