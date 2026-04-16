import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderHook, waitFor } from '@testing-library/react';
import useParentDashboard from './useParentDashboard';
import { server } from '../test/server';

describe('useParentDashboard', () => {
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
          { id: 3, reward_name: 'Movie', user_id: 2, user_name: 'Abby', status: 'pending', created_at: '2026-04-16T09:00:00Z' },
          { id: 4, reward_name: 'Fulfilled thing', user_id: 2, user_name: 'Abby', status: 'fulfilled', created_at: '2026-04-16T07:00:00Z' },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([{ id: 2, username: 'abby' }])),
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
    expect(result.current.kids).toHaveLength(1);
  });

  it('tolerates individual endpoint failures without throwing', async () => {
    server.use(
      http.get('*/api/chore-completions/', () => HttpResponse.json({ error: 'nope' }, { status: 500 })),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/dashboard/', () => HttpResponse.json({})),
    );

    const { result } = renderHook(() => useParentDashboard());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.pending).toEqual([]);
  });
});
