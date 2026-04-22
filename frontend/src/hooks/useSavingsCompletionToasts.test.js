import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { useSavingsCompletionToasts } from './useSavingsCompletionToasts';

const STORAGE_KEY = 'seenSavingsCompletions';

function completedGoal(over = {}) {
  return {
    id: 1,
    title: 'Lego Set',
    target_amount: '50.00',
    is_completed: true,
    completed_at: '2026-04-20T00:00:00Z',
    icon: '🧱',
    ...over,
  };
}

describe('useSavingsCompletionToasts', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('seeds seen-set from the first poll without emitting toasts', async () => {
    server.use(
      http.get('*/api/savings-goals/', () =>
        HttpResponse.json([completedGoal()]),
      ),
    );
    const { result } = renderHook(() => useSavingsCompletionToasts(1000));

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      expect(stored).toContain(1);
    });
    expect(result.current.toasts).toEqual([]);
  });

  it('emits a toast when a newly-completed goal appears after the first poll', async () => {
    let completed = [];
    server.use(
      http.get('*/api/savings-goals/', () => HttpResponse.json(completed)),
    );

    const { result } = renderHook(() => useSavingsCompletionToasts(50));
    // First poll: no completed goals -> seen-set stays empty.
    await waitFor(() =>
      expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull(),
    );

    // Server state flips: a goal completed.
    completed = [completedGoal({ id: 42, title: 'Bike', target_amount: '75.00' })];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60);
    });

    await waitFor(() => expect(result.current.toasts).toHaveLength(1));
    expect(result.current.toasts[0]).toMatchObject({
      id: 'savings-42',
      title: 'Bike',
      icon: '🧱', // default for completedGoal() is 🧱; we overrode title only.
      coin_bonus: 150, // 75 * COINS_PER_DOLLAR=2
    });

    // Seen-set persisted so a reload doesn't re-toast this goal.
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
    expect(stored).toContain(42);
  });

  it('does not re-emit a toast for a goal already in the seen-set', async () => {
    // Persist seen-set BEFORE the hook mounts.
    localStorage.setItem(STORAGE_KEY, JSON.stringify([42]));
    server.use(
      http.get('*/api/savings-goals/', () =>
        HttpResponse.json([completedGoal({ id: 42 })]),
      ),
    );

    const { result } = renderHook(() => useSavingsCompletionToasts(50));
    // Let polling settle.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(150);
    });
    expect(result.current.toasts).toEqual([]);
  });

  it('dismiss removes a toast without touching localStorage', async () => {
    let completed = [];
    server.use(
      http.get('*/api/savings-goals/', () => HttpResponse.json(completed)),
    );
    const { result } = renderHook(() => useSavingsCompletionToasts(50));
    await waitFor(() =>
      expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull(),
    );

    completed = [completedGoal({ id: 7, target_amount: '10.00' })];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60);
    });
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));

    act(() => {
      result.current.dismiss('savings-7');
    });
    expect(result.current.toasts).toEqual([]);
    // ID stays in the persisted seen-set — dismissing doesn't clear memory.
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toContain(7);
  });
});
