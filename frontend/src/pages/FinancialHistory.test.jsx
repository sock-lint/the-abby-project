import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, screen, waitFor } from '@testing-library/react';
import Payments from './Payments';
import Timecards from './Timecards';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import { buildParent } from '../test/factories';
import { spyHandler } from '../test/spy';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const entry = (id, description) => ({ id, description, entry_type: 'payout', amount: '-2.00', user: 1, created_at: '2026-10-12T12:00:00Z' });
const card = (id, status = 'pending') => ({ id, status, week_start: id === 1 ? '2026-10-12' : '2026-10-05', total_hours: id, total_earnings: id * 10, username: 'Abby' });
const page = (results, next = null, count = 3) => ({ results, count, next, previous: null });

function setup() {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/children/', () => HttpResponse.json([])),
    http.get('*/api/balance/', () => HttpResponse.json({ balance: 12, breakdown: {}, recent_transactions: [entry(90, 'Summary preview only')] })),
  );
}

describe('Financial history pagination', () => {
  it('opens the complete payments ledger and appends older records without duplicates', async () => {
    setup();
    const calls = [];
    server.use(http.get('*/api/payments/', ({ request }) => {
      const url = new URL(request.url);
      calls.push(url);
      return HttpResponse.json(url.searchParams.get('page') === '2'
        ? page([entry(2, 'Middle payment'), entry(3, 'Old payment')])
        : page([entry(1, 'Latest payment'), entry(2, 'Middle payment')], 'https://untrusted.invalid/api/payments/?page=2&user_id=999'));
    }));
    const { user } = renderWithProviders(<Payments />);
    expect(await screen.findByText('Showing 2 of 3 payment entries')).toBeInTheDocument();
    expect(screen.queryByText('Summary preview only')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load more payments' }));
    expect(await screen.findByText('Old payment')).toBeInTheDocument();
    expect(screen.getByText('Showing 3 of 3 payment entries')).toBeInTheDocument();
    expect(screen.getAllByText('Middle payment')).toHaveLength(1);
    expect(calls).toHaveLength(2);
    expect(calls[1].pathname).toBe('/api/payments/');
    expect(calls[1].searchParams.get('page')).toBe('2');
    expect(calls[1].searchParams.has('user_id')).toBe(false);
    expect(screen.queryByRole('button', { name: 'Load more payments' })).not.toBeInTheDocument();
  });

  it('keeps payment filters and visible records when an older page fails, then retries that page', async () => {
    setup();
    let olderAttempts = 0;
    const queries = [];
    server.use(http.get('*/api/payments/', ({ request }) => {
      const query = new URL(request.url).searchParams;
      queries.push(query);
      if (query.get('page') === '2') {
        olderAttempts += 1;
        return olderAttempts === 1 ? HttpResponse.json({ error: 'History unavailable' }, { status: 503 }) : HttpResponse.json(page([entry(2, 'Older filtered payment')], null, 2));
      }
      return HttpResponse.json(page([entry(1, 'Filtered payment')], '/api/payments/?page=2', 2));
    }));
    const { user } = renderWithProviders(<Payments />, { route: '/payments?types=payout' });
    expect(await screen.findByText('Showing 1 of 2 payment entries')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load more payments' }));
    expect(await screen.findByText('History unavailable')).toBeInTheDocument();
    expect(screen.getByText('Filtered payment')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try loading more payments again' }));
    expect(await screen.findByText('Older filtered payment')).toBeInTheDocument();
    expect(olderAttempts).toBe(2);
    expect(queries.every((query) => query.get('entry_type') === 'payout')).toBe(true);
  });

  it('discards an older-page response after the payment filters change', async () => {
    setup();
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    let olderStarted = false;
    server.use(http.get('*/api/payments/', async ({ request }) => {
      const query = new URL(request.url).searchParams;
      if (query.get('entry_type') === 'payout') return HttpResponse.json(page([entry(5, 'New filter result')], null, 1));
      if (query.get('page') === '2') {
        olderStarted = true;
        await gate;
        return HttpResponse.json(page([entry(2, 'Stale old record')], null, 2));
      }
      return HttpResponse.json(page([entry(1, 'Unfiltered result')], '/api/payments/?page=2', 2));
    }));
    const { user } = renderWithProviders(<Payments />);
    await screen.findByText('Showing 1 of 2 payment entries');
    await user.click(screen.getByRole('button', { name: 'Load more payments' }));
    await waitFor(() => expect(olderStarted).toBe(true));
    await user.click(screen.getByRole('button', { name: /^payout$/i }));
    expect(await screen.findByText('New filter result')).toBeInTheDocument();
    await act(async () => { release(); await gate; });
    expect(screen.queryByText('Stale old record')).not.toBeInTheDocument();
    expect(screen.queryByText('Unfiltered result')).not.toBeInTheDocument();
    expect(screen.getByText('Showing 1 of 1 payment entries')).toBeInTheDocument();
  });

  it('keeps an older timecard visible and updated after a parent approves it', async () => {
    setup();
    let approved = false;
    const approval = spyHandler('post', '*/api/timecards/2/approve/', () => {
      approved = true;
      return HttpResponse.json(card(2, 'approved'));
    });
    server.use(approval.handler,
      http.get('*/api/timecards/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.get('page') === '2'
        ? page([card(2, approved ? 'approved' : 'pending')], null, 2)
        : page([card(1)], '/api/timecards/?page=2', 2))),
      http.get('*/api/timecards/2/', () => HttpResponse.json({ ...card(2), hourly_earnings: 20, bonus_earnings: 0, entries: [] })),
    );
    const { user } = renderWithProviders(<Timecards />);
    await screen.findByText('Showing 1 of 2 timecards');
    await user.click(screen.getByRole('button', { name: 'Load more timecards' }));
    await user.click(await screen.findByRole('button', { name: /2h/ }));
    await user.click(await screen.findByRole('button', { name: /^approve$/i }));
    await waitFor(() => expect(approval.calls).toHaveLength(1));
    expect(approval.calls[0].body).toEqual({ notes: '' });
    expect(approval.calls[0].url).toMatch(/\/api\/timecards\/2\/approve\/$/);
    expect(await screen.findByRole('button', { name: /2h.*approved/i })).toBeInTheDocument();
    expect(screen.getByText('Showing 2 of 2 timecards')).toBeInTheDocument();
  });
});
