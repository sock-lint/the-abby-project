import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '../../test/render';
import usePrintRequestRefresh from './usePrintRequestRefresh';

const printing = [{ id: 1, status: 'printing' }];
const pending = [{ id: 1, status: 'pending' }];

async function advance(milliseconds) {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds); });
}

describe('usePrintRequestRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('refreshes a running print after ten seconds and stops when the server confirms completion', async () => {
    let applyResponse;
    const reload = vi.fn(async () => applyResponse([{ id: 1, status: 'completed' }]));
    const { result } = renderHook(() => {
      const [requests, setRequests] = useState(printing);
      applyResponse = setRequests;
      usePrintRequestRefresh({ requests, reload });
      return requests;
    });
    await advance(9999);
    expect(reload).not.toHaveBeenCalled();
    await advance(1);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(result.current[0].status).toBe('completed');
    await advance(90000);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('uses a slower refresh for requests awaiting a parent or coin exchange', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(({ requests }) => usePrintRequestRefresh({ requests, reload }), {
      initialProps: { requests: pending },
    });
    await advance(44999);
    expect(reload).not.toHaveBeenCalled();
    await advance(1);
    expect(reload).toHaveBeenCalledTimes(1);
    rerender({ requests: [{ id: 1, status: 'quoted' }] });
    await advance(45000);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it('uses the fast interval for an open paused printer job', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    renderHook(() => usePrintRequestRefresh({
      requests: [{ id: 1, status: 'approved', latest_job: { state: 'paused', finished_at: null } }], reload,
    }));
    await advance(10000);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it.each([
    { requests: [] }, { requests: [{ id: 1, status: 'completed' }] }, { requests: [{ id: 1, status: 'cancelled' }] },
  ])(
    'does not poll when there are no open requests ($requests)', async ({ requests }) => {
      const reload = vi.fn();
      renderHook(() => usePrintRequestRefresh({ requests, reload }));
      await advance(180000);
      expect(reload).not.toHaveBeenCalled();
    },
  );

  it('skips hidden document reads and resumes on a later visible tick', async () => {
    const visibility = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    const reload = vi.fn().mockResolvedValue(undefined);
    renderHook(() => usePrintRequestRefresh({ requests: printing, reload }));
    await advance(30000);
    expect(reload).not.toHaveBeenCalled();
    visibility.mockReturnValue(false);
    await advance(10000);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('waits for a slow read before scheduling another even when the cadence and callback change', async () => {
    let finish;
    const firstReload = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    const nextReload = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook((props) => usePrintRequestRefresh(props), {
      initialProps: { requests: printing, reload: firstReload },
    });
    await advance(10000);
    expect(firstReload).toHaveBeenCalledTimes(1);
    await advance(60000);
    expect(firstReload).toHaveBeenCalledTimes(1);
    rerender({ requests: pending, reload: nextReload });
    await advance(120000);
    expect(nextReload).not.toHaveBeenCalled();
    await act(async () => { finish(); });
    await advance(44999);
    expect(nextReload).not.toHaveBeenCalled();
    await advance(1);
    expect(nextReload).toHaveBeenCalledTimes(1);
  });

  it('pauses polling while a form or decision is open and resumes when allowed', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(({ paused }) => usePrintRequestRefresh({ requests: printing, reload, paused }), {
      initialProps: { paused: true },
    });
    await advance(30000);
    expect(reload).not.toHaveBeenCalled();
    rerender({ paused: false });
    await advance(10000);
    expect(reload).toHaveBeenCalledTimes(1);
    rerender({ paused: true });
    await advance(30000);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('cancels a pending tick on unmount', async () => {
    const reload = vi.fn();
    const { unmount } = renderHook(() => usePrintRequestRefresh({ requests: printing, reload }));
    await advance(9999);
    unmount();
    await advance(90000);
    expect(reload).not.toHaveBeenCalled();
  });

  it('does not schedule another read when an in-flight response finishes after unmount', async () => {
    let finish;
    const reload = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    const { unmount } = renderHook(() => usePrintRequestRefresh({ requests: printing, reload }));
    await advance(10000);
    expect(reload).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => { finish(); });
    await advance(90000);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('allows the existing source error UI to recover on a later read after rejection', async () => {
    const reload = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(undefined);
    renderHook(() => usePrintRequestRefresh({ requests: pending, reload }));
    await advance(45000);
    expect(reload).toHaveBeenCalledTimes(1);
    await advance(45000);
    expect(reload).toHaveBeenCalledTimes(2);
  });
});
