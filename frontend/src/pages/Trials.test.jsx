import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Trials from './Trials.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user = buildUser(), handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Trials />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Trials', () => {
  it('renders empty current state', async () => {
    renderPage(buildUser(), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getAllByText((t) => /quest|trial/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('switches to history tab', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () =>
        HttpResponse.json([{ id: 1, status: 'completed', completed_at: '2026-04-10', definition: { name: 'Old Quest', quest_type: 'boss' } }]),
      ),
    ]);
    const historyTab = await screen.findByRole('button', { name: /history/i });
    await user.click(historyTab);
    await waitFor(() => expect(screen.getByText(/old quest/i)).toBeInTheDocument());
  });

  it('hides the Issue Challenge button from child users', async () => {
    renderPage(buildUser({ role: 'child' }), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () => HttpResponse.json([])),
    ]);
    // Wait for quests page to settle (History tab is a stable signal).
    await screen.findByRole('button', { name: /history/i });
    expect(screen.queryByRole('button', { name: /issue challenge/i })).toBeNull();
  });

  it('exposes the Issue Challenge button to parents with children', async () => {
    renderPage(buildUser({ role: 'parent' }), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () => HttpResponse.json([])),
      http.get('*/api/quests/family/', () => HttpResponse.json({ results: [] })),
      http.get('*/api/children/', () =>
        HttpResponse.json([{ id: 1, username: 'kid', display_label: 'Kid' }]),
      ),
    ]);
    const button = await screen.findByRole('button', { name: /issue challenge/i });
    expect(button).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(button);
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: /assign to/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole('combobox', { name: /^type$/i })).toBeInTheDocument();
  });

  it('parent toggling Co-op swaps the single-child select for a multi-child picker', async () => {
    const user = userEvent.setup();
    renderPage(buildUser({ role: 'parent' }), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () => HttpResponse.json([])),
      http.get('*/api/quests/family/', () => HttpResponse.json({ results: [] })),
      http.get('*/api/children/', () =>
        HttpResponse.json([
          { id: 1, username: 'a', display_label: 'Abby' },
          { id: 2, username: 'b', display_label: 'Beck' },
        ]),
      ),
      http.get('*/api/skills/', () => HttpResponse.json([])),
    ]);
    await user.click(await screen.findByRole('button', { name: /issue challenge/i }));
    // Single-child Assign to is the default; toggling co-op swaps it out.
    expect(screen.getByRole('combobox', { name: /assign to/i })).toBeInTheDocument();
    const coopToggle = await screen.findByLabelText(/co-op campaign/i);
    await user.click(coopToggle);
    expect(screen.queryByRole('combobox', { name: /assign to/i })).toBeNull();
    expect(screen.getByText(/co-op participants/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/abby/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/beck/i)).toBeInTheDocument();
  });

  it('parent submitting a co-op challenge posts coop_user_ids + on_time trigger filter', async () => {
    const user = userEvent.setup();
    const createCalls = [];
    renderPage(buildUser({ role: 'parent' }), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () => HttpResponse.json([])),
      http.get('*/api/quests/family/', () => HttpResponse.json({ results: [] })),
      http.get('*/api/children/', () =>
        HttpResponse.json([
          { id: 1, username: 'a', display_label: 'Abby' },
          { id: 2, username: 'b', display_label: 'Beck' },
        ]),
      ),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      http.post('*/api/quests/', async ({ request }) => {
        createCalls.push(await request.clone().json());
        return HttpResponse.json({ id: 99 }, { status: 201 });
      }),
    ]);
    await user.click(await screen.findByRole('button', { name: /issue challenge/i }));
    // Required fields: title + description (the form uses TextField "Title").
    await user.type(screen.getByLabelText(/^title$/i), 'Tag-team week');
    await user.type(
      screen.getByLabelText(/description/i),
      'Both kids attack the same boss',
    );
    // Toggle co-op + pick two kids.
    await user.click(screen.getByLabelText(/co-op campaign/i));
    await user.click(screen.getByLabelText(/abby/i));
    await user.click(screen.getByLabelText(/beck/i));
    // Toggle on_time_only inside Advanced details (rendered as <details>/<summary>).
    const onTimeBox = screen.getByLabelText(/only count homework submitted on time/i);
    await user.click(onTimeBox);
    // Submit — the in-modal button reads "Issue the challenge".
    await user.click(screen.getByRole('button', { name: /issue the challenge/i }));

    await waitFor(() => expect(createCalls).toHaveLength(1));
    const body = createCalls[0];
    // Co-op id pair landed (numbers, not strings).
    expect(body.coop_user_ids?.slice().sort()).toEqual([1, 2]);
    expect(body.assigned_to).toBeUndefined();
    // on_time_only flowed into trigger_filter.on_time.
    expect(body.trigger_filter).toEqual({ on_time: true });
  });

  it('filters available trials by name via the search input', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () =>
        HttpResponse.json([
          { id: 1, name: 'Dragon Slayer', description: 'fell the wyrm', quest_type_display: 'Boss', target_value: 100, duration_days: 7 },
          { id: 2, name: 'Berry Hunt', description: 'collect 12 berries', quest_type_display: 'Collection', target_value: 12, duration_days: 3 },
        ]),
      ),
      http.get('*/api/quests/history/', () => HttpResponse.json([])),
    ]);
    const availableTab = await screen.findByRole('button', { name: /available/i });
    await user.click(availableTab);
    await waitFor(() => expect(screen.getByText(/dragon slayer/i)).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter available trials/i });
    await user.type(search, 'berry');

    expect(screen.queryByText(/dragon slayer/i)).not.toBeInTheDocument();
    expect(screen.getByText(/berry hunt/i)).toBeInTheDocument();
  });
});
