import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Homework from './Homework.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent, buildUser } from '../test/factories.js';
import { quickDueDates } from '../utils/dates.js';
import * as Sentry from '@sentry/react';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user, handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
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

  it('renders for a parent with pending submissions', async () => {
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], effort_level: 2, timeliness: 'on_time', subject: 'reading' },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 3 })])),
    ]);
    await waitFor(() => expect(screen.getByText(/reading log/i)).toBeInTheDocument());
  });

  it('parent approving a submission posts to /homework-submissions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/homework-submissions\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], effort_level: 2, timeliness: 'on_time', subject: 'reading', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
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
            { id: 9, assignment_title: 'Reading log', user_name: 'Abby', status: 'pending', proofs: [], effort_level: 2, timeliness: 'on_time', subject: 'reading', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
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

  it('child new-assignment form does not render effort/reward/coin inputs', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
      ),
    ]);
    const openButton = await screen.findByRole('button', { name: /new assignment/i });
    await user.click(openButton);
    // Title input is present to confirm form is open.
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/^title$/i)).toBeInTheDocument(),
    );
    // Effort/$ reward/Coins labels should NOT be present for children.
    expect(screen.queryByText(/effort \(1-5\)/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$ reward/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^coins$/i)).not.toBeInTheDocument();
    // Helper text is shown instead.
    expect(screen.getByText(/grown-up will set the reward/i)).toBeInTheDocument();
  });

  it('parent new-assignment form still renders effort/reward/coin inputs', async () => {
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
    expect(screen.getByText(/\$ reward/i)).toBeInTheDocument();
    expect(screen.getByText(/^coins$/i)).toBeInTheDocument();
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
    // Fill due_date via the (only) date input.
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
    expect(create.calls[0].body).toHaveProperty('due_date', quickDueDates().tomorrow);
  });

  it('renders all four quick-date chips and Friday submits a Friday due_date', async () => {
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
    expect(submitted).toBe(quickDueDates().friday);
    // Sanity check: it really is a Friday.
    expect(new Date(submitted + 'T12:00:00').getDay()).toBe(5);
  });

  it('surfaces a backend create error and reports it to Sentry', async () => {
    Sentry.captureException.mockClear();
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({ today: [], upcoming: [], overdue: [], stats: {} }),
      ),
      // Simulate the bug: backend returns 201 with an empty body (no
      // content-type) — client.js throws "Unexpected non-JSON response".
      http.post('*/api/homework/', () => new HttpResponse(null, { status: 201 })),
    ]);
    await user.click(await screen.findByRole('button', { name: /new assignment/i }));
    await user.type(await screen.findByPlaceholderText(/^title$/i), 'Will fail');
    await user.click(screen.getByRole('button', { name: /^tomorrow$/i }));
    await user.click(screen.getByRole('button', { name: /create assignment/i }));

    await waitFor(() =>
      expect(screen.getByText(/non-JSON response/i)).toBeInTheDocument(),
    );
    // Page-level capture fires with our area tag; client.js also captures
    // separately on the non-JSON branch, so we just assert our tagged one.
    const tagged = Sentry.captureException.mock.calls.find(
      ([, ctx]) => ctx?.tags?.area === 'homework.create',
    );
    expect(tagged).toBeDefined();
    expect(tagged[0]).toBeInstanceOf(Error);
  });

  it('clicking Adjust on a pending submission posts to /homework-submissions/{id}/adjust/', async () => {
    const user = userEvent.setup();
    const adjust = spyHandler('post', /\/api\/homework-submissions\/\d+\/adjust\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            {
              id: 42,
              assignment_title: 'Reading log',
              assignment_rewards_pending_review: true,
              assignment_created_by_role: 'child',
              user_name: 'Abby',
              status: 'pending',
              proofs: [],
              timeliness: 'on_time',
              subject: 'reading',
              reward_amount_snapshot: '0.00',
              coin_reward_snapshot: 0,
              reward_breakdown: {
                effort_level: 3,
                base_money: '0.00',
                base_coins: 0,
              },
            },
          ],
        }),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      adjust.handler,
    ]);

    await user.click(await screen.findByRole('button', { name: /^adjust$/i }));
    // Modal form should now show 3 inputs; find them via their labels.
    const modalTitle = await screen.findByText(/adjust reward/i);
    const form = modalTitle.closest('div[role="dialog"]') || document.body;
    const inputs = form.querySelectorAll('input[type="number"]');
    expect(inputs.length).toBeGreaterThanOrEqual(3);

    // Clear and set the first (effort) to 5.
    await user.clear(inputs[0]);
    await user.type(inputs[0], '5');
    await user.clear(inputs[1]);
    await user.type(inputs[1], '2.50');
    await user.clear(inputs[2]);
    await user.type(inputs[2], '10');

    await user.click(screen.getByRole('button', { name: /save adjustment/i }));

    await waitFor(() => expect(adjust.calls).toHaveLength(1));
    expect(adjust.calls[0].url).toMatch(/\/homework-submissions\/42\/adjust\/$/);
    // Number inputs with step=0.01 normalize trailing zeros, so reward_amount
    // comes through as "2.5" not "2.50".
    expect(adjust.calls[0].body).toEqual({
      effort_level: 5,
      reward_amount: '2.5',
      coin_reward: 10,
    });
  });
});

// NOTE: child submit-with-proof is not covered here — it requires File/Blob fixtures
// and the downscaleImage canvas pipeline, which deserves its own focused test.
