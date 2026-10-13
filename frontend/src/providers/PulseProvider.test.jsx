import { describe, expect, it, vi, afterEach } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { PulseProvider } from './PulseProvider.jsx';
import { usePulse } from './pulseContext';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';
import { useAuth } from '../hooks/useApi';

function Probe() {
  const { pulse } = usePulse();
  const { setUser } = useAuth();
  return <><div data-testid="probe">{pulse ? `coins:${pulse.header.coin_balance}` : 'no-beat'}</div><button onClick={() => setUser(buildUser({ id: 22 }))}>Switch child</button></>;
}

const pulseBody = (coins) => ({
  unread_count: 0,
  notifications: [],
  recent_drops: [],
  active_quest: null,
  companion_growth: { events: [] },
  expeditions_ready: [],
  savings_goals: [],
  newly_unlocked_lorebook: [],
  header: { active_timer: null, coin_balance: coins, streak_days: 0 },
});

function renderProvider() {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
  return renderWithProviders(
    <PulseProvider intervalMs={1000}>
      <Probe />
    </PulseProvider>,
    // The outer MockPulse from the helper is overridden by the real provider
    // nested inside it, which is what we're exercising here.
    { pulse: null },
  );
}

afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(document, 'hidden', { value: false, configurable: true });
});

describe('PulseProvider', () => {
  it('fetches a heartbeat and publishes it to consumers', async () => {
    server.use(http.get('*/api/pulse/', () => HttpResponse.json(pulseBody(120))));
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('coins:120'));
  });

  it('keeps beating on the interval', async () => {
    let beats = 0;
    server.use(http.get('*/api/pulse/', () => {
      beats += 1;
      return HttpResponse.json(pulseBody(beats));
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderProvider();
    await waitFor(() => expect(beats).toBeGreaterThanOrEqual(1));
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    await waitFor(() => expect(beats).toBeGreaterThanOrEqual(2));
  });

  it('skips beats while the tab is hidden', async () => {
    let beats = 0;
    server.use(http.get('*/api/pulse/', () => {
      beats += 1;
      return HttpResponse.json(pulseBody(1));
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderProvider();
    await waitFor(() => expect(beats).toBe(1));

    // A backgrounded phone shouldn't burn battery or cell data.
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(3100); });
    expect(beats).toBe(1);

    // …and catches up the moment it comes back, rather than waiting out the
    // remainder of the interval.
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
    await waitFor(() => expect(beats).toBe(2));
  });

  it('survives a failed beat without breaking consumers', async () => {
    server.use(http.get('*/api/pulse/', () =>
      HttpResponse.json({ error: 'boom' }, { status: 500 })));
    renderProvider();
    await new Promise((r) => setTimeout(r, 50));
    // Still rendering, just without a heartbeat — the next beat retries.
    expect(screen.getByTestId('probe')).toHaveTextContent('no-beat');
  });


  it('rejects a late receipt response from the previous child', async () => {
    let releaseOld;
    let requests = 0;
    server.use(http.get('*/api/pulse/', async () => {
      requests += 1;
      if (requests === 1) return await new Promise((resolve) => { releaseOld = () => resolve(HttpResponse.json(pulseBody(999))); });
      return HttpResponse.json(pulseBody(20));
    }));
    const { user } = renderProvider();
    await waitFor(() => expect(requests).toBe(1));
    await user.click(screen.getByRole('button', { name: 'Switch child' }));
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('coins:20'));
    await act(async () => { releaseOld(); });
    expect(screen.getByTestId('probe')).toHaveTextContent('coins:20');
  });

  it('hides the earlier child heartbeat while the new child is loading', async () => {
    let releaseNew;
    let requests = 0;
    server.use(http.get('*/api/pulse/', async () => {
      requests += 1;
      if (requests > 1) return await new Promise((resolve) => { releaseNew = () => resolve(HttpResponse.json(pulseBody(20))); });
      return HttpResponse.json(pulseBody(999));
    }));
    const { user } = renderProvider();
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('coins:999'));
    await user.click(screen.getByRole('button', { name: 'Switch child' }));
    expect(screen.getByTestId('probe')).toHaveTextContent('no-beat');
    await waitFor(() => expect(requests).toBe(2));
    await act(async () => { releaseNew(); });
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('coins:20'));
  });

  it('does not poll when nobody is signed in', async () => {
    let beats = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(null, { status: 401 })),
      http.get('*/api/pulse/', () => {
        beats += 1;
        return HttpResponse.json(pulseBody(0));
      }),
    );
    renderWithProviders(
      <PulseProvider intervalMs={1000}>
        <Probe />
      </PulseProvider>,
      { pulse: null },
    );
    await new Promise((r) => setTimeout(r, 60));
    expect(beats).toBe(0);
  });
});
