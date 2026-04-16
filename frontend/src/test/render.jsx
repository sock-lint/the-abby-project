import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../hooks/useApi.js';

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
 */
export function renderWithProviders(ui, options = {}) {
  const {
    route = '/',
    routePath,
    withAuth = true,
    ...rtlOptions
  } = options;

  const user = userEvent.setup();

  const WrappedUi = routePath ? (
    <Routes>
      <Route path={routePath} element={ui} />
    </Routes>
  ) : (
    ui
  );

  const Tree = (
    <MemoryRouter initialEntries={[route]}>
      {withAuth ? <AuthProvider>{WrappedUi}</AuthProvider> : WrappedUi}
    </MemoryRouter>
  );

  return { user, ...render(Tree, rtlOptions) };
}

// Re-export so callers don't import from two packages.
export * from '@testing-library/react';
export { userEvent };
