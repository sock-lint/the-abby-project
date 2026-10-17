import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from '../hooks/useApi';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent, buildChore, buildHabit } from '../test/factories';
import { selectDropdown } from '../test/selectDropdown';
import { PARENT_REVIEW_CHANGED } from '../api/parentReviewRefresh';
import Homework from './Homework';
import Chores from './Chores';
import Habits from './Habits';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const children = [{ id: 7, display_name: 'Abby' }, { id: 8, display_name: 'Sam' }];
const parent = buildParent({ id: 99, family: { id: 5 } });
function SwitchFamily() {
  const { setUser } = useAuth();
  return <button onClick={() => setUser(buildParent({ id: 100, family: { id: 6 } }))}>Switch family</button>;
}
function TaskLocation() {
  const { search } = useLocation();
  return <output aria-label="Task location">{search}</output>;
}
function renderTasks(route, handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
    ...handlers,
    http.get('*/api/children/', () => HttpResponse.json(children)),
  );
  return render(<MemoryRouter initialEntries={[route]}><AuthProvider>
    <SwitchFamily />
    <TaskLocation />
    <nav aria-label="Task test navigation"><Link to="/homework">Homework page</Link><Link to="/chores">Chores page</Link><Link to="/habits">Habits page</Link></nav>
    <Routes><Route path="/homework" element={<Homework />} /><Route path="/chores" element={<Chores />} /><Route path="/habits" element={<Habits />} /></Routes>
  </AuthProvider></MemoryRouter>);
}

