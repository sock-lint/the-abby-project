import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useConfirmState } from './useConfirmState.js';

describe('useConfirmState', () => {
  it('starts with confirmState null', () => {
    const { result } = renderHook(() => useConfirmState());
    expect(result.current.confirmState).toBeNull();
  });

  it('askConfirm stashes its opts', () => {
    const { result } = renderHook(() => useConfirmState());
    const opts = { title: 'Delete?', onConfirm: () => {} };
    act(() => result.current.askConfirm(opts));
    expect(result.current.confirmState).toBe(opts);
  });

  it('closeConfirm clears it', () => {
    const { result } = renderHook(() => useConfirmState());
    act(() => result.current.askConfirm({ title: 'x' }));
    act(() => result.current.closeConfirm());
    expect(result.current.confirmState).toBeNull();
  });
});
