import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App.jsx';
import { AuthProvider } from './hooks/useApi.js';
import { server } from './test/server.js';
import { buildUser } from './test/factories.js';
import * as pushSession from './pwa/pushSession.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

describe('App', () => {
  it('shows the sign-in page and cleanup error when an OAuth switch cannot stop old notifications', async () => {
    const replace = vi.spyOn(pushSession, 'replaceSessionToken').mockRejectedValue(
      new Error('Could not stop notifications on this device. Reconnect and try again.'),
    );
    window.history.replaceState({}, '', '/?token=another-account');
    try {
      renderApp();
      expect(await screen.findByRole('alert')).toHaveTextContent(/could not stop notifications/i);
      expect(screen.getByRole('button', { name: /^sign in$/i })).toBeEnabled();
      expect(replace).toHaveBeenCalledWith('another-account');
      expect(window.location.search).toBe('');
    } finally {
      replace.mockRestore();
      window.history.replaceState({}, '', '/');
    }
  });
  it('renders the loader while auth is bootstrapping', () => {
    // /auth/me/ never resolves — stays in loading state.
    server.use(
      http.get('*/api/auth/me/', () => new Promise(() => {})),
    );
    renderApp();
    expect(document.querySelector('.parchment-bg')).toBeTruthy();
  });

  it('renders the Login page when unauthenticated', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json({ detail: 'no' }, { status: 401 })),
      http.get('*/api/auth/google/login/', () => HttpResponse.json({})),
    );
    renderApp();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'The Abby Project' })).toBeInTheDocument(),
    );
  });

  it('renders the journal shell when authenticated', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
    );
    renderApp();
    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument());
    expect(document.title).toBe('Today — The Abby Project');
  });
});

describe('App — unknown routes', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('sends a signed-in user on an unknown URL back to Today instead of a blank screen', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
    );
    window.history.pushState({}, '', '/a-route-that-does-not-exist');

    renderApp();

    await waitFor(() => expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument());
    expect(window.location.pathname).toBe('/');
  });
});

describe('App — birthday celebration boot', () => {
  it('mounts BirthdayCelebrationModal when pending-celebration returns an entry', async () => {
    server.use(
      http.get('*/api/auth/me/', () =>
        HttpResponse.json(buildUser({ date_of_birth: '2011-04-21' })),
      ),
      http.get('*/api/chronicle/pending-celebration/', () =>
        HttpResponse.json({
          id: 9, kind: 'birthday', title: 'Turned 15',
          occurred_on: '2026-04-21', chapter_year: 2025,
          metadata: { gift_coins: 1500 },
        }),
      ),
    );
    renderApp();
    await waitFor(() => {
      expect(screen.getByRole('alertdialog', { name: /birthday/i })).toBeInTheDocument();
    });
  });

  it('does not mount modal when endpoint returns 204', async () => {
    server.use(
      http.get('*/api/auth/me/', () =>
        HttpResponse.json(buildUser({ date_of_birth: '2011-04-21' })),
      ),
      http.get('*/api/chronicle/pending-celebration/', () =>
        new HttpResponse(null, { status: 204 }),
      ),
    );
    renderApp();
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByRole('alertdialog', { name: /birthday/i })).toBeNull();
  });
});
