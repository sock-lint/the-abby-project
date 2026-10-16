import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildParent, buildUser } from '../../test/factories';
import Forge from './index';

function stubMe(user) {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(user)));
  localStorage.setItem('abby_auth_token', 'test-token');
}

// Mirrors the server: PrintRequestViewSet honours a CSV ?status= filter. The
// page fetches the open and closed sets separately, so a stub that ignored the
// param would hand both fetches the same rows and hide the split entirely.
function stubRequests(rows, { total } = {}) {
  server.use(
    http.get('*/api/print-requests/', ({ request }) => {
      const wanted = new URL(request.url).searchParams.get('status');
      const results = wanted
        ? rows.filter((r) => wanted.split(',').includes(r.status))
        : rows;
      return HttpResponse.json({
        count: total ?? results.length, next: null, previous: null, results,
      });
    }),
  );
}

function buildRequest(over = {}) {
  return {
    id: 5,
    user: 1,
    user_name: 'Abby',
    username: 'abby',
    title: 'Articulated Dragon',
    source_kind: 'makerworld',
    source_url: 'https://makerworld.com/en/models/1',
    thumbnail: null,
    color: 'green',
    reason: 'Present for Nana.',
    needed_by: null,
    status: 'pending',
    parent_notes: '',
    slug: '',
    plate_filename: '',
    latest_job: null,
    ...over,
  };
}

