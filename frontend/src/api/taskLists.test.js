import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { getFamilyChildren, getFamilyChores, getFamilyHabits } from './taskLists';

describe('Complete family task lists', () => {
  it.each([
    ['/children/', getFamilyChildren], ['/chores/', getFamilyChores], ['/habits/', getFamilyHabits],
  ])('reads beyond twenty %s records on the same endpoint', async (path, read) => {
    const calls = [];
    server.use(http.get(`*/api${path}`, ({ request }) => {
      const url = new URL(request.url);
      calls.push(url.pathname + (url.searchParams.has('page') ? `?page=${url.searchParams.get('page')}` : ''));
      return HttpResponse.json(url.searchParams.get('page') === '2'
        ? { count: 21, next: null, results: [{ id: 21 }] }
        : { count: 21, next: 'https://untrusted.invalid/api/other/?page=9', results: Array.from({ length: 20 }, (_, index) => ({ id: index + 1 })) });
    }));
    expect(await read()).toHaveLength(21);
    expect(calls).toEqual([`/api${path}`, `/api${path}?page=2`]);
  });

  it('rejects a failed later page instead of presenting the first page as complete', async () => {
    server.use(http.get('*/api/chores/', ({ request }) => new URL(request.url).searchParams.has('page')
      ? HttpResponse.json({ error: 'Later page unavailable' }, { status: 503 })
      : HttpResponse.json({ count: 21, next: '/api/chores/?page=2', results: [{ id: 1 }] })));
    await expect(getFamilyChores()).rejects.toThrow('Later page unavailable');
  });
});
