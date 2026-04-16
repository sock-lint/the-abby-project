import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useFormState } from './useFormState.js';

describe('useFormState', () => {
  it('seeds form with the initial values', () => {
    const { result } = renderHook(() => useFormState({ name: '', count: 0 }));
    expect(result.current.form).toEqual({ name: '', count: 0 });
    expect(result.current.saving).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('merges partial updates via set()', () => {
    const { result } = renderHook(() => useFormState({ name: '', age: 10 }));
    act(() => result.current.set({ name: 'abby' }));
    expect(result.current.form).toEqual({ name: 'abby', age: 10 });
  });

  it('supports functional updates via set()', () => {
    const { result } = renderHook(() => useFormState({ count: 1 }));
    act(() => result.current.set((f) => ({ count: f.count + 2 })));
    expect(result.current.form).toEqual({ count: 3 });
  });

  it('setForm replaces wholesale', () => {
    const { result } = renderHook(() => useFormState({ a: 1, b: 2 }));
    act(() => result.current.setForm({ a: 9 }));
    expect(result.current.form).toEqual({ a: 9 });
  });

  it('reset restores initial values', () => {
    const { result } = renderHook(() => useFormState({ name: 'x' }));
    act(() => result.current.set({ name: 'y' }));
    act(() => result.current.reset());
    expect(result.current.form).toEqual({ name: 'x' });
  });

  it('setSaving and setError round-trip', () => {
    const { result } = renderHook(() => useFormState({}));
    act(() => {
      result.current.setSaving(true);
      result.current.setError('boom');
    });
    expect(result.current.saving).toBe(true);
    expect(result.current.error).toBe('boom');
  });
});
