import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Chores from './Chores.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
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
      expect(screen.getByText(/no duties available today/i)).toBeInTheDocument(),
    );
  });

  it('renders empty state for parents', async () => {
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no duties inscribed yet/i)).toBeInTheDocument(),
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

  it('parent can open the new-duty form modal', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new duty/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /new duty/i }));
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

  it('child clicking Done posts to /chores/{id}/complete/', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', /\/api\/chores\/\d+\/complete\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/chores/', () =>
        HttpResponse.json([buildChore({ id: 12, title: 'Dishes', is_available: true, today_status: null })]),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      complete.handler,
    ]);

    const button = await screen.findByRole('button', { name: /done/i });
    await user.click(button);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/chores\/12\/complete\/$/);
    expect(complete.calls[0].body).toEqual({ notes: '' });
  });

  it('parent approving a pending completion posts to /chore-completions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/chore-completions\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 22, chore_title: 'Dishes', chore_icon: '🍽️', user_name: 'Abby', status: 'pending', completed_date: '2026-04-16', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/chore-completions\/22\/approve\/$/);
  });

  it('parent rejecting a pending completion posts to /chore-completions/{id}/reject/', async () => {
    const user = userEvent.setup();
    const reject = spyHandler('post', /\/api\/chore-completions\/\d+\/reject\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 22, chore_title: 'Dishes', chore_icon: '🍽️', user_name: 'Abby', status: 'pending', completed_date: '2026-04-16', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      reject.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^reject$/i });
    await user.click(button);

    await waitFor(() => expect(reject.calls).toHaveLength(1));
    expect(reject.calls[0].url).toMatch(/\/chore-completions\/22\/reject\/$/);
  });
});