describe('3D Printing', () => {
  it('shows the child an empty queue and a way in', async () => {
    stubMe(buildUser({ id: 1 }));
    stubRequests([]);
    renderWithProviders(<Forge />);

    expect(await screen.findByText(/No print requests yet/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /ask for a print/i }),
    ).toBeInTheDocument();
  });

  it('opens the submit modal from the ask button', async () => {
    stubMe(buildUser({ id: 1 }));
    stubRequests([]);
    const { user } = renderWithProviders(<Forge />);

    await user.click(await screen.findByRole('button', { name: /ask for a print/i }));
    expect(
      await screen.findByRole('dialog', { name: /ask for a print/i }),
    ).toBeInTheDocument();
  });

  it('opens the submit modal straight away on ?new=1 (the quick-action deep link)', async () => {
    stubMe(buildUser({ id: 1 }));
    stubRequests([]);
    renderWithProviders(<Forge />, { route: '/quests?tab=forge&new=1' });

    expect(
      await screen.findByRole('dialog', { name: /ask for a print/i }),
    ).toBeInTheDocument();
  });

  it('gives the parent an approval queue and the budget panel; the child gets neither', async () => {
    stubMe(buildParent());
    stubRequests([buildRequest()]);
    server.use(
      http.get('*/api/print-budgets/', () =>
        HttpResponse.json({
          count: 1, next: null, previous: null,
          results: [{
            id: 3, user: 1, user_name: 'Abby', username: 'abby',
            grams_per_month: '500.00', minutes_per_month: null, is_active: true,
            notes: '', period_month: '2026-08-01',
            grams_used: '120.00', minutes_used: 0,
            grams_remaining: '380.00', minutes_remaining: null,
          }],
        }),
      ),
    );
    const { unmount } = renderWithProviders(<Forge />);

    expect(await screen.findByText('Awaiting approval')).toBeInTheDocument();
    expect(screen.getByText('Monthly budgets')).toBeInTheDocument();
    expect(screen.getByText('Printers')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Decide' })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /ask for a print/i }),
    ).not.toBeInTheDocument();
    unmount();

    stubMe(buildUser({ id: 1 }));
    stubRequests([buildRequest()]);
    renderWithProviders(<Forge />);
    expect(await screen.findByText('Print requests')).toBeInTheDocument();
    expect(screen.queryByText('Monthly budgets')).not.toBeInTheDocument();
    expect(screen.queryByText('Awaiting approval')).not.toBeInTheDocument();
  });

  it('opens the approval sheet when a parent taps Decide', async () => {
    stubMe(buildParent());
    stubRequests([buildRequest()]);
    const { user } = renderWithProviders(<Forge />);

    await user.click(await screen.findByRole('button', { name: 'Decide' }));
    expect(
      await screen.findByRole('dialog', { name: /decide on this print/i }),
    ).toBeInTheDocument();
  });

  it('POSTs to the cancel endpoint after the owner confirms', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/5\/cancel\/$/, {
      id: 5, status: 'cancelled',
    });
    server.use(spy.handler);

    stubMe(buildUser({ id: 1 }));
    stubRequests([buildRequest()]);
    const { user } = renderWithProviders(<Forge />);

    await user.click(await screen.findByRole('button', { name: 'Cancel' }));
    await user.click(
      await screen.findByRole('button', { name: /cancel it/i }),
    );

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-requests\/5\/cancel\/$/);
  });

  it('asks only for unlinked jobs — without the filter a parent sees every print', async () => {
    const urls = [];
    server.use(
      http.get('*/api/print-jobs/', ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );
    stubMe(buildParent());
    stubRequests([]);
    renderWithProviders(<Forge />);

    await waitFor(() => expect(urls.length).toBeGreaterThan(0));
    const jobsUrl = new URL(urls[0]);
    expect(jobsUrl.pathname).toBe('/api/print-jobs/');
    expect(jobsUrl.searchParams.get('unlinked')).toBe('true');
    expect(jobsUrl.searchParams.get('_abby_session')).toBeTruthy();
  });

  it('asks the server for the open statuses so history cannot bury the queue', async () => {
    // The list endpoint paginates at 20, newest first. Deriving the approval
    // queue from one unfiltered page means a pending request falls off the end
    // once 20 finished ones pile up in front of it.
    const urls = [];
    server.use(
      http.get('*/api/print-requests/', ({ request }) => {
        urls.push(request.url);
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );
    stubMe(buildParent());
    renderWithProviders(<Forge />);

    await waitFor(() => expect(urls.length).toBeGreaterThanOrEqual(2));
    const statuses = urls.map((u) => new URL(u).searchParams.get('status'));
    expect(statuses).toContain('pending,quoted,approved,printing,failed');
    expect(statuses).toContain('completed,rejected,cancelled');
  });

  it('exchanges the owner’s quoted coins and displays the confirmed paid request', async () => {
    stubMe(buildUser({ id: 1 }));
    let request = buildRequest({
      status: 'quoted', coin_cost: 3, minutes_per_coin_snapshot: 10,
      estimated_minutes: 21, coins_paid: 0, coins_refunded: 0,
      plate_filename: 'req-0005-articulated-dragon.3mf',
    });
    let reads = 0;
    server.use(http.get('*/api/print-requests/', ({ request: read }) => {
      reads += 1;
      return HttpResponse.json(new URL(read.url).searchParams.get('status').includes(request.status) ? [request] : []);
    }));
    const exchange = spyHandler('post', /\/api\/print-requests\/5\/exchange\/$/, () => {
      request = { ...request, status: 'approved', coins_paid: 3 };
      return request;
    });
    server.use(exchange.handler);
    const { user } = renderWithProviders(<Forge />);
    await user.click(await screen.findByRole('button', { name: 'Exchange 3 coins' }));
    await waitFor(() => expect(exchange.calls).toHaveLength(1));
    expect(exchange.calls[0].body).toEqual({});
    expect(exchange.calls[0].url).toMatch(/\/api\/print-requests\/5\/exchange\/$/);
    expect(await screen.findByText('Exchanged 3 coins')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Exchange 3 coins' })).not.toBeInTheDocument();
    expect(await screen.findByText('req-0005-articulated-dragon.3mf')).toBeInTheDocument();
    await waitFor(() => expect(reads).toBeGreaterThanOrEqual(4));
  });

  it('keeps an insufficient-balance quote retryable and allows cancelling it', async () => {
    stubMe(buildUser({ id: 1 }));
    stubRequests([buildRequest({ status: 'quoted', coin_cost: 3, minutes_per_coin_snapshot: 10 })]);
    const exchange = spyHandler('post', /\/api\/print-requests\/5\/exchange\/$/,
      HttpResponse.json({ error: 'You need 3 coins but only have 2.' }, { status: 409 }));
    const cancel = spyHandler('post', /\/api\/print-requests\/5\/cancel\/$/, { id: 5, status: 'cancelled' });
    server.use(exchange.handler, cancel.handler);
    const { user } = renderWithProviders(<Forge />);
    await user.click(await screen.findByRole('button', { name: 'Exchange 3 coins' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('You need 3 coins but only have 2.');
    expect(screen.getByRole('button', { name: 'Exchange 3 coins' })).toBeEnabled();
    expect(screen.queryByText('Exchanged 3 coins')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(await screen.findByRole('button', { name: 'Cancel it' }));
    await waitFor(() => expect(cancel.calls).toHaveLength(1));
    expect(cancel.calls[0].body).toBeNull();
  });

  it('shows parents the waiting quote without the child’s exchange action', async () => {
    stubMe(buildParent());
    stubRequests([buildRequest({ status: 'quoted', coin_cost: 3 })]);
    renderWithProviders(<Forge />);
    expect(await screen.findByText('Awaiting coin exchange')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Exchange 3 coins' })).not.toBeInTheDocument();
  });

  it('keeps the paid server receipt when the follow-up list read fails', async () => {
    stubMe(buildUser({ id: 1 }));
    const quoted = buildRequest({
      status: 'quoted', coin_cost: 4, minutes_per_coin_snapshot: 15,
      estimated_minutes: 60, coins_paid: 0, coins_refunded: 0,
    });
    let paid = false;
    server.use(http.get('*/api/print-requests/', ({ request }) => {
      if (paid) return HttpResponse.json({ detail: 'Cannot refresh right now.' }, { status: 503 });
      return HttpResponse.json(new URL(request.url).searchParams.get('status').includes('quoted') ? [quoted] : []);
    }));
    const exchange = spyHandler('post', /\/api\/print-requests\/5\/exchange\/$/, () => {
      paid = true;
      return { ...quoted, status: 'approved', coins_paid: 4 };
    });
    server.use(exchange.handler);
    const { user } = renderWithProviders(<Forge />);
    await user.click(await screen.findByRole('button', { name: 'Exchange 4 coins' }));
    expect(await screen.findByText('Exchanged 4 coins')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot refresh right now.');
    expect(screen.queryByRole('button', { name: 'Exchange 4 coins' })).not.toBeInTheDocument();
    expect(exchange.calls).toHaveLength(1);
  });

  it('says how much closed history it is not showing', async () => {
    stubMe(buildParent());
    stubRequests(
      [buildRequest({ id: 9, status: 'completed', title: 'Old dragon' })],
      { total: 57 },
    );
    renderWithProviders(<Forge />);

    expect(await screen.findByText(/Showing the 1 most recent of 57/i)).toBeInTheDocument();
  });

  it('shows the live printer view to a child only while her own print is running', async () => {
    server.use(
      http.get('*/api/printers/', () =>
        HttpResponse.json({
          count: 1, next: null, previous: null,
          results: [{ id: 1, name: 'X1C in the garage', serial: 'ABC', is_active: true }],
        }),
      ),
    );

    stubMe(buildUser({ id: 1 }));
    stubRequests([buildRequest({ status: 'approved' })]);
    const { unmount } = renderWithProviders(<Forge />);
    expect(await screen.findByText('Print requests')).toBeInTheDocument();
    expect(screen.queryByText('Printing now')).not.toBeInTheDocument();
    unmount();

    stubMe(buildUser({ id: 1 }));
    stubRequests([buildRequest({
      status: 'printing',
      latest_job: {
        id: 7, state: 'running', percent_complete: 62,
        layer_num: 120, total_layer_num: 300, remaining_minutes: 45,
        failure_reason: null, started_at: '2026-08-27T10:00:00Z', finished_at: null,
      },
    })]);
    renderWithProviders(<Forge />);
    expect(await screen.findByText('Printing now')).toBeInTheDocument();
  });
});
