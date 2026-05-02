import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import Dashboard from './Dashboard.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
import { buildUser } from '../test/factories.js';

function renderDashboard(extraHandlers = []) {
  server.use(...extraHandlers);
  return renderWithProviders(<Dashboard />);
}

describe('Dashboard (router)', () => {
  it('renders the date header with full data', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null,
          current_balance: 12.5,
          coin_balance: 100,
          this_week: { hours_worked: 3, earnings: 25 },
          active_projects: [],
          recent_badges: [],
          streak_days: 5,
          savings_goals: [],
          chores_today: [],
          pending_chore_approvals: 0,
          rpg: { level: 2, xp_to_next: 40, xp_percent: 50, login_streak: 7, longest_login_streak: 10, perfect_days_count: 3, habits_today: [] },
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/today's entry/i)).toBeInTheDocument());
    // Treasury is rendered as an accordion heading — the title text is present.
    expect(screen.getByText(/treasury/i)).toBeInTheDocument();
  });

  it('threads next_actions through to ChildDashboard', async () => {
    const { spyHandler } = await import('../test/spy.js');
    const dashboard = spyHandler('get', /\/api\/dashboard\/$/, {
      role: 'child',
      active_timer: null,
      chores_today: [],
      homework: { dashboard: { overdue: [], today: [], upcoming: [] } },
      rpg: {
        level: 0, login_streak: 0, longest_login_streak: 0,
        perfect_days_count: 0, last_active_date: null, habits_today: [],
      },
      next_actions: [
        { kind: 'chore', id: 1, title: 'Threaded Chore',
          subtitle: 'duty', score: 70, due_at: null, reward: null,
          icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
      ],
    });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      dashboard.handler,
    ]);
    // Renders in both the hero and the quest log; either presence proves
    // the prop is threaded.
    await screen.findAllByText('Threaded Chore');
    expect(screen.getAllByText('Threaded Chore').length).toBeGreaterThanOrEqual(1);
  });

  it('shows the error retry block when the dashboard fetch fails', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ error: 'boom' }, { status: 500 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument());
  });
});
