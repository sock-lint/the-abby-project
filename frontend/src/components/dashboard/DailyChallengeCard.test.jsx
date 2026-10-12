import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import DailyChallengeCard from './DailyChallengeCard.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { buildUser, buildParent } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function buildChallenge(over = {}) {
  return {
    id: 11,
    challenge_type: 'chores',
    challenge_type_display: 'Finish N chores today',
    target_value: 2,
    current_progress: 0,
    progress_percent: 0,
    date: '2026-04-24',
    completed_at: null,
    coin_reward: 10,
    xp_reward: 20,
    is_complete: false,
    ...over,
  };
}

function TaskDestination() {
  const { pathname, search } = useLocation();
  return <p>Task destination: {pathname}{search}</p>;
}

function renderCard(user, handlers = [], refreshKey) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<DailyChallengeCard refreshKey={refreshKey} />} />
          <Route path="*" element={<TaskDestination />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('DailyChallengeCard', () => {
  it('does not fetch or render for parent users', async () => {
    const get = spyHandler('get', /\/api\/challenges\/daily\/$/, buildChallenge());
    const { container } = renderCard(buildParent(), [get.handler]);
    // Wait for AuthProvider to settle so any would-be fetch has a chance.
    await waitFor(() => expect(container.textContent).not.toMatch(/loading/i));
    expect(screen.queryByRole('heading', { name: 'Daily challenge' })).not.toBeInTheDocument();
    expect(get.calls).toHaveLength(0);
  });

  it('shows the goal, bonus reward, approval timing and progress while in progress', async () => {
    renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () =>
        HttpResponse.json(buildChallenge({ current_progress: 1, target_value: 2 })),
      ),
    ]);

    await screen.findByRole('heading', { name: 'Daily challenge' });
    expect(screen.getByText('Complete 2 chores today')).toBeInTheDocument();
    expect(screen.getByText('Progress counts after parent approval.')).toBeInTheDocument();
    expect(screen.getByText('Complete the goal, then claim +10 coins and +20 XP.')).toBeInTheDocument();
    expect(screen.getByText('1 / 2 complete')).toBeInTheDocument();
    expect(screen.getByText(/resets in/i)).toBeInTheDocument();
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '1');
    expect(bar).toHaveAttribute('aria-valuemax', '2');
    expect(bar).toHaveAttribute('aria-label', 'Complete 2 chores today progress');
    // The claim action appears only after the goal is complete.
    expect(screen.queryByText('Ready to claim')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View chores →' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
  });

  it('shows an enabled Claim button when the challenge is complete and unclaimed', async () => {
    renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () =>
        HttpResponse.json(
          buildChallenge({
            current_progress: 2,
            target_value: 2,
            is_complete: true,
            completed_at: '2026-04-24T12:00:00Z',
            coin_reward: 10,
            xp_reward: 20,
          }),
        ),
      ),
    ]);

    const button = await screen.findByRole('button', {
      name: /claim 10 coins and 20 xp/i,
    });
    expect(button).toBeEnabled();
    // Ready-to-claim keeps the FULL celebration card — kicker, challenge
    // line, and count all present (not the compact everyday row).
    expect(screen.getByText('Ready to claim')).toBeInTheDocument();
    expect(screen.getByText(/complete 2 chores/i)).toBeInTheDocument();
    expect(screen.getByText('2 / 2')).toBeInTheDocument();
  });

  it.each([
    ['clock_hour', 1, 'Clock 1 hour on a project today', 'View projects', 'ventures'],
    ['chores', 1, 'Complete 1 chore today', 'View chores', 'duties'],
    ['habits', 2, 'Log 2 positive habit taps today', 'View habits', 'rituals'],
    ['homework', 1, 'Complete 1 homework assignment today', 'View homework', 'study'],
    ['milestone', 1, 'Complete 1 project milestone today', 'View projects', 'ventures'],
  ])('explains the %s goal and opens its task tab', async (type, target, goal, action, tab) => {
    const user = userEvent.setup();
    renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () => HttpResponse.json(buildChallenge({
        challenge_type: type,
        target_value: target,
        challenge_type_display: 'Template with N tasks',
      }))),
    ]);

    await screen.findByText(goal);
    await user.click(screen.getByRole('button', { name: `${action} →` }));
    expect(screen.getByText(`Task destination: /quests?tab=${tab}`)).toBeInTheDocument();
  });

  it('refreshes challenge progress when the dashboard reloads after an action', async () => {
    let progress = 0;
    const { rerender } = renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () => HttpResponse.json(buildChallenge({
        current_progress: progress,
      }))),
    ], 0);
    await screen.findByText('0 / 2 complete');

    progress = 1;
    rerender(
      <MemoryRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<DailyChallengeCard refreshKey={1} />} />
            <Route path="*" element={<TaskDestination />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    await screen.findByText('1 / 2 complete');
  });

  it('keeps a previous day claim from hiding a refreshed challenge reward', async () => {
    const user = userEvent.setup();
    let challenge = buildChallenge({ current_progress: 2, is_complete: true });
    const claim = spyHandler('post', /\/api\/challenges\/daily\/claim\/$/, {
      already_claimed: false, coins: 10, xp: 20,
    });
    const { rerender } = renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () => HttpResponse.json(challenge)),
      claim.handler,
    ], 0);
    await user.click(await screen.findByRole('button', { name: 'Claim 10 coins and 20 XP' }));
    await screen.findByText('+10 coins · +20 XP earned.');
    await user.click(screen.getByRole('button', { name: 'Done' }));

    challenge = buildChallenge({
      id: 12, date: '2026-04-25', current_progress: 2, is_complete: true,
      coin_reward: 15, xp_reward: 25,
    });
    rerender(
      <MemoryRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<DailyChallengeCard refreshKey={1} />} />
            <Route path="*" element={<TaskDestination />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('button', { name: 'Claim 15 coins and 25 XP' })).toBeEnabled();
    expect(screen.queryByText('+10 coins · +20 XP earned.')).not.toBeInTheDocument();
  });

  it('clicking Claim POSTs to /challenges/daily/claim/ and shows the inked readout', async () => {
    const user = userEvent.setup();
    const claim = spyHandler('post', /\/api\/challenges\/daily\/claim\/$/, {
      already_claimed: false,
      coins: 10,
      xp: 20,
    });
    renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () =>
        HttpResponse.json(
          buildChallenge({
            current_progress: 2,
            target_value: 2,
            is_complete: true,
            completed_at: '2026-04-24T12:00:00Z',
          }),
        ),
      ),
      claim.handler,
    ]);

    const button = await screen.findByRole('button', { name: /claim 10 coins and 20 xp/i });
    await user.click(button);

    await waitFor(() => expect(claim.calls).toHaveLength(1));
    expect(claim.calls[0].url).toMatch(/\/challenges\/daily\/claim\/$/);
    expect(claim.calls[0].body).toBeNull();

    await waitFor(() =>
      expect(
        screen.getByText(/\+10 coins · \+20 xp earned\./i),
      ).toBeInTheDocument(),
    );
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
  });

  it('renders "Already claimed" when the challenge is complete with zeroed rewards', async () => {
    renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () =>
        HttpResponse.json(
          buildChallenge({
            current_progress: 2,
            target_value: 2,
            is_complete: true,
            completed_at: '2026-04-24T08:00:00Z',
            coin_reward: 0,
            xp_reward: 0,
          }),
        ),
      ),
    ]);

    await screen.findByRole('heading', { name: 'Daily challenge' });
    expect(
      screen.getByText('Reward claimed · A new challenge arrives tomorrow.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
    // Prior-session claims collapse back to the compact row too.
    expect(screen.queryByText('Ready to claim')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'View chores →' })).not.toBeInTheDocument();
  });

  it('renders nothing when the backend returns an empty payload', async () => {
    const { container } = renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () => HttpResponse.json({})),
    ]);
    // Give the fetch a tick to resolve.
    await waitFor(() => expect(container.textContent).not.toMatch(/loading/i));
    expect(screen.queryByRole('heading', { name: 'Daily challenge' })).not.toBeInTheDocument();
  });

  it('surfaces a 400 claim error inline and leaves the button enabled', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/challenges/daily/', () =>
        HttpResponse.json(
          buildChallenge({
            current_progress: 2,
            target_value: 2,
            is_complete: true,
            completed_at: '2026-04-24T12:00:00Z',
          }),
        ),
      ),
      http.post('*/api/challenges/daily/claim/', () =>
        HttpResponse.json(
          { error: 'Complete the challenge before claiming' },
          { status: 400 },
        ),
      ),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <DailyChallengeCard />
        </AuthProvider>
      </MemoryRouter>,
    );

    const button = await screen.findByRole('button', { name: /claim 10 coins and 20 xp/i });
    await user.click(button);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/complete the challenge before claiming/i);
    expect(screen.getByRole('button', { name: /claim 10 coins and 20 xp/i })).toBeEnabled();
  });
});
