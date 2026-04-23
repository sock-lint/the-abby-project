import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Habits from './Habits.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildUser, buildHabit, buildParent } from '../test/factories.js';

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
        <Habits />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Habits', () => {
  it('renders empty state when no habits', async () => {
    renderPage(buildUser(), [
      http.get('*/api/habits/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText((t) => /no rituals/i.test(t))).toBeInTheDocument(),
    );
  });

  it('renders a habit row', async () => {
    renderPage(buildUser(), [
      http.get('*/api/habits/', ({ request }) => {
        const pending = new URL(request.url).searchParams.get('pending') === 'true';
        return HttpResponse.json(pending
          ? { results: [] }
          : { results: [
            { id: 1, name: 'Read 20 min', icon: '📖', habit_type: 'positive', strength: 3, color: 'green' },
          ] },
        );
      }),
    ]);
    await waitFor(() => expect(screen.getByText(/read 20 min/i)).toBeInTheDocument());
  });

  it('clicking virtue posts {direction:1} to /habits/{id}/log/', async () => {
    const user = userEvent.setup();
    const tap = spyHandler('post', /\/api\/habits\/\d+\/log\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/habits/', () =>
        HttpResponse.json([
          buildHabit({ id: 9, max_taps_per_day: 2, taps_today: 0 }),
        ]),
      ),
      tap.handler,
    ]);

    const button = await screen.findByRole('button', { name: /virtue/i });
    await user.click(button);

    await waitFor(() => expect(tap.calls).toHaveLength(1));
    expect(tap.calls[0].body).toEqual({ direction: 1 });
    expect(tap.calls[0].url).toMatch(/\/habits\/9\/log\/$/);
  });

  it('clicking vice posts {direction:-1} to /habits/{id}/log/', async () => {
    const user = userEvent.setup();
    const tap = spyHandler('post', /\/api\/habits\/\d+\/log\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/habits/', () =>
        HttpResponse.json([
          buildHabit({
            id: 9,
            name: 'Skip dessert',
            icon: '🍰',
            habit_type: 'negative',
            strength: -2,
            color: 'red',
          }),
        ]),
      ),
      tap.handler,
    ]);

    const button = await screen.findByRole('button', { name: /vice/i });
    await user.click(button);

    await waitFor(() => expect(tap.calls).toHaveLength(1));
    expect(tap.calls[0].body).toEqual({ direction: -1 });
  });

  it('disables the virtue button when taps_today has hit max_taps_per_day', async () => {
    renderPage(buildUser(), [
      http.get('*/api/habits/', () =>
        HttpResponse.json([
          buildHabit({ id: 7, max_taps_per_day: 2, taps_today: 2 }),
        ]),
      ),
    ]);
    const button = await screen.findByRole('button', { name: /done/i });
    expect(button).toBeDisabled();
    // Count badge is shown as "2/2 today".
    expect(screen.getByText(/2\/2 today/)).toBeInTheDocument();
  });

  it('child sees "Propose a ritual" button and form hides xp + skill tags', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/habits/', () => HttpResponse.json([])),
    ]);
    const btn = await screen.findByRole('button', { name: /propose a ritual/i });
    await user.click(btn);
    await screen.findByRole('dialog', { name: /propose a ritual/i });
    expect(
      screen.getByText(/your parent will set the rewards/i),
    ).toBeInTheDocument();
    // XP + skill tags must not appear for the child.
    expect(screen.queryByLabelText(/^xp pool$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add skill/i })).not.toBeInTheDocument();
  });

  it('child submitting a proposal posts to /habits/ without xp_reward or skill_tags', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/habits\/$/, { id: 1 });
    renderPage(buildUser(), [
      http.get('*/api/habits/', () => HttpResponse.json([])),
      create.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /propose a ritual/i }));
    const submit = await screen.findByRole('button', { name: /send to parent/i });
    await user.type(screen.getByLabelText('Name'), 'Stretch');
    await user.click(submit);

    await waitFor(() => expect(create.calls).toHaveLength(1));
    const body = create.calls[0].body;
    expect(body.name).toBe('Stretch');
    expect(body.xp_reward).toBeUndefined();
    expect(body.skill_tags).toBeUndefined();
    expect(body.user).toBeUndefined();
  });

  it('parent reviewing a pending ritual proposal posts to /habits/{id}/approve/ with xp', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/habits\/\d+\/approve\/$/, { id: 77 });
    const proposal = {
      id: 77,
      name: 'Stretch',
      icon: '🧘',
      habit_type: 'positive',
      user: 2,
      xp_reward: 5,
      max_taps_per_day: 1,
      strength: 0,
      color: 'yellow',
      taps_today: 0,
      pending_parent_review: true,
      created_by: 2,
      created_by_name: 'Abby',
      skill_tags: [],
    };
    renderPage(buildParent(), [
      http.get('*/api/habits/', ({ request }) => {
        const url = new URL(request.url);
        return HttpResponse.json(url.searchParams.get('pending') === 'true'
          ? { results: [proposal] }
          : { results: [] });
      }),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      http.get('*/api/skills/', () => HttpResponse.json([])),
      approve.handler,
    ]);

    const review = await screen.findByRole('button', { name: /review & publish/i });
    await user.click(review);
    await screen.findByRole('dialog', { name: /approve ritual proposal/i });
    await user.click(screen.getByRole('button', { name: /approve & publish/i }));

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/habits\/77\/approve\/$/);
    expect(approve.calls[0].body.xp_reward).toBeDefined();
  });

  it('create-habit form submits max_taps_per_day and no coin_reward', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/habits\/$/, { id: 42 });
    renderPage(buildParent(), [
      http.get('*/api/habits/', () => HttpResponse.json([])),
      http.get('*/api/children/', () => HttpResponse.json([buildUser()])),
      create.handler,
    ]);
    const newBtn = await screen.findByRole('button', { name: /new ritual/i });
    await user.click(newBtn);
    // Wait for the modal's submit button to confirm it's open, then fill inputs.
    const submit = await screen.findByRole('button', { name: /create ritual/i });
    const textboxes = screen.getAllByRole('textbox');
    await user.type(textboxes[0], 'Brush teeth'); // Name field is first textbox.
    // Max taps and XP are the two spinbuttons; first is max_taps_per_day per form order.
    const spinbuttons = screen.getAllByRole('spinbutton');
    await user.clear(spinbuttons[0]);
    await user.type(spinbuttons[0], '2');
    await user.click(submit);
    await waitFor(() => expect(create.calls).toHaveLength(1));
    const body = create.calls[0].body;
    expect(body).not.toHaveProperty('coin_reward');
    expect(body.max_taps_per_day).toBe(2);
    expect(body.name).toBe('Brush teeth');
  });
});
