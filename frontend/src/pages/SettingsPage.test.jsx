import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPage from './SettingsPage.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
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
  return renderWithProviders(<SettingsPage />);
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

  // Cover unification (2026-05): the picker now routes through
  // ``equipCosmetic`` rather than ``updateMe({theme})``. Covers are
  // cosmetic_theme ``ItemDefinition`` rows; un-owned covers render as
  // locked intaglios with ``role="img"`` instead of clickable buttons.
  it('POSTs to /character/equip/ when picking an owned cover', async () => {
    const u = userEvent.setup();
    const spy = spyHandler('post', /\/api\/character\/equip\/$/, { slot: 'active_theme' });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_theme: [
            { id: 101, name: 'Hyrule Day', metadata: { theme: 'hyrule' }, rarity: 'common' },
            { id: 102, name: 'Night Vigil', metadata: { theme: 'vigil' }, rarity: 'rare' },
          ],
          active_frame: [], active_title: [], active_pet_accessory: [],
        }),
      ),
      spy.handler,
    );
    renderWithProviders(<SettingsPage />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Pick Night Vigil cover/i })).toBeInTheDocument(),
    );
    await u.click(screen.getByRole('button', { name: /Pick Night Vigil cover/i }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ item_id: 102 });
    expect(spy.calls[0].url).toMatch(/\/api\/character\/equip\/$/);
  });

  it('marks the active cover with aria-pressed and a READING label', async () => {
    const u = userEvent.setup();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_theme: [
            { id: 101, name: 'Hyrule Day', metadata: { theme: 'hyrule' }, rarity: 'common' },
            { id: 102, name: 'Night Vigil', metadata: { theme: 'vigil' }, rarity: 'rare' },
          ],
          active_frame: [], active_title: [], active_pet_accessory: [],
        }),
      ),
      http.post('*/api/character/equip/', () => HttpResponse.json({ slot: 'active_theme' })),
    );
    renderWithProviders(<SettingsPage />);

    // Default cover is Hyrule Day (from buildUser) — initially active.
    const hyrule = await screen.findByRole('button', { name: /Pick Hyrule Day cover/i });
    const vigil = screen.getByRole('button', { name: /Pick Night Vigil cover/i });
    expect(hyrule).toHaveAttribute('aria-pressed', 'true');
    expect(vigil).toHaveAttribute('aria-pressed', 'false');

    // Switch to Night Vigil — aria-pressed + READING flip to the new tile.
    await u.click(vigil);
    expect(vigil).toHaveAttribute('aria-pressed', 'true');
    expect(hyrule).toHaveAttribute('aria-pressed', 'false');
    expect(vigil.textContent).toMatch(/reading/i);
    expect(hyrule.textContent).not.toMatch(/reading/i);
  });

  it('renders all 6 covers — owned as buttons, un-owned as locked intaglios', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_theme: [
            { id: 101, name: 'Hyrule Day', metadata: { theme: 'hyrule' }, rarity: 'common' },
          ],
          active_frame: [], active_title: [], active_pet_accessory: [],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/journal cover/i)).toBeInTheDocument());

    // Hyrule is owned → renders as an interactive button.
    expect(screen.getByRole('button', { name: /Pick Hyrule Day cover/i })).toBeInTheDocument();

    // The other 5 covers render as locked intaglios (``role="img"``).
    const lockedNames = ['Night Vigil', 'Sunlit Field', 'Snowquill Tome', 'Verdant Pages', 'Harvest Folio'];
    for (const name of lockedNames) {
      expect(
        screen.getByRole('img', { name: new RegExp(`${name} cover .* not yet earned`, 'i') }),
      ).toBeInTheDocument();
      // The "Pick {name} cover" button DOES NOT exist for locked covers.
      expect(
        screen.queryByRole('button', { name: new RegExp(`Pick ${name} cover`, 'i') }),
      ).not.toBeInTheDocument();
    }

    // Whisper line summarizes earn progress + links to the Frontispiece.
    expect(screen.getByText(/1 of 6 covers bound/i)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /find more on your Frontispiece/i }),
    ).toBeInTheDocument();
  });

  it('does not call equip when a locked cover is rendered (no button to click)', async () => {
    const spy = spyHandler('post', /\/api\/character\/equip\/$/, {});
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_theme: [],  // No owned covers
          active_frame: [], active_title: [], active_pet_accessory: [],
        }),
      ),
      spy.handler,
    );
    renderWithProviders(<SettingsPage />);
    await waitFor(() => expect(screen.getByText(/journal cover/i)).toBeInTheDocument());

    // No "Pick X cover" buttons exist — all 6 covers are locked.
    expect(screen.queryAllByRole('button', { name: /Pick .* cover/i })).toHaveLength(0);
    expect(spy.calls).toHaveLength(0);
    expect(screen.getByText(/0 of 6 covers bound/i)).toBeInTheDocument();
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
    renderWithProviders(<SettingsPage />);
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
    renderWithProviders(<SettingsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: /change avatar/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /^remove$/i })).toBeInTheDocument();
  });
});
