import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import QuickActionsSheet from './QuickActionsSheet';
import { AuthProvider } from '../../hooks/useApi';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildUser, buildParent } from '../../test/factories';

// Bypass exit animation on the BottomSheet so unmount assertions don't hang.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderSheet(userFixture, handlers = [], props = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(userFixture)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <QuickActionsSheet
          status={null}
          isClocked={false}
          elapsedSecs={0}
          onClose={props.onClose || (() => {})}
          onClockReload={props.onClockReload || (async () => {})}
        />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('QuickActionsSheet', () => {
  it('shows child actions including Clock in and Add homework', async () => {
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ today: [], overdue: [], pending_submissions: [] })),
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/clock in/i)).toBeInTheDocument());
    expect(screen.getByText(/add homework/i)).toBeInTheDocument();
    // With zero goals the hoard affordance labels as "Set a savings goal".
    await waitFor(() =>
      expect(screen.getByText(/set a savings goal/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/view hoards/i)).not.toBeInTheDocument();
    // Guarded actions are NOT shown because preconditions aren't met.
    expect(screen.queryByText(/submit homework/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/start a quest/i)).not.toBeInTheDocument();
    // Reward shop is intentionally excluded from quick actions.
    expect(screen.queryByText(/request a reward/i)).not.toBeInTheDocument();
  });

  it('swaps hoard label to "View hoards" when the child has an active goal', async () => {
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ today: [], overdue: [], pending_submissions: [] })),
      http.get('*/api/savings-goals/', () =>
        HttpResponse.json([
          { id: 1, title: 'Bike', target_amount: '100.00', is_completed: false },
        ]),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/view hoards/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/set a savings goal/i)).not.toBeInTheDocument();
  });

  it('reveals Submit homework when an assignment is due', async () => {
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [{ id: 7, title: 'Math packet' }],
          overdue: [],
          pending_submissions: [],
        }),
      ),
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/submit homework/i)).toBeInTheDocument());
  });

  it('reveals Start a quest when a quest scroll is in inventory', async () => {
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ today: [], overdue: [], pending_submissions: [] })),
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
      http.get('*/api/inventory/', () =>
        HttpResponse.json([
          { id: 1, quantity: 2, item: { id: 9, item_type: 'quest_scroll', name: 'Boss Scroll' } },
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/start a quest/i)).toBeInTheDocument());
  });

  it('shows parent actions (Create homework, Adjust coins, Adjust payment)', async () => {
    renderSheet(buildParent());
    await waitFor(() => expect(screen.getByText(/create homework for a kid/i)).toBeInTheDocument());
    expect(screen.getByText(/adjust coins/i)).toBeInTheDocument();
    expect(screen.getByText(/adjust payment/i)).toBeInTheDocument();
    // No child-only actions surface for parents.
    expect(screen.queryByText(/add homework$/i)).not.toBeInTheDocument();
    // "Write in journal" is a child self-authoring affordance only.
    expect(screen.queryByText(/write in journal/i)).not.toBeInTheDocument();
  });

  it('shows "Write in journal" on the child menu', async () => {
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ today: [], overdue: [], pending_submissions: [] })),
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/write in journal/i)).toBeInTheDocument(),
    );
  });

  it('opens the JournalEntryFormModal in create mode when no entry exists yet', async () => {
    const u = userEvent.setup();
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ today: [], overdue: [], pending_submissions: [] })),
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    const row = await screen.findByRole('button', { name: /write in journal/i });
    await u.click(row);
    await waitFor(() =>
      expect(
        screen.getByRole('dialog', { name: /write in your journal/i }),
      ).toBeInTheDocument(),
    );
  });

  it('flips label to "Edit today\u2019s journal" and opens the modal in edit mode when today\u2019s entry exists', async () => {
    const u = userEvent.setup();
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ today: [], overdue: [], pending_submissions: [] })),
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      http.get('*/api/chronicle/journal/today/', () =>
        HttpResponse.json({
          id: 42, kind: 'journal', is_private: true,
          title: 'Earlier', summary: 'I already started',
          occurred_on: '2026-04-22',
        }),
      ),
    ]);
    const row = await screen.findByRole('button', { name: /edit today.s journal/i });
    expect(row).toBeInTheDocument();
    await u.click(row);
    await waitFor(() =>
      expect(
        screen.getByRole('dialog', { name: /edit your journal entry/i }),
      ).toBeInTheDocument(),
    );
  });

  it('Add homework submits to POST /homework/ with a self-assign payload', async () => {
    const u = userEvent.setup();
    const create = spyHandler('post', /\/api\/homework\/$/, { ok: true, id: 42 });
    renderSheet(buildUser(), [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ today: [], overdue: [], pending_submissions: [] })),
      http.get('*/api/savings-goals/', () => HttpResponse.json([])),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      create.handler,
    ]);
    // Open the Add homework pane.
    const addRow = await screen.findByRole('button', { name: /add homework/i });
    await u.click(addRow);

    const form = screen.getByRole('textbox');
    await u.type(form, 'Science poster');

    // The submit button lives inside the form.
    const submit = screen.getByRole('button', { name: /^add homework$/i });
    await u.click(submit);

    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ title: 'Science poster' });
    // due_date is null when left blank.
    expect(create.calls[0].body.due_date).toBeNull();
  });
});
