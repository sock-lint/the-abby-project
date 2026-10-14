import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRequestId } from './requestId';

afterEach(() => vi.unstubAllGlobals());

describe('Retry request identifiers', () => {
  it('uses the browser UUID when available', () => {
    const randomUUID = vi.fn(() => 'f708a533-ec64-48de-9ed0-9c488208adfe');
    vi.stubGlobal('crypto', { randomUUID });
    expect(createRequestId()).toBe('f708a533-ec64-48de-9ed0-9c488208adfe');
    expect(randomUUID).toHaveBeenCalledOnce();
  });

  it('creates distinct valid v4 UUIDs using secure bytes when Safari lacks randomUUID', () => {
    let sequence = 0;
    const getRandomValues = vi.fn((bytes) => {
      sequence += 1;
      bytes.fill(sequence);
      return bytes;
    });
    vi.stubGlobal('crypto', { getRandomValues });
    const first = createRequestId();
    const second = createRequestId();
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    expect(first).toMatch(uuid);
    expect(second).toMatch(uuid);
    expect(second).not.toBe(first);
    expect(getRandomValues).toHaveBeenCalledTimes(2);
    expect(getRandomValues.mock.calls[0][0]).toBeInstanceOf(Uint8Array);
  });
});
