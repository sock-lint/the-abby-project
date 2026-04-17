import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import SettingsPage from './SettingsPage.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
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

  it('PATCHes /api/auth/me/ with the picked cover slug on theme change', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('patch', /\/api\/auth\/me\/$/, {});
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      spy.handler,
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/journal cover/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /Pick Night Vigil cover/i }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ theme: 'vigil' });
    expect(spy.calls[0].url).toMatch(/\/api\/auth\/me\/$/);
  });

  it('marks the active cover with aria-pressed and a READING label', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.patch('*/api/auth/me/', () => HttpResponse.json({})),
    ]);
    await waitFor(() => expect(screen.getByText(/journal cover/i)).toBeInTheDocument());

    // Default cover is Hyrule Day (from buildUser theme fallback) — initially active.
    const hyrule = screen.getByRole('button', { name: /Pick Hyrule Day cover/i });
    const vigil = screen.getByRole('button', { name: /Pick Night Vigil cover/i });
    expect(hyrule).toHaveAttribute('aria-pressed', 'true');
    expect(vigil).toHaveAttribute('aria-pressed', 'false');

    // Switch to Night Vigil — aria-pressed + READING flip to the new tile.
    await user.click(vigil);
    expect(vigil).toHaveAttribute('aria-pressed', 'true');
    expect(hyrule).toHaveAttribute('aria-pressed', 'false');
    expect(vigil.textContent).toMatch(/reading/i);
    expect(hyrule.textContent).not.toMatch(/reading/i);
  });

  it('renders all 6 cover swatches with sample preview copy', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    ]);
    await waitFor(() => expect(screen.getByText(/journal cover/i)).toBeInTheDocument());
    const coverNames = [
      'Hyrule Day',
      'Night Vigil',
      'Sunlit Field',
      'Snowquill Tome',
      'Verdant Pages',
      'Harvest Folio',
    ];
    for (const name of coverNames) {
      expect(screen.getByRole('button', { name: new RegExp(`Pick ${name} cover`, 'i') })).toBeInTheDocument();
    }
    // Sample preview copy renders inside each swatch so users can eyeball
    // contrast before committing.
    expect(screen.getAllByText(/Ink the day's deeds here/i)).toHaveLength(6);
    expect(screen.getAllByText(/6 chapters opened/i)).toHaveLength(6);
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

  it('uploads an avatar via multipart PATCH /auth/me/', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('patch', /\/api\/auth\/me\/$/, buildUser({ avatar: '/media/avatars/me.png' }));
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      spy.handler,
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/profile/i)).toBeInTheDocument());

    const file = new File([new Uint8Array([137, 80, 78, 71])], 'me.png', { type: 'image/png' });
    // Target the hidden <input type="file"> sibling of the Upload avatar button.
    const fileInput = document.querySelector('input[type="file"][accept*="image"]');
    expect(fileInput).toBeTruthy();
    await user.upload(fileInput, file);
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/auth\/me\/$/);
    expect(spy.calls[0].method).toBe('PATCH');
  });

  it('shows Remove avatar button when user has an avatar set', async () => {
    // Register the avatar-having /auth/me/ handler BEFORE renderPage adds
    // its default — MSW picks the first matching handler in registration order.
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ avatar: '/media/avatars/x.png' }))),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <SettingsPage />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('button', { name: /change avatar/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /^remove$/i })).toBeInTheDocument();
  });
});
