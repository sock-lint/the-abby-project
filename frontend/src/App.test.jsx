import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App.jsx';
import { AuthProvider } from './hooks/useApi.js';
import { server } from './test/server.js';
import { buildUser } from './test/factories.js';

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
      expect(screen.getByText(/hyrule field notes/i)).toBeInTheDocument(),
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
    await waitFor(() => expect(screen.getByText(/today's entry/i)).toBeInTheDocument());
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
