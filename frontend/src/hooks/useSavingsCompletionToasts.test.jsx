import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import MockPulse from '../test/pulse.jsx';
import { emptyPulse } from '../test/pulseFixtures.js';
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

/** Render the hook under a heartbeat, with a `beat` to deliver a new one. */
function renderWithPulse(initial = emptyPulse()) {
  let current = initial;
  const view = renderHook(() => useSavingsCompletionToasts(), {
    wrapper: ({ children }) => <MockPulse pulse={current}>{children}</MockPulse>,
  });
  return { ...view, beat: (pulse) => { current = pulse; view.rerender(); } };
}

describe('useSavingsCompletionToasts', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('seeds seen-set from the first beat without emitting toasts', async () => {
    const { result } = renderWithPulse(
      emptyPulse({ savings_goals: [completedGoal()] }),
    );
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      expect(stored).toContain(1);
    });
    expect(result.current.toasts).toEqual([]);
  });

  it('emits a toast when a goal completes after the first beat', async () => {
    const { result, beat } = renderWithPulse();
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull());

    beat(emptyPulse({
      savings_goals: [completedGoal({ id: 42, title: 'Bike', target_amount: '75.00' })],
    }));

    await waitFor(() => expect(result.current.toasts).toHaveLength(1));
    expect(result.current.toasts[0]).toMatchObject({
      id: 'savings-42',
      title: 'Bike',
      icon: '🧱',
      coin_bonus: 150, // 75 × COINS_PER_DOLLAR (2)
    });

    // Seen-set persisted so a reload doesn't re-toast this goal.
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toContain(42);
  });

  it('does not re-emit a toast for a goal already in the seen-set', async () => {
    // Persist seen-set BEFORE the hook mounts.
    localStorage.setItem(STORAGE_KEY, JSON.stringify([42]));
    const { result, beat } = renderWithPulse();
    beat(emptyPulse({ savings_goals: [completedGoal({ id: 42 })] }));
    await new Promise((r) => setTimeout(r, 30));
    expect(result.current.toasts).toEqual([]);
  });

  it('dismiss removes a toast without touching localStorage', async () => {
    const { result, beat } = renderWithPulse();
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull());

    beat(emptyPulse({
      savings_goals: [completedGoal({ id: 7, target_amount: '10.00' })],
    }));
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));

    act(() => { result.current.dismiss('savings-7'); });
    expect(result.current.toasts).toEqual([]);
    // ID stays in the persisted seen-set — dismissing doesn't clear memory.
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toContain(7);
  });
});
