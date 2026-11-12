import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { delay, http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import * as Sentry from '@sentry/react';
import App from './App.jsx';
import { AuthProvider, DEFERRED_RECOVERY_DELAY_MS } from './hooks/useApi.js';
import { GATEWAY_RETRY_DELAY_MS } from './api/client.js';
import { server } from './test/server.js';
import { buildUser } from './test/factories.js';
import * as pushSession from './pwa/pushSession.js';
import { prepareGoogleCallback } from './test/googleAuthorization';
import avatarCatalog from '../../contracts/api/fixtures/avatar-catalog.json';
import defaultCharacter from '../../contracts/api/fixtures/character-avatar-default.json';

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

// Auth, routing and dashboard rendering can exceed RTL's 1s default under coverage.
const appReadyTimeout = 4000;

async function expectTodayReady() {
  expect(await screen.findByRole(
    'heading', { level: 1, name: 'Today' }, { timeout: appReadyTimeout },
  )).toBeInTheDocument();
}

describe('App', () => {
  it.each(['child', 'parent'])('opens the dedicated avatar editor directly for a signed-in %s', async (role) => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ role }))),
      http.get('*/api/notifications/pending-celebration/', () => new HttpResponse(null, { status: 204 })),
      http.get('*/api/character/', () => HttpResponse.json(defaultCharacter)),
      http.get('*/api/character/avatar/catalog/', () => HttpResponse.json(avatarCatalog)),
    );
    window.history.replaceState({}, '', '/profile/customize');
    try {
      renderApp();
      expect(await screen.findByRole('heading', { level: 1, name: 'Customize avatar' })).toBeInTheDocument();
      expect(window.location.pathname).toBe('/profile/customize');
      expect(document.title).toBe('Customize avatar — The Abby Project');
      expect(screen.getByRole('combobox', { name: 'Headwear' })).toHaveValue('none');
    } finally {
      window.history.replaceState({}, '', '/');
    }
  });

  it.each([
    ['/play/old-scene?legacy=1', '/bestiary'],
    ['/pets', '/bestiary'],
    ['/profile', '/sigil'],
  ])('keeps the %s bookmark inside the React app', async (path, destination) => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    window.history.replaceState({}, '', path);
    try {
      renderApp();
      await waitFor(() => expect(window.location.pathname).toBe(destination));
      expect(window.location.search).toBe('');
    } finally {
      window.history.replaceState({}, '', '/');
    }
  });

  it('drops retired Play credentials before authentication can replace the current account', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    const replace = vi.spyOn(pushSession, 'replaceSessionToken');
    window.history.replaceState({}, '', '/play/?token=synthetic-obsolete-token');
    try {
      renderApp();
      await waitFor(() => expect(window.location.pathname).toBe('/bestiary'));
      expect(window.location.search).toBe('');
      expect(replace).not.toHaveBeenCalled();
      expect(localStorage.getItem('abby_auth_token')).toBe('test-session');
    } finally {
      replace.mockRestore();
      window.history.replaceState({}, '', '/');
    }
  });

  it('shows the sign-in page and cleanup error when an OAuth switch cannot stop old notifications', async () => {
    const replace = vi.spyOn(pushSession, 'replaceSessionToken').mockRejectedValue(
      new Error('Could not stop notifications on this device. Reconnect and try again.'),
    );
    await prepareGoogleCallback();
    const exchanges = [];
    server.use(http.post('*/api/auth/google/exchange/', async ({ request }) => {
      exchanges.push({ body: await request.json(), auth: request.headers.get('authorization') });
      return HttpResponse.json({ mode: 'login', token: 'another-account', user: buildUser({ id: 22 }) });
    }));
    try {
      renderApp();
      expect(await screen.findByRole('alert')).toHaveTextContent(/could not stop notifications/i);
      expect(screen.getByRole('button', { name: /^sign in$/i })).toBeEnabled();
      expect(exchanges).toHaveLength(1);
      expect(exchanges[0].auth).toBeNull();
      expect(exchanges[0].body.code_verifier).toMatch(/^[A-Za-z0-9_-]{43}$/);
      expect(replace).toHaveBeenCalledWith('another-account', {
        expectedToken: 'test-session', isCurrent: expect.any(Function),
      });
      expect(window.location.search).toBe('');
      expect(window.location.hash).toBe('');
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
    await expectTodayReady();
    expect(document.title).toBe('Today — The Abby Project');
  }, 10000);
});

describe('App — unknown routes', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/');
  });

  it.each([
    { response: 'immediate', dashboardDelay: 0 },
    { response: 'slower than one second', dashboardDelay: 1500 },
  ])('sends a signed-in user on an unknown URL back to Today with $response dashboard data', async ({ dashboardDelay }) => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', async () => {
        await delay(dashboardDelay);
        return HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        });
      }),
    );
    window.history.pushState({}, '', '/a-route-that-does-not-exist');

    renderApp();

    await waitFor(() => expect(window.location.pathname).toBe('/'), { timeout: appReadyTimeout });
    await expectTodayReady();
    expect(window.location.pathname).toBe('/');
  }, 10000);
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

// THE-ABBY-PROJECT-40 (GitHub #345): the boot-time streak / Perfect Day
// celebration read answered an HTML 200 on both client attempts while a deploy
// swapped containers. It is a best-effort read, so the app waits out the rest
// of the window and reports only if the proxy is still failing.
describe('App — streak celebration read during a deploy window', () => {
  const html = () => new HttpResponse('<!doctype html><title>starting</title>', {
    status: 200, headers: { 'content-type': 'text/html' },
  });
  const perfectDay = {
    id: 31, notification_type: 'perfect_day', title: 'Perfect day', message: '',
  };
  let calls;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    calls = 0;
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the celebration without reporting when the proxy recovers after the client retry', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/notifications/pending-celebration/', () => {
        calls += 1;
        return calls <= 2 ? html() : HttpResponse.json(perfectDay);
      }),
    );
    renderApp();
    await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(calls).toBe(2));
    expect(Sentry.captureException).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS));
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(calls).toBe(3);
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('reports once, with both attempts counted, when the HTML persists', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/notifications/pending-celebration/', () => {
        calls += 1;
        return html();
      }),
    );
    renderApp();
    await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(calls).toBe(2));
    expect(Sentry.captureException).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS + GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(Sentry.captureException).toHaveBeenCalledTimes(1));
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'API 200 with non-JSON body: GET /notifications/pending-celebration/' }),
      { extra: expect.objectContaining({ status: 200, deferredRecoveryAttempts: 2 }) },
    );
    expect(calls).toBe(4);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('stops quietly when the app unmounts during the wait', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/notifications/pending-celebration/', () => {
        calls += 1;
        return html();
      }),
    );
    const { unmount } = renderApp();
    await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(calls).toBe(2));
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS * 2));
    expect(calls).toBe(2);
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });
});
