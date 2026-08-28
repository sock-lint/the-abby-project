import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import useBackDismiss from './useBackDismiss';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useBackDismiss', () => {
  it('pushes one history sentinel while active', () => {
    const push = vi.spyOn(window.history, 'pushState');
    renderHook(() => useBackDismiss(() => {}));
    expect(push).toHaveBeenCalledTimes(1);
    expect(push.mock.calls[0][0]).toHaveProperty('abbyOverlay');
  });

  it('calls onDismiss when the back gesture pops the sentinel', () => {
    const onDismiss = vi.fn();
    renderHook(() => useBackDismiss(onDismiss));
    act(() => { window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('leaves history alone and ignores popstate while inactive', () => {
    const push = vi.spyOn(window.history, 'pushState');
    const onDismiss = vi.fn();
    renderHook(() => useBackDismiss(onDismiss, false));
    expect(push).not.toHaveBeenCalled();
    act(() => { window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it('stops listening once it goes inactive', () => {
    const onDismiss = vi.fn();
    const { rerender } = renderHook(
      ({ active }) => useBackDismiss(onDismiss, active),
      { initialProps: { active: true } },
    );
    rerender({ active: false });
    act(() => { window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it('always fires the latest onDismiss, not the one from mount', () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ fn }) => useBackDismiss(fn), {
      initialProps: { fn: first },
    });
    rerender({ fn: second });
    act(() => { window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
