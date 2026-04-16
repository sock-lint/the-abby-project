import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import Inventory from './Inventory.jsx';
import { server } from '../test/server.js';

describe('Inventory', () => {
  it('renders empty state when satchel is empty', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([])));
    render(<Inventory />);
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
    render(<Inventory />);
    await waitFor(() => expect(screen.getByText(/eggs/i)).toBeInTheDocument());
    expect(screen.getByText(/potions/i)).toBeInTheDocument();
    expect(screen.getByText('Ember Egg')).toBeInTheDocument();
  });
});
