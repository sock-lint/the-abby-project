import { selectDropdown } from '../../test/selectDropdown';
import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within, waitFor, act } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildParent, buildUser } from '../../test/factories';
import { buildChallengeGoal, buildDailyBonus } from '../../test/challenges';
import { CHALLENGES_CHANGED } from '../../hooks/useChallenges';
import Trials from './index';
import { useLocation } from 'react-router-dom';
function LocationProbe() { const location = useLocation(); return <span data-testid="challenge-location">{location.pathname}{location.search}</span>; }

function renderGoals({ goals = [buildChallengeGoal()], pin = null, role = 'child', route = '/quests?tab=trials' } = {}) {
  let savedPin = pin;
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(role === 'parent' ? buildParent() : buildUser())),
    http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7, display_name: 'Abby' })])),
    http.get('*/api/challenges/', () => HttpResponse.json({ results: goals.map((goal) => ({ ...goal, pinned: goal.id === savedPin })), pin: savedPin, daily_bonus: buildDailyBonus() })),
  );
  return { ...renderWithProviders(<><Trials /><LocationProbe /></>, { route }), setPin: (value) => { savedPin = value; } };
}

describe('Automatic challenges', () => {
  it('assigns a catalog family challenge to the verified children and refreshes their shared goal', async () => {
    let assigned = false;
    const shared = buildChallengeGoal({ id: 'legacy:51', name: 'Family workshop', origin: 'legacy', legacy: true, unit: 'actions', action: null });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7, display_name: 'Abby' }), buildUser({ id: 8, display_name: 'Beck' })])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([{ id: 31, name: 'Family workshop', description: 'Build together.', is_cooperative: true, catalog_available: true, quest_type: 'collection', target_value: 5, duration_days: 7, coin_reward: 20, xp_reward: 40, reward_items: [] }])),
      http.get('*/api/challenges/', () => HttpResponse.json({ results: assigned ? [shared] : [], pin: null, daily_bonus: null })),
    );
    const assign = spyHandler('post', /\/api\/quests\/31\/co-op\/$/, () => { assigned = true; return { id: 51 }; });
    server.use(assign.handler);
    const { user } = renderWithProviders(<Trials />, { route: '/quests?tab=trials&child=7' });
    await user.click(await screen.findByRole('button', { name: 'Family challenges' }));
    const dialog = screen.getByRole('dialog', { name: 'Assign a family challenge' });
    await selectDropdown(user, await within(dialog).findByLabelText('Family challenge'), '31');
    await user.click(within(dialog).getByRole('checkbox', { name: 'Abby' }));
    await user.click(within(dialog).getByRole('checkbox', { name: 'Beck' }));
    await user.click(within(dialog).getByRole('button', { name: 'Assign family challenge' }));
    await waitFor(() => expect(assign.calls).toHaveLength(1));
    expect(assign.calls[0].url).toMatch(/\/api\/quests\/31\/co-op\/$/);
    expect(assign.calls[0].body).toEqual({ user_ids: [7, 8] });
    expect(await screen.findByRole('article', { name: 'Family workshop' })).toBeInTheDocument();
  });

  it('keeps family challenge assignment out of the child workspace', async () => {
    renderGoals();
    await screen.findByRole('article', { name: 'Run 2 miles this week' });
    expect(screen.queryByRole('button', { name: 'Family challenges' })).not.toBeInTheDocument();
  });

  it('records only mounted child catalog details and keeps prose visible while confirmation is pending', async () => {
    const goal = buildChallengeGoal({ origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null, progress: '0' });
    let finish;
    const opened = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/opened\/$/, () => new Promise((resolve) => { finish = () => resolve({ id: goal.id, first_details_opened_at: '2026-10-18T19:00:00Z' }); }));
    server.use(opened.handler);
    const { user } = renderGoals({ goals: [goal] });
    await screen.findByRole('region', { name: 'Explore challenges' });
    expect(opened.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: `View ${goal.name}` }));
    const dialog = await screen.findByRole('dialog', { name: goal.name });
    expect(within(dialog).getByText(goal.description)).toBeInTheDocument();
    await waitFor(() => expect(opened.calls).toHaveLength(1));
    expect(opened.calls[0].body).toEqual({});
    expect(screen.getByRole('region', { name: 'Explore challenges' })).toBeInTheDocument();
    // A newer server read must retain its progress when this older opening
    // request settles; the receipt confirms only the opening timestamp.
    server.use(http.get('*/api/challenges/', () => HttpResponse.json({ results: [{ ...goal, progress: '1.50' }], pin: null, daily_bonus: null })));
    act(() => window.dispatchEvent(new Event(CHALLENGES_CHANGED)));
    await waitFor(() => expect(within(dialog).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1.5'));
    await act(async () => finish());
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Explore challenges' })).not.toBeInTheDocument());
    expect(within(dialog).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1.5');
    expect(screen.getByRole('dialog', { name: goal.name })).toContainElement(within(dialog).getByText(goal.description));
  });

  it('keeps details readable and available to explore after failure, retrying only on close and reopen', async () => {
    const goal = buildChallengeGoal({ origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null, progress: '0' });
    const opened = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/opened\/$/, () => HttpResponse.json({ detail: 'Unavailable' }, { status: 503 }));
    server.use(opened.handler);
    const { user } = renderGoals({ goals: [goal] });
    await user.click(await screen.findByRole('button', { name: `View ${goal.name}` }));
    await waitFor(() => expect(opened.calls).toHaveLength(1));
    expect(within(screen.getByRole('dialog')).getByText(goal.description)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Explore challenges' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: `View ${goal.name}` }));
    await waitFor(() => expect(opened.calls).toHaveLength(2));
    expect(within(screen.getByRole('dialog')).getByText(goal.description)).toBeInTheDocument();
  });

  it('never records a parent inspecting child catalog details', async () => {
    const goal = buildChallengeGoal({ origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null, progress: '0' });
    const opened = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/opened\/$/, {});
    server.use(opened.handler);
    const { user } = renderGoals({ role: 'parent', goals: [goal] });
    await user.click(await screen.findByRole('button', { name: `View ${goal.name}` }));
    expect(within(await screen.findByRole('dialog')).getByText(goal.description)).toBeInTheDocument();
    expect(opened.calls).toHaveLength(0);
  });

  it('opens the requested parent goal for a roster-verified child and consumes only new', async () => {
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, buildChallengeGoal());
    const { user } = renderGoals({ role: 'parent', route: '/quests?tab=trials&new=1&child=7' });
    server.use(create.handler);
    const dialog = await screen.findByRole('dialog', { name: 'Create a challenge' });
    expect(within(dialog).getByRole('combobox', { name: 'Child' })).toHaveValue('7');
    await waitFor(() => expect(screen.getByTestId('challenge-location')).toHaveTextContent('/quests?tab=trials&child=7'));
    await user.click(within(dialog).getByRole('button', { name: 'Create challenge' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ user_id: 7, trigger_type: 'chore_complete' });
  });
  it('puts parent goals and the pin first while keeping a large bonus catalog collapsed', async () => {
    const catalog = Array.from({ length: 43 }, (_, i) => buildChallengeGoal({
      id: `goal:${100 + i}`, name: `Optional bonus ${i + 1}`, origin: 'catalog', progress: '0',
    }));
    const parent = buildChallengeGoal({ id: 'goal:parent', name: 'Family running goal', progress: '0' });
    const pinned = catalog[0];
    const { user, container } = renderGoals({ goals: [...catalog, parent], pin: pinned.id });
    const focus = await screen.findByRole('region', { name: 'Pinned challenge' });
    expect(within(focus).getByRole('article', { name: pinned.name })).toBeInTheDocument();
    const parents = screen.getByRole('region', { name: 'Parent goals' });
    expect(within(parents).getByRole('article', { name: parent.name })).toBeInTheDocument();
    expect(within(parents).getByText('From your parent')).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: catalog[1].name })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'In progress' })).not.toBeInTheDocument();
    expect(container.querySelector('[data-folio-verso="true"]')).not.toBeNull();
    expect(container.querySelector('[data-folio-recto="true"]')).toContainElement(parents);
    await user.click(screen.getByText('Browse bonus challenges'));
    expect(await screen.findByRole('article', { name: catalog[1].name })).toBeInTheDocument();
    expect(screen.getAllByRole('article', { name: pinned.name })).toHaveLength(1);
    expect(screen.getAllByRole('article', { name: parent.name })).toHaveLength(1);
  });

  it('shows three progressing bonus goals nearest completion, without turning zero progress into a task', async () => {
    const goals = [
      buildChallengeGoal({ id: 'goal:21', name: 'Many points', origin: 'catalog', progress: '100', target: '1000' }),
      buildChallengeGoal({ id: 'goal:22', name: 'Almost finished', origin: 'catalog', progress: '9', target: '10' }),
      buildChallengeGoal({ id: 'goal:23', name: 'Small target', origin: 'catalog', progress: '2', target: '3' }),
      buildChallengeGoal({ id: 'goal:24', name: 'Halfway there', origin: 'catalog', progress: '5', target: '10' }),
      buildChallengeGoal({ id: 'goal:25', name: 'Untouched goal', origin: 'catalog', progress: '0' }),
    ];
    renderGoals({ goals });
    const bonus = await screen.findByRole('region', { name: 'Bonus progress' });
    expect(within(bonus).getAllByRole('article').map((row) => row.getAttribute('aria-label')))
      .toEqual(['Almost finished', 'Small target', 'Halfway there']);
    expect(screen.queryByRole('article', { name: 'Many points' })).not.toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'Untouched goal' })).not.toBeInTheDocument();
    within(bonus).getAllByText(/Goal period/).forEach((period) => {
      expect(period).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    });
  });

  it('refreshes a hidden bonus into the preview when saved activity makes progress, without opening its browser', async () => {
    const goals = [buildChallengeGoal({ origin: 'catalog', progress: '0', name: 'Background goal' })];
    renderGoals({ goals });
    await screen.findByText('Browse bonus challenges');
    expect(screen.queryByRole('article', { name: 'Background goal' })).not.toBeInTheDocument();
    act(() => {
      goals[0] = { ...goals[0], progress: '1' };
      window.dispatchEvent(new Event('abby:challenges-changed'));
    });
    const preview = await screen.findByRole('region', { name: 'Bonus progress' });
    expect(within(preview).getByRole('article', { name: 'Background goal' })).toBeInTheDocument();
    expect(within(preview).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
  });

  it('shows all matching goals without start gating and opens full details', async () => {
    const { user } = renderGoals({ goals: [buildChallengeGoal(), buildChallengeGoal({ id: 'goal:12', name: 'Help at home', unit: 'actions', metric: 'count' })] });
    expect((await screen.findAllByRole('heading', { name: 'Challenges' })).length).toBeGreaterThan(0);
    expect(await screen.findByRole('article', { name: 'Help at home' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /start challenge/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'View Run 2 miles this week' }));
    const detail = await screen.findByRole('dialog', { name: 'Run 2 miles this week' });
    expect(within(detail).getByRole('heading', { name: 'What counts' })).toBeInTheDocument();
    expect(within(detail).getByText('Make time to move.')).toBeInTheDocument();
    expect(within(detail).getByRole('button', { name: 'Log a run' })).toBeInTheDocument();
    expect(within(detail).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0.75');
  });

  it('pins a goal using its exact occurrence identity and unpins after confirmation', async () => {
    const { user, setPin } = renderGoals();
    const pin = spyHandler('post', /\/api\/challenges\/goal:11\/pin\/$/, () => { setPin('goal:11'); return { pin: 'goal:11' }; });
    const clear = spyHandler('delete', /\/api\/challenges\/goal:11\/pin\/$/, () => { setPin(null); return { pin: null }; });
    server.use(pin.handler, clear.handler);
    await user.click(await screen.findByRole('button', { name: 'Pin to Today' }));
    await waitFor(() => expect(pin.calls).toHaveLength(1));
    expect(pin.calls[0].body).toEqual({});
    const unpin = await screen.findByRole('button', { name: 'Unpin' });
    expect(unpin).toHaveAttribute('aria-pressed', 'true');
    await user.click(unpin);
    await waitFor(() => expect(clear.calls).toHaveLength(1));
    expect(await screen.findByRole('button', { name: 'Pin to Today' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps the existing pin when replacement fails and shows the server error', async () => {
    const { user } = renderGoals({ pin: 'goal:11', goals: [buildChallengeGoal(), buildChallengeGoal({ id: 'goal:12', name: 'Other goal' })] });
    server.use(http.post('*/api/challenges/goal:12/pin/', () => HttpResponse.json({ error: 'Please try again.' }, { status: 503 })));
    await user.click(await screen.findByRole('button', { name: 'Pin to Today' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Please try again.');
    expect(screen.getByRole('button', { name: 'Unpin' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens a goal from saved header links and closes its detail', async () => {
    const { user } = renderGoals({ route: '/quests?tab=trials&goal=goal%3A11' });
    const dialog = await screen.findByRole('dialog', { name: 'Run 2 miles this week' });
    await user.click(within(dialog).getByRole('button', { name: /close/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('opens a zero-progress bonus from a saved link and retains its full bonus period', async () => {
    const { user } = renderGoals({
      goals: [buildChallengeGoal({ origin: 'catalog', progress: '0', timezone: 'America/Phoenix' })],
      route: '/quests?tab=trials&goal=goal%3A11',
    });
    const dialog = await screen.findByRole('dialog', { name: 'Run 2 miles this week' });
    expect(within(dialog).getByText(/Goal period/)).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    expect(within(dialog).getByRole('heading', { name: 'What counts' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Browse bonus challenges')).toHaveFocus());
  });

  it('restores focus after unpinning moves a zero-progress bonus back into browsing', async () => {
    const goal = buildChallengeGoal({ origin: 'catalog', progress: '0' });
    const { user, setPin } = renderGoals({ goals: [goal], pin: goal.id });
    const clear = spyHandler('delete', /\/api\/challenges\/goal:11\/pin\/$/, () => { setPin(null); return { pin: null }; });
    server.use(clear.handler);
    await user.click(await screen.findByRole('button', { name: `View ${goal.name}` }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Unpin' }));
    await waitFor(() => expect(clear.calls).toHaveLength(1));
    expect(clear.calls[0].url).toMatch(/\/api\/challenges\/goal:11\/pin\/$/);
    expect(clear.calls[0].body).toBeNull();
    await screen.findByRole('dialog', { name: goal.name });
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Browse bonus challenges')).toHaveFocus());
    await user.click(screen.getByText('Browse bonus challenges'));
    expect(await screen.findByRole('progressbar', { name: `${goal.name} progress` })).toHaveAttribute('aria-valuenow', '0');
  });

  it('preserves scroll deep links without starting or spending inventory', async () => {
    const start = spyHandler('post', /\/api\/quests\/start\/$/, {});
    server.use(start.handler);
    renderGoals({ route: '/quests?tab=trials&scroll=42' });
    expect(await screen.findByText(/Your saved scroll stays in Inventory/)).toBeInTheDocument();
    expect(start.calls).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /start/i })).not.toBeInTheDocument();
  });

  it('shows parent child selection and authoring while hiding self pin controls', async () => {
    renderGoals({ role: 'parent' });
    expect(await screen.findByRole('button', { name: 'Create challenge' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Viewing' })).toHaveValue('7');
    expect(screen.queryByRole('button', { name: 'Pin to Today' })).not.toBeInTheDocument();
  });


  it('opens the exact movement logging shortcut from the goal details', async () => {
    const { user } = renderGoals();
    await user.click(await screen.findByRole('button', { name: 'View Run 2 miles this week' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Log a run' }));
    expect(screen.getByTestId('challenge-location')).toHaveTextContent('/quests?tab=movement&log=1&movement_type=3');
  });

  it('shows a saved future challenge as Upcoming without pinning or starting it', async () => {
    renderGoals({ goals: [buildChallengeGoal({ status: 'upcoming', starts_at: '2026-10-16T07:00:00Z', timezone: 'America/Phoenix' })] });
    const upcoming = await screen.findByRole('region', { name: 'Upcoming challenges' });
    expect(within(upcoming).getByText('Upcoming')).toBeInTheDocument();
    expect(within(upcoming).getByText(/Goal period/)).toHaveTextContent('Goal period Oct 16, 2026 – Oct 18, 2026');
    expect(within(upcoming).queryByRole('button', { name: /pin/i })).not.toBeInTheDocument();
  });

  it('keeps legacy shared contributions and the boss shield readable in details', async () => {
    const { user } = renderGoals({ goals: [buildChallengeGoal({ legacy: true, rage_shield: 15, unit: 'damage', participants: [{ user: 7, user_name: 'Abby', contribution: 30 }, { user: 8, user_name: 'Beck', contribution: 15 }] })] });
    await user.click(await screen.findByRole('button', { name: 'View Run 2 miles this week' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Abby · 30 damage')).toBeInTheDocument();
    expect(within(dialog).getByText(/Boss shield adds 15 damage/)).toBeInTheDocument();
  });


  it('defaults authoring to the viewed child and shows a new goal when assigning another child', async () => {
    let created = null;
    const goal = buildChallengeGoal({ id: 'goal:88', name: 'Abby chores', metric: 'count', unit: 'actions' });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7, display_name: 'Abby' }), buildUser({ id: 8, display_name: 'Beck' })])),
      http.get('*/api/challenges/', ({ request }) => HttpResponse.json({
        results: created && new URL(request.url).searchParams.get('user_id') === String(created.user_id) ? [goal] : [], pin: null, daily_bonus: null,
      })),
    );
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, ({ body }) => { created = body; return goal; });
    server.use(create.handler);
    const { user } = renderWithProviders(<Trials />, { route: '/quests?tab=trials' });
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Viewing' }), '8');
    await user.click(await screen.findByRole('button', { name: 'Create challenge' }));
    const form = screen.getByRole('dialog', { name: 'Create a challenge' });
    expect(within(form).getByLabelText('Child')).toHaveValue('8');
    await selectDropdown(user, within(form).getByLabelText('Child'), '7');
    await user.click(within(form).getByRole('button', { name: 'Create challenge' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body.user_id).toBe(7);
    const details = await screen.findByRole('dialog', { name: 'Abby chores' });
    expect(screen.getByRole('combobox', { name: 'Viewing' })).toHaveValue('7');
    expect(within(details).getByRole('heading', { name: 'What counts' })).toBeInTheDocument();
  });

  it('preserves the current child view and authoring draft on an uncertain creation conflict', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7, display_name: 'Abby' }), buildUser({ id: 8, display_name: 'Beck' })])),
    );
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, () => HttpResponse.json({ error: 'request_id was already used for different goal details' }, { status: 409 }));
    server.use(create.handler);
    const { user } = renderWithProviders(<Trials />, { route: '/quests?tab=trials' });
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Viewing' }), '8');
    await user.click(await screen.findByRole('button', { name: 'Create challenge' }));
    const form = screen.getByRole('dialog', { name: 'Create a challenge' });
    await selectDropdown(user, within(form).getByLabelText('Child'), '7');
    await user.click(within(form).getByRole('button', { name: 'Create challenge' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This challenge was already saved with different details.');
    expect(screen.getByRole('combobox', { name: 'Viewing' })).toHaveValue('8');
    expect(within(screen.getByRole('dialog')).getByLabelText('Child')).toHaveValue('7');
    expect(within(screen.getByRole('dialog')).getByLabelText('Target')).toHaveValue(2);
  });

  it('keeps ended goals in history without pin actions', async () => {
    const { user } = renderGoals({ goals: [buildChallengeGoal({ status: 'completed', progress: '2.00' })] });
    await screen.findAllByRole('heading', { name: 'Challenges' });
    await user.click(await screen.findByText('History · 1'));
    expect(await screen.findByText('Bonus earned automatically · 10 coins')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pin to today/i })).not.toBeInTheDocument();
  });
});
