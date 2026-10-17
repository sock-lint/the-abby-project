import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderHook, waitFor } from '@testing-library/react';
import useParentDashboard from './useParentDashboard';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';

describe('useParentDashboard', () => {
  it('labels homework without a supplied title with the current feature name', async () => {
    server.use(http.get('*/api/homework/dashboard/', () => HttpResponse.json({
      pending_submissions: [{ id: 91, user_id: 2 }],
    })));
    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.pending.find((row) => row.id === 91)?.title).toBe('Homework');
  });

  it('merges chores + homework + redemptions into a single pending list sorted newest-first', async () => {
    server.use(
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 1, chore_title: 'Dishes', user: 2, user_name: 'Abby', submitted_at: '2026-04-16T08:00:00Z' },
        ]),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 2, assignment_title: 'Math', user_id: 2, user_name: 'Abby', submitted_at: '2026-04-16T10:00:00Z' },
          ],
        }),
      ),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([
          { id: 3, reward: { name: 'Movie', cost_coins: 60 }, coin_cost_snapshot: 50, user: 2, user_name: 'Abby', status: 'pending', requested_at: '2026-04-16T09:00:00Z' },
          { id: 4, reward: { name: 'Fulfilled thing' }, coin_cost_snapshot: 20, user: 2, user_name: 'Abby', status: 'fulfilled', requested_at: '2026-04-16T07:00:00Z' },
        ]),
      ),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ this_week: { hours_worked: 0, earnings: 0 } }),
      ),
    );

    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Fulfilled redemption is filtered out; 3 pending items remain.
    expect(result.current.pending).toHaveLength(3);
    // Sorted newest-first by submittedAt: homework (10:00) > redemption (09:00) > chore (08:00).
    expect(result.current.pending.map((i) => i.kind)).toEqual([
      'homework', 'redemption', 'chore',
    ]);
    expect(result.current.pending[1]).toMatchObject({
      title: 'Movie', subtitle: '50 coins', kidId: 2, submittedAt: '2026-04-16T09:00:00Z',
    });
  });

  it.each([
    ['/api/redemptions/', 'redemption', '?status=pending'],
    ['/api/coins/exchange/list/', 'exchange', '?status=pending'],
    ['/api/chore-completions/', 'chore', '?status=pending'],
    ['/api/chores/', 'chore_proposal', '?pending=true'],
    ['/api/habits/', 'habit_proposal', '?pending=true'],
  ])('includes every pending page from %s', async (path, kind, filter) => {
    const makeRow = (id) => ({
      id, user: 2, created_by: 2, user_name: 'Abby', status: 'pending',
      reward: { name: `Prize ${id}` }, coin_cost_snapshot: 30,
      dollar_amount: '3.00', coin_amount: 30,
    });
    const fetch = spyHandler('get', `*${path}`, ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get('status') === 'approved') return [];
      expect(url.searchParams.toString()).toContain(filter.slice(1));
      return url.searchParams.get('page') === '2'
        ? { count: 21, next: null, results: [makeRow(21)] }
        : { count: 21, next: `http://localhost${path}${filter}&page=2`, results: Array.from({ length: 20 }, (_, i) => makeRow(i + 1)) };
    });
    server.use(fetch.handler);
    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));
    const pending = result.current.pending.filter((row) => row.kind === kind);
    expect(pending).toHaveLength(21);
    expect(pending.some((row) => row.id === 21)).toBe(true);
    expect(fetch.calls.filter((call) => new URL(call.url).searchParams.get('status') !== 'approved')).toHaveLength(2);
    expect(result.current.failedSources).toEqual([]);
  });

  it('reports an incomplete paginated queue as failed instead of silently showing its first page', async () => {
    const fetch = spyHandler('get', '*/api/redemptions/', ({ request }) =>
      new URL(request.url).searchParams.get('status') === 'approved' ? [] : new URL(request.url).searchParams.has('page')
        ? HttpResponse.json({ detail: 'Temporary failure' }, { status: 503 })
        : {
          count: 21, next: 'http://localhost/api/redemptions/?status=pending&page=2',
          results: [{ id: 1, status: 'pending', reward: { name: 'Movie' } }],
        },
    );
    server.use(fetch.handler);
    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.failedSources).toContain('reward redemptions');
    expect(result.current.pending.filter((row) => row.kind === 'redemption')).toEqual([]);
    expect(fetch.calls.filter((call) => new URL(call.url).searchParams.get('status') !== 'approved')).toHaveLength(2);
  });

  it('counts every pending print page without adding prints to the inline approval queue', async () => {
    const fetch = spyHandler('get', '*/api/print-requests/', ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get('status')).toBe('pending');
      return url.searchParams.get('page') === '2'
        ? { count: 21, next: null, results: [{ id: 21, status: 'pending' }] }
        : {
          count: 21, next: 'http://localhost/api/print-requests/?status=pending&page=2',
          results: Array.from({ length: 20 }, (_, i) => ({ id: i + 1, status: 'pending' })),
        };
    });
    server.use(fetch.handler);
    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.pendingPrintCount).toBe(21);
    expect(result.current.pending).toEqual([]);
    expect(result.current.failedSources).toEqual([]);
    expect(fetch.calls.filter((call) => new URL(call.url).searchParams.get('status') !== 'approved')).toHaveLength(2);
  });

  it('counts parent print decisions without counting quotes that await the child', async () => {
    server.use(http.get('*/api/print-requests/', () => HttpResponse.json([
      { id: 1, status: 'pending' },
      { id: 2, status: 'quoted' },
      { id: 3, status: 'approved' },
      { id: 4, status: 'printing' },
      { id: 5, status: 'completed' },
    ])));
    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.pendingPrintCount).toBe(1);
    expect(result.current.pending).toEqual([]);
  });

  it('reports print approvals as unavailable if a later page cannot be checked', async () => {
    const fetch = spyHandler('get', '*/api/print-requests/', ({ request }) => (
      new URL(request.url).searchParams.has('page')
        ? HttpResponse.json({ detail: 'Temporary failure' }, { status: 503 })
        : {
          count: 21, next: 'http://localhost/api/print-requests/?status=pending&page=2',
          results: [{ id: 1, status: 'pending' }],
        }
    ));
    server.use(fetch.handler);
    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.failedSources).toContain('print approvals');
    expect(result.current.pendingPrintCount).toBe(0);
    expect(result.current.pending).toEqual([]);
    expect(fetch.calls.filter((call) => new URL(call.url).searchParams.get('status') !== 'approved')).toHaveLength(2);
  });

  it('includes pending money→coins exchange requests', async () => {
    server.use(
      http.get('*/api/coins/exchange/list/', () =>
        HttpResponse.json([
          {
            id: 7, user: 2, user_name: 'Abby', dollar_amount: '5.00',
            coin_amount: 50, status: 'pending', created_at: '2026-04-16T11:00:00Z',
          },
          {
            id: 8, user: 2, user_name: 'Abby', dollar_amount: '2.00',
            coin_amount: 20, status: 'approved', created_at: '2026-04-16T07:00:00Z',
          },
        ]),
      ),
    );

    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));

    const exchanges = result.current.pending.filter((i) => i.kind === 'exchange');
    expect(exchanges).toHaveLength(1);
    expect(exchanges[0].id).toBe(7);
    expect(exchanges[0].title).toContain('5.00');
    expect(exchanges[0].subtitle).toContain('50 coins');
  });

  it('tolerates individual endpoint failures without throwing', async () => {
    server.use(
      http.get('*/api/chore-completions/', () => HttpResponse.json({ error: 'nope' }, { status: 500 })),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/dashboard/', () => HttpResponse.json({})),
    );

    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.pending).toEqual([]);
  });

  it('surfaces a label for each failed source so the dashboard can warn the parent', async () => {
    server.use(
      http.get('*/api/chore-completions/', () => HttpResponse.json({ error: 'nope' }, { status: 500 })),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/dashboard/', () => HttpResponse.json({})),
    );

    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));
    // The chore endpoint 500s — the label for that source should appear.
    expect(result.current.failedSources).toContain('chore approvals');
  });

  it('reports an empty failedSources list when every fetch succeeds', async () => {
    // Default permissive handlers return success for every source — assert
    // the clean-path contract so future callers can branch on
    // ``failedSources.length`` without worrying about a misleading non-empty
    // sentinel slipping through.
    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.failedSources).toEqual([]);
  });
});
