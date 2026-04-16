import { http, HttpResponse } from 'msw';

/**
 * spyHandler(method, urlPattern, response) → { handler, calls }
 *
 * Returns an MSW handler that records every matching request as
 * { url, method, body } in the `calls` array, then returns `response`
 * (a plain JSON value, an `HttpResponse`, or a function that receives
 * `{ request, body }` and returns either).
 *
 * Use in interaction tests to verify that clicking a button actually
 * fires the right network call with the right payload — the gap that
 * permissive default handlers leave open.
 *
 * Example:
 *   const tap = spyHandler('post', /\/api\/habits\/\d+\/log\/$/, { ok: true });
 *   server.use(tap.handler);
 *   await user.click(button);
 *   await waitFor(() => expect(tap.calls).toHaveLength(1));
 *   expect(tap.calls[0].body).toEqual({ direction: 1 });
 *   expect(tap.calls[0].url).toMatch(/\/habits\/7\/log\/$/);
 */
export function spyHandler(method, urlPattern, response) {
  const calls = [];
  const m = method.toLowerCase();
  const handler = http[m](urlPattern, async ({ request }) => {
    let body = null;
    if (m !== 'get' && m !== 'delete' && m !== 'head') {
      try {
        body = await request.clone().json();
      } catch {
        body = null;
      }
    }
    calls.push({ url: request.url, method: request.method, body });
    const value = typeof response === 'function' ? response({ request, body }) : response;
    if (value instanceof HttpResponse) return value;
    return HttpResponse.json(value ?? { ok: true });
  });
  return { handler, calls };
}
