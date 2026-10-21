import { selectDropdown } from '../../test/selectDropdown';
import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within, waitFor, act } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import retryUnavailableError from '../../../../contracts/api/fixtures/challenge-retry-reward-unavailable.json';
import { buildParent, buildUser } from '../../test/factories';
import { buildChallengeGoal, buildDailyBonus } from '../../test/challenges';
import { CHALLENGES_CHANGED } from '../../hooks/useChallenges';
import Trials from './index';
import { useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
function LocationProbe() { const location = useLocation(); return <span data-testid="challenge-location">{location.pathname}{location.search}</span>; }

function renderGoals({ goals = [buildChallengeGoal()], lockedCatalog = [], pin = null, role = 'child', route = '/quests?tab=trials' } = {}) {
  let savedPin = pin;
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(role === 'parent' ? buildParent() : buildUser())),
    http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7, display_name: 'Abby' })])),
    http.get('*/api/challenges/', () => HttpResponse.json({ results: goals.map((goal) => ({ ...goal, pinned: goal.id === savedPin })), locked_catalog: lockedCatalog, pin: savedPin, daily_bonus: buildDailyBonus() })),
  );
  return { ...renderWithProviders(<><Trials /><LocationProbe /></>, { route }), setPin: (value) => { savedPin = value; } };
}

