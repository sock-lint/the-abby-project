import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import * as Sentry from '@sentry/react';
import { GATEWAY_RETRY_DELAY_MS } from '../api/client';
import { renderWithProviders, screen, waitFor, act } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent, buildUser } from '../test/factories';
import { buildChallengeGoal } from '../test/challenges';
import { DEFERRED_RECOVERY_DELAY_MS, useAuth } from './useApi';
import useChallenges from './useChallenges';

function Probe() {
  const { pinnedGoal } = useChallenges();
  const { setUser } = useAuth();
  const { user } = useAuth();
  return <><span>{user?.role}</span><span data-testid="goal-probe">{pinnedGoal?.name || 'No current pin'}</span><button onClick={() => setUser(buildUser({ id: 22 }))}>Switch child</button></>;
}

describe('Scoped challenge reads', () => {
  it('does not read a child challenge list for a parent without a selected child', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    const get = spyHandler('get', /\/api\/challenges\/$/, { results: [] });
    server.use(get.handler);
    renderWithProviders(<Probe />);
    await screen.findByText('parent');
    expect(get.calls).toHaveLength(0);
  });

  it('hides the previous child pin until the new scoped response arrives', async () => {
    let requests = 0;
    let releaseNew;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ id: 7 }))),
      http.get('*/api/challenges/', async () => {
        requests += 1;
        const goal = buildChallengeGoal({ name: requests === 1 ? 'Abby private goal' : 'Beck goal', pinned: true });
        if (requests === 1) return HttpResponse.json({ results: [goal], pin: goal.id });
        return await new Promise((resolve) => { releaseNew = () => resolve(HttpResponse.json({ results: [goal], pin: goal.id })); });
      }),
    );
    const { user } = renderWithProviders(<Probe />);
    await screen.findByText('Abby private goal');
    await user.click(screen.getByRole('button', { name: 'Switch child' }));
    expect(screen.queryByText('Abby private goal')).not.toBeInTheDocument();
    await waitFor(() => expect(requests).toBe(2));
    await act(async () => { releaseNew(); });
    expect(await screen.findByText('Beck goal')).toBeInTheDocument();
  });
});

// THE-ABBY-PROJECT-41: GET /api/challenges/ answered an HTML 200 on both client
// attempts while a deploy swapped containers, and each one was captured at
// once. The read now hands a persistent HTML 200 to useApi, which waits out the
// rest of the window and reports only if the proxy is still failing.
describe('Challenge read deploy-window recovery', () => {
  const html = () => new HttpResponse('<!doctype html><title>starting</title>', {
    status: 200, headers: { 'content-type': 'text/html' },
  });
  let calls;

  function RecoveryProbe() {
    const { pinnedGoal, error } = useChallenges();
    return <><span data-testid="pin">{pinnedGoal?.name || 'No current pin'}</span><span data-testid="error">{error || 'No error'}</span></>;
  }

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    calls = 0;
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ id: 7 }))));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads the goals without reporting when the proxy recovers after the client retry', async () => {
    const goal = buildChallengeGoal({ name: 'Recovered goal', pinned: true });
    server.use(http.get('*/api/challenges/', () => {
      calls += 1;
      return calls <= 2 ? html() : HttpResponse.json({ results: [goal], pin: goal.id });
    }));
    renderWithProviders(<RecoveryProbe />);
    await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(calls).toBe(2));
    expect(Sentry.captureException).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS));
    expect(await screen.findByText('Recovered goal')).toBeInTheDocument();
    expect(calls).toBe(3);
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });

  it('reports once, with both attempts counted, when the HTML persists', async () => {
    server.use(http.get('*/api/challenges/', () => {
      calls += 1;
      return html();
    }));
    renderWithProviders(<RecoveryProbe />);
    await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(calls).toBe(2));
    expect(Sentry.captureException).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS + GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(Sentry.captureException).toHaveBeenCalledTimes(1));
    expect(Sentry.captureException).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'API 200 with non-JSON body: GET /challenges/' }),
      { extra: expect.objectContaining({ status: 200, deferredRecoveryAttempts: 2 }) },
    );
    expect(calls).toBe(4);
    expect(await screen.findByTestId('error')).toHaveTextContent(/temporarily unavailable/i);
  });

  it('stops quietly when the page unmounts during the wait', async () => {
    server.use(http.get('*/api/challenges/', () => {
      calls += 1;
      return html();
    }));
    const { unmount } = renderWithProviders(<RecoveryProbe />);
    await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(calls).toBe(2));
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS * 2));
    expect(calls).toBe(2);
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });
});
