import { describe, expect, it } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import Inventory from './Inventory.jsx';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';

function renderInventory() {
  return render(
    <MemoryRouter initialEntries={['/bestiary?tab=satchel']}>
      <Routes>
        <Route path="/bestiary" element={<Inventory />} />
        <Route path="/trials" element={<div>Trials destination</div>} />
        <Route path="/sigil" element={<div>Sigil destination</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Inventory', () => {
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
    await waitFor(() => expect(screen.getByText(/eggs/i)).toBeInTheDocument());
    expect(screen.getByText(/potions/i)).toBeInTheDocument();
    expect(screen.getByText('Ember Egg')).toBeInTheDocument();
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
