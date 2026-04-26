import * as Sentry from '@sentry/react';
import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { useAuth } from './hooks/useApi';
import { applyTheme } from './themes';
import { getPendingCelebration } from './api';
import BirthdayCelebrationModal from './components/BirthdayCelebrationModal';
import { SpriteCatalogProvider } from './providers/SpriteCatalogProvider';
import JournalShell from './components/layout/JournalShell';
import { PwaStatusProvider } from './pwa/PwaStatusProvider';
import { InstallPromptProvider } from './pwa/useInstallPrompt';
import UpdateBanner from './pwa/UpdateBanner';
import OfflineReadyToast from './pwa/OfflineReadyToast';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ProjectDetail from './pages/ProjectDetail';
import ProjectNew from './pages/ProjectNew';
import ProjectIngest from './pages/ProjectIngest';
import ClockPage from './pages/ClockPage';
import Manage from './pages/Manage';
import ActivityPage from './pages/activity/ActivityPage';
import SettingsPage from './pages/SettingsPage';
import QuestsHub from './pages/quests';
import Trials from './pages/Trials';
import BestiaryHub from './pages/bestiary';
import Character from './pages/Character';
import TreasuryHub from './pages/treasury';
import AtlasHub from './pages/atlas';
import ChronicleHub from './pages/chronicle';
import DesignShowcase from './pages/__design';
import Loader from './components/Loader';

function ErrorFallback({ error, resetError }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center parchment-bg p-8 gap-4">
      <h1 className="font-display text-2xl text-ember-deep italic">Ink spilled.</h1>
      <p className="font-body text-ink-secondary text-sm max-w-sm text-center">
        {error?.message || 'An unexpected error occurred while rendering this page.'}
      </p>
      <button
        onClick={resetError}
        className="px-4 py-2 bg-sheikah-teal-deep text-ink-page-rune-glow rounded-lg font-medium hover:bg-sheikah-teal transition-colors"
      >
        Try again
      </button>
    </div>
  );
}

/**
 * Legacy route → new hub (with tab query) redirector. Any bookmark or
 * external link to the old flat routes keeps working.
 */
function LegacyRedirect({ to }) {
  return <Navigate to={to} replace />;
}

export default function App() {
  const { user, loading, login } = useAuth();
  const [celebration, setCelebration] = useState(null);

  useEffect(() => {
    if (user?.theme) applyTheme(user.theme);
    else applyTheme('hyrule');
  }, [user?.theme]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    getPendingCelebration()
      .then((res) => {
        if (cancelled) return;
        if (res && typeof res === 'object' && res.id) {
          setCelebration(res);
        }
      })
      .catch(() => {
        // 204 / unauthenticated / network — treat as nothing pending.
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  // Dev-only design showcase route bypasses auth so primitives can be QA'd
  // without a running backend. Matches the path before any other routing.
  if (typeof window !== 'undefined' && window.location.pathname === '/__design') {
    return (
      <Sentry.ErrorBoundary fallback={ErrorFallback} showDialog={false}>
        <DesignShowcase />
      </Sentry.ErrorBoundary>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center parchment-bg">
        <Loader />
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={login} />;
  }

  return (
    <Sentry.ErrorBoundary fallback={ErrorFallback} showDialog={false}>
      <InstallPromptProvider>
        <PwaStatusProvider>
          <UpdateBanner />
        {celebration && (
          <BirthdayCelebrationModal
            entry={celebration}
            onDismiss={() => setCelebration(null)}
          />
        )}
        <SpriteCatalogProvider>
          <BrowserRouter>
            <Routes>
            <Route element={<JournalShell />}>
              {/* Chapter I — Today */}
              <Route path="/" element={<Dashboard />} />

              {/* Chapter II — Quests (+ deep-link sub-routes for Projects) */}
              <Route path="/quests" element={<QuestsHub />} />
              <Route path="/quests/ventures/new" element={<ProjectNew />} />
              <Route path="/quests/ventures/ingest" element={<ProjectIngest />} />
              <Route path="/quests/ventures/:id" element={<ProjectDetail />} />

              {/* Trials — the adventure overlay (time-boxed boss/collection quests),
                  separated from the regular-cadence hub tabs. */}
              <Route path="/trials" element={<Trials />} />

              {/* Chapter III — Bestiary */}
              <Route path="/bestiary" element={<BestiaryHub />} />

              {/* Sigil — the user's character/identity page, surfaced via the avatar menu */}
              <Route path="/sigil" element={<Character />} />

              {/* Chapter IV — Treasury */}
              <Route path="/treasury" element={<TreasuryHub />} />

              {/* Chapter V — Atlas */}
              <Route path="/atlas" element={<AtlasHub />} />

              {/* Chapter VI — Chronicle (memoir: Sketchbook · Journal · Yearbook) */}
              <Route path="/chronicle" element={<ChronicleHub />} />

              {/* Utility */}
              <Route path="/clock" element={<ClockPage />} />
              <Route path="/manage" element={<Manage />} />
              <Route path="/activity" element={<ActivityPage />} />
              <Route path="/settings" element={<SettingsPage />} />

              {/* Legacy route redirects — keep old bookmarks working */}
              <Route path="/projects" element={<LegacyRedirect to="/quests?tab=ventures" />} />
              <Route path="/projects/new" element={<LegacyRedirect to="/quests/ventures/new" />} />
              <Route path="/projects/ingest" element={<LegacyRedirect to="/quests/ventures/ingest" />} />
              <Route path="/projects/:id" element={<LegacyRedirectWithId />} />
              <Route path="/chores" element={<LegacyRedirect to="/quests?tab=duties" />} />
              <Route path="/homework" element={<LegacyRedirect to="/quests?tab=study" />} />
              <Route path="/habits" element={<LegacyRedirect to="/quests?tab=rituals" />} />
              <Route path="/quests/trials" element={<LegacyRedirect to="/trials" />} />
              <Route path="/inventory" element={<LegacyRedirect to="/treasury?tab=satchel" />} />
              <Route path="/stable" element={<LegacyRedirect to="/bestiary?tab=companions" />} />
              <Route path="/character" element={<LegacyRedirect to="/sigil" />} />
              <Route path="/payments" element={<LegacyRedirect to="/treasury?tab=coffers" />} />
              <Route path="/timecards" element={<LegacyRedirect to="/treasury?tab=wages" />} />
              <Route path="/rewards" element={<LegacyRedirect to="/treasury?tab=bazaar" />} />
              <Route path="/achievements" element={<LegacyRedirect to="/atlas?tab=skills" />} />
              <Route path="/portfolio" element={<LegacyRedirect to="/chronicle?tab=sketchbook" />} />
              <Route path="/lorebook" element={<LegacyRedirect to="/atlas?tab=lorebook" />} />
              <Route path="/yearbook" element={<LegacyRedirect to="/chronicle?tab=yearbook" />} />
            </Route>
            </Routes>
          </BrowserRouter>
          <OfflineReadyToast />
        </SpriteCatalogProvider>
        </PwaStatusProvider>
      </InstallPromptProvider>
    </Sentry.ErrorBoundary>
  );
}

// Special-case /projects/:id → /quests/ventures/:id (needs useParams).
function LegacyRedirectWithId() {
  const { id } = useParams();
  return <Navigate to={`/quests/ventures/${id}`} replace />;
}
