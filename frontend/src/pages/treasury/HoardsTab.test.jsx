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
  it('renders the incipit hero with aggregate progress and stanza cards', async () => {
    server.use(
      http.get('*/api/savings-goals/', () =>
        HttpResponse.json([makeGoal()]),
      ),
    );
    const { container } = renderWithProviders(<HoardsTab />);
    await waitFor(() => expect(screen.getByText('Lego Set')).toBeInTheDocument());

    // Hero IncipitBand renders the "Hoards" title and a meta line summarising
    // active vs completed.
    expect(screen.getByRole('heading', { name: 'Hoards' })).toBeInTheDocument();
    expect(screen.getByText(/1 active · 40% across the lot/)).toBeInTheDocument();

    // Active stanza details — current/target amounts + coin bonus copy.
    expect(screen.getByText('$20.00')).toBeInTheDocument();
    expect(screen.getByText(/\$50\.00/)).toBeInTheDocument();
    expect(screen.getByText(/\+100 coins/)).toBeInTheDocument(); // 50 * 2

    // Two Atlas drop-caps: one in the IncipitBand hero, one in the stanza.
    const versals = container.querySelectorAll('[data-versal="true"]');
    expect(versals.length).toBe(2);
    // The stanza's versal carries the rising/cresting tier for 40% progress.
    const stanzaVersal = versals[1];
    expect(stanzaVersal.getAttribute('data-tier')).toBe('rising');
    expect(stanzaVersal.getAttribute('data-progress')).toBe('40');

    // §I rubric for the active section.
    expect(screen.getByRole('heading', { name: 'Active pursuits' })).toBeInTheDocument();
  });

  it('renders completed hoards as legendary wax seals under the Filled coffers rubric', async () => {
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
    const { container } = renderWithProviders(<HoardsTab />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Filled coffers' })).toBeInTheDocument(),
    );
    expect(screen.getByText('Headphones')).toBeInTheDocument();

    // Exactly one completed seal renders (no §I rubric since there are no
    // active goals).
    const seals = container.querySelectorAll('[data-hoard-seal="true"]');
    expect(seals.length).toBe(1);
    expect(screen.queryByRole('heading', { name: 'Active pursuits' })).not.toBeInTheDocument();

    // Meta line flips to the "all filled" phrasing.
    expect(screen.getByText(/all hoards filled · 1 sealed/)).toBeInTheDocument();
  });

  it('shows the script empty state when there are no hoards at all', async () => {
    server.use(
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
    );
    renderWithProviders(<HoardsTab />);
    await waitFor(() =>
      expect(screen.getByText(/no hoards yet/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/set a goal and begin to fill it/i),
    ).toBeInTheDocument();
  });

  it('creates a new goal and re-fetches on submit', async () => {
    server.use(
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
    );
    const create = spyHandler('post', /\/api\/savings-goals\/$/, { ok: true });
    server.use(create.handler);

    const { user } = renderWithProviders(<HoardsTab />);

    await waitFor(() =>
      expect(screen.getByText(/no hoards yet/i)).toBeInTheDocument(),
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
