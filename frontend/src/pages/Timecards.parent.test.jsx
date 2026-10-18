import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Timecards from './Timecards';
import { AuthProvider } from '../hooks/useApi';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent } from '../test/factories';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderCard(status, extra = []) {
  const card = { id: 2, user: 7, username: 'Abby', week_start: '2026-10-05', total_hours: '8.00', total_earnings: '20.00', status };
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Abby' }])),
    http.get('*/api/timecards/', () => HttpResponse.json([card])),
    http.get('*/api/timecards/2/', () => HttpResponse.json({
      ...card, hourly_earnings: '20.00', bonus_earnings: '0.00',
      entries: [{ id: 9, project_title: 'Birdhouse', clock_in: '2026-10-06T15:00:00Z', duration_minutes: 480, notes: 'Finished sanding the roof.', auto_clocked_out: true }],
    })),
    http.get('*/api/payments/greenlight/overview/', () => HttpResponse.json({ user_id: 7, approved_payable: '20.00', approved_timecards: [card], payouts: [] })),
    ...extra,
  );
  return render(<MemoryRouter><AuthProvider><Timecards /></AuthProvider></MemoryRouter>);
}

describe('Parent timecard review', () => {
  it('shows work notes and automatic clock-out warnings before approval', async () => {
    const user = userEvent.setup();
    renderCard('pending');
    await user.click(await screen.findByRole('button', { name: /week of/i }));
    expect(await screen.findByText('Finished sanding the roof.')).toBeInTheDocument();
    expect(screen.getByText(/automatically clocked out/i)).toBeInTheDocument();
  });

  it('resolves a disputed card with an optional parent note', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', '*/api/timecards/2/approve/', { id: 2, status: 'approved' });
    renderCard('disputed', [approve.handler]);
    await user.click(await screen.findByRole('button', { name: /week of/i }));
    await user.type(await screen.findByLabelText('Parent note (optional)'), 'Reviewed the timer together.');
    await user.click(screen.getByRole('button', { name: 'Resolve and approve' }));
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].body).toEqual({ notes: 'Reviewed the timer together.' });
    expect(approve.calls[0].url).toMatch(/\/api\/timecards\/2\/approve\/$/);
  });

  it('records a completed Greenlight transfer with this child and week preselected', async () => {
    const user = userEvent.setup();
    const payout = spyHandler('post', '*/api/payments/greenlight/payout/', { created: true });
    const legacy = spyHandler('post', '*/api/timecards/2/mark-paid/', {});
    renderCard('approved', [payout.handler, legacy.handler]);
    await user.click(await screen.findByRole('button', { name: /week of/i }));
    await user.click(await screen.findByRole('button', { name: /mark as paid|record completed transfer/i }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Record a Greenlight transfer for Abby' }));
    expect(await dialog.findByLabelText('Transfer amount')).toHaveValue(20);
    expect(dialog.getByRole('button', { name: 'Record completed transfer' })).toBeDisabled();
    expect(payout.calls).toHaveLength(0);
    expect(legacy.calls).toHaveLength(0);
    await user.click(dialog.getByLabelText('I already completed this earned-money transfer in Greenlight'));
    await user.click(dialog.getByRole('button', { name: 'Record completed transfer' }));
    await waitFor(() => expect(payout.calls).toHaveLength(1));
    expect(payout.calls[0].body).toEqual({
      user_id: 7, timecard_id: 2, amount: '20.00', transferred_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      reference: '', memo: '', idempotency_key: expect.any(String),
    });
    expect(payout.calls[0].url).toMatch(/\/api\/payments\/greenlight\/payout\/$/);
    expect(legacy.calls).toHaveLength(0);
  });
});
