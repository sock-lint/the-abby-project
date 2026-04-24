import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
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
    challenge_type_display: 'Complete 2 chores',
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

function renderCard(user, handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <DailyChallengeCard />
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
    expect(container.textContent).not.toMatch(/today's rite/i);
    expect(get.calls).toHaveLength(0);
  });

  it('renders title, kicker, progress, and rewards preview when in progress', async () => {
    renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () =>
        HttpResponse.json(buildChallenge({ current_progress: 1, target_value: 2 })),
      ),
    ]);

    await screen.findByText(/today's rite/i);
    expect(screen.getByText(/a small deed before the day turns/i)).toBeInTheDocument();
    expect(screen.getByText(/complete 2 chores/i)).toBeInTheDocument();
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '1');
    expect(bar).toHaveAttribute('aria-valuemax', '2');
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
    expect(screen.getByText(/reward waiting: 10 coins · 20 xp/i)).toBeInTheDocument();
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

    await waitFor(() =>
      expect(
        screen.getByText(/\+10 coins · \+20 xp — inked\./i),
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

    await screen.findByText(/today's rite/i);
    expect(
      screen.getByText(/already claimed — a new rite opens at midnight/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
  });

  it('renders nothing when the backend returns an empty payload', async () => {
    const { container } = renderCard(buildUser(), [
      http.get('*/api/challenges/daily/', () => HttpResponse.json({})),
    ]);
    // Give the fetch a tick to resolve.
    await waitFor(() => expect(container.textContent).not.toMatch(/loading/i));
    expect(container.textContent).not.toMatch(/today's rite/i);
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
