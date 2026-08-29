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

  it('shows the NoChildrenWelcome empty state when children_count is 0 and pending queue is empty', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 0 }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/creations/pending/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/welcome — let's add your first kid/i)).toBeInTheDocument(),
    );
    const link = screen.getByRole('link', { name: /add a child/i });
    expect(link).toHaveAttribute('href', '/manage');
    // The "nothing needs your seal" hero (which lives on the populated path)
    // must NOT render — that copy is reserved for parents who already have
    // kids but a clean queue.
    expect(screen.queryByText(/nothing needs your seal/i)).toBeNull();
  });

  it('hides NoChildrenWelcome when children_count is positive', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 2 }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/creations/pending/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/nothing needs your seal/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/welcome — let's add your first kid/i)).toBeNull();
  });

  it('renders per-kid hours and earnings from this_week_by_kid in Week at a glance', async () => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          ...emptyDashboard,
          children_count: 1,
          this_week_by_kid: [{ kid_id: 2, name: 'Abby', hours: 1.5, earnings: 15 }],
        }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    // Collapsed peek reflects the active-kid count…
    await waitFor(() => expect(screen.getByText(/1 kid active/i)).toBeInTheDocument());
    // …and expanding reveals the per-kid hours + earnings rows.
    await user.click(screen.getByRole('button', { name: /week at a glance/i }));
    expect(await screen.findByText('Abby')).toBeInTheDocument();
    expect(screen.getByText('1.5h')).toBeInTheDocument();
    expect(screen.getByText('$15.00')).toBeInTheDocument();
  });

  it('does not claim "all quiet" while the approval aggregate is still loading', async () => {
    let releaseChores;
    const choresPending = new Promise((resolve) => { releaseChores = resolve; });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 1 }),
      ),
      http.get('*/api/chore-completions/', async () => {
        await choresPending;
        return HttpResponse.json([
          { id: 12, chore_title: 'Trash', user: 2, user_name: 'Abby' },
        ]);
      }),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);

    // Mid-flight: neither the queue's empty state nor the hero's all-clear
    // may render — both told the parent "nothing pending" before the fetches
    // that carried the pending rows had even resolved.
    await waitFor(() =>
      expect(screen.getByText(/turning today's page/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/no pending approvals/i)).toBeNull();
    expect(screen.queryByText(/nothing needs your seal/i)).toBeNull();

    releaseChores();
    await waitFor(() => expect(screen.getByText('Trash')).toBeInTheDocument());
  });

  it('makes the whole Family Snapshot tile a single tap target', async () => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 1 }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () =>
        HttpResponse.json([{ id: 2, username: 'abby', display_name: 'Abby' }]),
      ),
    ]);

    await user.click(await screen.findByRole('button', { name: /family snapshot/i }));
    const tile = await screen.findByRole('button', { name: /manage abby/i });
    // The card is INSIDE the button (the Next Up pattern) — previously the
    // button sat inside the card, leaving its 20px padded ring inert.
    expect(tile.querySelector('.rounded-xl')).not.toBeNull();
    expect(tile).toHaveTextContent('Abby');
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
