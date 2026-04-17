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
          next_actions: [],
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
          next_actions: [
            { kind: 'chore', id: 1, title: 'dishes', subtitle: 'duty · $1',
              score: 70, due_at: null,
              reward: { money: '1', coins: 5 },
              icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
          ],
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
          next_actions: [],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByLabelText(/find a pet/i)).toBeInTheDocument());
  });

  it('renders hero using next_actions[0] and groups quest log by kind', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          role: 'child',
          active_timer: null,
          chores_today: [], // deprecated — still on wire
          homework: { dashboard: { overdue: [], today: [], upcoming: [] } },
          rpg: {
            level: 0, login_streak: 0, longest_login_streak: 0,
            perfect_days_count: 0, last_active_date: null, habits_today: [],
          },
          next_actions: [
            { kind: 'homework', id: 42, title: 'Math workbook',
              subtitle: 'Math · due tomorrow', score: 60, due_at: '2026-04-17',
              reward: null, icon: 'BookOpen', tone: 'royal', action_url: '/homework' },
            { kind: 'chore', id: 7, title: 'Clean Room',
              subtitle: 'duty · $1.00', score: 34, due_at: null,
              reward: { money: '1.00', coins: 2 },
              icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
          ],
        }),
      ),
    ]);

    await screen.findAllByText('Math workbook');
    // Hero shows top item — and the quest log echoes it; both should be present.
    expect(screen.getAllByText('Math workbook').length).toBeGreaterThanOrEqual(1);
    // Hero exposes a "Submit Math workbook" button (homework kind label).
    expect(screen.getByRole('button', { name: /submit math workbook/i })).toBeInTheDocument();
    // Quest log shows both items grouped by section. Section labels and the
    // per-row kind tags both render the same string, so use getAllByText.
    expect(screen.getAllByText(/study/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/duty/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Clean Room')).toBeInTheDocument();
  });

  it('clicking an open homework row opens the submit sheet', async () => {
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
          next_actions: [
            { kind: 'homework', id: 99, title: 'Poem recital',
              subtitle: 'Reading · due tomorrow', score: 60, due_at: null,
              reward: null, icon: 'BookOpen', tone: 'royal', action_url: '/homework' },
          ],
        }),
      ),
    ]);
    // Hero exposes a "Submit Poem recital" button; the quest log exposes
    // the per-row "Complete Poem recital" check-glyph. Either should open
    // the same sheet.
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
        next_actions: [
          { kind: 'habit', id: 7, title: 'Read 30min',
            subtitle: 'keep your 1-day streak', score: 65, due_at: null,
            reward: null, icon: 'Flame', tone: 'ember', action_url: '/habits' },
        ],
      }),
    );
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', dashboard),
      tap.handler,
    ]);

    // Quest log exposes per-row "Complete Read 30min" check-glyph.
    const buttons = await screen.findAllByRole('button', { name: /complete read 30min/i });
    await user.click(buttons[0]);

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
        next_actions: [
          { kind: 'chore', id: 4, title: 'dishes', subtitle: 'duty · $1',
            score: 70, due_at: null,
            reward: { money: '1', coins: 5 },
            icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
        ],
      }),
    );
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', dashboard),
      complete.handler,
    ]);

    // The quest log exposes the checkbox control with aria-label "Complete {title}".
    const buttons = await screen.findAllByRole('button', { name: /complete dishes/i });
    await user.click(buttons[0]);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].body).toEqual({ notes: '' });
    expect(complete.calls[0].url).toMatch(/\/chores\/4\/complete\/$/);
    await waitFor(() => expect(dashboard.mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
