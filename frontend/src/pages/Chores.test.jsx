import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Chores from './Chores.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildChore, buildParent, buildUser } from '../test/factories.js';

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
        <Chores />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Chores', () => {
  it('renders empty state for children', async () => {
    renderPage(buildUser(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no rituals available today/i)).toBeInTheDocument(),
    );
  });

  it('renders empty state for parents', async () => {
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no rituals inscribed yet/i)).toBeInTheDocument(),
    );
  });

  it('renders chore rows for a child', async () => {
    renderPage(buildUser(), [
      http.get('*/api/chores/', () =>
        HttpResponse.json([buildChore({ id: 1, title: 'Dishes', is_available: true, reward_amount: '1.00' })]),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Dishes')).toBeInTheDocument());
  });

  it('parent can open the new-ritual form modal', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new ritual/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /new ritual/i }));
    expect(await screen.findByRole('button', { name: /^create$/i })).toBeInTheDocument();
  });

  it('parent sees approval queue when completions are pending', async () => {
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 1, chore_title: 'Dishes', chore_icon: '🍽️', user_name: 'Abby', status: 'pending', completed_date: '2026-04-16', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/awaiting your seal/i)).toBeInTheDocument(),
    );
  });
});
