import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useIncubationRefresh from './useIncubationRefresh';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('Incubation server reconciliation', () => {
  it('refreshes at the server deadline without changing readiness or creating a pet', () => {
    vi.setSystemTime(new Date('2040-01-01T00:00:00Z'));
    const row = { id: 7, is_ready: false, remaining_seconds: 2, ready_at: '2026-10-18T10:00:00Z' };
    const reload = vi.fn();
    renderHook(() => useIncubationRefresh(row, reload));
    act(() => vi.advanceTimersByTime(2000));
    expect(reload).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(250));
    expect(reload).toHaveBeenCalledTimes(1);
    expect(row.is_ready).toBe(false);
  });

  it('reconciles on focus and visible resume even without an unfinished incubation', () => {
    let visibility = 'hidden';
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
    const reload = vi.fn();
    renderHook(() => useIncubationRefresh(null, reload));
    act(() => window.dispatchEvent(new Event('focus')));
    expect(reload).not.toHaveBeenCalled();
    visibility = 'visible';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('bounds zero-second waits and clears its timer/listeners after navigation', () => {
    const reload = vi.fn();
    const view = renderHook(() => useIncubationRefresh({ id: 7, is_ready: false, remaining_seconds: 0 }, reload));
    act(() => vi.advanceTimersByTime(59000));
    expect(reload).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1000));
    expect(reload).toHaveBeenCalledTimes(1);
    view.unmount();
    act(() => { vi.advanceTimersByTime(120000); window.dispatchEvent(new Event('focus')); });
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
