import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderWithProviders, screen } from '../test/render';
import ChallengeGoalCard, { ChallengeGoalDetail } from '../pages/trials/ChallengeGoalCard';
import createdGoal from '../../../contracts/api/fixtures/challenge-goal-created.json';
import initialGoals from '../../../contracts/api/fixtures/challenges-initial.json';
import goalOrigins from '../../../contracts/api/fixtures/challenges-origins.json';
import partialGoals from '../../../contracts/api/fixtures/challenges-partial.json';
import completedGoals from '../../../contracts/api/fixtures/challenges-completed.json';
import boostedGoals from '../../../contracts/api/fixtures/challenges-boosted.json';
import deliveredItems from '../../../contracts/api/fixtures/challenges-items-delivered.json';
import retiredPromisedItems from '../../../contracts/api/fixtures/challenges-items-promised-retired.json';
import skippedItems from '../../../contracts/api/fixtures/challenges-items-skipped.json';
import convertedItems from '../../../contracts/api/fixtures/challenges-items-converted.json';
import pinnedGoal from '../../../contracts/api/fixtures/challenge-pinned.json';
import unpinnedGoal from '../../../contracts/api/fixtures/challenge-unpinned.json';
import firstRun from '../../../contracts/api/fixtures/challenge-run-first.json';
import completedRun from '../../../contracts/api/fixtures/challenge-run-completed.json';
import invalidGoal from '../../../contracts/api/fixtures/challenge-goal-invalid.json';
import promisedQuest from '../../../contracts/api/fixtures/quest-promised-item-active.json';
import promisedQuestHistory from '../../../contracts/api/fixtures/quest-promised-item-history.json';
import legacyPromisedItems from '../../../contracts/api/fixtures/challenges-legacy-promised-item.json';
import readingGoal from '../../../contracts/api/fixtures/challenge-reading-goal-created.json';
import readingThreshold from '../../../contracts/api/fixtures/challenge-reading-threshold-session.json';
import readingCompleted from '../../../contracts/api/fixtures/challenges-reading-completed.json';
import openedDetails from '../../../contracts/api/fixtures/challenge-details-opened.json';
import discoveryObserved from '../../../contracts/api/fixtures/challenge-discovery-observed.json';
import familyAssigned from '../../../contracts/api/fixtures/challenge-family-assigned.json';
import familyCompleted from '../../../contracts/api/fixtures/challenges-family-completed.json';
import retriedGoal from '../../../contracts/api/fixtures/challenge-retried.json';
import retryCompleted from '../../../contracts/api/fixtures/challenges-retry-completed.json';
import retryUnavailable from '../../../contracts/api/fixtures/challenges-retry-reward-unavailable.json';
import retryUnavailableError from '../../../contracts/api/fixtures/challenge-retry-reward-unavailable.json';
import pausedSchedule from '../../../contracts/api/fixtures/challenge-schedule-paused.json';
import editedSchedule from '../../../contracts/api/fixtures/challenge-schedule-edited.json';
import scheduledWeek from '../../../contracts/api/fixtures/challenges-scheduled-week.json';
import milestoneLocked from '../../../contracts/api/fixtures/challenges-milestone-locked.json';
import milestoneReady from '../../../contracts/api/fixtures/challenges-milestone-ready.json';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import {
  createChallengeGoal, createReadingSession, getActiveQuest, getChallenges, getQuestHistory, logMovementSession, pinChallenge, unpinChallenge,
  recordChallengeOpening, getChallengeDiscovery, getQuestCatalog, startCoOpQuest,
  retryChallenge, updateChallengeSchedule,
} from './index';

