import { describe, expect, it } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import useParentPendingCounts from './useParentPendingCounts';
import { server } from '../test/server';

describe('complete parent attention counts', () => {
  it('counts creation bonuses and print requests alongside ordinary approvals', async () => {
    server.use(
      http.get('*/api/creations/pending/', () => HttpResponse.json([{ id: 9, user: 2 }])),
      http.get('*/api/print-requests/', () => HttpResponse.json([{ id: 10, status: 'pending' }])),
    );
    const { result } = renderHook(() => useParentPendingCounts());
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.total).toBe(2);
  });

  it('reports an unavailable source instead of claiming a complete zero', async () => {
    server.use(http.get('*/api/chore-completions/', () => HttpResponse.json({}, { status: 503 })));
    const { result } = renderHook(() => useParentPendingCounts());
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.incomplete).toBe(true);
  });
});
