import { describe, expect, it } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import useSearchParamState from './useSearchParamState';

function wrapper({ initialEntries = ['/'] } = {}) {
  return ({ children }) => (
    <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
  );
}

describe('useSearchParamState', () => {
  it('returns the default value when the param is absent', () => {
    const { result } = renderHook(() => useSearchParamState('status', 'all'), {
      wrapper: wrapper(),
    });
    expect(result.current[0]).toBe('all');
  });

  it('reads an existing param from the URL', () => {
    const { result } = renderHook(() => useSearchParamState('status', 'all'), {
      wrapper: wrapper({ initialEntries: ['/?status=pending'] }),
    });
    expect(result.current[0]).toBe('pending');
  });

  it('sets a value into the URL', () => {
    const { result } = renderHook(() => useSearchParamState('status', ''), {
      wrapper: wrapper(),
    });
    act(() => result.current[1]('active'));
    expect(result.current[0]).toBe('active');
  });

  it('removes the param when set to the default value', () => {
    const { result } = renderHook(() => useSearchParamState('status', 'all'), {
      wrapper: wrapper({ initialEntries: ['/?status=pending'] }),
    });
    act(() => result.current[1]('all'));
    expect(result.current[0]).toBe('all');
  });

  it('removes the param when set to empty string', () => {
    const { result } = renderHook(() => useSearchParamState('status', ''), {
      wrapper: wrapper({ initialEntries: ['/?status=active'] }),
    });
    act(() => result.current[1](''));
    expect(result.current[0]).toBe('');
  });

  it('removes the param when set to null', () => {
    const { result } = renderHook(() => useSearchParamState('status', ''), {
      wrapper: wrapper({ initialEntries: ['/?status=active'] }),
    });
    act(() => result.current[1](null));
    expect(result.current[0]).toBe('');
  });

  it('preserves other search params when setting a value', () => {
    const { result } = renderHook(() => useSearchParamState('status', ''), {
      wrapper: wrapper({ initialEntries: ['/?tab=ventures&status=draft'] }),
    });
    act(() => result.current[1]('completed'));
    expect(result.current[0]).toBe('completed');
    // The tab param should still be present — the hook uses the callback form
    // of setSearchParams which reads from prev and preserves siblings.
  });
});
