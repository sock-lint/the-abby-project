import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import usePrefersReducedMotion from './usePrefersReducedMotion';

describe('motion preference', () => {
  afterEach(() => vi.restoreAllMocks());
  it.each(['current', 'legacy'])('updates mounted content and releases its %s listener', (api) => {
    let matches = false;
    const listeners = new Set();
    const add = (...args) => listeners.add(args.at(-1));
    const remove = (...args) => listeners.delete(args.at(-1));
    vi.spyOn(window, 'matchMedia').mockReturnValue({ get matches() { return matches; },
      ...(api === 'current' ? { addEventListener: add, removeEventListener: remove } : { addListener: add, removeListener: remove }),
    });
    const { result, unmount } = renderHook(usePrefersReducedMotion);
    expect(result.current).toBe(false);
    act(() => { matches = true; listeners.forEach((listener) => listener()); });
    expect(result.current).toBe(true);
    unmount();
    expect(listeners.size).toBe(0);
  });
  it('uses a stable false value when a media query is unavailable', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue(undefined);
    expect(renderHook(usePrefersReducedMotion).result.current).toBe(false);
  });
});
