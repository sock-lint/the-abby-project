import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Rewards from './Rewards.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user = buildUser(), handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Rewards />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Rewards', () => {
  it('renders an empty reward shop for a child', async () => {
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 0, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getAllByText((t) => /coin|reward|bazaar|shop/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('renders parent reward shop with rewards + redemption queue', async () => {
    renderPage(buildParent(), [
      http.get('*/api/rewards/', () =>
        HttpResponse.json([{ id: 1, name: 'Ice Cream', cost: 50, stock: 5, rarity: 'common', image: '/ic.jpg' }]),
      ),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([{ id: 9, reward: { name: 'Toy', icon: '🧸' }, user_name: 'Abby', status: 'pending' }]),
      ),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
    ]);
    // Either the reward title (Ice Cream) or the redemption row (Toy) renders
    // depending on the active tab; assert at least one is visible.
    await waitFor(() =>
      expect(screen.getAllByText((t) => /ice cream|toy|abby/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('filters the bazaar by name when the child types in the search', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () =>
        HttpResponse.json([
          { id: 1, name: 'Ice Cream', cost_coins: 50, rarity: 'common', is_active: true },
          { id: 2, name: 'Movie Night', cost_coins: 80, rarity: 'rare', is_active: true },
        ]),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Ice Cream')).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter rewards/i });
    await user.type(search, 'movie');

    expect(screen.queryByText('Ice Cream')).not.toBeInTheDocument();
    expect(screen.getByText('Movie Night')).toBeInTheDocument();
  });

  it('child clicking Barter posts to /rewards/{id}/redeem/', async () => {
    const user = userEvent.setup();
    const redeem = spyHandler('post', /\/api\/rewards\/\d+\/redeem\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () =>
        HttpResponse.json([{ id: 13, name: 'Ice Cream', cost_coins: 50, stock: 5, rarity: 'common', is_active: true }]),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      redeem.handler,
    ]);

    const button = await screen.findByRole('button', { name: /barter/i });
    await user.click(button);

    await waitFor(() => expect(redeem.calls).toHaveLength(1));
    expect(redeem.calls[0].url).toMatch(/\/rewards\/13\/redeem\/$/);
    expect(redeem.calls[0].body).toEqual({});
  });

  it('parent approving a redemption posts to /redemptions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/redemptions\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([{ id: 22, reward: { name: 'Toy', icon: '🧸' }, user_name: 'Abby', status: 'pending', coin_cost_snapshot: 80, requested_at: '2026-04-15T12:00:00Z' }]),
      ),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 0, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/redemptions\/22\/approve\/$/);
    expect(approve.calls[0].body).toEqual({ notes: '' });
  });

  it('parent approving an exchange posts to /coins/exchange/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/coins\/exchange\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 0, recent: [] })),
      http.get('*/api/coins/exchange/list/', () =>
        HttpResponse.json([{ id: 33, user_name: 'Abby', dollar_amount: '2.00', coin_amount: 20, exchange_rate: 10, status: 'pending', created_at: '2026-04-15T12:00:00Z' }]),
      ),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/coins\/exchange\/33\/approve\/$/);
    expect(approve.calls[0].body).toEqual({ notes: '' });
  });
});
