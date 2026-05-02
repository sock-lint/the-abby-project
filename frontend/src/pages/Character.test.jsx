import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Character from './Character.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
import { buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
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
    expect(screen.getByRole('button', { name: /no hero seal/i })).toBeInTheDocument();
  });

  it('renders all four cosmetic chapters', async () => {
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
      expect(screen.getByRole('region', { name: 'Frames' })).toBeInTheDocument(),
    );
    expect(screen.getByRole('region', { name: 'Titles' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Journal Covers' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Pet Regalia' })).toBeInTheDocument();
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
      expect(screen.getByRole('button', { name: /no hero seal/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /no hero seal/i }));
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /choose your hero seal/i })).toBeInTheDocument(),
    );
  });
});
