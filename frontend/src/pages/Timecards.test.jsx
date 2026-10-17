import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Timecards from './Timecards.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user = buildUser(), extra = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...extra,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Timecards />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Timecards', () => {
  it('closes an approved zero-dollar week and retains its hours without posting a payment', async () => {
    const user = userEvent.setup();
    let card = { id: 2, week_start: '2026-10-05', total_hours: '0.10', total_earnings: '0.00', status: 'approved' };
    const close = spyHandler('post', /\/api\/timecards\/2\/close\/$/, () => {
      card = { ...card, status: 'closed' };
      return card;
    });
    const paid = spyHandler('post', /\/api\/timecards\/2\/mark-paid\/$/, {});
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () => HttpResponse.json([card])),
      http.get('*/api/timecards/2/', () => HttpResponse.json({
        ...card, hourly_earnings: '0.00', bonus_earnings: '0.00', entries: [],
      })), close.handler, paid.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: 'Close timecard' }));
    await waitFor(() => expect(close.calls).toHaveLength(1));
    expect(close.calls[0].body).toEqual({});
    expect(close.calls[0].url).toMatch(/\/api\/timecards\/2\/close\/$/);
    expect(await screen.findByText('Closed')).toBeInTheDocument();
    expect(screen.getByText('0.10h')).toBeInTheDocument();
    expect(screen.getByText('No payment due')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Close timecard' })).not.toBeInTheDocument();
    expect(paid.calls).toHaveLength(0);
  });

  it('prevents repeated close taps while saving and shows the confirmed closed state', async () => {
    const user = userEvent.setup();
    let card = { id: 2, week_start: '2026-10-05', total_hours: '0.10', total_earnings: '0.00', status: 'approved' };
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    let listCalls = 0;
    const close = spyHandler('post', /\/api\/timecards\/2\/close\/$/, () => {
      card = { ...card, status: 'closed' };
      return card;
    });
    renderPage(buildParent(), [
      http.get('*/api/timecards/', async () => {
        listCalls += 1;
        if (listCalls > 1) await gate;
        return HttpResponse.json([card]);
      }),
      http.get('*/api/timecards/2/', () => HttpResponse.json({ ...card, entries: [] })), close.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: 'Close timecard' }));
    const pending = await screen.findByRole('button', { name: 'Closing…' });
    expect(pending).toBeDisabled();
    await user.click(pending);
    release();
    expect(await screen.findByText('Closed')).toBeInTheDocument();
    expect(close.calls).toHaveLength(1);
    expect(close.calls[0].body).toEqual({});
  });

  it('keeps an approved zero-dollar week open when closing fails and permits a retry', async () => {
    const user = userEvent.setup();
    const card = { id: 2, week_start: '2026-10-05', total_hours: '0.10', total_earnings: '0.00', status: 'approved' };
    let attempts = 0;
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () => HttpResponse.json([card])),
      http.get('*/api/timecards/2/', () => HttpResponse.json({ ...card, entries: [] })),
      http.post('*/api/timecards/2/close/', () => {
        attempts += 1;
        return HttpResponse.json({ error: 'Could not close this timecard.' }, { status: 503 });
      }),
    ]);
    await user.click(await screen.findByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: 'Close timecard' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not close this timecard.');
    expect(screen.getByText('Approved')).toBeInTheDocument();
    const retry = screen.getByRole('button', { name: 'Close timecard' });
    expect(retry).toBeEnabled();
    await user.click(retry);
    await waitFor(() => expect(attempts).toBe(2));
  });

  it('renders empty state when no timecards', async () => {
    renderPage(buildUser(), [http.get('*/api/timecards/', () => HttpResponse.json([]))]);
    await waitFor(() => expect(screen.getByText(/no timecards yet/i)).toBeInTheDocument());
  });

  it('renders a list of timecards and expands on click', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([
          { id: 1, week_start: '2026-04-10', total_hours: 5, total_earnings: 50, status: 'pending', username: 'abby' },
        ]),
      ),
      http.get('*/api/timecards/1/', () =>
        HttpResponse.json({
          id: 1, hourly_earnings: 40, bonus_earnings: 10, total_earnings: 50,
          entries: [{ id: 9, project_title: 'P1', clock_in: '2026-04-10T12:00:00Z', duration_minutes: 120 }],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('5h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));
    await waitFor(() => expect(screen.getByText('P1')).toBeInTheDocument());
  });

  it('parent can approve a pending timecard', async () => {
    const user = userEvent.setup();
    const approved = vi.fn();
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([{ id: 1, week_start: '2026-04-10', total_hours: 5, total_earnings: 50, status: 'pending' }]),
      ),
      http.get('*/api/timecards/1/', () =>
        HttpResponse.json({ id: 1, hourly_earnings: 40, bonus_earnings: 10, total_earnings: 50, entries: [] }),
      ),
      http.post('*/api/timecards/1/approve/', () => { approved(); return HttpResponse.json({}); }),
    ]);
    await waitFor(() => expect(screen.getByText('5h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: /approve/i }));
    await waitFor(() => expect(approved).toHaveBeenCalled());
  });

  it('canceling the completed-transfer sheet records no payment', async () => {
    const user = userEvent.setup();
    const paid = spyHandler('post', /\/api\/timecards\/2\/mark-paid\/$/, {});
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([{ id: 2, user: 7, username: 'Abby', week_start: '2026-04-10', total_hours: 2, total_earnings: '20.00', status: 'approved' }]),
      ),
      http.get('*/api/timecards/2/', () =>
        HttpResponse.json({ id: 2, hourly_earnings: '20.00', bonus_earnings: '0.00', total_earnings: '20.00', entries: [] }),
      ),
      http.get('*/api/payments/greenlight/overview/', () => HttpResponse.json({ approved_payable: '20.00', approved_timecards: [{ id: 2, total_earnings: '20.00', week_start: '2026-04-10' }] })),
      paid.handler,
    ]);
    await waitFor(() => expect(screen.getByText('2h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: /record completed transfer/i }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Record a Greenlight transfer for Abby' }));
    await user.click(await dialog.findByRole('button', { name: 'Cancel' }));
    expect(paid.calls).toHaveLength(0);
  });

  it.each([
    { role: 'parent', account: buildParent(), total: '0.00' },
    { role: 'parent', account: buildParent(), total: '-1.00' },
    { role: 'child', account: buildUser(), total: '0.00' },
    { role: 'child', account: buildUser(), total: '-1.00' },
  ])('shows no payment due for an approved $total timecard to a $role', async ({ account, total }) => {
    const user = userEvent.setup();
    const paid = spyHandler('post', /\/api\/timecards\/2\/mark-paid\/$/, {});
    renderPage(account, [
      http.get('*/api/timecards/', () => HttpResponse.json([
        { id: 2, week_start: '2026-10-05', total_hours: '0.10', total_earnings: total, status: 'approved' },
      ])),
      http.get('*/api/timecards/2/', () => HttpResponse.json({
        id: 2, hourly_earnings: total, bonus_earnings: '0.00', total_earnings: total,
        entries: [{ id: 9, project_title: 'Bookmark', clock_in: '2026-10-11T12:00:00Z', duration_minutes: 6 }],
      })),
      paid.handler,
    ]);

    await user.click(await screen.findByRole('button', { name: /week of/i }));
    await screen.findByText('Bookmark');
    expect(screen.getByText('No payment due')).toBeInTheDocument();
    expect(screen.getByText('Approved')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /record completed transfer/i })).not.toBeInTheDocument();
    expect(paid.calls).toHaveLength(0);
    if (account.role === 'child' || Number(total) < 0) {
      expect(screen.queryByRole('button', { name: 'Close timecard' })).not.toBeInTheDocument();
    }
  });

  it('parent can dispute a pending timecard', async () => {
    const user = userEvent.setup();
    const disputed = vi.fn();
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([{ id: 3, week_start: '2026-04-10', total_hours: 1, total_earnings: 10, status: 'pending' }]),
      ),
      http.get('*/api/timecards/3/', () =>
        HttpResponse.json({ id: 3, hourly_earnings: 10, bonus_earnings: 0, total_earnings: 10, entries: [] }),
      ),
      http.post('*/api/timecards/3/dispute/', () => { disputed(); return HttpResponse.json({}); }),
    ]);
    await waitFor(() => expect(screen.getByText('1h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: /dispute/i }));
    await waitFor(() => expect(disputed).toHaveBeenCalled());
  });

  it('surfaces action errors via an ErrorAlert instead of window.alert', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([{ id: 4, week_start: '2026-04-10', total_hours: 1, total_earnings: 10, status: 'pending' }]),
      ),
      http.get('*/api/timecards/4/', () =>
        HttpResponse.json({ id: 4, hourly_earnings: 10, bonus_earnings: 0, total_earnings: 10, entries: [] }),
      ),
      http.post('*/api/timecards/4/approve/', () =>
        HttpResponse.json({ error: 'nope' }, { status: 400 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('1h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: /approve/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('a failed timecard fetch shows a retry-able alert, not the empty state', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderPage(buildUser(), [
      http.get('*/api/timecards/', () => {
        attempts += 1;
        if (attempts === 1) return HttpResponse.json({ detail: 'boom' }, { status: 500 });
        return HttpResponse.json([
          { id: 1, week_start: '2026-04-10', total_hours: 5, total_earnings: 50, status: 'pending' },
        ]);
      }),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/couldn't load your timecards/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/no timecards yet/i)).toBeNull();

    await user.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.getByText('5h')).toBeInTheDocument());
  });

  it('surfaces a failed detail fetch inline, with a retry, instead of never expanding', async () => {
    const user = userEvent.setup();
    let detailCalls = 0;
    renderPage(buildUser(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([{ id: 5, week_start: '2026-04-10', total_hours: 3, total_earnings: 30, status: 'pending' }]),
      ),
      http.get('*/api/timecards/5/', () => {
        detailCalls += 1;
        if (detailCalls === 1) return HttpResponse.json({ detail: 'gone' }, { status: 500 });
        return HttpResponse.json({
          id: 5, hourly_earnings: 30, bonus_earnings: 0, total_earnings: 30,
          entries: [{ id: 1, project_title: 'Shed', clock_in: '2026-04-10T12:00:00Z', duration_minutes: 60 }],
        });
      }),
    ]);
    await waitFor(() => expect(screen.getByText('3h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.getByText('Shed')).toBeInTheDocument());
  });

  it('repeated opening of a payment sheet never posts a payout before confirmation', async () => {
    const user = userEvent.setup();
    const card = { id: 2, user: 7, username: 'Abby', week_start: '2026-04-10', total_hours: 2, total_earnings: 20, status: 'approved' };
    const paid = spyHandler('post', /\/api\/timecards\/\d+\/mark-paid\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () => HttpResponse.json([card])),
      http.get('*/api/payments/greenlight/overview/', () => HttpResponse.json({ approved_payable: '20.00', approved_timecards: [card] })),
      http.get('*/api/timecards/2/', () =>
        HttpResponse.json({ id: 2, hourly_earnings: 20, bonus_earnings: 0, total_earnings: 20, entries: [] }),
      ),
      paid.handler,
    ]);
    await waitFor(() => expect(screen.getByText('2h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));

    await user.dblClick(await screen.findByRole('button', { name: /record completed transfer/i }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Record a Greenlight transfer for Abby' }));
    expect(await dialog.findByRole('button', { name: 'Record completed transfer' })).toBeDisabled();
    expect(paid.calls).toHaveLength(0);
  });

  it('collapses an expanded timecard on second click', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([{ id: 10, week_start: '2026-04-10', total_hours: 5, total_earnings: 50, status: 'paid' }]),
      ),
      http.get('*/api/timecards/10/', () =>
        HttpResponse.json({ id: 10, hourly_earnings: 50, bonus_earnings: 0, total_earnings: 50, entries: [] }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('5h')).toBeInTheDocument());
    const trigger = screen.getByRole('button', { name: /week of/i });
    await user.click(trigger);
    await waitFor(() => expect(screen.getByText('Hourly')).toBeInTheDocument());
    await user.click(trigger);
    expect(screen.queryByText('Hourly')).toBeNull();
  });
});
