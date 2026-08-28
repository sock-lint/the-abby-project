import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
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
  it('renders empty state when no timecards', async () => {
    renderPage(buildUser(), [http.get('*/api/timecards/', () => HttpResponse.json([]))]);
    await waitFor(() => expect(screen.getByText(/no weeks logged yet/i)).toBeInTheDocument());
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

  it('parent can mark approved timecard as paid', async () => {
    const user = userEvent.setup();
    const paid = vi.fn();
    renderPage(buildParent(), [
      http.get('*/api/timecards/', () =>
        HttpResponse.json([{ id: 2, week_start: '2026-04-10', total_hours: 2, total_earnings: 20, status: 'approved' }]),
      ),
      http.get('*/api/timecards/2/', () =>
        HttpResponse.json({ id: 2, hourly_earnings: 20, bonus_earnings: 0, total_earnings: 20, entries: [] }),
      ),
      http.post('*/api/timecards/2/mark-paid/', () => { paid(); return HttpResponse.json({}); }),
    ]);
    await waitFor(() => expect(screen.getByText('2h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: /mark as paid/i }));
    await waitFor(() => expect(paid).toHaveBeenCalled());
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
      expect(screen.getByText(/couldn't load your wages/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/no weeks logged yet/i)).toBeNull();

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

  it('double-tapping Mark as paid only posts once', async () => {
    // markTimecardPaid has no server-side status guard, so a second tap
    // during the in-flight window really would write a second payout row.
    const user = userEvent.setup();
    const card = { id: 2, week_start: '2026-04-10', total_hours: 2, total_earnings: 20, status: 'approved' };
    let listCalls = 0;
    let releaseReload;
    const reloadGate = new Promise((r) => { releaseReload = r; });
    const paid = spyHandler('post', /\/api\/timecards\/\d+\/mark-paid\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/timecards/', async () => {
        listCalls += 1;
        // Hold the post-action refetch open so the button stays in its
        // pending state long enough for a second tap.
        if (listCalls > 1) await reloadGate;
        return HttpResponse.json([card]);
      }),
      http.get('*/api/timecards/2/', () =>
        HttpResponse.json({ id: 2, hourly_earnings: 20, bonus_earnings: 0, total_earnings: 20, entries: [] }),
      ),
      paid.handler,
    ]);
    await waitFor(() => expect(screen.getByText('2h')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /week of/i }));

    await user.click(await screen.findByRole('button', { name: /mark as paid/i }));
    const pendingButton = await screen.findByRole('button', { name: /marking as paid/i });
    expect(pendingButton).toBeDisabled();

    await user.click(pendingButton);
    releaseReload();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /mark as paid/i })).toBeEnabled(),
    );
    expect(paid.calls).toHaveLength(1);
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
