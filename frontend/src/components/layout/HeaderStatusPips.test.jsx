import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HeaderStatusPips from './HeaderStatusPips';
import { server } from '../../test/server';
import { buildUser, buildParent } from '../../test/factories';

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
      expect(screen.getByLabelText(/4 pending approvals/i)).toBeInTheDocument(),
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
  });
});
