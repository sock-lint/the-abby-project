import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildUser } from '../test/factories.js';

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

import { nextDueTarget } from './_dashboardShared';

describe('ChildDashboard', () => {
  it('renders active-timer hero when a timer is active', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: { project_title: 'Bird Feeder', elapsed_minutes: 42, project_id: 5 },
          current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0, rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getAllByText(/bird feeder/i).length).toBeGreaterThan(0));
  });

  it('renders pet growth pip and savings goal peek', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [
            { id: 1, title: 'P1', status: 'in_progress', difficulty: 2, milestones_total: 3, milestones_completed: 1 },
          ],
          recent_badges: [{ badge__name: 'Gold', badge__icon: '🏅' }],
          savings_goals: [{ id: 1, title: 'Bike', icon: '🚲', current_amount: 20, target_amount: 100, percent_complete: 20 }],
          chores_today: [{ id: 1, title: 'dishes', reward_amount: '1', coin_reward: 5, is_done: false }],
          pending_chore_approvals: 0,
          rpg: {
            level: 3, xp_to_next: 10, xp_percent: 80,
            login_streak: 4, longest_login_streak: 6, perfect_days_count: 1,
            habits_today: [],
          },
        }),
      ),
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({
          pets: [{ id: 1, is_active: true, species: { name: 'Drake', icon_url: '/drake.png' }, potion: { name: 'Fire' }, growth_points: 40 }],
          mounts: [],
        }),
      ),
      http.get('*/api/drops/recent/', () =>
        HttpResponse.json([{ id: 1, item_name: 'Coin', item_icon: '🪙', rarity: 'common', was_salvaged: false }]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/recent loot/i)).toBeInTheDocument());
    // Savings peek renders the first goal title even while collapsed.
    expect(screen.getByText(/bike/i)).toBeInTheDocument();
    // Pet growth % visible in the vital pip.
    expect(screen.getByText(/40%/)).toBeInTheDocument();
  });

  it('renders a "no pet" pip when no active pet', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByLabelText(/find a pet/i)).toBeInTheDocument());
  });

  it('surfaces due-next-school-day homework in Today\'s Log with a Study kind tag', async () => {
    const { iso, label } = nextDueTarget();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [], overdue: [],
          upcoming: [
            { id: 55, title: 'Science worksheet', subject: 'Science', due_date: iso },
            { id: 56, title: 'Far future', subject: 'Math', due_date: '2099-01-01' },
          ],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/science worksheet/i)).toBeInTheDocument());
    // Row renders inside the main log; the old standalone "Coming up" card is gone.
    expect(screen.queryByText(/^coming up$/i)).not.toBeInTheDocument();
    // Meta line carries subject + due label.
    expect(screen.getByText(new RegExp(`science.*due ${label}`, 'i'))).toBeInTheDocument();
    // Study kind tag is present.
    expect(screen.getByText(/^study$/i)).toBeInTheDocument();
    // Far-future homework is filtered out.
    expect(screen.queryByText(/far future/i)).not.toBeInTheDocument();
  });

  it('surfaces due-today and overdue homework alongside next-school-day items', async () => {
    const { iso } = nextDueTarget();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [{ id: 10, title: 'Due-today worksheet', subject: 'Math', due_date: '2026-04-16' }],
          overdue: [{ id: 20, title: 'Overdue paper', subject: 'Writing', due_date: '2026-04-10' }],
          upcoming: [{ id: 30, title: 'Tomorrow prep', subject: 'Reading', due_date: iso }],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/due-today worksheet/i)).toBeInTheDocument());
    expect(screen.getByText(/overdue paper/i)).toBeInTheDocument();
    expect(screen.getByText(/tomorrow prep/i)).toBeInTheDocument();
    expect(screen.getByText(/writing.*overdue/i)).toBeInTheDocument();
    expect(screen.getByText(/math.*due today/i)).toBeInTheDocument();
  });

  it('hides homework whose submission is already approved', async () => {
    const { iso } = nextDueTarget();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [], overdue: [],
          upcoming: [
            { id: 55, title: 'Already approved', subject: 'Math', due_date: iso,
              submission_status: { id: 900, status: 'approved' } },
            { id: 56, title: 'Still pending submit', subject: 'Math', due_date: iso },
          ],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/still pending submit/i)).toBeInTheDocument());
    expect(screen.queryByText(/already approved/i)).not.toBeInTheDocument();
  });

  it('clicking an open homework row opens the submit sheet', async () => {
    const { iso } = nextDueTarget();
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [], overdue: [],
          upcoming: [{ id: 99, title: 'Poem recital', subject: 'Reading', due_date: iso }],
        }),
      ),
    ]);
    const row = await screen.findByRole('button', { name: /complete poem recital/i });
    await user.click(row);
    // Sheet content renders on document.body via portal.
    await waitFor(() =>
      expect(document.body.textContent).toMatch(/affix photographic evidence/i),
    );
    expect(document.body.textContent).toMatch(/poem recital/i);
  });

  it('tapping a habit on the today log posts to /habits/{id}/log/ and refetches', async () => {
    const user = userEvent.setup();
    const tap = spyHandler('post', /\/api\/habits\/\d+\/log\/$/, { ok: true });
    const dashboard = vi.fn(() =>
      HttpResponse.json({
        active_timer: null, current_balance: 0, coin_balance: 0,
        this_week: { hours_worked: 0, earnings: 0 },
        active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
        pending_chore_approvals: 0,
        rpg: {
          level: 1, xp_to_next: 10, xp_percent: 0,
          login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
          habits_today: [{ id: 7, name: 'Read 30min', icon: '📖', strength: 7, taps_today: 2, max_taps_per_day: 5 }],
        },
      }),
    );
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', dashboard),
      tap.handler,
    ]);

    const button = await screen.findByRole('button', { name: /complete read 30min/i });
    await user.click(button);

    await waitFor(() => expect(tap.calls).toHaveLength(1));
    expect(tap.calls[0].body).toEqual({ direction: 1 });
    expect(tap.calls[0].url).toMatch(/\/habits\/7\/log\/$/);
    await waitFor(() => expect(dashboard.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('completing a chore from the today log posts to /chores/{id}/complete/ and refetches', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', /\/api\/chores\/\d+\/complete\/$/, { ok: true });
    const dashboard = vi.fn(() =>
      HttpResponse.json({
        active_timer: null, current_balance: 0, coin_balance: 0,
        this_week: { hours_worked: 0, earnings: 0 },
        active_projects: [], recent_badges: [], savings_goals: [],
        chores_today: [{ id: 4, title: 'dishes', reward_amount: '1', coin_reward: 5, is_done: false }],
        pending_chore_approvals: 0,
        rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
      }),
    );
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', dashboard),
      complete.handler,
    ]);

    // The today log exposes the checkbox control with aria-label "Complete {title}".
    const buttons = await screen.findAllByRole('button', { name: /complete dishes/i });
    await user.click(buttons[0]);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].body).toEqual({ notes: '' });
    expect(complete.calls[0].url).toMatch(/\/chores\/4\/complete\/$/);
    await waitFor(() => expect(dashboard.mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
