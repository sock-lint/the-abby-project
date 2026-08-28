import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../hooks/useApi.js';
import MockPulse from './pulse.jsx';

/**
 * renderWithProviders — single entry point for tests that need a React
 * tree shaped like the real app shell. Wraps children in MemoryRouter +
 * AuthProvider so useAuth() and react-router hooks (useParams, useLocation,
 * useNavigate) behave like production.
 *
 * options:
 *   route        — initial URL (default '/')
 *   routePath    — route pattern if the component uses useParams (e.g.
 *                   '/quests/ventures/:id')
 *   withAuth     — wrap in AuthProvider (default true). The provider fetches
 *                   /auth/me/ on mount, so pages that mount before tests
 *                   stub /auth/me/ will see a null user; provide a token
 *                   in localStorage before render if you need one.
 *   pulse        — seed the shared heartbeat (PulseProvider's context) with
 *                   a payload. Returns a ``beat(next)`` helper that
 *                   re-renders with a new heartbeat, which is how the toast
 *                   hooks are driven now that they derive from the pulse
 *                   instead of owning timers. See test/pulseFixtures.js.
 */
export function renderWithProviders(ui, options = {}) {
  const {
    route = '/',
    routePath,
    withAuth = true,
    pulse = null,
    ...rtlOptions
  } = options;

  const user = userEvent.setup();

  const buildTree = (currentPulse) => {
    const WrappedUi = routePath ? (
      <Routes>
        <Route path={routePath} element={ui} />
      </Routes>
    ) : (
      ui
    );
    const withPulse = <MockPulse pulse={currentPulse}>{WrappedUi}</MockPulse>;
    return (
      <MemoryRouter initialEntries={[route]}>
        {withAuth ? <AuthProvider>{withPulse}</AuthProvider> : withPulse}
      </MemoryRouter>
    );
  };

  const view = render(buildTree(pulse), rtlOptions);
  // Re-render the WHOLE provider tree — a bare rerender(ui) would drop
  // AuthProvider and the router along with it.
  const beat = (next) => view.rerender(buildTree(next));

  return { user, beat, ...view };
}

// Re-export so callers don't import from two packages.
// eslint-disable-next-line react-refresh/only-export-components
export * from '@testing-library/react';
export { userEvent };
