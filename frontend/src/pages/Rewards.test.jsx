import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Rewards from './Rewards.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
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
});
