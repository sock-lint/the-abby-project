import { describe, expect, it, vi } from 'vitest';
import { StrictMode } from 'react';
import { http, HttpResponse } from 'msw';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPage from './SettingsPage.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
import { spyHandler } from '../test/spy.js';
import { buildUser } from '../test/factories.js';
import { setToken } from '../api/client.js';
import { applyTheme, themes } from '../themes.js';
import * as apiFunctions from '../api/index.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    ...handlers,
    http.get('*/api/cosmetics/', () => HttpResponse.json({ active_theme: [] })),
  );
  return renderWithProviders(<SettingsPage />);
}

describe('SettingsPage', () => {
  it('does not equip the already selected theme again', async () => {
    const user = userEvent.setup();
    const spy = spyHandler('post', /\/api\/character\/equip\/$/, { slot: 'active_theme' });
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () => HttpResponse.json({ active_theme: [
        { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' }, rarity: 'common' },
      ] })),
      spy.handler,
    ]);
    const selected = await screen.findByRole('button', { name: /Choose Memory Meadow color theme/i });
    await user.click(selected);
    expect(spy.calls).toHaveLength(0);
  });

  it('does not present missing ownership while themes are loading', async () => {
    let finishLoading;
    const pending = new Promise((resolve) => { finishLoading = resolve; });
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', async () => {
        await pending;
        return HttpResponse.json({ active_theme: [] });
      }),
    ]);
    try {
      await screen.findByText('Username');
      expect(screen.getByText('Loading your color themes…')).toHaveAttribute('role', 'status');
      expect(screen.queryByText(/0 of 6 (covers|themes) owned/i)).not.toBeInTheDocument();
      expect(screen.queryAllByRole('img', { name: /not yet earned/i })).toHaveLength(0);
    } finally {
      finishLoading();
    }
  });

  it('prevents overlapping theme saves and restores the previous theme when a save fails', async () => {
    const user = userEvent.setup();
    let finishSaving;
    const pending = new Promise((resolve) => { finishSaving = resolve; });
    const requests = [];
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () => HttpResponse.json({ active_theme: [
        { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' } },
        { id: 102, name: 'Twilight Meadow', metadata: { theme: 'vigil' } },
        { id: 103, name: 'Honey Meadow', metadata: { theme: 'sunlit' } },
      ] })),
      http.post('*/api/character/equip/', async ({ request }) => {
        requests.push({ url: request.url, body: await request.json() });
        await pending;
        return HttpResponse.json({ detail: 'Try again later' }, { status: 503 });
      }),
    ]);
    const memory = await screen.findByRole('button', { name: /Choose Memory Meadow color theme/i });
    const twilight = screen.getByRole('button', { name: /Choose Twilight Meadow color theme/i });
    const honey = screen.getByRole('button', { name: /Choose Honey Meadow color theme/i });
    try {
      await waitFor(() => expect(twilight).toBeEnabled());
      await user.click(twilight);
      await waitFor(() => expect(requests).toHaveLength(1));
      expect(requests[0].body).toEqual({ item_id: 102 });
      expect(requests[0].url).toMatch(/\/api\/character\/equip\/$/);
      expect(memory).toBeDisabled();
      expect(twilight).toBeDisabled();
      expect(honey).toBeDisabled();
      await user.click(honey);
      expect(requests).toHaveLength(1);
    } finally {
      finishSaving();
    }
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again later');
    expect(memory).toHaveAttribute('aria-pressed', 'true');
    expect(twilight).toHaveAttribute('aria-pressed', 'false');
    expect(document.documentElement.style.getPropertyValue('--color-ink-page')).toBe(themes.hyrule.page);
    expect(honey).toBeEnabled();
  });

  it.each([200, 503])('ignores a late theme response after the account credential changes (%i)', async (status) => {
    const user = userEvent.setup();
    let finishSaving;
    const pending = new Promise((resolve) => { finishSaving = resolve; });
    const mutation = vi.spyOn(apiFunctions, 'equipCosmetic');
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () => HttpResponse.json({ active_theme: [
        { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' } },
        { id: 102, name: 'Twilight Meadow', metadata: { theme: 'vigil' } },
      ] })),
      http.post('*/api/character/equip/', async () => {
        await pending;
        return HttpResponse.json({ slot: 'active_theme', detail: 'Old account response' }, { status });
      }),
    ]);
    try {
      const twilight = await screen.findByRole('button', { name: /Choose Twilight Meadow color theme/i });
      await waitFor(() => expect(twilight).toBeEnabled());
      await user.click(twilight);
      expect(mutation).toHaveBeenCalledWith(102);
      // The replacement session owns its new palette while the old save finishes.
      act(() => {
        setToken('synthetic-replacement-account');
        applyTheme('snowquill');
      });
      await act(async () => {
        finishSaving();
        try { await mutation.mock.results[0].value; } catch { /* HTTP error tested below. */ }
      });
      expect(document.documentElement.style.getPropertyValue('--color-ink-page')).toBe(themes.snowquill.page);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    } finally {
      finishSaving();
      mutation.mockRestore();
    }
  });

  it('keeps unavailable saved themes owned without offering an equip action', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () => HttpResponse.json({ active_theme: [
        { id: 102, name: 'Twilight Meadow', metadata: { theme: 'vigil' }, catalog_available: false },
      ] })),
    ]);
    expect(await screen.findByRole('img', { name: /Twilight Meadow color theme .* saved, currently unavailable/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Choose Twilight Meadow color theme/i })).not.toBeInTheDocument();
    expect(screen.getByText(/1 of 6 themes owned/i)).toBeInTheDocument();
  });

  it('keeps failed ownership unknown and retries loading themes', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json({ detail: 'Unavailable' }, { status: 503 })
          : HttpResponse.json({ active_theme: [
            { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' }, rarity: 'common' },
          ] });
      }),
    ]);
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load your color themes/i);
    expect(screen.queryByText(/0 of 6 (covers|themes) owned/i)).not.toBeInTheDocument();
    expect(screen.queryAllByRole('img', { name: /not yet earned/i })).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: /retry color themes/i }));
    expect(await screen.findByRole('button', { name: /Choose Memory Meadow color theme/i })).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it('keeps a newer ownership result when an earlier StrictMode request fails late', async () => {
    let failFirstLoad;
    const pending = new Promise((_resolve, reject) => { failFirstLoad = reject; });
    const loads = vi.spyOn(apiFunctions, 'getCosmetics')
      .mockImplementationOnce(() => pending)
      .mockResolvedValue({ active_theme: [
        { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' } },
      ] });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    );
    try {
      renderWithProviders(<SettingsPage />, { wrapper: StrictMode });
      expect(loads).toHaveBeenCalledTimes(2);
      expect(await screen.findByRole('button', { name: /Choose Memory Meadow color theme/i })).toBeInTheDocument();
      await act(async () => {
        failFirstLoad(new Error('Old request failed'));
        try { await pending; } catch { /* The older failed request must be ignored. */ }
      });
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByText(/1 of 6 themes owned/i)).toBeInTheDocument();
    } finally {
      failFirstLoad(new Error('Old request failed'));
      loads.mockRestore();
    }
  });

  it('renders account details and sends profile editing to Profile', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    ]);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Account details' })).toBeInTheDocument());
    expect(screen.getByText(/username/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View profile' })).toHaveAttribute('href', '/sigil');
    expect(screen.queryByRole('button', { name: /avatar|picture/i })).not.toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Appearance' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Color theme' })).toBeInTheDocument();
  });

  it('opens the Appearance section from a direct color-theme link', async () => {
    const scroll = vi.spyOn(Element.prototype, 'scrollIntoView');
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/cosmetics/', () => HttpResponse.json({ active_theme: [] })),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    );
    try {
      renderWithProviders(<SettingsPage />, { route: '/settings#appearance' });
      await waitFor(() => expect(scroll).toHaveBeenCalledWith({ block: 'start' }));
      expect(scroll.mock.contexts.some((element) => element.id === 'appearance')).toBe(true);
    } finally {
      scroll.mockRestore();
    }
  });

  it('shows Connect Google button when unlinked', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /connect google/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/Apple Calendar \(\.ics\)/)).toHaveTextContent('one-time copies');
    expect(screen.getByText(/On a Mac/)).toHaveTextContent('File → Import');
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
    // ToggleField renders role="switch". Click it and assert aria-checked flipped.
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await user.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
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
            { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' }, rarity: 'common' },
            { id: 102, name: 'Twilight Meadow', metadata: { theme: 'vigil' }, rarity: 'rare' },
          ],
          active_frame: [], active_title: [], active_pet_accessory: [],
        }),
      ),
      spy.handler,
    );
    renderWithProviders(<SettingsPage />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Choose Twilight Meadow color theme/i })).toBeInTheDocument(),
    );
    await u.click(screen.getByRole('button', { name: /Choose Twilight Meadow color theme/i }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({ item_id: 102 });
    expect(spy.calls[0].url).toMatch(/\/api\/character\/equip\/$/);
  });

  it('marks the selected color theme with aria-pressed and a Selected label', async () => {
    const u = userEvent.setup();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_theme: [
            { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' }, rarity: 'common' },
            { id: 102, name: 'Twilight Meadow', metadata: { theme: 'vigil' }, rarity: 'rare' },
          ],
          active_frame: [], active_title: [], active_pet_accessory: [],
        }),
      ),
      http.post('*/api/character/equip/', () => HttpResponse.json({ slot: 'active_theme' })),
    );
    renderWithProviders(<SettingsPage />);

    // Default cover is Memory Meadow (from buildUser) — initially active.
    const hyrule = await screen.findByRole('button', { name: /Choose Memory Meadow color theme/i });
    const vigil = screen.getByRole('button', { name: /Choose Twilight Meadow color theme/i });
    expect(hyrule).toHaveAttribute('aria-pressed', 'true');
    expect(vigil).toHaveAttribute('aria-pressed', 'false');

    // Switch to Twilight Meadow — aria-pressed + READING flip to the new tile.
    await u.click(vigil);
    expect(vigil).toHaveAttribute('aria-pressed', 'true');
    expect(hyrule).toHaveAttribute('aria-pressed', 'false');
    await waitFor(() => expect(vigil.textContent).toMatch(/selected/i));
    expect(hyrule.textContent).not.toMatch(/selected/i);
  });

  it('renders all 6 covers — owned as buttons, un-owned as locked intaglios', async () => {
    renderPage([
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
      http.get('*/api/cosmetics/', () =>
        HttpResponse.json({
          active_theme: [
            { id: 101, name: 'Memory Meadow', metadata: { theme: 'hyrule' }, rarity: 'common' },
          ],
          active_frame: [], active_title: [], active_pet_accessory: [],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/themes owned/i)).toBeInTheDocument());

    // Hyrule is owned → renders as an interactive button.
    expect(screen.getByRole('button', { name: /Choose Memory Meadow color theme/i })).toBeInTheDocument();

    // The other 5 covers render as locked intaglios (``role="img"``).
    const lockedNames = ['Twilight Meadow', 'Honey Meadow', 'Cloud Meadow', 'Clover Meadow', 'Peach Meadow'];
    for (const name of lockedNames) {
      expect(
        screen.getByRole('img', { name: new RegExp(`${name} color theme .* not yet earned`, 'i') }),
      ).toBeInTheDocument();
      // The "Pick {name} cover" button DOES NOT exist for locked covers.
      expect(
        screen.queryByRole('button', { name: new RegExp(`Choose ${name} color theme`, 'i') }),
      ).not.toBeInTheDocument();
    }

    // Whisper line summarizes earn progress + links to the Frontispiece.
    expect(screen.getByText(/1 of 6 themes owned/i)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /view earned cosmetics/i }),
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
    await waitFor(() => expect(screen.getByText(/themes owned/i)).toBeInTheDocument());

    // No "Pick X cover" buttons exist — all 6 covers are locked.
    expect(screen.queryAllByRole('button', { name: /Choose .* color theme/i })).toHaveLength(0);
    expect(spy.calls).toHaveLength(0);
    expect(screen.getByText(/0 of 6 (covers|themes) owned/i)).toBeInTheDocument();
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
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Account details' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /sign out/i }));
    await waitFor(() => expect(logoutSpy).toHaveBeenCalled());
  });

  it('keeps parent account details and the family summary without picture controls', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ role: 'parent', avatar: '/media/avatars/saved.png', family: { name: 'Meadow family' } }))),
      http.get('*/api/auth/google/account/', () => HttpResponse.json({ linked: false })),
    );
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByText('Meadow family')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Account details' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View profile' })).toHaveAttribute('href', '/sigil');
    expect(screen.queryByRole('button', { name: /avatar|picture/i })).not.toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toBeNull();
  });

  it('renders a Google unlink failure as an ember alert, not a teal success note', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/auth/google/account/', () =>
        HttpResponse.json({ linked: true, google_email: 'x@x.com', calendar_sync_enabled: false }),
      ),
      http.delete('*/api/auth/google/account/', () =>
        HttpResponse.json({ detail: 'nope' }, { status: 500 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/x@x\.com/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /unlink google account/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/failed to unlink google account/i);
  });

  it('renders a calendar-toggle failure as an alert and leaves the toggle where it was', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/auth/google/account/', () =>
        HttpResponse.json({ linked: true, google_email: 'x@x.com', calendar_sync_enabled: false }),
      ),
      http.patch('*/api/auth/google/calendar/', () =>
        HttpResponse.json({ detail: 'nope' }, { status: 500 }),
      ),
    ]);
    await waitFor(() => expect(screen.getAllByText(/calendar sync/i).length).toBeGreaterThan(0));
    const toggle = screen.getByRole('switch');
    await user.click(toggle);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/failed to update calendar settings/i);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });
});
