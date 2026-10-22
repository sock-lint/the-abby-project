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
