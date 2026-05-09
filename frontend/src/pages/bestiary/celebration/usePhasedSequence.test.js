import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import usePhasedSequence from './usePhasedSequence';

describe('usePhasedSequence', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts at phase 0 and advances through each milestone', async () => {
    const { result } = renderHook(() => usePhasedSequence([100, 200, 300]));
    expect(result.current).toBe(0);

    await act(async () => { await vi.advanceTimersByTimeAsync(110); });
    expect(result.current).toBe(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(210); });
    expect(result.current).toBe(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(320); });
    expect(result.current).toBe(3); // terminal
  });

  it('jumps straight to the terminal phase when reduced is true', () => {
    const { result } = renderHook(() =>
      usePhasedSequence([100, 200, 300], { reduced: true }),
    );
    expect(result.current).toBe(3);
  });

  it('clears its timers on unmount', async () => {
    const { result, unmount } = renderHook(() =>
      usePhasedSequence([100, 200, 300]),
    );
    expect(result.current).toBe(0);
    unmount();
    // No assertion failure on advancing post-unmount means the component
    // didn't try to setState on a torn-down hook (vitest would warn).
    await act(async () => { await vi.advanceTimersByTimeAsync(800); });
  });
});
