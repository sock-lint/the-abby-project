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

function stubRequests(rows) {
  server.use(
    http.get('*/api/print-requests/', () =>
      HttpResponse.json({
        count: rows.length, next: null, previous: null, results: rows,
      }),
    ),
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

describe('Forge', () => {
  it('shows the child an empty queue and a way in', async () => {
    stubMe(buildUser({ id: 1 }));
    stubRequests([]);
    renderWithProviders(<Forge />);

    expect(await screen.findByText(/Nothing in the queue/i)).toBeInTheDocument();
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

    expect(await screen.findByText('Awaiting your decision')).toBeInTheDocument();
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
    expect(await screen.findByText('In the queue')).toBeInTheDocument();
    expect(screen.queryByText('Monthly budgets')).not.toBeInTheDocument();
    expect(screen.queryByText('Awaiting your decision')).not.toBeInTheDocument();
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
    expect(urls[0]).toMatch(/\/api\/print-jobs\/\?unlinked=true$/);
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
    expect(await screen.findByText('In the queue')).toBeInTheDocument();
    expect(screen.queryByText('On the bed')).not.toBeInTheDocument();
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
    expect(await screen.findByText('On the bed')).toBeInTheDocument();
  });
});
