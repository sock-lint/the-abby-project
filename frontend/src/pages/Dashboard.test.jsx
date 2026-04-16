import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildParent, buildUser } from '../test/factories.js';

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

describe('Dashboard', () => {
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

  it('renders active-timer rune band when a timer is active', async () => {
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

  it('renders the parent pending-approvals banner', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [],
          chores_today: [], pending_chore_approvals: 2,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/ritual.*awaiting your seal/i)).toBeInTheDocument());
  });

  it('renders active pet card and savings goals', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [
            { id: 1, title: 'P1', status: 'in_progress', difficulty: 2, milestones_total: 3, milestones_completed: 1 },
            { id: 2, title: 'P2', status: 'completed', difficulty: 5, milestones_total: 0 },
          ],
          recent_badges: [{ badge__name: 'Gold', badge__icon: '🏅' }],
          savings_goals: [{ id: 1, title: 'Bike', icon: '🚲', current_amount: 20, target_amount: 100, percent_complete: 20 }],
          chores_today: [{ id: 1, title: 'dishes', reward_amount: '1', coin_reward: 5, is_done: false }],
          pending_chore_approvals: 0,
          rpg: {
            level: 3, xp_to_next: 10, xp_percent: 80,
            login_streak: 4, longest_login_streak: 6, perfect_days_count: 1,
            habits_today: [{ id: 1, name: 'Read 30min', icon: '📖', strength: 7, taps_today: 2 }],
          },
        }),
      ),
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({
          pets: [{ id: 1, is_active: true, species: { name: 'Drake', icon_url: '/drake.png' }, potion: { name: 'Fire' }, growth_points: 40 }],
          mounts: [{ id: 9, is_active: true, species: { name: 'Griffon' } }],
        }),
      ),
      http.get('*/api/quests/active/', () =>
        HttpResponse.json({
          id: 5, status: 'active',
          progress_percent: 50, current_progress: 5, effective_target: 10,
          definition: { name: 'Boss Quest', quest_type: 'boss' },
        }),
      ),
      http.get('*/api/drops/recent/', () =>
        HttpResponse.json([{ id: 1, item_name: 'Coin', item_icon: '🪙', rarity: 'common', was_salvaged: false }]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/drake/i)).toBeInTheDocument());
    expect(screen.getByText(/recent loot/i)).toBeInTheDocument();
    expect(screen.getByText(/bike/i)).toBeInTheDocument();
  });

  it('renders "find an egg" card when no active pet', async () => {
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
    await waitFor(() => expect(screen.getByText(/no companion yet/i)).toBeInTheDocument());
  });
});
