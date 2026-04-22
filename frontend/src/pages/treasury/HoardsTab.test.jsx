import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '../../test/render';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import HoardsTab from './HoardsTab';

function makeGoal(over = {}) {
  return {
    id: 1,
    title: 'Lego Set',
    target_amount: '50.00',
    current_amount: '20.00',
    percent_complete: 40,
    icon: '🧱',
    is_completed: false,
    completed_at: null,
    created_at: '2026-04-15T00:00:00Z',
    ...over,
  };
}

describe('HoardsTab', () => {
  it('renders active goals with progress and empty state otherwise', async () => {
    server.use(
      http.get('*/api/savings-goals/', () =>
        HttpResponse.json([makeGoal()]),
      ),
    );
    renderWithProviders(<HoardsTab />);
    await waitFor(() => expect(screen.getByText('Lego Set')).toBeInTheDocument());
    expect(screen.getByText('$20.00')).toBeInTheDocument();
    expect(screen.getByText('$50.00')).toBeInTheDocument();
    expect(screen.getByText(/\+100 coins/)).toBeInTheDocument(); // 50 * 2
  });

  it('shows completed history in a collapsible section', async () => {
    server.use(
      http.get('*/api/savings-goals/', () =>
        HttpResponse.json([
          makeGoal({
            id: 2,
            title: 'Headphones',
            is_completed: true,
            completed_at: '2026-04-10T00:00:00Z',
          }),
        ]),
      ),
    );
    renderWithProviders(<HoardsTab />);
    await waitFor(() =>
      expect(screen.getByText('Completed hoards')).toBeInTheDocument(),
    );
    expect(screen.getByText('Headphones')).toBeInTheDocument();
  });

  it('creates a new goal and re-fetches on submit', async () => {
    server.use(
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
    );
    const create = spyHandler('post', /\/api\/savings-goals\/$/, { ok: true });
    server.use(create.handler);

    const { user } = renderWithProviders(<HoardsTab />);

    await waitFor(() =>
      expect(screen.getByText(/No active hoards/)).toBeInTheDocument(),
    );

    await user.click(
      screen.getByRole('button', { name: /start a new hoard/i }),
    );

    const titleField = await screen.findByLabelText(/What are you saving for/i);
    await user.type(titleField, 'Bike');
    await user.type(screen.getByLabelText(/Target amount/i), '75');
    await user.type(screen.getByLabelText(/Icon/i), '🚲');

    await user.click(screen.getByRole('button', { name: /Start saving/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].url).toMatch(/\/api\/savings-goals\/$/);
    expect(create.calls[0].body).toEqual({
      title: 'Bike',
      target_amount: 75,
      icon: '🚲',
    });
  });

  it('deletes a goal after confirm', async () => {
    server.use(
      http.get('*/api/savings-goals/', () =>
        HttpResponse.json([makeGoal({ id: 42 })]),
      ),
    );
    const del = spyHandler('delete', /\/api\/savings-goals\/42\/$/, { ok: true });
    server.use(del.handler);

    const { user } = renderWithProviders(<HoardsTab />);

    await user.click(
      await screen.findByRole('button', { name: /Remove Lego Set/i }),
    );

    // ConfirmDialog uses role="alertdialog"
    await screen.findByRole('alertdialog');
    await user.click(
      await screen.findByRole('button', { name: /^Remove$/ }),
    );

    await waitFor(() => expect(del.calls).toHaveLength(1));
    expect(del.calls[0].url).toMatch(/\/api\/savings-goals\/42\/$/);
  });
});
