import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Chores from './Chores.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildChore, buildParent, buildUser } from '../test/factories.js';
import { buildCalendarFile, downloadCalendarFile } from '../utils/calendar';
import { formatDate } from '../utils/format';

vi.mock('../utils/calendar', async (importOriginal) => ({
  ...await importOriginal(),
  downloadCalendarFile: vi.fn(),
}));

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user = buildUser(), handlers = [], route = '/quests?tab=duties') {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <Chores />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Chores', () => {
  it('offers an optional deadline only for a one-time chore and sends the selected date', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/chores\/$/, { id: 7, title: 'Plant bulbs' });
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      create.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /new chore/i }));
    expect(screen.queryByLabelText('Due date (optional)')).not.toBeInTheDocument();
    await user.click(screen.getByLabelText('Recurrence'));
    await user.click(screen.getByRole('option', { name: 'One-time' }));
    const dueDate = screen.getByLabelText('Due date (optional)');
    expect(dueDate).not.toBeRequired();
    fireEvent.change(dueDate, { target: { value: '2026-10-18' } });
    await user.type(screen.getByLabelText('Title'), 'Plant bulbs');
    await user.click(screen.getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ recurrence: 'one_time', due_date: '2026-10-18' });
  });

  it('clears a one-time deadline when editing the chore to repeat weekly', async () => {
    const user = userEvent.setup();
    const chore = buildChore({ id: 7, recurrence: 'one_time', due_date: '2026-10-18' });
    const update = spyHandler('patch', /\/api\/chores\/7\/$/, chore);
    renderPage(buildParent(), [
      http.get('*/api/chores/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.get('pending') === 'true' ? [] : [chore],
      )),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      update.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: 'Edit chore' }));
    expect(screen.getByLabelText('Due date (optional)')).toHaveValue('2026-10-18');
    await user.click(screen.getByLabelText('Recurrence'));
    await user.click(screen.getByRole('option', { name: 'Weekly' }));
    expect(screen.queryByLabelText('Due date (optional)')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ recurrence: 'weekly', due_date: null });
  });

  it('explains and saves clearing an optional one-time deadline', async () => {
    const user = userEvent.setup();
    const chore = buildChore({ id: 7, recurrence: 'one_time', due_date: '2026-10-18' });
    const update = spyHandler('patch', /\/api\/chores\/7\/$/, chore);
    renderPage(buildParent(), [
      http.get('*/api/chores/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.get('pending') === 'true' ? [] : [chore],
      )),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      update.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: 'Edit chore' }));
    const field = screen.getByLabelText('Due date (optional)');
    expect(field).toHaveAccessibleDescription('Leave blank for no deadline.');
    fireEvent.change(field, { target: { value: '' } });
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ recurrence: 'one_time', due_date: null });
  });

  it('shows the saved weekly period, Sunday deadline and actual Friday submission in parent review', async () => {
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([{
        id: 22, chore_title: 'Weekly watering', user: 1, user_name: 'Abby', status: 'pending',
        completed_date: '2026-10-12', reward_amount_snapshot: '0.00', coin_reward_snapshot: 0,
        timing_snapshot: {
          version: 1, timezone: 'America/Phoenix', schedule: 'weekly',
          submitted_at: '2026-10-16T18:30:00+00:00', submitted_on: '2026-10-16',
          period_start: '2026-10-12', period_end: '2026-10-18', due_on: '2026-10-18', timeliness: 'on_time',
        },
      }])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
    ]);
    await screen.findByText('Scheduled week');
    expect(screen.getByText('Scheduled week').parentElement.querySelector('time')).toHaveAttribute('datetime', '2026-10-12');
    expect(screen.getByText('Due').parentElement.querySelector('time')).toHaveAttribute('datetime', '2026-10-18');
    expect(screen.getByText('Marked complete').parentElement.querySelector('time')).toHaveAttribute('datetime', '2026-10-16T18:30:00+00:00');
    expect(screen.getByText('Marked complete').parentElement).toHaveTextContent('Oct 16');
    expect(screen.getByText('On time')).toBeInTheDocument();
  });

  it('loads selected-child reviewed chores outside the pending queue only when opened', async () => {
    const user = userEvent.setup();
    const historyQueries = [];
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', ({ request }) => {
        const params = new URL(request.url).searchParams;
        if (params.get('status') !== 'reviewed') return HttpResponse.json([]);
        historyQueries.push(Object.fromEntries(params));
        return HttpResponse.json({ count: 1, next: null, previous: null, results: [{
          id: 23, user: 2, user_name: 'Sibling', chore_title: 'Reviewed shelves', status: 'approved',
          created_at: '2026-10-16T18:30:00Z', decided_at: '2026-10-19T18:30:00Z',
          completed_date: '2026-10-12', timing_snapshot: null,
        }] });
      }),
      http.get('*/api/children/', () => HttpResponse.json([buildUser(), buildUser({ id: 2, username: 'sibling' })])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
    ], '/quests?tab=duties&child=2');
    await screen.findByText('Reviewed chores');
    expect(historyQueries).toHaveLength(0);
    await user.click(screen.getByText('Reviewed chores'));
    await screen.findByText('Sibling · Reviewed shelves');
    expect(historyQueries).toHaveLength(1);
    expect(historyQueries[0]).toMatchObject({ status: 'reviewed', user_id: '2', page: '1' });
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.getByText('Recorded period date')).toBeInTheDocument();
    expect(screen.getByText(/original deadline and schedule were not saved/i)).toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
  });

  it('shows one-time deadlines on cards and preserves unknown legacy timing in child history', async () => {
    renderPage(buildUser(), [
      http.get('*/api/chores/', () => HttpResponse.json([
        buildChore({ recurrence: 'one_time', due_date: '2026-10-18' }),
      ])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([{
        id: 24, user: 1, chore_title: 'Old watering', status: 'approved', completed_date: '2026-10-12',
        created_at: '2026-10-16T18:30:00Z', timing_snapshot: null,
        reward_amount_snapshot: '0.00', coin_reward_snapshot: 0,
      }])),
    ]);
    await screen.findByText('Old watering');
    expect(screen.getByText(`Due ${formatDate('2026-10-18')}`)).toBeInTheDocument();
    expect(screen.getByText('Recorded period date')).toBeInTheDocument();
    expect(screen.getByText('Marked complete').parentElement.querySelector('time')).toHaveAttribute('datetime', '2026-10-16T18:30:00Z');
    expect(screen.getByText(/original deadline and schedule were not saved/i)).toBeInTheDocument();
    expect(screen.queryByText('Reviewed chores')).not.toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
  });

  it.each([
    ['child proposal', buildUser(), /propose a chore/i, /send to parent/i],
    ['parent creation', buildParent(), /new chore/i, /^create$/i],
  ])('saves a selected icon for %s only after explicit submit', async (_mode, account, openLabel, submitLabel) => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/chores\/$/, { id: 7, title: 'Tidy room' });
    renderPage(account, [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      create.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: openLabel }));
    await user.type(screen.getByLabelText('Title'), 'Tidy room');
    if (account.role === 'parent') await user.click(screen.getByRole('button', { name: 'Advanced options' }));
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    await user.click(screen.getByRole('button', { name: 'Broom' }));
    expect(screen.getByLabelText('Icon')).toHaveValue('🧹');
    expect(create.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: submitLabel }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ title: 'Tidy room', icon: '🧹' });
    if (account.role === 'child') {
      expect(create.calls[0].body).not.toHaveProperty('reward_amount');
      expect(create.calls[0].body).not.toHaveProperty('coin_reward');
      expect(create.calls[0].body).not.toHaveProperty('xp_reward');
    }
  });

  it.each([false, true])('parent editing a chore preserves custom icon or saves selected icon (choose: %s)', async (choose) => {
    const user = userEvent.setup();
    const chore = buildChore({ id: 7, title: 'Tidy room', icon: 'family mark' });
    const update = spyHandler('patch', /\/api\/chores\/7\/$/, chore);
    renderPage(buildParent(), [
      http.get('*/api/chores/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.get('pending') === 'true' ? [] : [chore],
      )),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      update.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: 'Edit chore' }));
    expect(screen.getByLabelText('Icon')).toHaveValue('family mark');
    if (choose) {
      await user.click(screen.getByRole('button', { name: 'Choose icon' }));
      await user.click(screen.getByRole('button', { name: 'Broom' }));
    }
    expect(update.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body.icon).toBe(choose ? '🧹' : 'family mark');
  });

  it('saves a selected icon when approving a chore proposal', async () => {
    const user = userEvent.setup();
    const proposal = buildChore({ id: 7, title: 'Tidy room', icon: 'custom', pending_parent_review: true, assigned_to: 1, created_by_name: 'Abby' });
    const approve = spyHandler('post', /\/api\/chores\/7\/approve\/$/, proposal);
    renderPage(buildParent(), [
      http.get('*/api/chores/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.get('pending') === 'true' ? [proposal] : [],
      )),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      approve.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /review & publish/i }));
    expect(screen.getByLabelText('Icon')).toHaveValue('custom');
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    await user.click(screen.getByRole('button', { name: 'Broom' }));
    expect(approve.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Approve & publish' }));
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].body).toMatchObject({ icon: '🧹', title: 'Tidy room', coin_reward: expect.any(Number), xp_reward: expect.any(Number) });
  });

  it('creates Google and Apple reminders on the selected active chore date', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2020-12-29T16:00:00Z'));
    try {
      const user = userEvent.setup();
      renderPage(buildUser(), [
        http.get('*/api/chores/', ({ request }) => HttpResponse.json(
          new URL(request.url).searchParams.get('pending') === 'true' ? [] : [
            buildChore({ id: 7, title: 'Feed cat', week_schedule: 'alternating', schedule_start_date: '2020-12-21' }),
          ],
        )),
        http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      ]);

      await user.click(await screen.findByRole('button', { name: 'Add Chore reminder: Feed cat to calendar' }));
      const dialog = await screen.findByRole('dialog', { name: 'Add to calendar' });
      const date = within(dialog).getByLabelText('Reminder date');
      expect(date).toHaveValue('2021-01-11');
      expect(within(dialog).getByText(/choose one day for this chore reminder/i)).toBeInTheDocument();

      fireEvent.change(date, { target: { value: '2021-01-13' } });
      const google = new URL(within(dialog).getByRole('link', { name: /Google Calendar/ }).href);
      expect(google.searchParams.get('text')).toBe('Chore reminder: Feed cat');
      expect(google.searchParams.get('dates')).toBe('20210113/20210114');
      expect(google.searchParams.has('recur')).toBe(false);

      await user.click(within(dialog).getByRole('button', { name: /Apple Calendar/ }));
      expect(downloadCalendarFile).toHaveBeenCalledTimes(1);
      const exported = buildCalendarFile(downloadCalendarFile.mock.calls[0][0]);
      expect(exported).toContain('SUMMARY:Chore reminder: Feed cat');
      expect(exported).toContain('DTSTART;VALUE=DATE:20210113');
      expect(exported).toContain('DTEND;VALUE=DATE:20210114');
      expect(exported).not.toContain('RRULE');

      fireEvent.change(date, { target: { value: '2021-01-04' } });
      expect(within(dialog).getByText(/this chore is off that week/i)).toBeInTheDocument();
      expect(within(dialog).getByRole('link', { name: /Google Calendar/ })).toHaveAttribute('aria-disabled', 'true');
      expect(within(dialog).getByRole('link', { name: /Google Calendar/ })).not.toHaveAttribute('href');
      expect(within(dialog).getByRole('button', { name: /Apple Calendar/ })).toBeDisabled();
      await user.click(within(dialog).getByRole('button', { name: /Apple Calendar/ }));
      expect(downloadCalendarFile).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('offers reminders only for active chores that have finished parent review', async () => {
    renderPage(buildParent(), [
      http.get('*/api/chores/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.get('pending') === 'true' ? [] : [
          buildChore({ id: 1, title: 'Daily dishes', is_active: true }),
          buildChore({ id: 2, title: 'Retired chore', is_active: false }),
          buildChore({ id: 3, title: 'Unreviewed proposal', pending_parent_review: true }),
        ],
      )),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
    ]);

    expect(await screen.findByRole('button', { name: 'Add Chore reminder: Daily dishes to calendar' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /add .* to calendar/i })).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Add Chore reminder: Retired chore to calendar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add Chore reminder: Unreviewed proposal to calendar' })).toBeNull();
  });

  // The quick-actions FAB deep-links here with ?propose=1. The param was
  // never read, so the row just landed on the tab and the kid had to hunt
  // for the button again.
  it('opens the propose sheet when deep-linked with ?propose=1', async () => {
    renderPage(buildUser(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
    ], '/quests?tab=duties&propose=1');
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('does not open the sheet without the param', async () => {
    renderPage(buildUser(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('renders empty state for children', async () => {
    renderPage(buildUser(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no chores available today/i)).toBeInTheDocument(),
    );
  });

  it('renders empty state for parents', async () => {
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no chores yet/i)).toBeInTheDocument(),
    );
  });

  it('renders chore rows for a child', async () => {
    renderPage(buildUser(), [
      http.get('*/api/chores/', ({ request }) => {
        const pending = new URL(request.url).searchParams.get('pending') === 'true';
        return HttpResponse.json(pending
          ? []
          : [buildChore({ id: 1, title: 'Dishes', is_available: true, reward_amount: '1.00' })],
        );
      }),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Dishes')).toBeInTheDocument());
  });

  it('parent can open the new-chore form modal', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new chore/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /new chore/i }));
    expect(await screen.findByRole('button', { name: /^create$/i })).toBeInTheDocument();
  });

  it('new-chore form includes SkillTagEditor with skills from /skills/', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([
        { id: 1, name: 'Persistence', icon: '💪', category_name: 'Life Skills' },
      ])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new chore/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /new chore/i }));
    await user.click(screen.getByRole('button', { name: 'Advanced options' }));
    // Empty-state copy comes from SkillTagEditor — prove the component is mounted.
    expect(
      await screen.findByText(/no skills tagged/i, {}, { timeout: 2000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add skill/i })).toBeInTheDocument();
  });

  // Regression: the Active toggle was a raw <input type="checkbox"> in a
  // hand-rolled <label>, so it had no htmlFor/id association. CheckboxField
  // gives it one, which is what makes getByLabelText resolve it.
  it('renders the Active toggle as a labelled checkbox', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
    ]);
    await user.click(await screen.findByRole('button', { name: /new chore/i }));

    await user.click(screen.getByRole('button', { name: 'Advanced options' }));
    const active = await screen.findByLabelText('Active');
    expect(active).toHaveAttribute('type', 'checkbox');
    expect(active).toBeChecked();
    await user.click(active);
    expect(active).not.toBeChecked();
  });

  it('saving a new chore posts skill_tags alongside the chore', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/chores\/$/, { id: 1, title: 'Dishes' });
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([
        { id: 7, name: 'Persistence', icon: '💪', category_name: 'Life Skills' },
      ])),
      create.handler,
    ]);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new chore/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /new chore/i }));
    await user.click(screen.getByRole('button', { name: 'Advanced options' }));
    await screen.findByText(/no skills tagged/i);

    await user.type(screen.getByLabelText('Title'), 'Dishes');
    await user.click(screen.getByRole('button', { name: /add skill/i }));
    await user.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    const body = create.calls[0].body;
    expect(body.title).toBe('Dishes');
    expect(body.skill_tags).toEqual([{ skill_id: 7, xp_weight: 1 }]);
  });

  it('parent sees approval queue when completions are pending', async () => {
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 1, chore_title: 'Dishes', chore_icon: '🍽️', user: 1, user_name: 'Abby', status: 'pending', completed_date: '2026-04-16', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /awaiting approval/i })).toBeInTheDocument(),
    );
  });

  it('child clicking Done posts to /chores/{id}/complete/', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', /\/api\/chores\/\d+\/complete\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/chores/', ({ request }) => {
        const pending = new URL(request.url).searchParams.get('pending') === 'true';
        return HttpResponse.json(pending
          ? []
          : [buildChore({ id: 12, title: 'Dishes', is_available: true, today_status: null })],
        );
      }),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      complete.handler,
    ]);

    const button = await screen.findByRole('button', { name: /done/i });
    await user.click(button);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/chores\/12\/complete\/$/);
    expect(complete.calls[0].body).toEqual({ notes: '' });
  });

  it('child clicking Done buzzes, matching the dashboard quick-complete', async () => {
    const vibrate = vi.fn();
    Object.defineProperty(navigator, 'vibrate', { value: vibrate, configurable: true });
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/chores/', ({ request }) => {
        const pending = new URL(request.url).searchParams.get('pending') === 'true';
        return HttpResponse.json(pending
          ? []
          : [buildChore({ id: 12, title: 'Dishes', is_available: true, today_status: null })],
        );
      }),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.post(/\/api\/chores\/\d+\/complete\/$/, () => HttpResponse.json({ ok: true })),
    ]);

    await user.click(await screen.findByRole('button', { name: /done/i }));
    expect(vibrate).toHaveBeenCalled();
  });

  it('locks the chore sheet closed while a create is in flight', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      // Never resolves — holds the form in its saving state.
      http.post('*/api/chores/', () => new Promise(() => {})),
    ]);
    await user.click(await screen.findByRole('button', { name: /new chore/i }));
    const dialog = await screen.findByRole('dialog', { name: /new chore/i });
    await user.type(within(dialog).getByRole('textbox', { name: /title/i }), 'Sweep');
    await user.click(within(dialog).getByRole('button', { name: /^create$/i }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^close$/i })).toBeDisabled(),
    );
    expect(screen.getByRole('dialog', { name: /new chore/i })).toBeInTheDocument();
  });

  it('parent approving a pending completion posts to /chore-completions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/chore-completions\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 22, chore_title: 'Dishes', chore_icon: '🍽️', user: 1, user_name: 'Abby', status: 'pending', completed_date: '2026-04-16', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/chore-completions\/22\/approve\/$/);
  });

  it('child sees "Propose a chore" button and form hides reward fields', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
    ]);
    const btn = await screen.findByRole('button', { name: /propose a chore/i });
    await user.click(btn);
    // Dialog header should mention "Propose" for children.
    await screen.findByRole('dialog', { name: /propose a chore/i });
    // Notice to the child: parent sets rewards.
    expect(
      screen.getByText(/your parent will set the rewards/i),
    ).toBeInTheDocument();
    // Reward inputs must NOT appear — only the "what it is" fields.
    expect(screen.queryByLabelText(/reward \(\$\)/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^coins$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^xp pool$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add skill/i })).not.toBeInTheDocument();
  });

  it('child submitting a proposal posts to /chores/ without reward fields', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/chores\/$/, { id: 1, title: 'Feed cat' });
    renderPage(buildUser(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      create.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /propose a chore/i }));
    await screen.findByRole('dialog', { name: /propose a chore/i });
    await user.type(screen.getByLabelText('Title'), 'Feed cat');
    await user.click(screen.getByRole('button', { name: /send to parent/i }));

    await waitFor(() => expect(create.calls).toHaveLength(1));
    const body = create.calls[0].body;
    expect(body.title).toBe('Feed cat');
    // Server strips these anyway, but the client shouldn't bother sending them.
    expect(body.reward_amount).toBeUndefined();
    expect(body.coin_reward).toBeUndefined();
    expect(body.xp_reward).toBeUndefined();
    expect(body.skill_tags).toBeUndefined();
  });

  it('parent reviewing a pending proposal posts to /chores/{id}/approve/ with rewards', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/chores\/\d+\/approve\/$/, { id: 99, title: 'Feed cat' });
    const proposal = {
      id: 99,
      title: 'Feed cat',
      description: '',
      icon: '🐈',
      reward_amount: '0.00',
      coin_reward: 0,
      xp_reward: 10,
      recurrence: 'daily',
      week_schedule: 'every_week',
      is_active: true,
      pending_parent_review: true,
      created_by: 1,
      assigned_to: 1,
      created_by_name: 'Abby',
      skill_tags: [],
    };
    renderPage(buildParent(), [
      // First call (no params) returns the regular list; same MSW handler
      // serves the ?pending=true call too.
      http.get('*/api/chores/', ({ request }) => {
        const url = new URL(request.url);
        return HttpResponse.json(url.searchParams.get('pending') === 'true' ? [proposal] : []);
      }),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      approve.handler,
    ]);

    const review = await screen.findByRole('button', { name: /review & publish/i });
    await user.click(review);
    const dialog = await screen.findByRole('dialog', { name: /approve chore proposal/i });
    // The banner lives inside the modal; the row also mentions "proposed by",
    // so scope the assertion to the dialog.
    expect(within(dialog).getByText(/proposed by/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: /approve & publish/i }));

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/chores\/99\/approve\/$/);
    // Parent's submission carries the reward block.
    expect(approve.calls[0].body.reward_amount).toBeDefined();
    expect(approve.calls[0].body.coin_reward).toBeDefined();
    expect(approve.calls[0].body.xp_reward).toBeDefined();
  });

  it('parent rejecting a pending completion posts to /chore-completions/{id}/reject/', async () => {
    const user = userEvent.setup();
    const reject = spyHandler('post', /\/api\/chore-completions\/\d+\/reject\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/chores/', () => HttpResponse.json([])),
      http.get('*/api/chore-completions/', () =>
        HttpResponse.json([
          { id: 22, chore_title: 'Dishes', chore_icon: '🍽️', user: 1, user_name: 'Abby', status: 'pending', completed_date: '2026-04-16', reward_amount_snapshot: '1.00', coin_reward_snapshot: 5 },
        ]),
      ),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      reject.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^reject$/i });
    await user.click(button);

    await waitFor(() => expect(reject.calls).toHaveLength(1));
    expect(reject.calls[0].url).toMatch(/\/chore-completions\/22\/reject\/$/);
  });

  it('child clicking ↩ withdraw on a pending chore posts to /chore-completions/{id}/withdraw/', async () => {
    const user = userEvent.setup();
    const withdraw = spyHandler(
      'post',
      /\/api\/chore-completions\/\d+\/withdraw\/$/,
      { ok: true },
    );
    renderPage(buildUser(), [
      http.get('*/api/chores/', () =>
        HttpResponse.json([
          buildChore({
            id: 5,
            title: 'Dishes',
            today_status: 'pending',
            today_completion_id: 71,
            is_available: true,
          }),
        ]),
      ),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
      withdraw.handler,
    ]);

    const button = await screen.findByRole(
      'button', { name: /withdraw this chore submission/i },
    );
    await user.click(button);

    await waitFor(() => expect(withdraw.calls).toHaveLength(1));
    expect(withdraw.calls[0].url).toMatch(/\/chore-completions\/71\/withdraw\/$/);
  });

  it('filters chores via the search input and shows a no-match empty state', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/chores/', ({ request }) => {
        const pending = new URL(request.url).searchParams.get('pending') === 'true';
        return HttpResponse.json(pending
          ? []
          : [
            buildChore({ id: 1, title: 'Wash dishes', description: 'after dinner' }),
            buildChore({ id: 2, title: 'Feed cat', description: 'morning kibble' }),
          ],
        );
      }),
      http.get('*/api/chore-completions/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter chores/i });
    await user.type(search, 'cat');

    expect(screen.queryByText('Wash dishes')).not.toBeInTheDocument();
    expect(screen.getByText('Feed cat')).toBeInTheDocument();

    await user.clear(search);
    await user.type(search, 'zzzz');
    expect(screen.getByText(/no matches for/i)).toBeInTheDocument();
  });
});
