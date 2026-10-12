import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import usePetMutationGuard from './usePetMutationGuard';

describe('Pet mutation receipt guard', () => {
  it('blocks a duplicate click until the first request finishes', () => {
    const { result } = renderHook(() => usePetMutationGuard());
    const first = result.current();
    expect(first.isCurrent()).toBe(true);
    expect(result.current()).toBeNull();
    first.finish();
    expect(result.current()).not.toBeNull();
  });
  it('rejects receipts from the account that was replaced during a request', () => {
    const { result } = renderHook(() => usePetMutationGuard());
    const request = result.current();
    localStorage.setItem('abby_auth_token', 'different-synthetic-session');
    expect(request.isCurrent()).toBe(false);
    request.finish();
  });
  it('rejects receipts after leaving the page even if the save committed', () => {
    const { result, unmount } = renderHook(() => usePetMutationGuard());
    const request = result.current();
    unmount();
    expect(request.isCurrent()).toBe(false);
    request.finish();
  });
});
