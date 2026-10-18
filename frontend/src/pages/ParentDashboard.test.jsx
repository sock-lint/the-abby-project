import { describe, expect, it } from 'vitest';
import { delay, http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Dashboard from './Dashboard.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent } from '../test/factories.js';

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current location">{location.pathname + location.search}</output>;
}
function renderDashboard(extraHandlers = []) {
  server.use(...extraHandlers);
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Dashboard />
        <LocationProbe />
      </AuthProvider>
    </MemoryRouter>,
  );
}

const emptyDashboard = {
  active_timer: null, current_balance: 0, coin_balance: 0,
  this_week: { hours_worked: 0, earnings: 0 },
  active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
  pending_chore_approvals: 0,
  rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
};

describe('ParentDashboard', () => {
  it('shows a legacy chore marked complete on the family-local day in the approval queue', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({
        family: { id: 1, timezone: 'Asia/Tokyo' },
      }))),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json([{
        id: 11, chore_title: 'Dishes', user: 2, user_name: 'Abby', status: 'pending',
        completed_date: '2026-10-17', created_at: '2026-10-17T23:30:00Z',
        timing_snapshot: null, reward_amount_snapshot: '1.00', coin_reward_snapshot: 0,
      }])),
    ]);
    const doneOn = (await screen.findByText('Done on')).parentElement;
    expect(doneOn).not.toHaveTextContent('UTC');
    expect(doneOn.querySelector('time')).toHaveAttribute('datetime', '2026-10-18');
  });

  it('keeps the daily gratitude pad off the parent Today screen', async () => {
    const wellbeing = spyHandler('get', /\/api\/wellbeing\/today\/$/, {});
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      wellbeing.handler,
    ]);
    expect(await screen.findByRole('heading', { name: /you're all caught up/i })).toBeInTheDocument();
    expect(screen.queryByText(/today's note/i)).toBeNull();
    expect(screen.queryByRole('textbox', { name: /Gratitude line/ })).toBeNull();
    expect(wellbeing.calls).toHaveLength(0);
  });

  it.each([
    { response: 'immediate', queueDelay: 0 },
    { response: 'slower than one second', queueDelay: 1500 },
  ])('renders the all-clear hero when the queue is empty with $response data', async ({ queueDelay }) => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', async () => {
        await delay(queueDelay);
        return HttpResponse.json([]);
      }),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/you're all caught up/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 2, name: /you're all caught up/i })).toBeInTheDocument();
  });

  it('renders count copy and approval queue grouped by kid', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 10, chore_title: 'Dishes', user: 2, user_name: 'Abby', reward_amount_snapshot: '1.00', submitted_at: '2026-04-16T10:00:00Z' },
        ]),
      ),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 20, assignment_title: 'Math packet', user_id: 2, user_name: 'Abby', reward_amount_snapshot: '2.00', submitted_at: '2026-04-16T09:00:00Z' },
          ],
        }),
      ),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([
          { id: 30, reward: { name: 'Screen time' }, user: 2, user_name: 'Abby', coin_cost_snapshot: 25, status: 'pending', requested_at: '2026-04-16T08:00:00Z' },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/3 things to review today/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/^dishes$/i)).toBeInTheDocument();
    expect(screen.getByText(/^math packet$/i)).toBeInTheDocument();
    expect(screen.getByText(/^screen time$/i)).toBeInTheDocument();
  });

  it('approving a chore fires /chore-completions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/chore-completions\/\d+\/approve\/$/, { ok: true });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 11, chore_title: 'Dishes', user: 2, user_name: 'Abby', reward_amount_snapshot: '1.00' },
        ]),
      ),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);
    const btn = await screen.findByRole('button', { name: /approve dishes/i });
    await user.click(btn);
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/chore-completions\/11\/approve\/$/);
  });

  it('approving a homework submission fires /homework-submissions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/homework-submissions\/\d+\/approve\/$/, { ok: true });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () =>
        HttpResponse.json({
          pending_submissions: [
            { id: 22, assignment_title: 'Reading log', user_id: 2, user_name: 'Abby' },
          ],
        }),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);
    const btn = await screen.findByRole('button', { name: /approve reading log/i });
    await user.click(btn);
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/homework-submissions\/22\/approve\/$/);
  });

  it('shows a retry-able banner when an approval queue fails to load', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json({ error: 'boom' }, { status: 500 })),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/chore approvals/i),
    );
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByText(/you're all caught up|no pending approvals/i)).toBeNull();
    const summary = screen.getByRole('heading', { name: /some updates are unavailable/i });
    expect(screen.getByRole('alert').compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('places decisions and the visible family overview before optional setup', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ ...emptyDashboard, children_count: 1 })),
      http.get('*/api/children/', () => HttpResponse.json([{ id: 2, username: 'abby', display_name: 'Abby' }])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([
        { id: 11, chore_title: 'Dishes', user: 2, user_name: 'Abby' },
      ])),
    ]);
    const approval = await screen.findByRole('button', { name: /approve dishes/i });
    const family = screen.getByRole('heading', { name: 'Family overview' });
    const setup = screen.getByText('Getting started');
    expect(approval.compareDocumentPosition(family) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(family.compareDocumentPosition(setup) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole('link', { name: /view abby's timeline/i })).toBeVisible();
    expect(screen.queryByRole('button', { name: /add a child to your family/i })).toBeNull();
  });

  it('includes pending timecards in attention with a direct review link', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ ...emptyDashboard, children_count: 1, pending_timecards: 2 })),
    ]);
    const link = await screen.findByRole('link', { name: /review 2 timecards/i });
    expect(link).toHaveAttribute('href', '/treasury?tab=wages');
    expect(link.closest('#approval-queue')).not.toBeNull();
    expect(screen.queryByText(/you're all caught up|no pending approvals/i)).toBeNull();
    expect(screen.getByText(/2 (things|items) to review/i)).toBeInTheDocument();
  });

  it.each([1, 2])('includes %i pending prints in attention with a review link instead of inline approval', async (count) => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ ...emptyDashboard, children_count: 1 })),
      http.get('*/api/print-requests/', () => HttpResponse.json({
        count, next: null,
        results: Array.from({ length: count }, (_, i) => ({ id: i + 1, title: 'Dragon', status: 'pending' })),
      })),
    ]);

    const link = await screen.findByRole('link', { name: `Review ${count} print request${count === 1 ? '' : 's'}` });
    expect(link).toHaveAttribute('href', '/treasury?tab=forge');
    expect(link.closest('#approval-queue')).not.toBeNull();
    expect(screen.getByRole('heading', { name: `${count} ${count === 1 ? 'thing' : 'things'} to review today` })).toBeInTheDocument();
    expect(screen.queryByText(/you're all caught up|no pending approvals/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /approve dragon|approve all/i })).toBeNull();

    await user.click(link);
    expect(screen.getByLabelText('Current location')).toHaveTextContent('/treasury?tab=forge');
  });

  it('adds print reviews to the timecard and inline approval attention counts', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ ...emptyDashboard, children_count: 1, pending_timecards: 2 })),
      http.get('*/api/chore-completions/', () => HttpResponse.json([
        { id: 11, chore_title: 'Dishes', user: 2, user_name: 'Abby' },
      ])),
      http.get('*/api/print-requests/', () => HttpResponse.json([
        { id: 1, status: 'pending' }, { id: 2, status: 'pending' },
      ])),
    ]);

    expect(await screen.findByRole('heading', { name: '5 things to review today' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review 2 print requests' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review 2 timecards' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve Dishes' })).toBeInTheDocument();
  });

  it('keeps a failed print queue incomplete and recovers its review link on retry', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const fetch = spyHandler('get', '*/api/print-requests/', ({ request }) => {
      expect(new URL(request.url).searchParams.get('status')).toBe('pending');
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json({ detail: 'Temporary failure' }, { status: 503 })
        : [{ id: 1, status: 'pending' }];
    });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ ...emptyDashboard, children_count: 1 })),
      fetch.handler,
    ]);

    expect(await screen.findByRole('alert')).toHaveTextContent(/print approvals/i);
    expect(screen.getByRole('heading', { name: 'Some updates are unavailable' })).toBeInTheDocument();
    expect(screen.queryByText(/you're all caught up|no pending approvals/i)).toBeNull();

    await user.click(screen.getByRole('button', { name: /^retry$/i }));
    expect(await screen.findByRole('link', { name: 'Review 1 print request' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(/you're all caught up|no pending approvals/i)).toBeNull();
    expect(fetch.calls).toHaveLength(2);
  });

  it('shows a child-list failure without claiming the family has no children', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ ...emptyDashboard, children_count: 1 })),
      http.get('*/api/children/', () => HttpResponse.json({ error: 'Family lookup failed' }, { status: 500 })),
    ]);
    const family = await screen.findByRole('region', { name: 'Family overview' });
    expect(await within(family).findByRole('alert')).toHaveTextContent(/couldn't load your family/i);
    expect(within(family).queryByText(/no children added yet/i)).toBeNull();
    expect(within(family).getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('shows the NoChildrenWelcome empty state when children_count is 0 and pending queue is empty', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 0 }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/creations/pending/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/welcome — let's add your first kid/i)).toBeInTheDocument(),
    );
    const link = screen.getByRole('link', { name: /add a child/i });
    expect(link).toHaveAttribute('href', '/manage');
    // The "you're all caught up" hero (which lives on the populated path)
    // must NOT render — that copy is reserved for parents who already have
    // kids but a clean queue.
    expect(screen.queryByText(/you're all caught up/i)).toBeNull();
  });

  it('hides NoChildrenWelcome when children_count is positive', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 2 }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/creations/pending/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/you're all caught up/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/welcome — let's add your first kid/i)).toBeNull();
  });

  it('shows clocked hours and earnings once in the visible family overview', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          ...emptyDashboard,
          children_count: 1,
          this_week_by_kid: [{ kid_id: 2, name: 'Abby', hours: 1.5, earnings: 15 }],
        }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([{ id: 2, username: 'abby', display_name: 'Abby' }])),
    ]);
    const child = (await screen.findByRole('link', { name: /view abby's timeline/i })).closest('article');
    expect(child).toHaveTextContent(/1.5h clocked/);
    expect(child).toHaveTextContent(/\$15.00 clocked earnings/);
    expect(screen.getAllByText(/\$15.00/)).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /week at a glance/i })).toBeNull();
    expect(screen.getByRole('button', { name: 'Assign homework' })).toBeVisible();
  });

  it('does not claim "all quiet" while the approval aggregate is still loading', async () => {
    let releaseChores;
    const choresPending = new Promise((resolve) => { releaseChores = resolve; });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 1 }),
      ),
      http.get('*/api/chore-completions/', async () => {
        await choresPending;
        return HttpResponse.json([
          { id: 12, chore_title: 'Trash', user: 2, user_name: 'Abby' },
        ]);
      }),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);

    // Mid-flight: neither the queue's empty state nor the hero's all-clear
    // may render — both told the parent "nothing pending" before the fetches
    // that carried the pending rows had even resolved.
    await waitFor(() =>
      expect(screen.getByText(/checking for updates/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/no pending approvals/i)).toBeNull();
    expect(screen.queryByText(/you're all caught up/i)).toBeNull();

    releaseChores();
    await waitFor(() => expect(screen.getByText('Trash')).toBeInTheDocument());
  });

  it('links the child timeline from the Family overview card', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({ ...emptyDashboard, children_count: 1 }),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () =>
        HttpResponse.json([{ id: 2, username: 'abby', display_name: 'Abby' }]),
      ),
    ]);

    const tile = await screen.findByRole('link', { name: /view abby's timeline/i });
    expect(tile.closest('article')).toHaveTextContent('Abby');
    await userEvent.setup().click(tile);
    expect(screen.getByLabelText('Current location')).toHaveTextContent('/chronicle?tab=yearbook&child=2');
  });

  it('shows the server household summary with child-specific task links before clocked earnings', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json({
        ...emptyDashboard, children_count: 1,
        family_overview: {
          date: '2026-10-18', timezone: 'America/Phoenix', children: [{
            kid_id: 2, name: 'Abby', homework: { due_today: 2, overdue: 1, pending_review: 3 },
            chores: { remaining: 2, pending_review: 1, approved: 3, total: 6 },
            parent_goals: { active_count: 4, items: [{
              id: 'goal:8', name: 'Read together', progress: '7.500', target: '20.000', unit: 'minutes',
            }] },
            recent_accomplishment: { kind: 'badge', title: 'Steady learner', occurred_at: '2026-10-18T20:00:00Z' },
            clocked_week: { hours: 1.5, earnings: 15 },
          }],
        },
      })),
      http.get('*/api/children/', () => HttpResponse.json([])),
    ]);
    const family = await screen.findByRole('region', { name: 'Family overview' });
    expect(await within(family).findByText(/2 due today · 1 overdue/)).toBeVisible();
    expect(within(family).getByText('3 awaiting your review')).toBeVisible();
    expect(within(family).getByText('2 remaining · 1 awaiting review · 3 approved')).toBeVisible();
    expect(within(family).getByText('7.5 / 20 minutes')).toBeVisible();
    expect(within(family).getByRole('progressbar', { name: 'Read together progress' })).toHaveAttribute('aria-valuenow', '7.5');
    expect(within(family).getByText('Earned a badge: Steady learner')).toBeVisible();
    expect(within(family).getByText(/household day \(America\/Phoenix\)/)).toBeVisible();
    expect(within(family).getByRole('link', { name: "View Abby's homework" })).toHaveAttribute('href', '/quests?tab=study&child=2');
    expect(within(family).getByRole('link', { name: "View Abby's chores" })).toHaveAttribute('href', '/quests?tab=duties&child=2');
    expect(within(family).getByRole('link', { name: "View Abby's goals" })).toHaveTextContent('View all 4 goals');
    const accomplished = within(family).getByText('Earned a badge: Steady learner');
    const earnings = within(family).getByText(/1.5h clocked/);
    expect(accomplished.compareDocumentPosition(earnings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('approving a redemption fires /redemptions/{id}/approve/ with notes body', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/redemptions\/\d+\/approve\/$/, { ok: true });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/dashboard/', () => HttpResponse.json(emptyDashboard)),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ pending_submissions: [] })),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([
          { id: 33, reward: { name: 'Movie night' }, user: 2, user_name: 'Abby', coin_cost_snapshot: 30, requested_at: '2026-04-16T08:00:00Z', status: 'pending' },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([])),
      approve.handler,
    ]);
    const btn = await screen.findByRole('button', { name: /approve movie night/i });
    await user.click(btn);
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].body).toEqual({ notes: '' });
    expect(approve.calls[0].url).toMatch(/\/redemptions\/33\/approve\/$/);
  });
});
