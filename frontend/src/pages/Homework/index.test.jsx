import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Homework from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { buildParent, buildUser } from '../../test/factories.js';
import * as Sentry from '@sentry/react';

function buildAssignment(over = {}) {
  return {
    id: 42,
    title: 'Finish lab report',
    description: 'Write up the volcano experiment.',
    subject: 'science',
    effort_level: 3,
    due_date: '2026-04-20',
    assigned_to: 1,
    assigned_to_name: 'Abby',
    created_by: 99,
    created_by_name: 'Parent',
    is_active: true,
    notes: '',
    project: null,
    has_project: false,
    skill_tags: [],
    submission_status: null,
    timeliness_preview: { timeliness: 'on_time' },
    ...over,
  };
}

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user, handlers = [], { route = '/homework' } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <Homework />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Homework', () => {
  it('renders for a child with an empty dashboard', async () => {
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ assignments: [], submissions: [] }),
      ),
    ]);
    await waitFor(() =>
      expect(
        screen.getAllByText((t) => /homework|study/i.test(t)).length,
      ).toBeGreaterThan(0),
    );
  });

  it('renders the QuestFolio verso with a RarityStrand when assignments span effort levels', async () => {
    const { container } = renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [
            buildAssignment({ id: 1, title: 'Lab',  effort_level: 1 }),
            buildAssignment({ id: 2, title: 'Read', effort_level: 3 }),
          ],
          upcoming: [],
          overdue: [],
          stats: { completion_rate: 40, on_time_rate: 80, total_approved: 4 },
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('Lab')).toBeInTheDocument());
    const verso = container.querySelector('[data-folio-verso="true"]');
    expect(verso).not.toBeNull();
    // 40% completion → rising tier (>= 25, < 60).
    expect(verso).toHaveAttribute('data-tier', 'rising');
    expect(verso).toHaveAttribute('data-progress', '40');
    // Effort 1 → common, effort 3 → rare. Both segments paint.
    expect(container.querySelector('[data-rarity="common"]')).not.toBeNull();
    expect(container.querySelector('[data-rarity="rare"]')).not.toBeNull();
  });

  it('renders for a parent with pending submissions', async () => {
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], timeliness: 'on_time', subject: 'reading' },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 3 })])),
    ]);
    await waitFor(() => expect(screen.getByText(/reading log/i)).toBeInTheDocument());
  });

  it('parent approval queue does not render $ / coins anywhere', async () => {
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], timeliness: 'on_time', subject: 'reading' },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/reading log/i)).toBeInTheDocument());
    // No currency glyphs anywhere.
    expect(document.body.textContent).not.toMatch(/\$\d/);
    expect(document.body.textContent).not.toMatch(/\dc\b/);
    // No legacy pending-review / AI-effort badges.
    expect(screen.queryByText(/rewards pending review/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ai estimated effort/i)).not.toBeInTheDocument();
    // No Adjust button.
    expect(screen.queryByRole('button', { name: /^adjust$/i })).not.toBeInTheDocument();
  });

  it('parent approving a submission posts to /homework-submissions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/homework-submissions\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], timeliness: 'on_time', subject: 'reading' },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/homework-submissions\/9\/approve\/$/);
  });

  it('parent rejecting a submission posts to /homework-submissions/{id}/reject/', async () => {
    const user = userEvent.setup();
    const reject = spyHandler('post', /\/api\/homework-submissions\/\d+\/reject\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], timeliness: 'on_time', subject: 'reading' },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      reject.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^reject$/i });
    await user.click(button);

    await waitFor(() => expect(reject.calls).toHaveLength(1));
    expect(reject.calls[0].url).toMatch(/\/homework-submissions\/9\/reject\/$/);
  });

  it('child new-assignment form does not render reward inputs', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
      ),
    ]);
    const openButton = await screen.findByRole('button', { name: /new assignment/i });
    await user.click(openButton);
    // Title input confirms the form is open.
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/^title$/i)).toBeInTheDocument(),
    );
    // Effort + reward + coin inputs are NOT present for children.
    expect(screen.queryByText(/effort \(1-5\)/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$ reward/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^coins$/i)).not.toBeInTheDocument();
    // Child-facing helper copy explains the new reward shape.
    expect(screen.getByText(/xp, streaks, and a chance at loot/i)).toBeInTheDocument();
  });

  it('parent visiting /homework?new=1 from quick action auto-opens the form modal', async () => {
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ pending_submissions: [] }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 3 })])),
    ], { route: '/homework?new=1' });
    // Form modal should auto-open on mount, not require clicking "New assignment".
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /new assignment/i })).toBeInTheDocument(),
    );
  });

  it('parent new-assignment form renders the assignee dropdown when /api/children/ returns the DRF paginated shape', async () => {
    // Pin: production /api/children/ returns {count, results: [...]} (DRF
    // PageNumberPagination), not a raw array. A previous build read .length
    // off the wrapper, so the dropdown silently never rendered for any parent.
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ pending_submissions: [] }),
      ),
      http.get('*/api/children/', () =>
        HttpResponse.json({
          count: 1,
          next: null,
          previous: null,
          results: [buildUser({ id: 7, display_name: 'Abby' })],
        }),
      ),
    ]);
    await user.click(await screen.findByRole('button', { name: /new assignment/i }));
    const dialog = await screen.findByRole('dialog', { name: /new assignment/i });
    const select = await within(dialog).findByRole('combobox', { name: /assign to/i });
    expect(select).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: /abby/i })).toBeInTheDocument();
  });

  it('parent new-assignment form shows "add a child first" empty-state when no children exist', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ pending_submissions: [] }),
      ),
      http.get('*/api/children/', () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    ]);
    await user.click(await screen.findByRole('button', { name: /new assignment/i }));
    const dialog = await screen.findByRole('dialog', { name: /new assignment/i });
    expect(
      await within(dialog).findByText(/no children registered yet/i),
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole('combobox', { name: /assign to/i })).not.toBeInTheDocument();
  });

  it('parent new-assignment form blocks submit when no child is selected', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/homework\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ pending_submissions: [] }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 3 })])),
      create.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /new assignment/i }));
    await user.type(await screen.findByPlaceholderText(/^title$/i), 'No assignee yet');
    const dialog = screen.getByRole('dialog', { name: /new assignment/i });
    const dateInput = dialog.querySelector('input[type="date"]');
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
    await user.type(dateInput, tomorrow);
    // Bypass the HTML5 required attr to exercise the JS guard directly.
    dialog.querySelector('form').noValidate = true;
    await user.click(screen.getByRole('button', { name: /create assignment/i }));
    expect(create.calls).toHaveLength(0);
    expect(
      await within(dialog).findByText(/please select a child/i),
    ).toBeInTheDocument();
  });

  it('parent new-assignment form renders effort input but no currency inputs', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ pending_submissions: [] }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 3 })])),
    ]);
    const openButton = await screen.findByRole('button', { name: /new assignment/i });
    await user.click(openButton);
    await waitFor(() =>
      expect(screen.getByText(/effort \(1-5\)/i)).toBeInTheDocument(),
    );
    // The two currency inputs must be gone.
    expect(screen.queryByText(/\$ reward/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^coins$/i)).not.toBeInTheDocument();
  });

  it('child create posts only title/description/subject/due_date (no reward fields)', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/homework\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
      ),
      create.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /new assignment/i }));
    await user.type(await screen.findByPlaceholderText(/^title$/i), 'My homework');
    const container = screen.getByPlaceholderText(/^title$/i).closest('form');
    const dateInput = container.querySelector('input[type="date"]');
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
    await user.type(dateInput, tomorrow);
    await user.click(screen.getByRole('button', { name: /create assignment/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    const body = create.calls[0].body;
    expect(body).toHaveProperty('title', 'My homework');
    expect(body).toHaveProperty('subject');
    expect(body).toHaveProperty('due_date', tomorrow);
    expect(body).not.toHaveProperty('effort_level');
    expect(body).not.toHaveProperty('reward_amount');
    expect(body).not.toHaveProperty('coin_reward');
    expect(body).not.toHaveProperty('assigned_to');
  });

  it('clicking the Tomorrow quick-date chip sets due_date and submits it', async () => {
    // Freeze to Wednesday so the Tomorrow chip isn't deduped against Friday.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 3, 15, 9, 0));
    try {
      const user = userEvent.setup();
      const create = spyHandler('post', /\/api\/homework\/$/, { ok: true });
      renderPage(buildUser(), [
        http.get('*/api/homework/dashboard/', () =>
          HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
        ),
        create.handler,
      ]);
      await user.click(await screen.findByRole('button', { name: /new assignment/i }));
      await user.type(await screen.findByPlaceholderText(/^title$/i), 'Quick homework');
      const tomorrowChip = screen.getByRole('button', { name: /^tomorrow$/i });
      expect(tomorrowChip).toHaveAttribute('aria-pressed', 'false');
      await user.click(tomorrowChip);
      expect(tomorrowChip).toHaveAttribute('aria-pressed', 'true');
      await user.click(screen.getByRole('button', { name: /create assignment/i }));

      await waitFor(() => expect(create.calls).toHaveLength(1));
      expect(create.calls[0].body).toHaveProperty('due_date', '2026-04-16');
    } finally {
      vi.useRealTimers();
    }
  });

  it('renders all four quick-date chips and Friday submits a Friday due_date', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 3, 15, 9, 0)); // Wed 2026-04-15
    try {
      const user = userEvent.setup();
      const create = spyHandler('post', /\/api\/homework\/$/, { ok: true });
      renderPage(buildUser(), [
        http.get('*/api/homework/dashboard/', () =>
          HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
        ),
        create.handler,
      ]);
      await user.click(await screen.findByRole('button', { name: /new assignment/i }));
      for (const label of [/^tomorrow$/i, /^friday$/i, /^next mon$/i, /\+1 week/i]) {
        expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
      }
      await user.type(await screen.findByPlaceholderText(/^title$/i), 'Friday work');
      await user.click(screen.getByRole('button', { name: /^friday$/i }));
      await user.click(screen.getByRole('button', { name: /create assignment/i }));

      await waitFor(() => expect(create.calls).toHaveLength(1));
      const submitted = create.calls[0].body.due_date;
      expect(submitted).toBe('2026-04-17');
      expect(new Date(submitted + 'T12:00:00').getDay()).toBe(5);
    } finally {
      vi.useRealTimers();
    }
  });

  it('hides the Friday chip on Thursdays so Tomorrow is not duplicated', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 3, 16, 9, 0)); // Thu 2026-04-16 — Tomorrow == Friday
    try {
      const user = userEvent.setup();
      renderPage(buildUser(), [
        http.get('*/api/homework/dashboard/', () =>
          HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
        ),
      ]);
      await user.click(await screen.findByRole('button', { name: /new assignment/i }));
      expect(screen.queryByRole('button', { name: /^friday$/i })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^tomorrow$/i })).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /^tomorrow$/i }));
      const pressed = screen
        .getAllByRole('button')
        .filter((b) => b.getAttribute('aria-pressed') === 'true');
      expect(pressed).toHaveLength(1);
      expect(pressed[0]).toHaveTextContent(/tomorrow/i);
    } finally {
      vi.useRealTimers();
    }
  });

  it('hides the Next Mon chip on Mondays so +1 week is not duplicated', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 3, 13, 9, 0)); // Mon 2026-04-13 — Next Mon == +1 week
    try {
      const user = userEvent.setup();
      renderPage(buildUser(), [
        http.get('*/api/homework/dashboard/', () =>
          HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
        ),
      ]);
      await user.click(await screen.findByRole('button', { name: /new assignment/i }));
      expect(screen.queryByRole('button', { name: /^next mon$/i })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /\+1 week/i })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('surfaces a backend create error and reports it to Sentry', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 3, 15, 9, 0));
    try {
      Sentry.captureException.mockClear();
      const user = userEvent.setup();
      renderPage(buildUser(), [
        http.get('*/api/homework/dashboard/', () =>
          HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
        ),
        http.post('*/api/homework/', () => new HttpResponse(null, { status: 201 })),
      ]);
      await user.click(await screen.findByRole('button', { name: /new assignment/i }));
      await user.type(await screen.findByPlaceholderText(/^title$/i), 'Will fail');
      await user.click(screen.getByRole('button', { name: /^tomorrow$/i }));
      await user.click(screen.getByRole('button', { name: /create assignment/i }));

      await waitFor(() =>
        expect(screen.getByText(/non-JSON response/i)).toBeInTheDocument(),
      );
      const tagged = Sentry.captureException.mock.calls.find(
        ([, ctx]) => ctx?.tags?.area === 'homework.create',
      );
      expect(tagged).toBeDefined();
      expect(tagged[0]).toBeInstanceOf(Error);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('Homework — edit & delete', () => {
  it('clicking edit opens the form pre-filled and PATCHes the assignment', async () => {
    const user = userEvent.setup();
    const patch = spyHandler('patch', /\/api\/homework\/\d+\/$/, { id: 42 });

    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          assignments: [buildAssignment()],
          pending_submissions: [],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      patch.handler,
    ]);

    const editBtn = await screen.findByRole('button', { name: /edit assignment/i });
    await user.click(editBtn);

    const dialog = await screen.findByRole('dialog', { name: /edit assignment/i });
    const titleInput = within(dialog).getByDisplayValue('Finish lab report');
    await user.clear(titleInput);
    await user.type(titleInput, 'Finish volcano report');

    await user.click(within(dialog).getByRole('button', { name: /update assignment/i }));

    await waitFor(() => expect(patch.calls).toHaveLength(1));
    expect(patch.calls[0].url).toMatch(/\/homework\/42\/$/);
    expect(patch.calls[0].body.title).toBe('Finish volcano report');
    expect(patch.calls[0].body.subject).toBe('science');
    expect(patch.calls[0].body.due_date).toBe('2026-04-20');
  });

  it('clicking delete then confirm DELETEs the assignment', async () => {
    const user = userEvent.setup();
    const del = spyHandler('delete', /\/api\/homework\/\d+\/$/, null);

    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          assignments: [buildAssignment()],
          pending_submissions: [],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      del.handler,
    ]);

    const deleteBtn = await screen.findByRole('button', { name: /delete assignment/i });
    await user.click(deleteBtn);

    const confirm = await screen.findByRole('alertdialog', { name: /delete assignment\?/i });
    await user.click(within(confirm).getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(del.calls).toHaveLength(1));
    expect(del.calls[0].url).toMatch(/\/homework\/42\/$/);
  });

  it('does not render edit or delete buttons for child users', async () => {
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [buildAssignment()],
          upcoming: [],
          overdue: [],
          stats: { completion_rate: 0, on_time_rate: 0, total_approved: 0 },
        }),
      ),
    ]);

    await screen.findByText(/finish lab report/i);
    expect(screen.queryByRole('button', { name: /edit assignment/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /delete assignment/i })).toBeNull();
  });
});

