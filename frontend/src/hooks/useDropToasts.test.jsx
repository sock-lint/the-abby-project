import { act, renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../test/server.js';
import { useDropToasts } from './useDropToasts.js';

const makeDrop = (over = {}) => ({
  id: 1,
  item_name: 'Ember Potion',
  item_icon: 'flask',
  item_sprite_key: 'ember',
  item_rarity: 'common',
  was_salvaged: false,
  ...over,
});

describe('useDropToasts', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('suppresses toasts on the first poll (seeds seen IDs)', async () => {
    server.use(
      http.get('*/api/drops/recent/', () =>
        HttpResponse.json([makeDrop({ id: 1 }), makeDrop({ id: 2 })]),
      ),
    );
    const { result } = renderHook(() => useDropToasts(1000));
    await waitFor(() => expect(result.current.toasts).toEqual([]));
  });

  it('emits toasts for new drops on subsequent polls', async () => {
    let drops = [makeDrop({ id: 1 })];
    server.use(
      http.get('*/api/drops/recent/', () => HttpResponse.json(drops)),
    );
    const { result } = renderHook(() => useDropToasts(1000));
    await waitFor(() => expect(result.current.toasts).toEqual([]));

    drops = [makeDrop({ id: 1 }), makeDrop({ id: 2, item_name: 'Silver Feather' })];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));
    expect(result.current.toasts[0].item_name).toBe('Silver Feather');
  });

  it('dismiss() removes a toast by id', async () => {
    let drops = [];
    server.use(
      http.get('*/api/drops/recent/', () => HttpResponse.json(drops)),
    );
    const { result } = renderHook(() => useDropToasts(1000));
    await waitFor(() => expect(result.current.toasts).toEqual([]));
    drops = [makeDrop({ id: 5 })];
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));
    act(() => result.current.dismiss(5));
    expect(result.current.toasts).toEqual([]);
  });

  it('handles DRF-paginated response shape', async () => {
    let body = { count: 0, results: [] };
    server.use(
      http.get('*/api/drops/recent/', () => HttpResponse.json(body)),
    );
    const { result } = renderHook(() => useDropToasts(1000));
    await waitFor(() => expect(result.current.toasts).toEqual([]));
    body = { count: 1, results: [makeDrop({ id: 9 })] };
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));
  });

  it('handles a non-object response without crashing', async () => {
    server.use(
      http.get('*/api/drops/recent/', () => HttpResponse.json(null)),
    );
    const { result } = renderHook(() => useDropToasts(1000));
    // Should complete the first poll without throwing.
    await waitFor(() => expect(result.current.toasts).toEqual([]));
  });

  it('swallows fetch errors silently', async () => {
    server.use(
      http.get('*/api/drops/recent/', () =>
        HttpResponse.json({ error: 'boom' }, { status: 500 }),
      ),
    );
    const { result } = renderHook(() => useDropToasts(1000));
    // Component should not crash; toasts stay empty.
    await waitFor(() => expect(result.current.toasts).toEqual([]));
  });

  it('stops polling on unmount', async () => {
    server.use(
      http.get('*/api/drops/recent/', () => HttpResponse.json([])),
    );
    const { unmount } = renderHook(() => useDropToasts(1000));
    await waitFor(() => expect(vi.getTimerCount()).toBeGreaterThan(0));
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
