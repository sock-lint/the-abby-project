import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent } from '../test/factories.js';

function renderDashboard(extraHandlers = []) {
  server.use(...extraHandlers);
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Dashboard />
      </AuthProvider>
    </MemoryRouter>,
  );
}

const emptyDashboard = {
  active_timer: null, current_balance: 0, coin_balance: 0,
  this_week: { hours_worked: 0, earnings: 0 },
  active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
  pending_chore_approvals: 0,
  rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
};

describe('ParentDashboard', () => {
  it('renders "nothing needs your seal" hero when queue is empty', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/nothing needs your seal/i)).toBeInTheDocument(),
    );
  });

  it('renders count copy and approval queue grouped by kid', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 10, chore_title: 'Dishes', user: 2, user_name: 'Abby', reward_amount_snapshot: '1.00', submitted_at: '2026-04-16T10:00:00Z' },
        ]),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 20, assignment_title: 'Math packet', user_id: 2, user_name: 'Abby', reward_amount_snapshot: '2.00', submitted_at: '2026-04-16T09:00:00Z' },
          ],
        }),
      ),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([
          { id: 30, reward_name: 'Screen time', user_id: 2, user_name: 'Abby', cost_coins: 25, status: 'pending', created_at: '2026-04-16T08:00:00Z' },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/3 things need your seal today/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/dishes/i)).toBeInTheDocument();
    expect(screen.getByText(/math packet/i)).toBeInTheDocument();
    expect(screen.getByText(/screen time/i)).toBeInTheDocument();
  });

  it('approving a chore fires /chore-completions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/chore-completions\/\d+\/approve\/$/, { ok: true });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 11, chore_title: 'Dishes', user: 2, user_name: 'Abby', reward_amount_snapshot: '1.00' },
        ]),
      ),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);
    const btn = await screen.findByRole('button', { name: /approve dishes/i });
    await user.click(btn);
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/chore-completions\/11\/approve\/$/);
  });

  it('approving a homework submission fires /homework-submissions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/homework-submissions\/\d+\/approve\/$/, { ok: true });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 22, assignment_title: 'Reading log', user_id: 2, user_name: 'Abby' },
          ],
        }),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);
    const btn = await screen.findByRole('button', { name: /approve reading log/i });
    await user.click(btn);
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/homework-submissions\/22\/approve\/$/);
  });

  it('shows a retry-able banner when an approval queue fails to load', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json({ error: 'boom' }, { status: 500 })),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/chore approvals/i),
    );
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('approving a redemption fires /redemptions/{id}/approve/ with notes body', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/redemptions\/\d+\/approve\/$/, { ok: true });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([
          { id: 33, reward_name: 'Movie night', user_id: 2, user_name: 'Abby', status: 'pending' },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);
    const btn = await screen.findByRole('button', { name: /approve movie night/i });
    await user.click(btn);
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].body).toEqual({ notes: '' });
    expect(approve.calls[0].url).toMatch(/\/redemptions\/33\/approve\/$/);
  });
});
