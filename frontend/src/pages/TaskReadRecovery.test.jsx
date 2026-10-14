import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within } from '../test/render';
import { server } from '../test/server';
import { buildUser, buildParent, buildHabit, buildChore } from '../test/factories';
import Habits from './Habits';
import Chores from './Chores';
import Movement from './Movement';

function auth(user = buildUser()) {
  localStorage.setItem('abby_auth_token', 'test-token');
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(user)));
}

describe('Task read recovery', () => {
  it('groups Today using the family day at a device midnight boundary', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-05-01T00:30:00Z'));
    try {
      auth(buildUser({ family: { timezone: 'America/Phoenix' } }));
      server.use(http.get('*/api/movement-sessions/', () => HttpResponse.json([
        { id: 1, user: 1, movement_type_name: 'Family day run', duration_minutes: 20,
          intensity: 'medium', occurred_on: '2026-04-30', created_at: '2026-05-01T00:15:00Z', xp_awarded: 5 },
        { id: 2, user: 1, movement_type_name: 'Different day walk', duration_minutes: 20,
          intensity: 'medium', occurred_on: '2026-05-01', created_at: '2026-05-01T00:15:00Z', xp_awarded: 8 },
      ])));
      renderWithProviders(<Movement />);
      await screen.findByText('Family day run');
      const today = screen.getByText('Today').closest('section');
      expect(within(today).getByText('Family day run')).toBeInTheDocument();
      expect(within(today).queryByText('Different day walk')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps a loaded habit visible after a confirmed tap followed by a failed read', async () => {
    auth();
    let reads = 0;
    let posted;
    server.use(
      http.get('*/api/habits/', ({ request }) => {
        if (new URL(request.url).searchParams.has('pending')) return HttpResponse.json([]);
        reads += 1;
        return reads === 1
          ? HttpResponse.json([buildHabit({ id: 7, name: 'Read every evening', max_taps_per_day: 3 })])
          : HttpResponse.json({ detail: 'Refresh unavailable.' }, { status: 503 });
      }),
      http.post('*/api/habits/7/log/', async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ direction: 1, new_strength: 1 });
      }),
    );
    const { user } = renderWithProviders(<Habits />);
    await user.click(await screen.findByRole('button', { name: 'Log progress' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/last loaded list/i);
    expect(screen.getByText('Read every evening')).toBeInTheDocument();
    expect(posted).toEqual({ direction: 1 });
    expect(screen.queryByText(/no habits yet/i)).not.toBeInTheDocument();
  });

  it.each([
    ['habits', Habits, buildHabit({ name: 'Read every evening' }), /no habits yet/i],
    ['chores', Chores, buildChore({ title: 'Wash the dishes' }), /no chores available today/i],
  ])('a failed %s read offers retry without claiming an empty list', async (endpoint, Page, item, empty) => {
    auth();
    let attempts = 0;
    server.use(http.get(`*/api/${endpoint}/`, ({ request }) => {
      if (new URL(request.url).searchParams.has('pending')) return HttpResponse.json([]);
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json({ detail: 'Tasks temporarily unavailable.' }, { status: 503 })
        : HttpResponse.json([item]);
    }));
    const { user } = renderWithProviders(<Page />);
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('Tasks temporarily unavailable.');
    expect(screen.queryByText(empty)).not.toBeInTheDocument();
    await user.click(within(error).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(item.name || item.title)).toBeInTheDocument();
  });

  it('keeps loaded chores visible when their completion queue fails and retries that source', async () => {
    auth(buildParent());
    let attempts = 0;
    server.use(
      http.get('*/api/chores/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.has('pending') ? [] : [buildChore({ title: 'Wash the dishes' })],
      )),
      http.get('*/api/chore-completions/', () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json({ detail: 'Queue unavailable.' }, { status: 503 })
          : HttpResponse.json([]);
      }),
    );
    const { user } = renderWithProviders(<Chores />);
    expect(await screen.findByText('Wash the dishes')).toBeInTheDocument();
    const error = screen.getByRole('alert');
    expect(error).toHaveTextContent(/completion.*unavailable/i);
    await user.click(within(error).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Wash the dishes')).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it.each([
    ['habits', Habits, buildHabit({ name: 'Read every evening' }), 'Filter habits'],
    ['chores', Chores, buildChore({ title: 'Wash the dishes' }), 'Filter chores'],
  ])('clears a %s search from its filtered empty state', async (endpoint, Page, item, label) => {
    auth();
    server.use(http.get(`*/api/${endpoint}/`, ({ request }) => HttpResponse.json(
      new URL(request.url).searchParams.has('pending') ? [] : [item],
    )));
    const { user } = renderWithProviders(<Page />);
    await screen.findByText(item.name || item.title);
    await user.type(screen.getByRole('searchbox', { name: label }), 'not present');
    const empty = screen.getByText(/No (?:habits |chores )?match/i).closest('[role="status"]');
    await user.click(within(empty).getByRole('button', { name: 'Clear filter' }));
    expect(screen.getByRole('searchbox', { name: label })).toHaveValue('');
    expect(screen.getByText(item.name || item.title)).toBeInTheDocument();
  });

  it('separates recorded activity from verified XP and names the child for parents', async () => {
    auth(buildParent());
    const today = new Date().toLocaleDateString('en-CA');
    server.use(http.get('*/api/movement-sessions/', () => HttpResponse.json([
      { id: 1, user: 2, user_display: 'Alex', movement_type_name: 'Run', duration_minutes: 5,
        intensity: 'medium', occurred_on: today, created_at: new Date().toISOString(), xp_awarded: 0,
        notes: 'A full note that stays readable on small screens without hiding its ending.' },
      { id: 2, user: 3, user_display: 'Sam', movement_type_name: 'Walk', duration_minutes: 30,
        intensity: 'low', occurred_on: today, created_at: new Date().toISOString(), xp_awarded: 8 },
    ])));
    renderWithProviders(<Movement />);
    await screen.findByText('Run');
    expect(screen.getByText('Alex')).toBeInTheDocument();
    expect(screen.getByText('Sam')).toBeInTheDocument();
    expect(screen.queryByText(/rewarded sessions logged/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/2 sessions recorded today.*8 XP earned/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/A full note/)).not.toHaveClass('truncate');
  });
});
