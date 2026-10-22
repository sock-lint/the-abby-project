import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import activityStreakPulse from '../../../../contracts/api/fixtures/pulse-activity-streak.json';
import HeaderStatusPips from './HeaderStatusPips';
import VitalPipStrip from '../dashboard/VitalPipStrip';
import { server } from '../../test/server';
import { buildUser, buildParent } from '../../test/factories';
import { renderWithProviders } from '../../test/render';

const emptyDash = {
  active_timer: null,
  current_balance: 0,
  coin_balance: 12,
  this_week: { hours_worked: 0, earnings: 45 },
  active_projects: [], recent_badges: [], savings_goals: [],
  chores_today: [], pending_chore_approvals: 0,
  rpg: { login_streak: 3, longest_login_streak: 3, perfect_days_count: 0 },
};

function renderPips(user, handlers = []) {
  server.use(...handlers);
  return render(
    <MemoryRouter>
      <HeaderStatusPips user={user} />
    </MemoryRouter>,
  );
}

describe('HeaderStatusPips', () => {
  it.each([
    [1, 1.1, 5, 0.05, 0.05, 'kindled'],
    [5, 1.5, 7, 0.25, 0.25, 'kindled'],
    [10, 2, 10, 0.5, 0.5, 'strong'],
    [20, 3, 15, 0.5, 1, 'blazing'],
    [40, 3, 15, 0.5, 1, 'blazing'],
  ])('shows the confirmed daily bonus for a %i-day streak', async (days, multiplier, coins, dropBonus, intensity, state) => {
    renderPips(buildUser(), [http.get('*/api/dashboard/', () => HttpResponse.json({
      ...emptyDash,
      rpg: { login_streak: days, streak_bonus: {
        active_today: true, check_in_multiplier: multiplier, check_in_coins: coins,
        drop_bonus: dropBonus, intensity,
      } },
    }))]);
    const streak = await screen.findByRole('button', { name: `${days}-day streak` });
    expect(streak).toHaveAccessibleDescription(`Daily check-in: ${coins} Coins at ${multiplier}×. Streak drop chance: +${Math.round(dropBonus * 100)} percentage points.`);
    expect(streak.querySelector('[data-header-streak-flame]')).toHaveAttribute('data-state', state);
  });

  it('refreshes the bonus from the heartbeat and extinguishes it without resetting the saved streak', async () => {
    server.use(http.get('*/api/dashboard/', () => HttpResponse.json({
      ...emptyDash,
      rpg: { login_streak: 20, streak_bonus: {
        active_today: true, check_in_multiplier: 3, check_in_coins: 15, drop_bonus: 0.5, intensity: 1,
      } },
    })));
    const { beat } = renderWithProviders(<HeaderStatusPips user={buildUser()} />, { withAuth: false });
    const streak = await screen.findByRole('button', { name: '20-day streak' });
    expect(streak.querySelector('[data-header-streak-flame]')).toHaveAttribute('data-state', 'blazing');

    beat({ header: { streak_days: 20, streak_bonus: {
      active_today: false, check_in_multiplier: 1, check_in_coins: 0, drop_bonus: 0, intensity: 0,
    } } });
    expect(streak).toHaveTextContent('20');
    expect(streak).toHaveAccessibleDescription('Streak bonus is inactive. Complete an activity to start today’s check-in.');
    expect(streak.querySelector('[data-header-streak-flame]')).toHaveAttribute('data-state', 'dormant');

    // A rolling-deploy response without bonus metadata must not inherit an old
    // active bonus or infer a new reward from the saved count.
    beat({ header: { streak_days: 20 } });
    expect(streak).toHaveAccessibleDescription('Streak bonus is unavailable.');
    expect(streak.querySelector('[data-header-streak-flame]')).toHaveAttribute('data-state', 'dormant');
  });

  it('presents server bonus values without recalculating the reward from the saved streak', async () => {
    renderPips(buildUser(), [http.get('*/api/dashboard/', () => HttpResponse.json({
      ...emptyDash,
      rpg: { login_streak: 40, streak_bonus: {
        active_today: true, check_in_multiplier: 1.5, check_in_coins: 7, drop_bonus: 0.25, intensity: 0.25,
      } },
    }))]);
    const streak = await screen.findByRole('button', { name: '40-day streak' });
    expect(streak).toHaveAccessibleDescription('Daily check-in: 7 Coins at 1.5×. Streak drop chance: +25 percentage points.');
    expect(streak.querySelector('[data-header-streak-flame]')).toHaveAttribute('data-state', 'kindled');
  });

  it('shows streak and coins pips for a child', async () => {
    renderPips(buildUser(), [
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDash)),
    ]);
    await waitFor(() => expect(screen.getByLabelText(/3-day streak/i)).toBeInTheDocument());
    expect(screen.getByLabelText(/12 coins/i)).toBeInTheDocument();
  });

  it('keeps the header and Today tile on the same activity streak after a heartbeat', async () => {
    const dashboard = {
      ...emptyDash,
      // The child has an activity streak without a work-timer streak.
      streak_days: 0,
      rpg: { ...emptyDash.rpg, login_streak: 4 },
    };
    server.use(http.get('*/api/dashboard/', () => HttpResponse.json(dashboard)));
    const { beat } = renderWithProviders(
      <>
        <HeaderStatusPips user={buildUser()} />
        <VitalPipStrip loginStreak={dashboard.rpg.login_streak} />
      </>,
      { withAuth: false },
    );
    await waitFor(() => expect(screen.getAllByRole('button', { name: '4-day streak' })).toHaveLength(2));

    // This raw response is also produced by the authenticated Django endpoint.
    beat(activityStreakPulse);
    const header = within(screen.getByRole('group', { name: 'Status shortcuts' }));
    expect(header.getByRole('button', { name: '4-day streak' })).toHaveTextContent('4');
    expect(screen.getAllByRole('button', { name: '4-day streak' })).toHaveLength(2);
    expect(header.getByRole('button', { name: `${activityStreakPulse.header.coin_balance} coins` })).toBeInTheDocument();
  });

  it('refreshes the activity streak and accepts a real zero instead of the dashboard fallback', async () => {
    const dashboard = { ...emptyDash, rpg: { ...emptyDash.rpg, login_streak: 4 } };
    server.use(http.get('*/api/dashboard/', () => HttpResponse.json(dashboard)));
    const { beat } = renderWithProviders(<HeaderStatusPips user={buildUser()} />, { withAuth: false });
    await screen.findByRole('button', { name: '4-day streak' });

    beat({ ...activityStreakPulse, header: { ...activityStreakPulse.header, streak_days: 5 } });
    expect(screen.getByRole('button', { name: '5-day streak' })).toHaveTextContent('5');

    beat({ ...activityStreakPulse, header: { ...activityStreakPulse.header, streak_days: 0 } });
    expect(screen.getByRole('button', { name: '0-day streak' })).toHaveTextContent('0');
    expect(screen.queryByRole('button', { name: '4-day streak' })).not.toBeInTheDocument();
  });

  it('shows approvals and week-earnings pips for a parent', async () => {
    renderPips(buildParent(), [
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDash)),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([{ id: 1 }, { id: 2 }]),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ pending_submissions: [{ id: 10 }] }),
      ),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([{ id: 20, status: 'pending' }]),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByLabelText(/4 items needing attention/i)).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/earnings this week/i)).toBeInTheDocument();
  });

  it('surfaces a clock pip when a timer is active', async () => {
    renderPips(buildUser(), [
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          ...emptyDash,
          active_timer: { project_title: 'Bird Feeder', elapsed_minutes: 75, project_id: 2 },
        }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByLabelText(/clocked in on bird feeder/i)).toBeInTheDocument(),
    );
    // Shared formatDuration — the pip used to render "1h 15", which reads as
    // a clock time and disagreed with the hero card's "1h 15m" for the same
    // running timer.
    expect(screen.getByText('1h 15m')).toBeInTheDocument();
  });

  it('formats a sub-hour timer without an hour part', async () => {
    renderPips(buildUser(), [
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          ...emptyDash,
          active_timer: { project_title: 'Bird Feeder', elapsed_minutes: 45, project_id: 2 },
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('45m')).toBeInTheDocument());
  });
});
