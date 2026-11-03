import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import * as Sentry from '@sentry/react';
import { http, HttpResponse } from 'msw';
import { PulseProvider } from './PulseProvider.jsx';
import { usePulse } from './pulseContext';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';
import { useAuth } from '../hooks/useApi';
import { GATEWAY_RETRY_DELAY_MS } from '../api/client';
import { PULSE_OUTAGE_BEATS } from './pulseContext';

function Probe() {
  const { pulse, refresh } = usePulse();
  const { setUser } = useAuth();
  return <><div data-testid="probe">{pulse ? `coins:${pulse.header.coin_balance}` : 'no-beat'}</div><button onClick={() => setUser(buildUser({ id: 22 }))}>Switch child</button><button onClick={() => refresh()}>Refresh pulse</button></>;
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

function renderProvider(intervalMs = 1000) {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
  return renderWithProviders(
    <PulseProvider intervalMs={intervalMs}>
      <Probe />
    </PulseProvider>,
    // The outer MockPulse from the helper is overridden by the real provider
    // nested inside it, which is what we're exercising here.
    { pulse: null },
  );
}

beforeEach(() => {
  Sentry.captureException.mockClear();
});

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


  it('recovers a beat the proxy answered with a 504 during a deploy', async () => {
    let requests = 0;
    server.use(http.get('*/api/pulse/', () => {
      requests += 1;
      return requests === 1
        ? new HttpResponse('upstream timed out', { status: 504 })
        : HttpResponse.json(pulseBody(7));
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderProvider();
    await waitFor(() => expect(requests).toBe(1));
    await act(async () => { await vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS); });
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('coins:7'));
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  const BEAT_MS = 10000;
  const failedBeat = (kind) => (kind === 'html'
    ? new HttpResponse('<!doctype html><title>starting</title>', { status: 200, headers: { 'content-type': 'text/html' } })
    : new HttpResponse('upstream timed out', { status: 504 }));
  const runBeat = async () => {
    await act(async () => { await vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS); });
  };

  // THE-ABBY-PROJECT-3X: a deploy answered both attempts of a beat with HTML.
  it.each(['html', 'gateway'])('does not report a deploy window that spans one whole %s beat', async (kind) => {
    let requests = 0;
    server.use(http.get('*/api/pulse/', () => {
      requests += 1;
      return requests <= 2 ? failedBeat(kind) : HttpResponse.json(pulseBody(9));
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderProvider(BEAT_MS);
    await waitFor(() => expect(requests).toBe(1));
    await runBeat();
    await waitFor(() => expect(requests).toBe(2));
    await act(async () => { await vi.advanceTimersByTimeAsync(BEAT_MS); });
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('coins:9'));
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it.each([
    ['html', 'API 200 with non-JSON body: GET /pulse/'],
    ['gateway', 'API 504: GET /pulse/'],
  ])('reports once when %s failures persist across consecutive beats', async (kind, message) => {
    let requests = 0;
    server.use(http.get('*/api/pulse/', () => {
      requests += 1;
      return failedBeat(kind);
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderProvider(BEAT_MS);
    for (let beat = 1; beat <= PULSE_OUTAGE_BEATS + 2; beat += 1) {
      await waitFor(() => expect(requests).toBe((beat - 1) * 2 + 1));
      await runBeat();
      await waitFor(() => expect(requests).toBe(beat * 2));
      if (beat < PULSE_OUTAGE_BEATS) expect(Sentry.captureException).not.toHaveBeenCalled();
      await act(async () => { await vi.advanceTimersByTimeAsync(BEAT_MS - GATEWAY_RETRY_DELAY_MS); });
    }
    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
    const [error, { extra }] = Sentry.captureException.mock.calls[0];
    expect(error.message).toBe(message);
    expect(extra).toMatchObject({ attempts: 2, consecutiveFailedBeats: PULSE_OUTAGE_BEATS });
    expect(screen.getByTestId('probe')).toHaveTextContent('no-beat');
  });

  // THE-ABBY-PROJECT-43: `refresh()` (after a write) and tab focus start extra
  // beats, so three failures can arrive within seconds of one deploy window.
  it.each(['html', 'gateway'])('does not report %s failures that pile up from refreshes within one beat interval', async (kind) => {
    let requests = 0;
    server.use(http.get('*/api/pulse/', () => {
      requests += 1;
      return failedBeat(kind);
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = renderProvider(30000);
    await waitFor(() => expect(requests).toBe(1));
    await runBeat();
    await waitFor(() => expect(requests).toBe(2));
    for (let refresh = 1; refresh <= PULSE_OUTAGE_BEATS; refresh += 1) {
      await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
      await waitFor(() => expect(requests).toBe(2 + (refresh - 1) * 2 + 1));
      await runBeat();
      await waitFor(() => expect(requests).toBe(2 + refresh * 2));
    }
    // Four failed beats, none more than a few seconds apart: still one deploy.
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('reports the outage once it has lasted the full span, even after early refreshes', async () => {
    let requests = 0;
    server.use(http.get('*/api/pulse/', () => {
      requests += 1;
      return failedBeat('html');
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = renderProvider(BEAT_MS);
    await waitFor(() => expect(requests).toBe(1));
    await runBeat();
    await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
    await waitFor(() => expect(requests).toBe(3));
    await runBeat();
    // Three failed beats so far, but only a few seconds old.
    expect(Sentry.captureException).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(BEAT_MS * 2); });
    await waitFor(() => expect(Sentry.captureException).toHaveBeenCalledTimes(1));
    expect(Sentry.captureException.mock.calls[0][1].extra.failingForMs).toBeGreaterThanOrEqual((PULSE_OUTAGE_BEATS - 1) * BEAT_MS);
  });

  it('does not join a failure from before a long hidden-tab gap to later ones', async () => {
    let requests = 0;
    server.use(http.get('*/api/pulse/', () => {
      requests += 1;
      return failedBeat('html');
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = renderProvider(BEAT_MS);
    await waitFor(() => expect(requests).toBe(1));
    await runBeat();
    // The tab is hidden for an hour (no beats), then two refreshes fail.
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(60 * 60 * 1000); });
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    const before = requests;
    for (let refresh = 0; refresh < 2; refresh += 1) {
      await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
      await waitFor(() => expect(requests).toBe(before + refresh * 2 + 1));
      await runBeat();
    }
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('reports one continuous outage once even when an older beat fails late', async () => {
    const INTERVAL = 30000;
    let requests = 0;
    let releaseHeld;
    server.use(http.get('*/api/pulse/', async () => {
      requests += 1;
      if (requests === 1) await new Promise((resolve) => { releaseHeld = resolve; });
      return failedBeat('html');
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderProvider(INTERVAL);
    await waitFor(() => expect(requests).toBe(1));
    const start = Date.now();
    const advanceTo = async (t) => {
      await act(async () => { await vi.advanceTimersByTimeAsync(Math.max(0, start + t - Date.now())); });
    };
    // Beats at 30s, 60s and 90s fail (two requests each) and report once.
    for (let beat = 1; beat <= 3; beat += 1) {
      await advanceTo(beat * INTERVAL);
      await waitFor(() => expect(requests).toBe(1 + (beat - 1) * 2 + 1));
      await runBeat();
      await waitFor(() => expect(requests).toBe(1 + beat * 2));
    }
    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
    // The beat held since t=0 finally fails, then the outage simply continues.
    await advanceTo(95000);
    await act(async () => { releaseHeld(); });
    await runBeat();
    await waitFor(() => expect(requests).toBe(8));
    for (let beat = 4; beat <= 6; beat += 1) {
      await advanceTo(beat * INTERVAL);
      await waitFor(() => expect(requests).toBe(8 + (beat - 4) * 2 + 1));
      await runBeat();
      await waitFor(() => expect(requests).toBe(8 + (beat - 3) * 2));
    }
    expect(Sentry.captureException).toHaveBeenCalledTimes(1);
  });

  it('does not let a beat held across a hidden-tab gap join the failures after it', async () => {
    const INTERVAL = 30000;
    let requests = 0;
    let releaseHeld;
    server.use(http.get('*/api/pulse/', async () => {
      requests += 1;
      if (requests === 1) await new Promise((resolve) => { releaseHeld = resolve; });
      return failedBeat('html');
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = renderProvider(INTERVAL);
    await waitFor(() => expect(requests).toBe(1));
    const start = Date.now();
    const advanceTo = async (t) => {
      await act(async () => { await vi.advanceTimersByTimeAsync(Math.max(0, start + t - Date.now())); });
    };
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    await advanceTo(3599000);
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    // The interval beat at t=1h fails, as do two refreshes seconds later.
    await advanceTo(3600000);
    await runBeat();
    await advanceTo(3605000);
    await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
    await runBeat();
    // Now the beat that has been pending since t=0 finally fails.
    await act(async () => { releaseHeld(); });
    await runBeat();
    await advanceTo(3610000);
    await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
    await runBeat();
    await waitFor(() => expect(requests).toBeGreaterThanOrEqual(8));
    // The post-gap run is ten seconds old, however stale the held beat is.
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('does not let a beat that began before a successful one seed a new failure run', async () => {
    const INTERVAL = 30000;
    let requests = 0;
    let healthy = true;
    let releaseHeld;
    server.use(http.get('*/api/pulse/', async () => {
      requests += 1;
      if (requests === 1) {
        await new Promise((resolve) => { releaseHeld = resolve; });
        return failedBeat('html');
      }
      return healthy ? HttpResponse.json(pulseBody(4)) : failedBeat('html');
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = renderProvider(INTERVAL);
    await waitFor(() => expect(requests).toBe(1));
    const start = Date.now();
    const advanceTo = async (t) => {
      await act(async () => { await vi.advanceTimersByTimeAsync(Math.max(0, start + t - Date.now())); });
    };
    // Beats at 30s and 55s succeed; the beat held since t=0 then fails, and the
    // service really goes down just before the 60s beat.
    await advanceTo(30000);
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('coins:4'));
    await advanceTo(55000);
    await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
    await waitFor(() => expect(requests).toBe(3));
    healthy = false;
    await advanceTo(56000);
    await act(async () => { releaseHeld(); });
    await runBeat();
    await advanceTo(59000);
    await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
    await runBeat();
    await advanceTo(61000);
    await user.click(screen.getByRole('button', { name: 'Refresh pulse' }));
    await runBeat();
    await waitFor(() => expect(requests).toBeGreaterThanOrEqual(10));
    // The outage is two seconds old; the t=0 failure predates the last success.
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('restarts the outage count after a beat succeeds', async () => {
    let requests = 0;
    // Two failed beats (four requests), one good beat, then failures again.
    server.use(http.get('*/api/pulse/', () => {
      requests += 1;
      return requests === 5 ? HttpResponse.json(pulseBody(3)) : failedBeat('html');
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderProvider(BEAT_MS);
    let expected = 0;
    // Beats 1-2 fail (2 requests each), beat 3 succeeds (1 request), beats 4-5 fail.
    for (const requestsInBeat of [2, 2, 1, 2, 2]) {
      await waitFor(() => expect(requests).toBe(expected + 1));
      if (requestsInBeat === 2) await runBeat();
      expected += requestsInBeat;
      await waitFor(() => expect(requests).toBe(expected));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(requestsInBeat === 2 ? BEAT_MS - GATEWAY_RETRY_DELAY_MS : BEAT_MS);
      });
    }
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it("keeps counting the new child's failed beats when the previous child's late beat succeeds", async () => {
    let releaseOld;
    let requests = 0;
    server.use(http.get('*/api/pulse/', async () => {
      requests += 1;
      if (requests === 1) return await new Promise((resolve) => { releaseOld = () => resolve(HttpResponse.json(pulseBody(999))); });
      return failedBeat('html');
    }));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = renderProvider(BEAT_MS);
    await waitFor(() => expect(requests).toBe(1));
    await user.click(screen.getByRole('button', { name: 'Switch child' }));
    // Two failed beats (two requests each) for the new child, then the old answer lands.
    for (let beat = 1; beat < PULSE_OUTAGE_BEATS; beat += 1) {
      await waitFor(() => expect(requests).toBe(1 + (beat - 1) * 2 + 1));
      await runBeat();
      await waitFor(() => expect(requests).toBe(1 + beat * 2));
      await act(async () => { await vi.advanceTimersByTimeAsync(BEAT_MS - GATEWAY_RETRY_DELAY_MS); });
    }
    await act(async () => { releaseOld(); });
    await waitFor(() => expect(requests).toBe(1 + (PULSE_OUTAGE_BEATS - 1) * 2 + 1));
    await runBeat();
    await waitFor(() => expect(Sentry.captureException).toHaveBeenCalledTimes(1));
    expect(Sentry.captureException.mock.calls[0][1].extra).toMatchObject({ consecutiveFailedBeats: PULSE_OUTAGE_BEATS });
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