describe('automatic challenge responses through the shared React API client', () => {
  it.each(['card', 'detail'])('explains the actual unavailable reward response and blocks retry in the %s', async (surface) => {
    server.use(http.get('*/api/challenges/', () => HttpResponse.json(retryUnavailable)));
    const saved = await getChallenges();
    const goal = saved.results.find((row) => row.retry?.reason === 'reward_unavailable');
    expect(goal).toMatchObject({ status: 'expired', retry: { allowed: false, reason: 'reward_unavailable' } });
    expect(goal.rewards.items[0].item_catalog_available).toBe(false);
    const retry = spyHandler('post', /\/api\/challenges\/goal(?:%3A|:)1\/retry\/$/, () => HttpResponse.json(retryUnavailableError, { status: 409 }));
    server.use(retry.handler);
    const onRetry = () => retryChallenge(goal.id);
    const { user } = renderWithProviders(createElement(surface === 'card' ? ChallengeGoalCard : ChallengeGoalDetail,
      { goal, onSelect: () => {}, onClose: () => {}, onRetry }), { withAuth: false });
    expect(screen.getByText("A new attempt can't start while this challenge's reward is unavailable.")).toBeInTheDocument();
    const blocked = screen.getByRole('button', { name: `Try ${goal.name} again` });
    expect(blocked).toBeDisabled();
    await user.click(blocked);
    expect(retry.calls).toHaveLength(0);
  });

  it('preserves the actual reward-unavailable rejection for readable retry feedback', async () => {
    const retry = spyHandler('post', /\/api\/challenges\/goal(?:%3A|:)1\/retry\/$/, () => HttpResponse.json(retryUnavailableError, { status: 409 }));
    server.use(retry.handler);
    await expect(retryChallenge('goal:1')).rejects.toMatchObject({ status: 409, response: retryUnavailableError });
    expect(retry.calls).toHaveLength(1);
    expect(retry.calls[0].body).toEqual({});
  });

  it('opens a fresh catalog attempt and keeps one actual award separate from closed unpaid history', async () => {
    const retry = spyHandler('post', /\/api\/challenges\/goal(?:%3A|:)1\/retry\/$/, retriedGoal);
    server.use(
      retry.handler,
      http.get('*/api/challenges/', () => HttpResponse.json(retryCompleted)),
    );
    expect(await retryChallenge('goal:1')).toEqual(retriedGoal);
    expect(retry.calls).toEqual([{
      method: 'POST', url: expect.stringMatching(/\/api\/challenges\/goal(?:%3A|:)1\/retry\/$/), body: {},
    }]);
    expect(retriedGoal).toMatchObject({ retry_of: 'goal:1', status: 'active', progress: '0', origin: 'catalog' });
    expect(retriedGoal.qualifying_triggers).toEqual(['movement_session']);
    const saved = await getChallenges();
    expect(saved).toEqual(retryCompleted);
    const paid = saved.results.find((row) => row.id === retriedGoal.id);
    expect(paid).toMatchObject({
      status: 'completed', progress: '2', retry: { allowed: false },
      reward_receipt: { status: 'awarded', coins_awarded: 5, xp_awarded: 10 },
    });
    const closed = saved.results.find((row) => row.id === 'goal:1');
    expect(closed).toMatchObject({
      status: 'closed', closed_reason: expect.any(String),
      reward_receipt: { status: 'pending', awarded_at: null, coins_awarded: 0, xp_awarded: 0 },
    });
  });

  it('sends versioned parent schedule changes and reads the next accepted weekly promise', async () => {
    const writes = [];
    server.use(
      http.patch(`*/api/challenges/goals/${createdGoal.goal_definition_id}/schedule/`, async ({ request }) => {
        writes.push(await request.json());
        return HttpResponse.json(writes.length === 1 ? pausedSchedule : editedSchedule);
      }),
      http.get('*/api/challenges/', () => HttpResponse.json(scheduledWeek)),
    );
    const pause = { expected_revision: createdGoal.schedule.revision, paused: true };
    expect(await updateChallengeSchedule(createdGoal.goal_definition_id, pause)).toEqual(pausedSchedule);
    expect(pausedSchedule.schedule.next_week.paused).toBe(true);
    const edit = {
      expected_revision: pausedSchedule.schedule.revision, paused: false,
      next_week: { name: 'Run four miles next week', target: '4', coin_reward: 11 },
    };
    expect(await updateChallengeSchedule(createdGoal.goal_definition_id, edit)).toEqual(editedSchedule);
    expect(editedSchedule.schedule.paused).toBe(true);
    expect(editedSchedule.schedule.next_week).toMatchObject({ paused: false, target: '4', coin_reward: 11 });
    expect(writes).toEqual([pause, edit]);
    const saved = await getChallenges(7);
    expect(saved).toEqual(scheduledWeek);
    const active = saved.results.find((row) => row.origin === 'parent' && row.status === 'active');
    expect(active).toMatchObject({
      goal_definition_id: createdGoal.goal_definition_id, name: 'Run four miles next week',
      target: '4', progress: '0', rewards: { coins: 11, xp: 15 },
      qualifying_triggers: ['movement_session'],
    });
    const original = saved.results.find((row) => row.id === createdGoal.id);
    expect(original).toMatchObject({ name: createdGoal.name, target: createdGoal.target, rewards: createdGoal.rewards });
  });

  it('assigns a parent-selected family catalog goal and preserves the completed pooled contributions', async () => {
    const assign = spyHandler('post', /\/api\/quests\/52\/co-op\/$/, familyAssigned);
    const selectedChildren = [];
    server.use(
      // The producer verifies this exact nested definition equals the real
      // parent catalog row before accepting the shared assignment.
      http.get('*/api/quests/catalog/', () => HttpResponse.json([familyAssigned.definition])),
      assign.handler,
      http.get('*/api/challenges/', ({ request }) => {
        selectedChildren.push(new URL(request.url).searchParams.get('user_id'));
        return HttpResponse.json(familyCompleted);
      }),
    );
    const catalog = await getQuestCatalog();
    expect(catalog).toEqual([familyAssigned.definition]);
    expect(catalog[0]).toMatchObject({ id: 52, is_cooperative: true, catalog_available: true, target_value: 20 });
    const assigned = await startCoOpQuest(catalog[0].id, [7, 8]);
    expect(assigned).toEqual(familyAssigned);
    expect(assigned.participants.map(({ user, contribution }) => ({ user, contribution }))).toEqual([
      { user: 7, contribution: 0 }, { user: 8, contribution: 0 },
    ]);
    expect(assign.calls).toEqual([{ url: expect.stringMatching(/\/api\/quests\/52\/co-op\/$/), method: 'POST', body: { user_ids: [7, 8] } }]);
    const saved = await getChallenges(7);
    expect(selectedChildren).toEqual(['7']);
    expect(saved).toEqual(familyCompleted);
    expect(saved.results).toHaveLength(1);
    expect(saved.results[0]).toMatchObject({
      id: `legacy:${assigned.id}`, origin: 'legacy', legacy: true,
      progress: '20', target: '20', status: 'completed',
      rewards: { coins: 100, xp: 30, items: [] },
      participants: [
        { user: 7, contribution: 10 }, { user: 8, contribution: 10 },
      ],
    });
    // Legacy history exposes an unavailable receipt, rather than inventing
    // paid amounts. The producer checks both participants' actual ledgers.
    expect(saved.results[0].reward_receipt).toEqual({
      id: `legacy:${assigned.id}`, status: 'legacy', coins_awarded: 0, xp_awarded: 0, awarded_at: null,
    });
  });

  it.each([
    ['locked', milestoneLocked, false], ['ready for a new qualifying activity', milestoneReady, true],
  ])('preserves the %s milestone catalog independently of accepted personal goals', async (_label, body, unlocked) => {
    const calls = [];
    server.use(http.all('*/api/challenges/', ({ request }) => {
      calls.push({ method: request.method, authorization: request.headers.get('Authorization') });
      return HttpResponse.json(body);
    }));
    const response = await getChallenges();
    expect(response).toEqual(body);
    expect(calls).toEqual([{ method: 'GET', authorization: 'Token test-session' }]);
    const voyager = response.locked_catalog.find((definition) => definition.name === 'Reading Voyager');
    expect(voyager).toMatchObject({
      id: 53, duration_days: 56, target_value: 20,
      prerequisite_quest: 52, prerequisite_quest_name: 'Reading Companion',
      required_skill: 24, required_skill_name: 'Reading Comprehension', required_skill_level: 1,
      milestone_eligibility: { unlocked, requirements: [
        { kind: 'challenge', met: unlocked, description: expect.any(String) },
        { kind: 'skill', met: unlocked, description: expect.any(String) },
      ] },
    });
    for (const field of ['starts_at', 'expires_at', 'progress', 'reward_receipt', 'pinned']) expect(voyager).not.toHaveProperty(field);
    expect(response.results).toEqual(body.results);
    expect(response.recent_receipts).toEqual(body.recent_receipts);
  });

  it('preserves daily Reading Adventure rules and the goal receipt after the real reading threshold', async () => {
    const writes = [];
    const payload = {
      request_id: '44444444-4444-4444-8444-444444444444',
      user_id: 7, name: 'One Reading Adventure', trigger_type: 'reading_logged',
      metric: 'count', target: '1', unit: 'actions', period: 'from_today', coin_reward: 0, xp_reward: 0,
    };
    const sessionPayload = {
      book: 101, duration_minutes: 6, format: 'audiobook',
      client_request_id: '99999999-9999-4999-8999-999999999999',
    };
    const capture = (body, status) => async ({ request }) => {
      writes.push({ path: new URL(request.url).pathname, body: await request.json() });
      return HttpResponse.json(body, { status });
    };
    server.use(
      http.post('*/api/challenges/goals/', capture(readingGoal, 201)),
      http.post('*/api/reading-sessions/', capture(readingThreshold, 201)),
      http.get('*/api/challenges/', () => HttpResponse.json(readingCompleted)),
    );
    expect(await createChallengeGoal(payload)).toEqual(readingGoal);
    expect(readingGoal).toMatchObject({
      metric: 'count', progress: '0', target: '1', origin: 'parent',
      action: { label: 'Read for ten minutes', path: '/quests?tab=reading' },
    });
    expect(readingGoal.what_counts).toMatch(/once per day/);
    const savedSession = await createReadingSession(sessionPayload);
    expect(savedSession.reading_reward).toEqual({ day: '2026-10-14', coins_awarded: 5, xp_awarded: 15 });
    const goals = await getChallenges();
    expect(goals).toEqual(readingCompleted);
    expect(goals.results[0]).toMatchObject({
      id: readingGoal.id, progress: '1', status: 'completed',
      reward_receipt: { status: 'awarded', coins_awarded: 0, xp_awarded: 0, items: [] },
    });
    expect(goals.daily_bonus.awarded).toBe(false);
    expect(writes).toEqual([
      { path: '/api/challenges/goals/', body: payload },
      { path: '/api/reading-sessions/', body: sessionPayload },
    ]);
  });

  it('records only a self details opening and reads bounded household discovery separately from completion', async () => {
    const requests = [];
    server.use(
      http.post(`*/api/challenges/${encodeURIComponent(openedDetails.id)}/opened/`, async ({ request }) => {
        requests.push(await request.json());
        return HttpResponse.json(openedDetails);
      }),
      http.get('*/api/challenges/discovery/', () => HttpResponse.json(discoveryObserved)),
    );
    expect(await recordChallengeOpening(openedDetails.id)).toEqual(openedDetails);
    expect(requests).toEqual([{}]);
    expect(await getChallengeDiscovery()).toEqual(discoveryObserved);
    expect(discoveryObserved.catalog_occurrences).toMatchObject({
      cohort_materialized: 2, opened: 1, completed: 2, completed_without_recorded_opening: 1,
    });
    expect(discoveryObserved.cohort).toMatchObject({ tracked_children: 1, untracked_children: 1 });
  });

  it('creates a weekly distance goal with its exact activity rule and unpaid reward preview', async () => {
    const submitted = [];
    const payload = {
      request_id: '33333333-3333-4333-8333-333333333333',
      user_id: 7, name: 'Run 2 miles this week', trigger_type: 'movement_session',
      movement_type_id: 31, metric: 'distance', target: '2', unit: 'mi',
      period: 'this_week', repeat_weekly: true, coin_reward: 7, xp_reward: 15,
      skill_tags: [{ skill_id: 22, xp_weight: 1 }],
    };
    server.use(http.post('*/api/challenges/goals/', async ({ request }) => {
      submitted.push({ body: await request.json(), authorization: request.headers.get('Authorization') });
      return HttpResponse.json(createdGoal, { status: 201 });
    }));
    const goal = await createChallengeGoal(payload);
    expect(goal).toEqual(createdGoal);
    expect(goal).toMatchObject({
      origin: 'parent', catalog_icon: null,
      metric: 'distance', target: '2', progress: '0', unit: 'mi', repeat_weekly: true,
      action: { label: 'Log movement', movement_type_id: 31 },
      reward_receipt: { status: 'pending', coins_awarded: 0, xp_awarded: 0, awarded_at: null },
    });
    expect(submitted).toEqual([{ body: payload, authorization: 'Token test-session' }]);
    expect(goal.reward_receipt).not.toHaveProperty('items');
  });

  it.each([
    ['initial', initialGoals], ['partial', partialGoals], ['completed', completedGoals], ['boosted', boostedGoals],
  ])('reads %s goals with decimal measurements, pin identity and actual receipts intact', async (_label, body) => {
    const calls = [];
    server.use(http.all('*/api/challenges/', ({ request }) => {
      calls.push({ method: request.method, userId: new URL(request.url).searchParams.get('user_id') });
      return HttpResponse.json(body);
    }));
    expect(await getChallenges()).toEqual(body);
    expect(await getChallenges(7)).toEqual(body);
    expect(calls).toEqual([{ method: 'GET', userId: null }, { method: 'GET', userId: '7' }]);
    for (const goal of [...body.results, ...body.recent_receipts]) {
      expect(['parent', 'catalog', 'legacy']).toContain(goal.origin);
      expect(typeof goal.target).toBe('string');
      expect(typeof goal.progress).toBe('string');
      expect(goal.reward_receipt.id).toBe(goal.id);
    }
  });

  it('preserves distinct server origins for equally named parent, retired catalog and legacy goals', async () => {
    server.use(http.get('*/api/challenges/', () => HttpResponse.json(goalOrigins)));
    const saved = await getChallenges();
    expect(saved).toEqual(goalOrigins);
    expect(new Set(saved.results.map((goal) => goal.name)).size).toBe(1);
    expect(Object.fromEntries(saved.results.map((goal) => [goal.id, goal.origin]))).toEqual({
      'goal:1': 'parent', 'goal:2': 'catalog', 'legacy:91': 'legacy',
    });
    expect(saved.results.find((goal) => goal.origin === 'legacy')).toMatchObject({ legacy: true });
    expect(saved.results.filter((goal) => goal.origin !== 'legacy').every((goal) => !goal.legacy)).toBe(true);
  });

  it('keeps a boosted daily paid amount separate from the unchanged goal reward', async () => {
    server.use(http.get('*/api/challenges/', () => HttpResponse.json(boostedGoals)));
    const goals = await getChallenges();
    const runningGoal = goals.results.find((goal) => goal.metric === 'distance');
    expect(runningGoal.rewards.coins).toBe(7);
    expect(runningGoal.reward_receipt).toMatchObject({ status: 'awarded', coins_awarded: 7 });
    expect(goals.daily_bonus).toMatchObject({ coin_reward: 10, coins_awarded: 20, awarded: true });
  });

  it('preserves newest-first activity and completion receipts when server timestamps tie', async () => {
    server.use(http.get('*/api/challenges/', () => HttpResponse.json(completedGoals)));
    const saved = await getChallenges();
    expect(saved.challenge_receipts.map((row) => row.id)).toEqual(['activity:2', 'activity:1']);
    expect(saved.challenge_receipts[0].daily_bonus).toBeNull();
    expect(saved.challenge_receipts[1].daily_bonus.awarded).toBe(true);
    expect(saved.recent_receipts.map((row) => row.id)).toEqual(['goal:2', 'goal:1']);
  });

  it.each([
    ['delivered', deliveredItems, [{ item_name: 'Fixture frame', item_catalog_icon: null, quantity: 1 }], 5],
    ['promised before retirement', retiredPromisedItems, [{ item_name: 'Fixture Wolf Egg', item_catalog_icon: null, quantity: 1 }], 5],
    ['unavailable before acceptance', skippedItems, [], 5],
    ['converted', convertedItems, [{ item_name: 'Fixture Wolf Egg', item_catalog_icon: null, quantity: 1, salvaged_to_coins: 25 }], 30],
  ])('preserves recorded %s item outcomes independently of reward previews', async (_label, body, items, coins) => {
    server.use(http.get('*/api/challenges/', () => HttpResponse.json(body)));
    const saved = await getChallenges();
    expect(saved).toEqual(body);
    expect(saved.results[0].reward_receipt).toMatchObject({ status: 'awarded', items, coins_awarded: coins });
    const receivedItems = saved.recent_receipts[0].reward_receipt.items;
    expect(receivedItems).toHaveLength(items.length);
    expect(receivedItems).toMatchObject(items);
    for (const item of receivedItems) {
      expect(item).toMatchObject({ item_id: expect.any(Number), item_rarity: 'common', item_effect_summary: expect.any(String) });
      expect(item.item_catalog_available).toBe(_label !== 'promised before retirement');
    }
  });

  it('keeps an accepted legacy item promise visible through active quest, challenge and completed history reads', async () => {
    server.use(
      http.get('*/api/quests/active/', () => HttpResponse.json(promisedQuest)),
      http.get('*/api/quests/history/', () => HttpResponse.json(promisedQuestHistory)),
      http.get('*/api/challenges/', () => HttpResponse.json(legacyPromisedItems)),
    );
    const active = await getActiveQuest();
    expect(active).toEqual(promisedQuest);
    expect(active.definition.reward_items).toMatchObject([{ item: 63, item_name: 'Fixture Wolf Egg', quantity: 2 }]);
    const goals = await getChallenges();
    expect(goals).toEqual(legacyPromisedItems);
    const legacy = goals.results.find((goal) => goal.origin === 'legacy');
    expect(legacy.rewards.items).toEqual(active.definition.reward_items);
    const history = await getQuestHistory();
    expect(history).toEqual(promisedQuestHistory);
    expect(history[0]).toMatchObject({ id: active.id, status: 'completed' });
    expect(history[0].definition.reward_items).toEqual(active.definition.reward_items);
  });

  it('pins and unpins presentation with one POST or DELETE and the server pin receipt', async () => {
    const calls = [];
    server.use(http.all(`*/api/challenges/${createdGoal.id}/pin/`, async ({ request }) => {
      const body = await request.text();
      calls.push({ method: request.method, body });
      return HttpResponse.json(request.method === 'POST' ? pinnedGoal : unpinnedGoal);
    }));
    expect(await pinChallenge(createdGoal.id)).toEqual(pinnedGoal);
    expect(await unpinChallenge(createdGoal.id)).toEqual(unpinnedGoal);
    expect(calls).toEqual([{ method: 'POST', body: '{}' }, { method: 'DELETE', body: '' }]);
  });

  it.each([
    ['first run', '0.75', firstRun], ['completing run', '1.25', completedRun],
  ])('logs the %s with measured distance and preserves all goal progress receipts', async (_label, distance, response) => {
    const submitted = [];
    const payload = {
      movement_type_id: 31, duration_minutes: 20, distance, distance_unit: 'mi', notes: 'A fixture run.',
      client_request_id: response.client_request_id,
    };
    server.use(http.post('*/api/movement-sessions/', async ({ request }) => {
      submitted.push(await request.json());
      return HttpResponse.json(response, { status: 201 });
    }));
    const saved = await logMovementSession(payload);
    expect(saved).toEqual(response);
    expect(saved.distance).toBe(distance);
    expect(saved.distance_unit).toBe('mi');
    expect(saved.challenge_receipts).toHaveLength(1);
    expect(saved.challenge_receipts[0].goals).toHaveLength(2);
    expect(saved.challenge_receipts[0].goals.map((receipt) => receipt.id)).toEqual(['goal:1', 'goal:2']);
    expect(saved.challenge_receipts[0].goals.map((receipt) => receipt.id).sort())
      .toEqual(completedGoals.results.map((goal) => goal.id).sort());
    expect(submitted).toEqual([payload]);
  });

  it('preserves field validation errors and never retries a rejected goal creation', async () => {
    let calls = 0;
    server.use(http.post('*/api/challenges/goals/', () => {
      calls += 1;
      return HttpResponse.json(invalidGoal, { status: 400 });
    }));
    await expect(createChallengeGoal({ target: '0' })).rejects.toMatchObject({ status: 400, response: invalidGoal });
    expect(invalidGoal.target).toBeInstanceOf(Array);
    expect(calls).toBe(1);
  });
});
