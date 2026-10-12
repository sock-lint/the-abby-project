import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useExpeditionRefresh from './useExpeditionRefresh';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe('Expedition server refresh', () => {
  it('reconciles on focus and visible resume, never while hidden', () => {
    const reload = vi.fn();
    let visibility = 'hidden';
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
    renderHook(() => useExpeditionRefresh([], reload));
    act(() => window.dispatchEvent(new Event('focus')));
    expect(reload).not.toHaveBeenCalled();
    visibility = 'visible';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    act(() => window.dispatchEvent(new Event('focus')));
    expect(reload).toHaveBeenCalledTimes(2);
  });
  it('refreshes at the server return deadline without local ready or claim transitions', () => {
    const reload = vi.fn();
    const mounts = [{ active_expedition: { status: 'active', is_ready: false, seconds_remaining: 2 } }];
    renderHook(() => useExpeditionRefresh(mounts, reload));
    act(() => vi.advanceTimersByTime(2000));
    expect(reload).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(250));
    expect(reload).toHaveBeenCalledTimes(1);
    expect(mounts[0].active_expedition.is_ready).toBe(false);
  });
  it('uses server seconds until the next day even with a wildly incorrect phone date', () => {
    vi.setSystemTime(new Date('2040-01-01T00:00:00Z'));
    const reload = vi.fn();
    const mounts = [{ expedition_available: false, expedition_available_at: '2026-10-13T00:00:00-07:00', expedition_available_in_seconds: 5 }];
    renderHook(() => useExpeditionRefresh(mounts, reload));
    act(() => vi.advanceTimersByTime(5000));
    expect(reload).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(250));
    expect(reload).toHaveBeenCalledTimes(1);
    expect(mounts[0].expedition_available).toBe(false);
  });
  it('bounds retries for a rounded zero that the server still reports as not ready', () => {
    const reload = vi.fn();
    const mounts = [{ active_expedition: { status: 'active', is_ready: false, seconds_remaining: 0 } }];
    renderHook(() => useExpeditionRefresh(mounts, reload));
    act(() => vi.advanceTimersByTime(59000));
    expect(reload).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1000));
    expect(reload).toHaveBeenCalledTimes(1);
  });
  it('cancels listeners and the scheduled return check after leaving Pets', () => {
    const reload = vi.fn();
    const mounts = [{ active_expedition: { status: 'active', is_ready: false, seconds_remaining: 2 } }];
    const view = renderHook(() => useExpeditionRefresh(mounts, reload));
    view.unmount();
    act(() => { vi.advanceTimersByTime(10000); window.dispatchEvent(new Event('focus')); });
    expect(reload).not.toHaveBeenCalled();
  });
});
