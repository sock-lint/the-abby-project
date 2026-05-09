import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
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

  it('adjust modal lists children by name and submits the chosen id', async () => {
    const user = userEvent.setup();
    const adjustSpy = [];
    renderPage(buildParent(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
      http.get('*/api/children/', () =>
        HttpResponse.json([
          { id: 7, username: 'abby', display_name: 'Abby', role: 'child' },
          { id: 8, username: 'beck', display_name: 'Beck', role: 'child' },
        ]),
      ),
      http.post('*/api/payments/adjust/', async ({ request }) => {
        adjustSpy.push(await request.clone().json());
        return HttpResponse.json({});
      }),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /adjust balance/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /adjust balance/i }));

    // Scope to the modal — the page also has a filter <select> rendering
    // "Abby" as an option, so global getByRole('option', ...) ambiguously
    // matches both controls. The dialog is the relevant context here.
    const dialog = await screen.findByRole('dialog');
    const kidPicker = within(dialog).getByLabelText(/^kid$/i);
    await waitFor(() =>
      expect(within(dialog).getByRole('option', { name: 'Abby' })).toBeInTheDocument(),
    );
    expect(within(dialog).getByRole('option', { name: 'Beck' })).toBeInTheDocument();
    await user.selectOptions(kidPicker, '8');

    const amount = within(dialog).getByRole('spinbutton');
    await user.type(amount, '10');
    await user.click(within(dialog).getByRole('button', { name: /^adjust$/i }));

    await waitFor(() => expect(adjustSpy).toHaveLength(1));
    expect(adjustSpy[0]).toEqual({ user_id: 8, amount: 10, description: '' });
  });

  it('adjust modal surfaces server error', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
      http.get('*/api/children/', () =>
        HttpResponse.json([{ id: 7, username: 'abby', display_name: 'Abby', role: 'child' }]),
      ),
      http.post('*/api/payments/adjust/', () =>
        HttpResponse.json({ error: 'bad amount' }, { status: 400 }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /adjust balance/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /adjust balance/i }));
    const dialog = await screen.findByRole('dialog');
    await waitFor(() =>
      expect(within(dialog).getByRole('option', { name: 'Abby' })).toBeInTheDocument(),
    );
    await user.selectOptions(within(dialog).getByLabelText(/^kid$/i), '7');
    await user.type(within(dialog).getByRole('spinbutton'), '1');
    await user.click(within(dialog).getByRole('button', { name: /^adjust$/i }));
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

  it('child does not see Export CSV (parent-only affordance)', async () => {
    renderPage(buildUser(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /coffers/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: /export csv/i })).toBeNull();
  });

  it('parent clicking Export CSV calls /payments/export/ and triggers a CSV download', async () => {
    const user = userEvent.setup();
    const exportCalls = [];
    renderPage(buildParent(), [
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/payments/export/', ({ request }) => {
        exportCalls.push(request.url);
        return new HttpResponse('id,amount\n', {
          status: 200,
          headers: { 'Content-Type': 'text/csv' },
        });
      }),
    ]);

    // Stub the URL/blob plumbing so the test doesn't need a real iframe.
    const createSpy = vi.fn(() => 'blob:fake-csv');
    const revokeSpy = vi.fn();
    window.URL.createObjectURL = createSpy;
    window.URL.revokeObjectURL = revokeSpy;

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /export csv/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /export csv/i }));

    await waitFor(() => expect(exportCalls).toHaveLength(1));
    expect(exportCalls[0]).toMatch(/\/api\/payments\/export\//);
    // The Blob object URL was created and the temporary anchor was clicked,
    // so revokeObjectURL fires after the synchronous download is dispatched.
    expect(createSpy).toHaveBeenCalled();
    expect(revokeSpy).toHaveBeenCalled();
  });
});
