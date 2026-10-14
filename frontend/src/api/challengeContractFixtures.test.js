import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import createdGoal from '../../../contracts/api/fixtures/challenge-goal-created.json';
import initialGoals from '../../../contracts/api/fixtures/challenges-initial.json';
import partialGoals from '../../../contracts/api/fixtures/challenges-partial.json';
import completedGoals from '../../../contracts/api/fixtures/challenges-completed.json';
import boostedGoals from '../../../contracts/api/fixtures/challenges-boosted.json';
import deliveredItems from '../../../contracts/api/fixtures/challenges-items-delivered.json';
import skippedItems from '../../../contracts/api/fixtures/challenges-items-skipped.json';
import convertedItems from '../../../contracts/api/fixtures/challenges-items-converted.json';
import pinnedGoal from '../../../contracts/api/fixtures/challenge-pinned.json';
import unpinnedGoal from '../../../contracts/api/fixtures/challenge-unpinned.json';
import firstRun from '../../../contracts/api/fixtures/challenge-run-first.json';
import completedRun from '../../../contracts/api/fixtures/challenge-run-completed.json';
import invalidGoal from '../../../contracts/api/fixtures/challenge-goal-invalid.json';
import { server } from '../test/server';
import {
  createChallengeGoal, getChallenges, logMovementSession, pinChallenge, unpinChallenge,
} from './index';

describe('automatic challenge responses through the shared React API client', () => {
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
    for (const goal of body.results) {
      expect(typeof goal.target).toBe('string');
      expect(typeof goal.progress).toBe('string');
      expect(goal.reward_receipt.id).toBe(goal.id);
    }
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
    ['delivered', deliveredItems, [{ item_name: 'Fixture frame', quantity: 1 }], 5],
    ['skipped', skippedItems, [], 5],
    ['converted', convertedItems, [{ item_name: 'Fixture Wolf Egg', quantity: 1, salvaged_to_coins: 25 }], 30],
  ])('preserves recorded %s item outcomes independently of reward previews', async (_label, body, items, coins) => {
    server.use(http.get('*/api/challenges/', () => HttpResponse.json(body)));
    const saved = await getChallenges();
    expect(saved).toEqual(body);
    expect(saved.results[0].reward_receipt).toMatchObject({ status: 'awarded', items, coins_awarded: coins });
    expect(saved.recent_receipts[0].reward_receipt.items).toEqual(items);
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
