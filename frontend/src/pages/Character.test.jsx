import { describe, expect, it, beforeEach, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Character from './Character.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
import { buildUser } from '../test/factories.js';
import { setToken } from '../api/client.js';

vi.mock('../components/avatar/AvatarPreview', () => ({ default: () => <div role="img" aria-label="Your Archer avatar" /> }));

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

vi.mock('../themes', async () => {
  const actual = await vi.importActual('../themes');
  return { ...actual, applyTheme: vi.fn() };
});
import { applyTheme } from '../themes';

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView — TomeShelf calls it whenever
  // activeId changes.
  Element.prototype.scrollIntoView = vi.fn();
  applyTheme.mockClear();
  try { window.localStorage.clear(); } catch { /* ignore */ }
  setToken('character-test-session');
});

function stubRoutes({
  profile = {},
  cosmetics = {},
  catalog = {},
  badges = [],
  summary = { badges_earned: [] },
  user = buildUser(),
} = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    http.get('*/api/character/', () => HttpResponse.json(profile)),
    http.get('*/api/cosmetics/', () => HttpResponse.json(cosmetics)),
    http.get('*/api/cosmetics/catalog/', () => HttpResponse.json(catalog)),
    http.get('*/api/badges/', () => HttpResponse.json(badges)),
    http.get('*/api/achievements/summary/', () => HttpResponse.json(summary)),
  );
}

function renderPage() {
  return renderWithProviders(<Character />);
}

