import { selectDropdown, openDropdown } from '../test/selectDropdown';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, screen, waitFor, within } from '@testing-library/react';
import Payments from './Payments';
import Timecards from './Timecards';
import * as api from '../api';
import { useAuth } from '../hooks/useApi';
import { STORAGE_KEYS } from '../constants/storage';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import { buildParent, buildUser } from '../test/factories';
import { spyHandler } from '../test/spy';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

afterEach(() => { vi.restoreAllMocks(); });

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

const payment = (id, description) => ({
  id, description, entry_type: 'payout', amount: '-2.00', user: 1,
  created_at: '2026-10-12T12:00:00Z',
});
const timecard = (id, status = 'pending') => ({
  id, status, week_start: id === 1 ? '2026-10-12' : '2026-10-05',
  total_hours: id, total_earnings: id * 10, username: 'Abby',
});
const page = (results, next = null, count = 2) => ({ results, count, next, previous: null });

function setup() {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ family: { id: 1 } }))),
    http.get('*/api/children/', () => HttpResponse.json([
      buildUser({ id: 1, display_name: 'Abby' }),
      buildUser({ id: 2, display_name: 'Beck' }),
    ])),
    http.get('*/api/balance/', () => HttpResponse.json({ balance: 12, breakdown: {}, recent_transactions: [] })),
  );
}

function SwitchAccountButton() {
  const { setUser } = useAuth();
  return <button onClick={() => {
    localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'replacement-finance-session');
    setUser(buildParent({ id: 100, family: { id: 2 } }));
  }}>Switch account</button>;
}

describe('Financial history recovery', () => {
  it.each(['account', 'selected child'])('discards an unresolved older payment page after the %s changes', async (change) => {
    setup();
    const read = vi.spyOn(api, 'getPaymentLedger');
    const olderGate = deferred();
    let olderStarted = false;
    server.use(http.get('*/api/payments/', async ({ request }) => {
      const query = new URL(request.url).searchParams;
      if (request.headers.get('Authorization') === 'Token replacement-finance-session' || query.get('user_id') === '2') {
        return HttpResponse.json(page([payment(20, 'Current account or child payment')], null, 1));
      }
      if (query.get('page') === '2') {
        olderStarted = true;
        await olderGate.promise;
        return HttpResponse.json(page([payment(2, 'Previous account or child older payment')]));
      }
      return HttpResponse.json(page([payment(1, 'Previous account or child latest payment')], '/api/payments/?page=2'));
    }));
    const { user } = renderWithProviders(<><SwitchAccountButton /><Payments /></>, {
      route: change === 'selected child' ? '/payments?kid=1' : '/payments',
    });

    await screen.findByText('Showing 1 of 2 payment entries');
    await user.click(screen.getByRole('button', { name: 'Load more payments' }));
    await waitFor(() => expect(olderStarted).toBe(true));
    const oldRead = read.mock.results[read.mock.calls.findIndex(([filters]) => filters.page === 2)].value;
    try {
      if (change === 'account') {
        await user.click(screen.getByRole('button', { name: 'Switch account' }));
      } else {
        const childFilter = screen.getByRole('combobox', { name: 'Filter by kid' });
        await (await openDropdown(user, childFilter)).findByRole('option', { name: 'Beck' });
        await selectDropdown(user, childFilter, '2');
      }
      expect(await screen.findByText('Current account or child payment')).toBeVisible();
      expect(screen.queryByText('Previous account or child latest payment')).not.toBeInTheDocument();
    } finally {
      await act(async () => { olderGate.resolve(); await oldRead; });
    }

    expect(screen.queryByText('Previous account or child older payment')).not.toBeInTheDocument();
    expect(screen.getByText('Current account or child payment')).toBeVisible();
    expect(screen.getByText('Showing 1 of 1 payment entries')).toBeInTheDocument();
  });

  it('sends exactly one older-page request when Load more is double-clicked before it resolves', async () => {
    setup();
    const read = vi.spyOn(api, 'getPaymentLedger');
    const olderGate = deferred();
    let olderCalls = 0;
    server.use(http.get('*/api/payments/', async ({ request }) => {
      if (new URL(request.url).searchParams.get('page') === '2') {
        olderCalls += 1;
        await olderGate.promise;
        return HttpResponse.json(page([payment(2, 'Older payment')]));
      }
      return HttpResponse.json(page([payment(1, 'Latest payment')], '/api/payments/?page=2'));
    }));
    const { user } = renderWithProviders(<Payments />);
    await screen.findByText('Showing 1 of 2 payment entries');
    const more = screen.getByRole('button', { name: 'Load more payments' });
    await user.dblClick(more);
    await waitFor(() => expect(olderCalls).toBe(1));
    const pendingRead = read.mock.results[read.mock.calls.findIndex(([filters]) => filters.page === 2)].value;
    try {
      expect(more).toBeDisabled();
      await user.click(more);
      expect(olderCalls).toBe(1);
      expect(screen.getByText('Latest payment')).toBeVisible();
    } finally {
      await act(async () => { olderGate.resolve(); await pendingRead; });
    }
    expect(await screen.findByText('Older payment')).toBeVisible();
    expect(screen.getByText('Showing 2 of 2 payment entries')).toBeInTheDocument();
    expect(olderCalls).toBe(1);
  });

  it('retries a failed older-week refresh after approval without repeating the mutation or losing loaded depth', async () => {
    setup();
    let approved = false;
    let olderReads = 0;
    const pagesRead = [];
    const approval = spyHandler('post', '*/api/timecards/2/approve/', () => {
      approved = true;
      return HttpResponse.json(timecard(2, 'approved'));
    });
    server.use(
      approval.handler,
      http.get('*/api/timecards/', ({ request }) => {
        const requestedPage = Number(new URL(request.url).searchParams.get('page') || 1);
        pagesRead.push(requestedPage);
        if (requestedPage === 2) {
          olderReads += 1;
          if (olderReads === 2) return HttpResponse.json({ detail: 'Older weeks are temporarily unavailable.' }, { status: 503 });
          return HttpResponse.json(page([timecard(2, approved ? 'approved' : 'pending')]));
        }
        return HttpResponse.json(page([timecard(1)], '/api/timecards/?page=2'));
      }),
      http.get('*/api/timecards/2/', () => HttpResponse.json({
        ...timecard(2), hourly_earnings: 20, bonus_earnings: 0, entries: [],
      })),
    );
    const { user } = renderWithProviders(<Timecards />);
    await screen.findByText('Showing 1 of 2 timecards');
    await user.click(screen.getByRole('button', { name: 'Load more timecards' }));
    await user.click(await screen.findByRole('button', { name: /2h.*pending/i }));
    await user.click(await screen.findByRole('button', { name: /^approve$/i }));

    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('Older weeks are temporarily unavailable.');
    expect(approval.calls).toHaveLength(1);
    expect(approval.calls[0].body).toEqual({ notes: '' });
    await user.click(within(error).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: /2h.*approved/i })).toBeVisible();
    expect(screen.getByText('Showing 2 of 2 timecards')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load more timecards' })).not.toBeInTheDocument();
    expect(pagesRead).toEqual([1, 2, 1, 2, 1, 2]);
    expect(approval.calls).toHaveLength(1);
  });
});
