import { describe, expect, it } from 'vitest';
import { HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, within } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import ApprovalSheet from './ApprovalSheet';

const REQUEST = {
  id: 7,
  user: 1,
  user_name: 'Abby',
  username: 'abby',
  title: 'Articulated Dragon',
  color: 'green',
  reason: 'Present for Nana.',
  status: 'pending',
  estimated_grams: null,
  estimated_minutes: null,
};

const OVER_BUDGET = HttpResponse.json({
  error: 'That would go over this month’s print budget: Filament: 120g over',
  problems: ['Filament: 120g over the 500g monthly cap'],
  budget: {
    period_month: '2026-08-01',
    grams_per_month: '500.00', grams_used: '480.00',
    minutes_per_month: null, minutes_used: 300,
  },
}, { status: 409 });

describe('ApprovalSheet', () => {
  it('requires a positive whole-minute estimate and sends a rounded-up coin quote', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/7\/approve\/$/, {
      id: 7, title: REQUEST.title, status: 'quoted', coin_cost: 5,
      estimated_minutes: 61, minutes_per_coin_snapshot: 15,
      plate_filename: 'req-0007-articulated-dragon.3mf',
    });
    server.use(spy.handler);
    const { user } = renderWithProviders(
      <ApprovalSheet request={REQUEST} budget={{ minutes_per_coin: 15 }} onClose={() => {}} />,
    );
    const send = screen.getByRole('button', { name: 'Send coin quote' });
    expect(send).toBeDisabled();
    const estimate = screen.getByLabelText(/print time estimate/i);
    await user.type(estimate, '0');
    expect(send).toBeDisabled();
    await user.clear(estimate);
    await user.type(estimate, '1.5');
    expect(send).toBeDisabled();
    await user.clear(estimate);
    await user.type(estimate, '60');
    expect(screen.getByText('Coin quote: 4 coins')).toBeInTheDocument();
    await user.clear(estimate);
    await user.type(estimate, '61');
    expect(screen.getByText('Coin quote: 5 coins')).toBeInTheDocument();
    await user.click(send);
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body).toEqual({
      estimated_grams: null, estimated_minutes: 61, notes: '', force: false,
    });
    expect(await screen.findByRole('dialog', { name: 'Coin quote sent' })).toBeInTheDocument();
    expect(screen.getByText(/must exchange 5 coins before this print can start/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /copy plate filename/i })).not.toBeInTheDocument();
  });

  it('keeps sending a priced quote behind an explicit monthly-cap override', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/7\/approve\/$/, ({ body }) => body.force
      ? { id: 7, title: REQUEST.title, status: 'quoted', coin_cost: 4 }
      : OVER_BUDGET);
    server.use(spy.handler);
    const { user } = renderWithProviders(<ApprovalSheet request={REQUEST} budget={{ minutes_per_coin: 15 }} />);
    await user.type(screen.getByLabelText(/print time estimate/i), '60');
    await user.click(screen.getByRole('button', { name: 'Send coin quote' }));
    await user.click(await screen.findByRole('button', { name: 'Send quote anyway' }));
    await waitFor(() => expect(spy.calls).toHaveLength(2));
    expect(spy.calls[1].body).toEqual({
      estimated_grams: null, estimated_minutes: 60, notes: '', force: true,
    });
    expect(await screen.findByRole('dialog', { name: 'Coin quote sent' })).toBeInTheDocument();
  });

  it('waits for pricing settings and blocks approval when they cannot be read', () => {
    const { unmount } = renderWithProviders(<ApprovalSheet request={REQUEST} pricingLoading />);
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByText('Loading coin exchange settings…')).toBeInTheDocument();
    unmount();
    renderWithProviders(<ApprovalSheet request={REQUEST} pricingError="Service unavailable" />);
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load coin exchange settings. Service unavailable');
  });

  it('POSTs the slicer estimates on approve', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/7\/approve\/$/, {
      id: 7, status: 'approved', title: 'Articulated Dragon',
      plate_filename: 'req-0007-articulated-dragon.3mf',
    });
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <ApprovalSheet request={REQUEST} onClose={() => {}} />,
    );

    await user.type(screen.getByLabelText(/filament estimate/i), '120');
    await user.type(screen.getByLabelText(/print time estimate/i), '240');
    await user.type(screen.getByLabelText(/note/i), 'go ahead');
    await user.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-requests\/7\/approve\/$/);
    expect(spy.calls[0].body).toEqual({
      estimated_grams: 120,
      estimated_minutes: 240,
      notes: 'go ahead',
      force: false,
    });
  });

  it('shows the minted plate filename after a successful approve', async () => {
    server.use(
      spyHandler('post', /\/api\/print-requests\/7\/approve\/$/, {
        id: 7, status: 'approved', title: 'Articulated Dragon',
        plate_filename: 'req-0007-articulated-dragon.3mf',
      }).handler,
    );

    const { user } = renderWithProviders(
      <ApprovalSheet request={REQUEST} onClose={() => {}} />,
    );
    await user.click(screen.getByRole('button', { name: 'Approve' }));

    expect(
      await screen.findByText('req-0007-articulated-dragon.3mf'),
    ).toBeInTheDocument();
  });

  it('surfaces the 409 problems and re-POSTs with force on "Approve anyway"', async () => {
    const spy = spyHandler(
      'post',
      /\/api\/print-requests\/7\/approve\/$/,
      ({ body }) => (body?.force
        ? HttpResponse.json({
            id: 7, status: 'approved', title: 'Articulated Dragon',
            plate_filename: 'req-0007-articulated-dragon.3mf',
          })
        : OVER_BUDGET),
    );
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <ApprovalSheet request={REQUEST} onClose={() => {}} />,
    );

    await user.type(screen.getByLabelText(/filament estimate/i), '620');
    await user.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].body.force).toBe(false);
    expect(
      await screen.findByText('Filament: 120g over the 500g monthly cap'),
    ).toBeInTheDocument();
    expect(screen.getByText(/480 g of 500 g/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /approve anyway/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(2));
    expect(spy.calls[1].body).toEqual({
      estimated_grams: 620,
      estimated_minutes: null,
      notes: '',
      force: true,
    });
    expect(
      await screen.findByText('req-0007-articulated-dragon.3mf'),
    ).toBeInTheDocument();
  });

  it('POSTs the note to the reject endpoint after the confirm step', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/7\/reject\/$/, {
      id: 7, status: 'rejected',
    });
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <ApprovalSheet request={REQUEST} onClose={() => {}} />,
    );

    await user.type(screen.getByLabelText(/note/i), 'not this month');
    await user.click(screen.getByRole('button', { name: 'Reject' }));

    // Rejecting is final, so the first tap only opens the confirm — nothing
    // has been POSTed yet.
    expect(spy.calls).toHaveLength(0);
    const confirm = await screen.findByRole('dialog', { name: /Reject “Articulated Dragon”\?/ });
    // The note typed on the decide sheet carries into the confirm.
    expect(screen.getByLabelText(/note for them/i)).toHaveValue('not this month');

    await user.click(within(confirm).getByRole('button', { name: 'Reject' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-requests\/7\/reject\/$/);
    expect(spy.calls[0].body).toEqual({ notes: 'not this month' });
  });

  it('backs out of the confirm without rejecting', async () => {
    const spy = spyHandler('post', /\/api\/print-requests\/7\/reject\/$/, {
      id: 7, status: 'rejected',
    });
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <ApprovalSheet request={REQUEST} onClose={() => {}} />,
    );

    await user.click(screen.getByRole('button', { name: 'Reject' }));
    await user.click(await screen.findByRole('button', { name: /keep it pending/i }));

    expect(spy.calls).toHaveLength(0);
    // Back on the decide sheet, both decisions still available.
    expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });
});