describe('Parent task child context', () => {
  it.each([
    ['/chores?child=7&propose=1', 'New chore', 'Title', 'Assign to', 'Create', /\/api\/chores\/$/],
    ['/habits?child=7&propose=1', 'New habit', 'Name', 'Child', 'Create habit', /\/api\/habits\/$/],
  ])('follows a newly saved assignee once without reopening the form from %s', async (route, title, field, picker, submit, endpoint) => {
    const user = userEvent.setup();
    const create = spyHandler('post', endpoint, { id: 62 });
    renderTasks(route, [http.get('*/api/chores/', () => HttpResponse.json([])), http.get('*/api/habits/', () => HttpResponse.json([])), create.handler]);
    const dialog = await screen.findByRole('dialog', { name: title });
    await user.type(within(dialog).getByLabelText(field), 'A task for Sam');
    await selectDropdown(user, within(dialog).getByRole('combobox', { name: picker }), '8');
    await user.click(within(dialog).getByRole('button', { name: submit }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: title })).not.toBeInTheDocument());
    expect(await screen.findByRole('combobox', { name: 'Viewing' })).toHaveValue('8');
    expect(screen.getByLabelText('Task location')).not.toHaveTextContent('propose=1');
  });
  it('ignores an old-family create completion after the account workspace changes', async () => {
    const user = userEvent.setup();
    let finish;
    const response = new HttpResponse(new ReadableStream({ start(controller) {
      finish = () => { controller.enqueue(new TextEncoder().encode(JSON.stringify({ id: 61 }))); controller.close(); };
    } }), { headers: { 'Content-Type': 'application/json' } });
    const create = spyHandler('post', /\/api\/chores\/$/, response);
    renderTasks('/chores?child=7&propose=1', [http.get('*/api/chores/', () => HttpResponse.json([])), create.handler]);
    const dialog = await screen.findByRole('dialog', { name: 'New chore' });
    await user.type(within(dialog).getByLabelText('Title'), 'Old family task');
    await selectDropdown(user, within(dialog).getByRole('combobox', { name: 'Assign to' }), '8');
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    server.use(http.get('*/api/children/', () => HttpResponse.json([{ id: 9, display_name: 'New child' }])));
    fireEvent.click(screen.getByRole('button', { name: 'Switch family', hidden: true }));
    expect(await screen.findByRole('combobox', { name: 'Viewing' })).toHaveValue('9');
    const completed = new Promise((resolve) => window.addEventListener(PARENT_REVIEW_CHANGED, resolve, { once: true }));
    await act(async () => { finish(); await completed; });
    expect(screen.getByLabelText('Task location')).not.toHaveTextContent('child=8');
    expect(screen.queryByDisplayValue('Old family task')).not.toBeInTheDocument();
    expect(create.calls).toHaveLength(1);
    expect(create.calls[0].body.assigned_to).toBe(8);
  });
  it('clears old-family tasks and the selected roster immediately while another family loads', async () => {
    const user = userEvent.setup();
    renderTasks('/chores?child=7', [http.get('*/api/chores/', ({ request }) => HttpResponse.json(
      new URL(request.url).searchParams.has('pending') ? [] : [buildChore({ id: 41, title: 'Old family chore', assigned_to: 7 })],
    ))]);
    await screen.findByText('Old family chore');
    let release;
    server.use(http.get('*/api/children/', async () => {
      await new Promise((resolve) => { release = resolve; });
      return HttpResponse.json([{ id: 9, display_name: 'New child' }]);
    }));
    await user.click(screen.getByRole('button', { name: 'Switch family' }));
    expect(screen.queryByText('Old family chore')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Viewing' })).not.toBeInTheDocument();
    await waitFor(() => expect(release).toBeDefined());
    server.use(http.get('*/api/chores/', ({ request }) => HttpResponse.json(
      new URL(request.url).searchParams.has('pending') ? [] : [buildChore({ id: 42, title: 'New family chore', assigned_to: 9 })],
    )));
    release();
    expect(await screen.findByText('New family chore')).toBeInTheDocument();
    expect(screen.queryByText('Old family chore')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Viewing' })).toHaveValue('9');
  });
  it('keeps chore tuning in Advanced and saves a selected-child alternating schedule with an optional reward', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/chores\/$/, { id: 32 });
    renderTasks('/chores?child=8&propose=1', [
      http.get('*/api/chores/', () => HttpResponse.json([])), create.handler,
    ]);
    const dialog = await screen.findByRole('dialog', { name: 'New chore' });
    expect(within(dialog).queryByLabelText('XP pool')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Order')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Reward ($)')).not.toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Title'), 'Feed cat');
    await selectDropdown(user, within(dialog).getByRole('combobox', { name: 'Custody schedule' }), 'alternating');
    fireEvent.change(within(dialog).getByLabelText('Start date (on-week)'), { target: { value: '2026-10-12' } });
    expect(within(dialog).getByRole('status')).toHaveTextContent('Next available day:');
    await user.click(within(dialog).getByLabelText('Offer money or coins (optional)'));
    await user.clear(within(dialog).getByLabelText('Reward ($)'));
    await user.type(within(dialog).getByLabelText('Reward ($)'), '2.50');
    await user.click(within(dialog).getByRole('button', { name: 'Advanced options' }));
    await user.clear(within(dialog).getByLabelText('XP pool'));
    await user.type(within(dialog).getByLabelText('XP pool'), '12');
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ title: 'Feed cat', assigned_to: 8, recurrence: 'daily', week_schedule: 'alternating', schedule_start_date: '2026-10-12', reward_amount: '2.5', xp_reward: 12 });
  });

  it('defaults a chore to no money or coins without hiding its daily schedule', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/chores\/$/, { id: 33 });
    renderTasks('/chores?child=7&propose=1', [http.get('*/api/chores/', () => HttpResponse.json([])), create.handler]);
    const dialog = await screen.findByRole('dialog', { name: 'New chore' });
    await user.type(within(dialog).getByLabelText('Title'), 'Put toys away');
    await user.click(within(dialog).getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ assigned_to: 7, reward_amount: '0.00', coin_reward: 0, recurrence: 'daily' });
  });
  it('does not offer child habit logging to a parent or send a log request', async () => {
    const log = spyHandler('post', /\/api\/habits\/6\/log\/$/, { ok: true });
    renderTasks('/habits?child=7', [
      http.get('*/api/habits/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.has('pending') ? [] : [buildHabit({ id: 6, name: 'Abby reading', user: 7 })])), log.handler,
    ]);
    expect(await screen.findByText('Abby reading')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /log progress|log setback/i })).not.toBeInTheDocument();
    expect(log.calls).toHaveLength(0);
  });
  it('retains the verified selected child across homework, chores and habits and creates for that child', async () => {
    const user = userEvent.setup();
    const create = spyHandler('post', /\/api\/habits\/$/, { id: 31 });
    renderTasks('/homework?child=7', [
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ assignments: [
        { id: 1, title: 'Abby math', assigned_to: 7 }, { id: 2, title: 'Sam writing', assigned_to: 8 },
      ], pending_submissions: [] })),
      http.get('*/api/chores/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.has('pending') ? [] : [
        buildChore({ id: 3, title: 'Abby room', assigned_to: 7 }), buildChore({ id: 4, title: 'Sam room', assigned_to: 8 }),
        buildChore({ id: 5, title: 'Shared dishes', assigned_to: null }),
      ])),
      http.get('*/api/habits/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.has('pending') ? [] : [
        buildHabit({ id: 6, name: 'Abby reading', user: 7 }), buildHabit({ id: 7, name: 'Sam reading', user: 8 }),
      ])), create.handler,
    ]);
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Viewing' }), '8');
    expect(await screen.findByText('Sam writing')).toBeInTheDocument();
    expect(screen.queryByText('Abby math')).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Chores page' }));
    expect(await screen.findByText('Sam room')).toBeInTheDocument();
    expect(screen.queryByText('Abby room')).not.toBeInTheDocument();
    expect(screen.getByText('Shared dishes')).toBeInTheDocument();
    expect(screen.getByText('All children')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Habits page' }));
    expect(await screen.findByText('Sam reading')).toBeInTheDocument();
    expect(screen.queryByText('Abby reading')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'New habit' }));
    const dialog = await screen.findByRole('dialog', { name: 'New habit' });
    await user.type(within(dialog).getByLabelText('Name'), 'Drink water');
    await user.click(within(dialog).getByRole('button', { name: 'Create habit' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ name: 'Drink water', user: 8 });
  });

  it('finds selected-child chores beyond the first family page and never requests an unverified ID', async () => {
    const pages = [];
    renderTasks('/chores?child=999', [
      http.get('*/api/chores/', ({ request }) => {
        const query = new URL(request.url).searchParams;
        if (query.get('pending')) return HttpResponse.json([]);
        pages.push(query.get('page') || '1');
        expect(query.get('child')).toBeNull();
        expect(query.get('user_id')).toBeNull();
        return HttpResponse.json(query.get('page') === '2'
          ? { count: 21, next: null, results: [buildChore({ id: 21, title: 'Abby last chore', assigned_to: 7 })] }
          : { count: 21, next: 'https://other.invalid/api/chores/?page=2', results: Array.from({ length: 20 }, (_, i) => buildChore({ id: i + 1, title: `Sam chore ${i}`, assigned_to: 8 })) });
      }),
    ]);
    expect(await screen.findByText('Abby last chore')).toBeInTheDocument();
    expect(screen.queryByText('Sam chore 0')).not.toBeInTheDocument();
    expect(pages).toEqual(['1', '2']);
  });
});
