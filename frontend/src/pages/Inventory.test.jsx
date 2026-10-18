import { describe, expect, it, beforeEach, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import Inventory from './Inventory.jsx';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { selectDropdown } from '../test/selectDropdown.js';

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView — TomeShelf calls it whenever
  // activeId changes (on mount and after every spine click).
  Element.prototype.scrollIntoView = vi.fn();
  try { window.localStorage.clear(); } catch { /* ignore */ }
});

function renderInventory() {
  return render(
    <MemoryRouter initialEntries={['/treasury?tab=satchel']}>
      <Routes>
        <Route path="/treasury" element={<Inventory />} />
        <Route path="/trials" element={<div>Trials destination</div>} />
        <Route path="/sigil" element={<div>Sigil destination</div>} />
        <Route path="/settings" element={<div>Settings appearance destination</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Inventory', () => {
  it('filters rare rewards and sorts by rarity or the server update time', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 1, quantity: 1, updated_at: '2026-10-16T10:00:00Z', item: { id: 1, name: 'Common frame', item_type: 'cosmetic_frame', rarity: 'common', icon: '🖼️' } },
      { id: 2, quantity: 1, updated_at: '2026-10-17T10:00:00Z', item: { id: 2, name: 'Rare frame', item_type: 'cosmetic_frame', rarity: 'rare', icon: '🖼️' } },
      { id: 3, quantity: 1, updated_at: '2026-10-15T10:00:00Z', item: { id: 3, name: 'Legendary frame', item_type: 'cosmetic_frame', rarity: 'legendary', icon: '🖼️' } },
    ])));
    const user = userEvent.setup();
    renderInventory();
    await screen.findByText('Rare frame');
    const names = () => screen.getAllByText(/^(Common|Rare|Legendary) frame$/).map((node) => node.textContent);
    expect(names()).toEqual(['Rare frame', 'Common frame', 'Legendary frame']);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Rarity' }), 'rare');
    expect(screen.queryByText('Common frame')).toBeNull();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Sort items' }), 'rarity');
    expect(names()).toEqual(['Legendary frame', 'Rare frame']);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Rarity' }), 'all');
    expect(names()).toEqual(['Legendary frame', 'Rare frame', 'Common frame']);
  });

  it('can clear a rarity filter that hides every item', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 1, quantity: 1, item: { id: 1, name: 'Common frame', item_type: 'cosmetic_frame', rarity: 'common' } },
    ])));
    const user = userEvent.setup();
    renderInventory();
    await screen.findByText('Common frame');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Rarity' }), 'rare');
    expect(screen.queryByText('Common frame')).toBeNull();
    await user.click(screen.getByRole('button', { name: /clear filter/i }));
    expect(await screen.findByText('Common frame')).toBeInTheDocument();
  });

  it('explains a pouch from its server metadata before opening it', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 1, quantity: 1, item: { id: 1, name: 'Coin pouch', item_type: 'coin_pouch', rarity: 'rare', metadata: { coins: 75 }, effect_summary: 'Open to collect 75 coins.' } },
    ])));
    renderInventory();
    expect(await screen.findByText('Open to collect 75 coins.')).toBeInTheDocument();
  });

  it('identifies stored eggs as the first stage of their declared family', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 1, quantity: 2, item: { id: 1, name: 'Fox Egg', pet_species_name: 'Fox', lifecycle_stage: 'egg', item_type: 'egg', rarity: 'common', icon: '🥚' } },
    ])));
    renderInventory();
    expect(await screen.findByText('Egg stage · Fox family')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Feed' })).toBeNull();
  });

  it('uses the same theme name as Settings and routes its action to Appearance', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 9, quantity: 1, item: { id: 9, name: 'Hyrule Day', item_type: 'cosmetic_theme', rarity: 'common', icon: '📖', metadata: { theme: 'hyrule' } }, available_actions: [{ id: 'equip', label: 'Change color theme', to: '/settings#appearance' }] },
    ])));
    const user = userEvent.setup();
    renderInventory();
    expect(await screen.findByText('Memory Meadow')).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox', { name: /filter inventory/i }), 'Memory Meadow');
    expect(screen.getByText('Memory Meadow')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Change color theme' }));
    expect(await screen.findByText('Settings appearance destination')).toBeInTheDocument();
  });
  it('keeps unsupported eggs and accessories as stored items without hatch or equip actions', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 1, quantity: 2, item: { id: 1, name: 'Earlier Egg', item_type: 'egg', rarity: 'common', icon: '🥚', catalog_available: false }, available_actions: [{ id: 'hatch', label: 'Hatch', to: '/bestiary?tab=hatchery' }] },
      { id: 2, quantity: 1, item: { id: 2, name: 'Party Hat', item_type: 'cosmetic_pet_accessory', rarity: 'common', icon: '🎩', catalog_available: false }, available_actions: [{ id: 'equip', label: 'Equip', to: '/sigil' }] },
    ])));
    renderInventory();
    expect(await screen.findByRole('heading', { name: 'Saved collection' })).toBeInTheDocument();
    expect(screen.getByText('Earlier Egg')).toBeInTheDocument();
    expect(screen.getByText('Party Hat')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hatch' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Equip' })).toBeNull();
  });
  it('renders empty state when satchel is empty', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([])));
    renderInventory();
    await waitFor(() =>
      expect(screen.getAllByText((t) => /empty|satchel|no items/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('groups items by type', async () => {
    server.use(
      http.get('*/api/inventory/', () =>
        HttpResponse.json([
          { id: 1, quantity: 2, item: { id: 1, name: 'Ember Egg', item_type: 'egg', rarity: 'common', sprite_key: 'big-egg', icon: '🥚' } },
          { id: 2, quantity: 1, item: { id: 2, name: 'Fire Potion', item_type: 'potion', rarity: 'rare', sprite_key: 'potion-normal-red', icon: '🧪' } },
        ]),
      ),
    );
    renderInventory();
    // Eggs H2 = active compartment header; Potions spine = on the shelf.
    // Use heading + tab role queries to disambiguate from spine titles.
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Eggs' })).toBeInTheDocument(),
    );
    expect(screen.getByRole('tab', { name: /Potions/i })).toBeInTheDocument();
    expect(screen.getByText('Ember Egg')).toBeInTheDocument();
  });

  it('filters items by name when the user types in the search', async () => {
    server.use(
      http.get('*/api/inventory/', () =>
        HttpResponse.json([
          { id: 1, quantity: 2, item: { id: 1, name: 'Ember Egg', item_type: 'egg', rarity: 'common', sprite_key: 'big-egg', icon: '🥚' } },
          { id: 2, quantity: 1, item: { id: 2, name: 'Fire Potion', item_type: 'potion', rarity: 'rare', sprite_key: 'potion-normal-red', icon: '🧪' } },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderInventory();
    await waitFor(() => expect(screen.getByText('Ember Egg')).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter inventory/i });
    await user.type(search, 'potion');

    expect(screen.queryByText('Ember Egg')).not.toBeInTheDocument();
    expect(screen.getByText('Fire Potion')).toBeInTheDocument();
  });

  it('shows a Use button on consumables and fires the right endpoint', async () => {
    const freeze = {
      id: 42,
      quantity: 1,
      item: {
        id: 7,
        name: 'Streak Freeze',
        item_type: 'consumable',
        rarity: 'rare',
        sprite_key: 'magic-ice-1',
        icon: '❄️',
      },
      available_actions: [{ id: 'use', label: 'Use' }],
    };
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([freeze])));

    const use = spyHandler('post', /\/api\/inventory\/7\/use\/$/, {
      item_id: 7, item_name: 'Streak Freeze', effect: 'streak_freeze',
    });
    server.use(use.handler);

    const user = userEvent.setup();
    renderInventory();
    const button = await screen.findByRole('button', { name: /use/i });
    await user.click(button);

    await waitFor(() => expect(use.calls).toHaveLength(1));
    expect(use.calls[0].url).toMatch(/\/api\/inventory\/7\/use\/$/);
    expect(use.calls[0].method).toBe('POST');
  });

  it.each([
    ['mystery_box', 'A surprise item was added to your Inventory.'],
    ['food_basket', 'Food was added to your Inventory.'],
  ])('names Inventory in the %s receipt', async (effect, message) => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 42, quantity: 1, item: { id: 7, name: 'Gift', item_type: 'consumable', rarity: 'common', icon: '🎁' }, available_actions: [{ id: 'use', label: 'Use' }] },
    ])));
    const use = spyHandler('post', /\/api\/inventory\/7\/use\/$/, { item_id: 7, item_name: 'Gift', effect });
    server.use(use.handler);
    const user = userEvent.setup();
    renderInventory();
    await user.click(await screen.findByRole('button', { name: 'Use' }));
    expect(await screen.findByText(`Used Gift. ${message}`)).toBeInTheDocument();
    expect(use.calls).toHaveLength(1);
  });

  it('does not show a Use button on non-consumable items', async () => {
    server.use(
      http.get('*/api/inventory/', () =>
        HttpResponse.json([
          { id: 1, quantity: 1, item: { id: 1, name: 'Ember Egg', item_type: 'egg', rarity: 'common', sprite_key: 'big-egg', icon: '🥚' } },
        ]),
      ),
    );
    renderInventory();
    await waitFor(() => expect(screen.getByText('Ember Egg')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /use/i })).toBeNull();
  });

  it('opens coin pouches through the inventory action endpoint', async () => {
    const pouch = {
      id: 5,
      quantity: 1,
      item: {
        id: 11,
        name: 'Small Coin Pouch',
        item_type: 'coin_pouch',
        rarity: 'common',
        sprite_key: 'money-purse',
        icon: '👛',
      },
      available_actions: [{ id: 'open', label: 'Open' }],
    };
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([pouch])));
    const open = spyHandler('post', /\/api\/inventory\/11\/open\/$/, {
      item_id: 11, item_name: 'Small Coin Pouch', coins_awarded: 5,
    });
    server.use(open.handler);

    const user = userEvent.setup();
    renderInventory();
    await user.click(await screen.findByRole('button', { name: /open/i }));

    await waitFor(() => expect(open.calls).toHaveLength(1));
    expect(open.calls[0].method).toBe('POST');
  });

  it('renders a TomeShelf with one spine per populated compartment and only the active one\'s grid', async () => {
    server.use(
      http.get('*/api/inventory/', () =>
        HttpResponse.json([
          { id: 1, quantity: 2, item: { id: 1, name: 'Ember Egg', item_type: 'egg', rarity: 'common', sprite_key: 'big-egg', icon: '🥚' } },
          { id: 2, quantity: 1, item: { id: 2, name: 'Fire Potion', item_type: 'potion', rarity: 'rare', sprite_key: 'potion-normal-red', icon: '🧪' } },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderInventory();

    await waitFor(() =>
      expect(screen.getByRole('tablist', { name: /inventory categories/i })).toBeInTheDocument(),
    );

    // Two spines (Eggs + Potions), Eggs active by default (first in TYPE_COMPARTMENTS).
    expect(screen.getAllByRole('tab')).toHaveLength(2);
    expect(screen.getByText('Ember Egg')).toBeInTheDocument();
    expect(screen.queryByText('Fire Potion')).toBeNull();

    // Switching the spine swaps which compartment's grid is rendered.
    await user.click(screen.getByRole('tab', { name: /Potions/i }));
    expect(screen.getByText('Fire Potion')).toBeInTheDocument();
    expect(screen.queryByText('Ember Egg')).toBeNull();
  });

  it('persists the active compartment to localStorage', async () => {
    server.use(
      http.get('*/api/inventory/', () =>
        HttpResponse.json([
          { id: 1, quantity: 2, item: { id: 1, name: 'Ember Egg', item_type: 'egg', rarity: 'common', sprite_key: 'big-egg', icon: '🥚' } },
          { id: 2, quantity: 1, item: { id: 2, name: 'Fire Potion', item_type: 'potion', rarity: 'rare', sprite_key: 'potion-normal-red', icon: '🧪' } },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderInventory();
    await waitFor(() =>
      expect(screen.getByRole('tablist', { name: /inventory categories/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /Potions/i }));
    expect(window.localStorage.getItem('atlas:satchel:active-compartment')).toBe('potion');
  });

  it('routes contextual actions to their owning pages', async () => {
    const scroll = {
      id: 6,
      quantity: 1,
      item: {
        id: 12,
        name: 'Trial Scroll',
        item_type: 'quest_scroll',
        rarity: 'rare',
        sprite_key: 'scroll',
        icon: '📜',
      },
      available_actions: [{ id: 'start_quest', label: 'Start trial', to: '/trials?scroll=12' }],
    };
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([scroll])));

    const user = userEvent.setup();
    renderInventory();
    await user.click(await screen.findByRole('button', { name: /start trial/i }));

    expect(await screen.findByText(/trials destination/i)).toBeInTheDocument();
  });
});