describe('Character (/sigil)', () => {
  it('keeps earlier accessories in a saved collection without an equip claim and allows clearing a previous selection', async () => {
    const user = userEvent.setup();
    const hat = { id: 90, name: 'Party Hat', icon: '🎩', rarity: 'common', catalog_available: false };
    const remove = vi.fn(() => HttpResponse.json({ ok: true }));
    stubRoutes({ profile: { display_name: 'Abby', level: 1, active_pet_accessory: hat }, cosmetics: { active_pet_accessory: [hat] }, catalog: { active_pet_accessory: [hat] } });
    server.use(http.post('*/api/character/unequip/', remove));
    renderPage();
    expect(await screen.findByRole('region', { name: 'Saved collection' })).toBeInTheDocument();
    expect(screen.getByText('Party Hat')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Pet Accessories/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Party Hat.*equip/ })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Remove previous selection' }));
    await waitFor(() => expect(remove).toHaveBeenCalled());
  });
  it('keeps profile focused on avatar customization and links to pets separately', async () => {
    stubRoutes({ profile: { display_name: 'Abby', level: 2 } });
    const stableSpy = vi.fn(() => HttpResponse.json({ pets: [], mounts: [] }));
    server.use(http.get('*/api/pets/stable/', stableSpy));
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Your look' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit account & settings' })).toHaveAttribute('href', '/settings');
    expect(screen.getByRole('link', { name: 'My pets' })).toHaveAttribute('href', '/bestiary');
    expect(screen.getByRole('heading', { name: 'Your character' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Customize character' })).toBeInTheDocument();
    expect(stableSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Show 3D view' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Say hello' })).toBeNull();
  });

  it('keeps parent pet navigation and does not show child wellbeing controls', async () => {
    stubRoutes({ profile: { display_name: 'Parent', level: 2 }, user: buildUser({ role: 'parent' }) });
    renderPage();
    expect(await screen.findByRole('link', { name: 'My pets' })).toHaveAttribute('href', '/bestiary');
    expect(screen.queryByRole('link', { name: 'View companion home' })).toBeNull();
    expect(screen.queryByText('How are you feeling?')).toBeNull();
  });

  it('renders the frontispiece with display name, level chip, and trophy slot', async () => {
    stubRoutes({
      profile: {
        display_name: 'Abby', username: 'abby', level: 3,
        login_streak: 5, longest_login_streak: 10, perfect_days_count: 2,
        active_trophy_badge: null, active_frame: null, active_title: null,
      },
      cosmetics: {
        active_frame: [], active_title: [], active_theme: [], active_pet_accessory: [],
      },
      catalog: {
        active_frame: [], active_title: [], active_theme: [], active_pet_accessory: [],
      },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Abby' })).toBeInTheDocument(),
    );
    expect(screen.getByText(/level 3/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /no trophy badge/i })).toBeInTheDocument();
  });

  it('keeps editable profile collections to frames and titles', async () => {
    const user = userEvent.setup();
    stubRoutes({
      profile: {
        display_name: 'Abby', username: 'abby', level: 1,
        login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
        active_trophy_badge: null,
      },
      cosmetics: {
        active_frame: [], active_title: [], active_theme: [], active_pet_accessory: [],
      },
      catalog: {
        active_frame: [], active_title: [], active_theme: [], active_pet_accessory: [],
      },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('tablist', { name: /profile collections/i })).toBeInTheDocument(),
    );
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.queryByRole('tab', { name: /Journal Covers/i })).toBeNull();

    // Frames is the first chapter, so its folio opens by default.
    expect(screen.getByRole('region', { name: 'Frames' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Titles' })).toBeNull();

    // Switching spines swaps the rendered chapter.
    await user.click(screen.getByRole('tab', { name: /Titles/i }));
    expect(screen.getByRole('region', { name: 'Titles' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Frames' })).toBeNull();
  });

  it('equips an owned cosmetic', async () => {
    const user = userEvent.setup();
    const equipSpy = vi.fn(() => HttpResponse.json({ ok: true }));
    stubRoutes({
      profile: {
        display_name: 'Abby', username: 'abby', level: 1,
        login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
        active_trophy_badge: null,
      },
      cosmetics: {
        active_frame: [{ id: 1, name: 'Gold Frame', icon: '\ud83d\uddbc', rarity: 'rare' }],
        active_title: [], active_theme: [], active_pet_accessory: [],
      },
      catalog: {
        active_frame: [{ id: 1, name: 'Gold Frame', icon: '\ud83d\uddbc', rarity: 'rare' }],
        active_title: [], active_theme: [], active_pet_accessory: [],
      },
    });
    server.use(http.post('*/api/character/equip/', equipSpy));
    renderPage();
    await waitFor(() => expect(screen.getByText(/gold frame/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /Gold Frame.*click to equip/i }));
    await waitFor(() => expect(equipSpy).toHaveBeenCalled());
  });

  it('summarizes the saved color theme and links to the single Settings picker', async () => {
    const equip = vi.fn(() => HttpResponse.json({ ok: true }));
    const unequip = vi.fn(() => HttpResponse.json({ ok: true }));
    stubRoutes({
      profile: { display_name: 'Abby', active_theme: { id: 3, name: 'Vigil Cover' } },
      cosmetics: { active_theme: [{ id: 3, name: 'Vigil Cover', metadata: { theme: 'vigil' } }] },
      user: buildUser({ theme: 'vigil' }),
    });
    server.use(http.post('*/api/character/equip/', equip), http.post('*/api/character/unequip/', unequip));
    renderPage();
    expect(await screen.findByText('Twilight Meadow')).toBeInTheDocument();
    expect(screen.getByText(/Color theme:/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Change color theme' })).toHaveAttribute('href', '/settings#appearance');
    expect(screen.queryByRole('tab', { name: /Journal Covers/i })).toBeNull();
    expect(equip).not.toHaveBeenCalled();
    expect(unequip).not.toHaveBeenCalled();
    expect(applyTheme).not.toHaveBeenCalled();
  });

  it('shows the account profile picture alongside the separate character controls', async () => {
    stubRoutes({ profile: { display_name: 'Abby' }, user: buildUser({ avatar: '/media/avatars/abby.png' }) });
    renderPage();
    expect(await screen.findByRole('img', { name: 'Your profile picture' })).toHaveAttribute('src', '/media/avatars/abby.png');
    expect(screen.getByRole('button', { name: 'Change picture' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Your character' })).toBeInTheDocument();
  });

  it('surfaces an error when equip fails', async () => {
    const user = userEvent.setup();
    stubRoutes({
      profile: {
        display_name: 'Abby', username: 'abby', level: 1,
        login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
        active_trophy_badge: null,
      },
      cosmetics: {
        active_frame: [],
        active_title: [{ id: 7, name: 'Adept', icon: '\ud83d\udc51', rarity: 'common' }],
        active_theme: [], active_pet_accessory: [],
      },
      catalog: {
        active_frame: [],
        active_title: [{ id: 7, name: 'Adept', icon: '\ud83d\udc51', rarity: 'common' }],
        active_theme: [], active_pet_accessory: [],
      },
    });
    server.use(
      http.post('*/api/character/equip/', () =>
        HttpResponse.json({ error: 'not owned' }, { status: 400 }),
      ),
    );
    renderPage();
    // Default chapter is Frames; switch to Titles so the Adept cosmetic
    // becomes visible (and equip-clickable).
    await waitFor(() =>
      expect(screen.getByRole('tablist', { name: /profile collections/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /Titles/i }));
    await waitFor(() => expect(screen.getByText('Adept')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /Adept.*click to equip/i }));
    await waitFor(() => expect(screen.getByText(/not owned/i)).toBeInTheDocument());
  });

  it('opens the trophy picker when the hero slot is clicked', async () => {
    const user = userEvent.setup();
    stubRoutes({
      profile: {
        display_name: 'Abby', username: 'abby', level: 1,
        login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
        active_trophy_badge: null,
      },
      cosmetics: {
        active_frame: [], active_title: [], active_theme: [], active_pet_accessory: [],
      },
      catalog: {
        active_frame: [], active_title: [], active_theme: [], active_pet_accessory: [],
      },
      badges: [
        { id: 1, name: 'First Project', rarity: 'common', icon: '\ud83e\udd47', criterion_type: 'first_project' },
      ],
      summary: {
        badges_earned: [
          { badge: { id: 1, name: 'First Project', rarity: 'common', icon: '\ud83e\udd47', criterion_type: 'first_project' }, earned_at: '2026-04-01' },
        ],
      },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /no trophy badge/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /no trophy badge/i }));
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /choose your trophy badge/i })).toBeInTheDocument(),
    );
  });
});
