import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import BudgetPanel from './BudgetPanel';

function buildBudget(over = {}) {
  return {
    id: 3,
    user: 1,
    user_name: 'Abby',
    username: 'abby',
    grams_per_month: '500.00',
    minutes_per_month: null,
    is_active: true,
    notes: '',
    period_month: '2026-08-01',
    grams_used: '120.00',
    minutes_used: 300,
    grams_remaining: '380.00',
    minutes_remaining: null,
    ...over,
  };
}

describe('BudgetPanel', () => {
  it('renders used vs cap, and "No cap" for an uncapped dimension', () => {
    renderWithProviders(<BudgetPanel budgets={[buildBudget()]} />);
    expect(screen.getByText('Abby')).toBeInTheDocument();
    expect(screen.getByText('120 g / 500 g')).toBeInTheDocument();
    expect(screen.getByText('5h 0m / No cap')).toBeInTheDocument();
    expect(
      screen.getByRole('progressbar', { name: /filament used this month/i }),
    ).toHaveAttribute('aria-valuenow', '24');
  });

  it('shows an overage in the ember tone rather than clamping to zero', () => {
    renderWithProviders(
      <BudgetPanel
        budgets={[buildBudget({ grams_used: '620.00', grams_remaining: '-120.00' })]}
      />,
    );
    const overage = screen.getByText('Over by 120 g');
    expect(overage).toBeInTheDocument();
    expect(overage.className).toMatch(/ember/);
  });

  it('renders an empty state when the family has no budgets yet', () => {
    renderWithProviders(<BudgetPanel budgets={[]} />);
    expect(screen.getByText(/No print budgets yet/i)).toBeInTheDocument();
  });

  it('PATCHes the caps, sending null for a blank dimension', async () => {
    const spy = spyHandler('patch', /\/api\/print-budgets\/3\/$/, { id: 3 });
    server.use(spy.handler);

    const { user } = renderWithProviders(<BudgetPanel budgets={[buildBudget()]} />);
    await user.click(screen.getByRole('button', { name: 'Caps' }));

    const grams = screen.getByLabelText(/grams per month/i);
    await user.clear(grams);
    await user.type(grams, '800');
    await user.click(screen.getByRole('button', { name: /save caps/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-budgets\/3\/$/);
    expect(spy.calls[0].body).toEqual({
      grams_per_month: 800,
      minutes_per_month: null,
      is_active: true,
    });
  });

  it('POSTs a manual adjustment to the ledger', async () => {
    const spy = spyHandler('post', /\/api\/print-budgets\/3\/adjust\/$/, { id: 3 });
    server.use(spy.handler);

    const { user } = renderWithProviders(<BudgetPanel budgets={[buildBudget()]} />);
    await user.click(screen.getByRole('button', { name: 'Adjust' }));

    await user.type(screen.getByLabelText('Grams'), '-25');
    await user.type(screen.getByLabelText('Note'), 'spool ran out');
    await user.click(screen.getByRole('button', { name: 'Record' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-budgets\/3\/adjust\/$/);
    expect(spy.calls[0].body).toEqual({ grams: -25, minutes: 0, note: 'spool ran out' });
  });

  it('loads the recent ledger on demand', async () => {
    server.use(
      http.get(/\/api\/print-budgets\/3\/ledger\/$/, () =>
        HttpResponse.json([
          {
            id: 1, user: 1, request: 42, request_title: 'Articulated Dragon',
            job: 7, period_month: '2026-08-01', grams: '120.00', minutes: 240,
            reason: 'print_completed', reason_display: 'Print completed',
            note: '', created_at: '2026-08-20T12:00:00Z',
          },
        ]),
      ),
    );

    const { user } = renderWithProviders(<BudgetPanel budgets={[buildBudget()]} />);
    await user.click(screen.getByRole('button', { name: 'Ledger' }));

    expect(await screen.findByText('Print completed')).toBeInTheDocument();
    expect(screen.getByText(/Articulated Dragon/)).toBeInTheDocument();
  });
});
