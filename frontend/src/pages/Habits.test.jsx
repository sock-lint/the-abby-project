import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Habits from './Habits.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildUser } from '../test/factories.js';

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
        <Habits />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Habits', () => {
  it('renders empty state when no habits', async () => {
    renderPage(buildUser(), [
      http.get('*/api/habits/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText((t) => /no habits/i.test(t))).toBeInTheDocument(),
    );
  });

  it('renders a habit row', async () => {
    renderPage(buildUser(), [
      http.get('*/api/habits/', () =>
        HttpResponse.json([
          { id: 1, name: 'Read 20 min', icon: '📖', habit_type: 'positive', strength: 3, color: 'green' },
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/read 20 min/i)).toBeInTheDocument());
  });

  it('clicking virtue posts {direction:1} to /habits/{id}/log/', async () => {
    const user = userEvent.setup();
    const tap = spyHandler('post', /\/api\/habits\/\d+\/log\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/habits/', () =>
        HttpResponse.json([
          { id: 9, name: 'Read 20 min', icon: '📖', habit_type: 'positive', strength: 3, color: 'green', coin_reward: 0, xp_reward: 0 },
        ]),
      ),
      tap.handler,
    ]);

    const button = await screen.findByRole('button', { name: /virtue/i });
    await user.click(button);

    await waitFor(() => expect(tap.calls).toHaveLength(1));
    expect(tap.calls[0].body).toEqual({ direction: 1 });
    expect(tap.calls[0].url).toMatch(/\/habits\/9\/log\/$/);
  });

  it('clicking vice posts {direction:-1} to /habits/{id}/log/', async () => {
    const user = userEvent.setup();
    const tap = spyHandler('post', /\/api\/habits\/\d+\/log\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/habits/', () =>
        HttpResponse.json([
          { id: 9, name: 'Skip dessert', icon: '🍰', habit_type: 'negative', strength: -2, color: 'red', coin_reward: 0, xp_reward: 0 },
        ]),
      ),
      tap.handler,
    ]);

    const button = await screen.findByRole('button', { name: /vice/i });
    await user.click(button);

    await waitFor(() => expect(tap.calls).toHaveLength(1));
    expect(tap.calls[0].body).toEqual({ direction: -1 });
  });
});
