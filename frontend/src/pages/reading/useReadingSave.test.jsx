import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import useReadingSave from './useReadingSave';

it('saves on browsers with secure random bytes but no randomUUID', async () => {
  const browserCrypto = globalThis.crypto;
  vi.stubGlobal('crypto', { getRandomValues: browserCrypto.getRandomValues.bind(browserCrypto) });
  try {
    const create = vi.fn().mockResolvedValue({ id: 1, title: 'A reading book' });
    const saved = vi.fn();
    const { result } = renderHook(() => useReadingSave({
      create, update: vi.fn(), onSaved: saved, credential: 'test-session',
    }));
    await act(async () => { await result.current.save({ title: 'A reading book' }); });
    expect(create).toHaveBeenCalledOnce();
    expect(create.mock.calls[0][0]).toEqual({
      title: 'A reading book',
      client_request_id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/),
    });
    expect(saved).toHaveBeenCalledWith({ id: 1, title: 'A reading book' });
  } finally { vi.unstubAllGlobals(); }
});
