import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '../test/server.js';
import { buildParent, buildUser } from '../test/factories.js';
import { AuthProvider } from './useApi.js';
import { useRole } from './useRole.js';

function wrap({ children }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('useRole', () => {
  it('returns isParent=true for parent users', async () => {
    const parent = buildParent();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(parent)));
    const { result } = renderHook(() => useRole(), { wrapper: wrap });
    await waitFor(() => expect(result.current.user).toEqual(parent));
    expect(result.current.isParent).toBe(true);
    expect(result.current.isChild).toBe(false);
    expect(result.current.role).toBe('parent');
  });

  it('returns isChild=true for child users', async () => {
    const child = buildUser();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(child)));
    const { result } = renderHook(() => useRole(), { wrapper: wrap });
    await waitFor(() => expect(result.current.user).toEqual(child));
    expect(result.current.isParent).toBe(false);
    expect(result.current.isChild).toBe(true);
    expect(result.current.role).toBe('child');
  });

  it('returns neither role when unauthenticated', async () => {
    server.use(
      http.get('*/api/auth/me/', () =>
        HttpResponse.json({ detail: 'unauth' }, { status: 401 }),
      ),
    );
    const { result } = renderHook(() => useRole(), { wrapper: wrap });
    await waitFor(() => expect(result.current.user).toBeNull());
    expect(result.current.isParent).toBe(false);
    expect(result.current.isChild).toBe(false);
    expect(result.current.role).toBeUndefined();
  });
});
