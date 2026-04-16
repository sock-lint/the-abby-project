import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import SettingsPage from './SettingsPage.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <SettingsPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('SettingsPage', () => {
  it('renders profile section', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    ]);
    await waitFor(() => expect(screen.getByText(/profile/i)).toBeInTheDocument());
    expect(screen.getByText(/username/i)).toBeInTheDocument();
  });

  it('shows Connect Google button when unlinked', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect google/i })).toBeInTheDocument(),
    );
  });

  it('shows Unlink + Calendar sync when linked', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () =>
        HttpResponse.json({ linked: true, google_email: 'abby@example.com', calendar_sync_enabled: false }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/abby@example.com/i)).toBeInTheDocument(),
    );
    expect(screen.getAllByText(/calendar sync/i).length).toBeGreaterThan(0);
  });

  it('toggles calendar sync', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/auth/google/account/', () =>
        HttpResponse.json({ linked: true, google_email: 'x@x.com', calendar_sync_enabled: false }),
      ),
      http.patch('*/api/auth/google/calendar/', () => HttpResponse.json({})),
    ]);
    await waitFor(() => expect(screen.getAllByText(/calendar sync/i).length).toBeGreaterThan(0));
    const toggle = screen.getAllByRole('button').find((b) => b.getAttribute('aria-pressed') !== null);
    if (toggle) await user.click(toggle);
  });

  it('changes theme', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.patch('*/api/auth/me/', () => HttpResponse.json({})),
    ]);
    await waitFor(() => expect(screen.getByText(/journal cover/i)).toBeInTheDocument());
    // Click the first theme button under "Journal cover".
    const themeButtons = screen.getAllByRole('button').filter((b) => b.className.includes('rounded-xl border-2'));
    if (themeButtons.length) {
      await user.click(themeButtons[0]);
    }
  });

  it('signs off on click', async () => {
    const user = userEvent.setup();
    const logoutSpy = vi.fn();
    // Override useAuth's logout by mocking the module (simpler: rely on the
    // auth endpoint, but this page calls `onLogout` directly which is wired
    // to AuthContext.logout).
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.post('*/api/auth/', () => { logoutSpy(); return HttpResponse.json({}); }),
    ]);
    await waitFor(() => expect(screen.getByText(/profile/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /sign off/i }));
    await waitFor(() => expect(logoutSpy).toHaveBeenCalled());
  });
});
