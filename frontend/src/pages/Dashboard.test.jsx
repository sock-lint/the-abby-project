import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
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
