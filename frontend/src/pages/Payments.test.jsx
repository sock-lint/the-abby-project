import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Payments from './Payments.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildParent, buildUser } from '../test/factories.js';

function renderPage(user = buildUser(), handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Payments />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Payments', () => {
  it('shows the retry block when balance fetch fails', async () => {
    renderPage(buildUser(), [
      http.get('*/api/balance/', () => HttpResponse.json({ error: 'x' }, { status: 500 })),
    ]);
    await waitFor(() => expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument());
  });

  it('renders balance and breakdown tiles', async () => {
    renderPage(buildUser(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({
          balance: 42.5,
          breakdown: { hourly: 30, project_bonus: 12.5, adjustment: 0 },
          recent_transactions: [
            { id: 1, entry_type: 'hourly', amount: '30.00', description: 'week 1' },
            { id: 2, entry_type: 'payout', amount: '-5.00', description: 'paid out' },
          ],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('$42.50')).toBeInTheDocument());
    expect(screen.getAllByText(/hourly/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/paid out/i)).toBeInTheDocument();
  });

  it('shows empty rune badge when nothing is inked', async () => {
    renderPage(buildUser(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: null, recent_transactions: [] }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/nothing inked yet/i)).toBeInTheDocument());
  });

  it('parent opens the adjust balance modal and submits', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
      http.post('*/api/payments/adjust/', () => HttpResponse.json({})),
    ]);
    await waitFor(() => expect(screen.getByText(/adjust balance/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /adjust balance/i }));
    const fields = screen.getAllByRole('spinbutton');
    await user.type(fields[0], '3');
    await user.type(fields[1], '10');
    await user.click(screen.getByRole('button', { name: /^adjust$/i }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /^adjust$/i })).toBeNull());
  });

  it('adjust modal surfaces server error', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
      http.post('*/api/payments/adjust/', () =>
        HttpResponse.json({ error: 'bad amount' }, { status: 400 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/adjust balance/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /adjust balance/i }));
    const fields = screen.getAllByRole('spinbutton');
    await user.type(fields[0], '3');
    await user.type(fields[1], '1');
    await user.click(screen.getByRole('button', { name: /^adjust$/i }));
    expect(await screen.findByText(/bad amount/i)).toBeInTheDocument();
  });

  it('adjust modal cancel closes without saving', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/adjust balance/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /adjust balance/i }));
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole('spinbutton')).toBeNull());
  });
});