describe('Automatic challenges', () => {
  it('keeps a conflicting future-settings draft until a failed refresh can be retried successfully', async () => {
    const next = { starts_at: '2026-10-26T07:00:00Z', paused: false, name: 'Weekly running', description: '', metric: 'distance', target: '2', unit: 'mi', trigger_type: 'movement_session', movement_type_id: 3, coin_reward: 10, xp_reward: 0, skill_tags: [] };
    const goal = buildChallengeGoal({ name: 'Weekly running', goal_definition_id: 21, repeat_weekly: true, timezone: 'America/Phoenix', schedule: { revision: 0, paused: false, next_week: next } });
    let reads = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7 })])),
      http.get('*/api/challenges/', () => ++reads === 1
        ? HttpResponse.json({ results: [goal], pin: null, daily_bonus: null })
        : HttpResponse.json({ error: 'Refresh unavailable.' }, { status: 503 })),
    );
    const conflict = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, () => HttpResponse.json({ error: 'Saved revision changed.' }, { status: 409 }));
    server.use(conflict.handler);
    const { user } = renderWithProviders(<Trials />, { route: '/quests?tab=trials&child=7' });
    await user.click(await screen.findByRole('button', { name: 'View Weekly running' }));
    await user.click(screen.getByRole('button', { name: 'Change future weeks' }));
    const dialog = screen.getByRole('dialog', { name: 'Change future weeks' });
    const target = within(dialog).getByLabelText('Future target (miles)');
    await user.clear(target); await user.type(target, '3');
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    await screen.findByText('Refresh unavailable.');
    const load = await within(dialog).findByRole('button', { name: 'Load saved future settings' });
    await user.click(load);
    expect(target).toHaveValue(3);
    expect(load).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Save future weeks' })).toBeDisabled();
    expect(conflict.calls).toHaveLength(1);

    const current = { ...goal, schedule: { revision: 2, paused: false, next_week: { ...next, target: '4' } } };
    const refresh = spyHandler('get', /\/api\/challenges\/$/, { results: [current], pin: null, daily_bonus: null });
    server.use(refresh.handler);
    await user.click(within(dialog).getByRole('button', { name: 'Retry saved future settings' }));
    await waitFor(() => expect(load).toBeEnabled());
    expect(refresh.calls).toHaveLength(1);
    expect(target).toHaveValue(3);
    await user.click(load);
    expect(target).toHaveValue(4);
    const save = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, { goal_definition_id: 21, schedule: { ...current.schedule, revision: 3 } });
    server.use(save.handler);
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toMatchObject({ expected_revision: 2, next_week: { target: '4' } });
    expect(conflict.calls).toHaveLength(1);
  });

  it('keeps the confirmed successor pin if the retry follow-up read fails', async () => {
    const expired = buildChallengeGoal({ origin: 'catalog', status: 'expired', pinned: true, retry: { allowed: true, reason: null, latest_attempt_id: 'goal:11' } });
    const fresh = buildChallengeGoal({ id: 'goal:12', name: 'Fresh retry', origin: 'catalog', pinned: true, progress: '0', retry: { allowed: false, reason: 'not_expired', latest_attempt_id: 'goal:12' } });
    let reads = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/challenges/', () => ++reads === 1
        ? HttpResponse.json({ results: [expired], pin: expired.id, daily_bonus: null })
        : HttpResponse.json({ error: 'Refresh unavailable.' }, { status: 503 })),
    );
    const retry = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/retry\/$/, fresh);
    server.use(retry.handler);
    const { user } = renderWithProviders(<Trials />, { route: '/quests?tab=trials' });
    await user.click(await screen.findByRole('button', { name: 'Find challenges to try again' }));
    await user.click(screen.getByRole('button', { name: `Try ${expired.name} again` }));
    await screen.findByRole('dialog', { name: fresh.name });
    await screen.findByText('Refresh unavailable.');
    const pinned = document.querySelector('section[aria-label="Pinned challenge"]');
    expect(pinned).not.toBeNull();
    expect(within(pinned).getByRole('article', { name: fresh.name, hidden: true })).toHaveTextContent('Pinned');
    expect(retry.calls).toHaveLength(1);
  });

  it('starts a fresh attempt from retryable history with an exact empty POST and preserves the old period', async () => {
    const expired = buildChallengeGoal({ origin: 'catalog', status: 'expired', catalog_repeatable: false, retry: { allowed: true, reason: null, latest_attempt_id: null } });
    const fresh = buildChallengeGoal({ id: 'goal:12', origin: 'catalog', progress: '0', catalog_repeatable: false, starts_at: '2026-10-20T07:00:00Z', ends_at: '2026-10-27T07:00:00Z', retry: { allowed: false, reason: 'active', latest_attempt_id: null } });
    let retried = false;
    const retry = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/retry\/$/, () => { retried = true; return fresh; });
    server.use(retry.handler);
    const { user } = renderGoals({ goals: [expired] });
    server.use(http.get('*/api/challenges/', () => HttpResponse.json({ results: retried ? [{ ...expired, retry: { allowed: false, reason: 'superseded', latest_attempt_id: fresh.id } }, fresh] : [expired], pin: null, daily_bonus: null })));
    await user.click(await screen.findByText('History · 1'));
    await user.click(screen.getByRole('button', { name: `Try ${expired.name} again` }));
    await waitFor(() => expect(retry.calls).toHaveLength(1));
    expect(retry.calls[0]).toMatchObject({ url: expect.stringMatching(/\/api\/challenges\/goal(?::|%3A)11\/retry\/$/), body: {} });
    const detail = await screen.findByRole('dialog', { name: fresh.name });
    expect(within(detail).getByText('0 / 2 miles')).toBeInTheDocument();
    expect(within(detail).getByText(/Goal period/)).toHaveTextContent('Oct 20, 2026');
    expect(screen.getByText('History · 1')).toBeInTheDocument();
  });

  it('lets a parent pause future weeks without changing the current goal promise', async () => {
    const next_week = { starts_at: '2026-10-26T07:00:00Z', paused: false, name: 'Weekly running', description: 'Make time to move.', metric: 'distance', target: '2', unit: 'mi', trigger_type: 'movement_session', movement_type_id: 3, coin_reward: 10, xp_reward: 0, skill_tags: [] };
    const schedule = { revision: 1, paused: false, next_week };
    const goal = buildChallengeGoal({ name: 'Weekly running', repeat_weekly: true, goal_definition_id: 21, schedule });
    const pause = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, () => {
      goal.schedule = { ...schedule, revision: 2, next_week: { ...next_week, paused: true } };
      return { goal_definition_id: 21, schedule: goal.schedule };
    });
    server.use(pause.handler);
    const { user } = renderGoals({ role: 'parent', goals: [goal] });
    await user.click(await screen.findByRole('button', { name: `View ${goal.name}` }));
    const detail = screen.getByRole('dialog');
    await user.click(within(detail).getByRole('button', { name: 'Pause future weeks' }));
    await waitFor(() => expect(pause.calls).toHaveLength(1));
    expect(pause.calls[0].body).toEqual({ expected_revision: 1, paused: true });
    expect(await within(detail).findByRole('button', { name: 'Resume future weeks' })).toBeInTheDocument();
    expect(within(detail).getByText('0.75 / 2 miles')).toBeInTheDocument();
    expect(within(detail).getByText('Completion bonus · 10 coins')).toBeInTheDocument();
  });

  it('explains a newly unavailable reward and keeps retry disabled when the follow-up read fails', async () => {
    const expired = buildChallengeGoal({ origin: 'catalog', status: 'expired', retry: { allowed: true, reason: null, latest_attempt_id: null } });
    let reads = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/challenges/', () => ++reads === 1
        ? HttpResponse.json({ results: [expired], pin: null, daily_bonus: null })
        : HttpResponse.json({ error: 'Reward status refresh unavailable.' }, { status: 503 })),
    );
    const retry = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/retry\/$/, () => HttpResponse.json(retryUnavailableError, { status: 409 }));
    server.use(retry.handler);
    const { user } = renderWithProviders(<Trials />, { route: '/quests?tab=trials' });
    await user.click(await screen.findByText('History · 1'));
    await user.click(screen.getByRole('button', { name: `Try ${expired.name} again` }));
    const detail = await screen.findByRole('dialog', { name: expired.name });
    expect(await within(detail).findByRole('alert')).toHaveTextContent("A new attempt can't start while this challenge's reward is unavailable.");
    const blocked = within(detail).getByRole('button', { name: `Try ${expired.name} again` });
    expect(blocked).toBeDisabled();
    await screen.findByText('Reward status refresh unavailable.');
    await user.click(blocked);
    expect(retry.calls).toHaveLength(1);
    expect(retry.calls[0].body).toEqual({});
    expect(within(detail).queryByText('reward_unavailable')).not.toBeInTheDocument();
  });

  it('shows a retry failure inside the details and retries only after another explicit click', async () => {
    const expired = buildChallengeGoal({ origin: 'catalog', status: 'expired', retry: { allowed: true, reason: null, latest_attempt_id: null } });
    const retry = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/retry\/$/, () => HttpResponse.json({ error: 'Could not start this period.' }, { status: 503 }));
    server.use(retry.handler);
    const { user } = renderGoals({ goals: [expired] });
    await user.click(await screen.findByRole('button', { name: 'Find challenges to try again' }));
    expect(screen.getByRole('combobox', { name: 'Show history' })).toHaveValue('retryable');
    await user.click(screen.getByRole('button', { name: `Try ${expired.name} again` }));
    const detail = screen.getByRole('dialog');
    expect(await within(detail).findByRole('alert')).toHaveTextContent('Could not start this period.');
    expect(retry.calls).toHaveLength(1);
    expect(within(detail).getByText('0.75 / 2 miles')).toBeInTheDocument();
    await user.click(within(detail).getByRole('button', { name: `Try ${expired.name} again` }));
    await waitFor(() => expect(retry.calls).toHaveLength(2));
    expect(retry.calls.map((call) => call.body)).toEqual([{}, {}]);
  });

  it.each(['child', 'credential'])('ignores a parent retry response after the selected %s changes', async (change) => {
    const expired = buildChallengeGoal({ origin: 'catalog', status: 'expired', retry: { allowed: true, reason: null, latest_attempt_id: null } });
    const other = buildChallengeGoal({ id: 'goal:other', name: 'Other child goal' });
    const fresh = buildChallengeGoal({ id: 'goal:fresh', name: 'Fresh retry window', origin: 'catalog' });
    let finish;
    let changeChild;
    function ChangeChild() {
      const [, setParams] = useSearchParams();
      useEffect(() => { changeChild = () => setParams({ tab: 'trials', child: '8' }); }, [setParams]);
      return null;
    }
    const reads = [];
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7 }), buildUser({ id: 8 })])),
      http.get('*/api/challenges/', ({ request }) => {
        const child = new URL(request.url).searchParams.get('user_id'); reads.push(child);
        return HttpResponse.json({ results: child === '8' ? [other] : [expired], pin: null, daily_bonus: null });
      }),
    );
    const retry = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/retry\/$/, () => new Promise((resolve) => { finish = () => resolve(fresh); }));
    server.use(retry.handler);
    const { user } = renderWithProviders(<><Trials /><ChangeChild /></>, { route: '/quests?tab=trials&child=7' });
    await user.click(await screen.findByRole('button', { name: 'Find challenges to try again' }));
    await user.click(screen.getByRole('button', { name: `Try ${expired.name} again` }));
    await waitFor(() => expect(retry.calls).toHaveLength(1));
    if (change === 'child') {
      act(() => changeChild());
      await screen.findByRole('article', { name: other.name });
    } else localStorage.setItem('abby_auth_token', 'replacement-session');
    const before = reads.length;
    await act(async () => finish());
    expect(reads).toHaveLength(before);
    expect(screen.queryByRole('dialog', { name: fresh.name })).not.toBeInTheDocument();
    expect(screen.queryByRole('article', { name: fresh.name })).not.toBeInTheDocument();
  });

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

  it('shows server-confirmed milestone requirements without creating a goal, timer, opening receipt or pin', async () => {
    const definition = { id: 77, name: 'Reading Voyager', description: 'Complete 20 daily Reading Adventures within 56 days.', duration_days: 56,
      required_skill: 4, required_skill_level: 1, prerequisite_quest: 76,
      milestone_eligibility: { unlocked: false, locked_reasons: ['Complete Reading Companion'], requirements: [
        { kind: 'challenge', met: false, description: 'Complete Reading Companion' },
        { kind: 'skill', met: true, description: 'Reach Reading Comprehension level 1' },
      ] } };
    const writes = spyHandler('post', /\/api\/(?:challenges|quests)\/.*/, {});
    const { user } = renderGoals({ lockedCatalog: [definition] });
    server.use(writes.handler);
    const coming = await screen.findByRole('region', { name: 'Coming next' });
    expect(within(coming).getByText('Reading Voyager')).toBeVisible();
    expect(within(coming).getByText('Locked challenge')).toBeVisible();
    await user.click(within(coming).getByRole('button', { name: 'View requirements for Reading Voyager' }));
    const dialog = await screen.findByRole('dialog', { name: 'Reading Voyager requirements' });
    const requirements = within(within(dialog).getByRole('list', { name: 'Reading Voyager milestone requirements' }));
    expect(requirements.getByText('Complete Reading Companion')).toBeVisible();
    expect(requirements.getByText('Reach Reading Comprehension level 1')).toBeVisible();
    expect(within(dialog).getByText(/56 days after it starts/)).toBeVisible();
    expect(within(dialog).getByText(/No deadline is running yet/)).toBeVisible();
    expect(within(dialog).queryByRole('progressbar')).toBeNull();
    expect(within(dialog).queryByRole('button', { name: /Pin|Start|Begin|Log reading/i })).toBeNull();
    expect(writes.calls).toHaveLength(0);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(within(coming).getByRole('button', { name: 'View requirements for Reading Voyager' })).toHaveFocus();
  });
  it('shows met milestones as ready for the next qualifying activity and removes the catalog row only after a fresh server offer', async () => {
    const definition = { id: 77, name: 'Reading Voyager', description: 'Read on 20 qualifying days.', duration_days: 56,
      milestone_eligibility: { unlocked: true, requirements: [{ kind: 'challenge', met: true, description: 'Complete Reading Companion' }], locked_reasons: [] } };
    const { user } = renderGoals({ lockedCatalog: [definition] });
    const coming = await screen.findByRole('region', { name: 'Coming next' });
    expect(within(coming).getByText('Requirements met')).toBeVisible();
    expect(within(coming).getByText(/next matching saved activity/)).toBeVisible();
    const accepted = buildChallengeGoal({ id: 'goal:77', name: definition.name, origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null, progress: '0', description: definition.description });
    server.use(http.get('*/api/challenges/', () => HttpResponse.json({ results: [accepted], locked_catalog: [], pin: null, daily_bonus: null })));
    server.use(http.post('*/api/challenges/goal:77/opened/', () => HttpResponse.json({ id: accepted.id, first_details_opened_at: '2026-10-20T18:00:00Z' })));
    act(() => window.dispatchEvent(new Event(CHALLENGES_CHANGED)));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Coming next' })).toBeNull());
    await user.click(screen.getByRole('button', { name: `View ${accepted.name}` }));
    expect(within(await screen.findByRole('dialog', { name: accepted.name })).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
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
