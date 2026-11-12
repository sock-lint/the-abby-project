import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CodexSection from './CodexSection.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const ACTIVE_SECTION_KEY = 'manage:codex:active-section';

beforeEach(() => {
  // The active-section key is sticky via localStorage; clear it so each
  // case starts on the default Items spine unless it pre-seeds otherwise.
  window.localStorage.removeItem(ACTIVE_SECTION_KEY);
});

describe('CodexSection', () => {
  it('shows no deadline in an untimed catalog challenge detail', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([
        { id: 67, name: 'Reading Companion', quest_type: 'collection', quest_type_display: 'Activity count', target_value: 3, duration_days: null, icon: '📖' },
      ])),
    );
    const user = userEvent.setup();
    render(<CodexSection />);
    await user.click(await screen.findByRole('tab', { name: /Challenges/ }));
    await user.click(await screen.findByRole('button', { name: /Reading Companion/ }));
    const detail = screen.getByRole('dialog', { name: 'Reading Companion' });
    expect(within(detail).getByText('No deadline')).toBeInTheDocument();
    expect(within(detail).queryByText(/^days$/)).not.toBeInTheDocument();
  });

  it('renders with empty catalogs', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);
    // The shelf renders even with empty catalogs; assert the
    // shelf is the navigation surface.
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /Items/ })).toBeInTheDocument(),
    );
  });

  it('renders with a populated item catalog', async () => {
    server.use(
      http.get('*/api/items/catalog/', () =>
        HttpResponse.json([
          { slug: 'gold-coin', name: 'Gold Coin', item_type: 'coin_pouch', rarity: 'common', icon: '🪙', sprite_key: 'gold-coin-stack', description: 'Shiny' },
        ]),
      ),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);
    await waitFor(() => expect(screen.getByText(/gold coin/i)).toBeInTheDocument());
  });

  it('shows the seven original pouch artworks without duplicate payout-version cards', async () => {
    const pouches = [
      ['pouch-small', 'Small Coin Pouch', 'common', '1 Coin'],
      ['pouch-rupee', 'Loose Rupee', 'common', '2 Coins'],
      ['pouch-medium', 'Medium Coin Pouch', 'uncommon', '3 Coins'],
      ['pouch-large', 'Large Coin Pouch', 'rare', '10 Coins'],
      ['pouch-gold', 'Gold Stack', 'epic', '20 Coins'],
      ['pouch-treasure', 'Treasure Hoard', 'legendary', '50 Coins'],
      ['pouch-mega', 'Mega Hoard', 'legendary', '100 Coins'],
    ];
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json(pouches.flatMap(
        ([slug, name, rarity, amount], index) => [
          { id: index * 2 + 1, slug, name, item_type: 'coin_pouch', rarity, icon: '🪙', coin_value: 5 },
          { id: index * 2 + 2, slug: `${slug}-v2`, name: `${name} (${amount})`, item_type: 'coin_pouch', rarity, icon: '🪙' },
        ],
      ))),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    render(<CodexSection />);

    await screen.findByText('Small Coin Pouch');
    for (const [, name, , amount] of pouches) {
      expect(screen.getByText(name)).toBeInTheDocument();
      expect(screen.queryByText(`${name} (${amount})`)).not.toBeInTheDocument();
    }
    expect(screen.getByRole('tab', { name: 'Items, 7 entries' })).toBeInTheDocument();
    const group = screen.getByRole('heading', { name: 'Coin Pouches' }).parentElement;
    expect(within(group).getByText('(7)')).toBeInTheDocument();
    expect(screen.getAllByText('×7')).toHaveLength(2);

    await user.click(screen.getByRole('button', { name: /Small Coin Pouch/ }));
    const detail = screen.getByRole('dialog', { name: 'Small Coin Pouch' });
    expect(within(detail).getByText('5 coins')).toBeInTheDocument();
  });

  it('keeps custom amount-labeled pouches and other versioned items in the catalog', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([
        { id: 101, slug: 'pouch-custom-v2', name: 'Special Pouch (7 Coins)', item_type: 'coin_pouch', rarity: 'common', icon: '🪙' },
        { id: 102, slug: 'food-berry-v2', name: 'Fresh Berry', item_type: 'food', rarity: 'common', icon: '🫐' },
      ])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);

    expect(await screen.findByRole('tab', { name: 'Items, 2 entries' })).toBeInTheDocument();
    expect(screen.getByText('Special Pouch (7 Coins)')).toBeInTheDocument();
    expect(screen.getByText('Fresh Berry')).toBeInTheDocument();
  });

  it('uses the current color-theme name in catalog cards and their details', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([
        { id: 12, name: 'Night Vigil', item_type: 'cosmetic_theme', rarity: 'rare', icon: 'T', metadata: { theme: 'vigil' }, type_display: 'Dashboard Theme' },
      ])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    render(<CodexSection />);
    expect(await screen.findByRole('heading', { name: 'Color themes' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Twilight Meadow/ }));
    const detail = screen.getByRole('dialog', { name: 'Twilight Meadow' });
    expect(within(detail).getByText(/Color theme/)).toBeInTheDocument();
    expect(screen.queryByText('Night Vigil')).not.toBeInTheDocument();
    expect(screen.queryByText(/Dashboard Theme/)).not.toBeInTheDocument();
  });

  it('shows the four content sections without a Sprites section or admin request', async () => {
    const sprites = spyHandler('get', /\/api\/sprites\/admin\/$/, []);
    server.use(
      sprites.handler,
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /Items/ })).toBeInTheDocument(),
    );
    for (const label of ['Items', 'Pet species', 'Grown pets', 'Challenges']) {
      expect(screen.getByRole('tab', { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(screen.getAllByRole('tab')).toHaveLength(4);
    expect(screen.queryByRole('tab', { name: /Sprites/ })).not.toBeInTheDocument();
    expect(sprites.calls).toHaveLength(0);
  });

  it('falls back to Items when the retired Sprites section was remembered', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    window.localStorage.setItem(ACTIVE_SECTION_KEY, 'sprites');
    render(<CodexSection />);

    expect(await screen.findByRole('heading', { name: 'Items' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Items/ })).toHaveAttribute('aria-selected', 'true');
    expect(window.localStorage.getItem(ACTIVE_SECTION_KEY)).toBe('items');
  });

  it('opens grown-pet artwork details without a generation shortcut', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([
        { id: 1, name: 'Fox', sprite_key: 'fox', icon: '🦊', available_potions: [] },
      ])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    render(<CodexSection />);
    await user.click(await screen.findByRole('tab', { name: /Grown pets/ }));
    await user.click(screen.getByRole('button', { name: /Fox/ }));
    const detail = screen.getByRole('dialog', { name: 'Fox mount' });
    expect(within(detail).queryByRole('button', { name: /regenerate/i })).not.toBeInTheDocument();
    expect(within(detail).getByText('fox-mount')).toBeInTheDocument();
  });

  it('restores the previously-active section from localStorage on mount', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    window.localStorage.setItem(ACTIVE_SECTION_KEY, 'creatures');

    render(<CodexSection />);

    expect(await screen.findByRole('heading', { name: 'Pet species' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Pet species/ })).toHaveAttribute('aria-selected', 'true');
    expect(window.localStorage.getItem(ACTIVE_SECTION_KEY)).toBe('creatures');
  });
});