describe('Homework — child self-plan gate', () => {
  it('shows "Plan it out" to a child when can_plan is true (long-lead)', async () => {
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [],
          upcoming: [
            buildAssignment({
              id: 100, title: 'Big project', can_plan: true,
            }),
          ],
          overdue: [],
          stats: { completion_rate: 0, on_time_rate: 0, total_approved: 0 },
        }),
      ),
    ]);
    await screen.findByText(/big project/i);
    expect(screen.getByRole('button', { name: /plan it out/i })).toBeInTheDocument();
  });

  it('hides "Plan it out" from a child when can_plan is false (short-lead)', async () => {
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [
            buildAssignment({
              id: 101, title: 'Due tomorrow', can_plan: false,
            }),
          ],
          upcoming: [],
          overdue: [],
          stats: { completion_rate: 0, on_time_rate: 0, total_approved: 0 },
        }),
      ),
    ]);
    await screen.findByText(/due tomorrow/i);
    expect(screen.queryByRole('button', { name: /plan it out/i })).toBeNull();
  });

  it('child clicking "Plan it out" POSTs to /api/homework/<id>/plan/', async () => {
    const user = userEvent.setup();
    const plan = spyHandler('post', /\/api\/homework\/\d+\/plan\/$/, {
      project_id: 555,
    });
    // Stub window.location.href to avoid jsdom navigation noise.
    const origHref = window.location.href;
    delete window.location;
    window.location = { href: origHref };

    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          today: [],
          upcoming: [
            buildAssignment({
              id: 200, title: 'Long lead project', can_plan: true,
            }),
          ],
          overdue: [],
          stats: { completion_rate: 0, on_time_rate: 0, total_approved: 0 },
        }),
      ),
      plan.handler,
    ]);

    const button = await screen.findByRole('button', { name: /plan it out/i });
    await user.click(button);

    await waitFor(() => expect(plan.calls).toHaveLength(1));
    expect(plan.calls[0].url).toMatch(/\/homework\/200\/plan\/$/);
  });
});

// NOTE: child submit-with-proof is not covered here — it requires File/Blob fixtures
// and the downscaleImage canvas pipeline, which deserves its own focused test.
