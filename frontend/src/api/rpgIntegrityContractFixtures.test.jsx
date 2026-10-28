import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import earned from '../../../contracts/api/fixtures/character-progression-earned.json';
import maximum from '../../../contracts/api/fixtures/character-progression-max.json';
import pending from '../../../contracts/api/fixtures/redemption-frozen-promise-pending.json';
import fulfilled from '../../../contracts/api/fixtures/redemption-frozen-promise-fulfilled.json';
import coopCompleted from '../../../contracts/api/fixtures/habit-coop-completed.json';
import nonrepeatableRestart from '../../../contracts/api/fixtures/quest-nonrepeatable-restart.json';
import unreachableStart from '../../../contracts/api/fixtures/quest-unreachable-start.json';
import { renderWithProviders, screen } from '../test/render';
import { server } from '../test/server';
import SigilFrontispiece from '../pages/character/SigilFrontispiece';
import { approveRedemption, getCharacterProfile, getRedemptions, logHabitTap, redeemReward, startQuest } from './index';

describe('server-confirmed RPG progression and purchased promises', () => {
  it('shows progress from the actual earned character response', async () => {
    server.use(http.get('*/api/character/', () => HttpResponse.json(earned)));
    const profile = await getCharacterProfile();
    expect(profile).toMatchObject({ level: 2, total_xp: 375, xp_in_level: 75, xp_needed_for_level: 300 });
    renderWithProviders(<SigilFrontispiece profile={profile} onOpenTrophyPicker={() => {}} />);
    expect(screen.getByRole('img', { name: 'Level 2', exact: true })).toHaveTextContent('Lv. 2');
    expect(screen.getByText('25% toward the next level')).toBeInTheDocument();
  });

  it('recognizes the confirmed maximum without inventing another threshold', async () => {
    server.use(http.get('*/api/character/', () => HttpResponse.json(maximum)));
    const profile = await getCharacterProfile();
    expect(profile).toMatchObject({ level: 6, total_xp: 2500, xp_needed_for_level: 0 });
    renderWithProviders(<SigilFrontispiece profile={profile} onOpenTrophyPicker={() => {}} />);
    expect(screen.getByText('Highest level')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Level 6', exact: true })).toHaveTextContent('Lv. 6');
    expect(screen.queryByText(/toward the next level/)).not.toBeInTheDocument();
  });

  it('retains the paid item, fulfillment kind and price through request, history and approval', async () => {
    const requests = [];
    server.use(
      http.post('*/api/rewards/701/redeem/', async ({ request }) => {
        requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json(pending, { status: 201 });
      }),
      http.get('*/api/redemptions/', () => HttpResponse.json({ count: 1, next: null, previous: null, results: [pending] })),
      http.post('*/api/redemptions/1/approve/', async ({ request }) => {
        requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json(fulfilled);
      }),
    );
    const requested = await redeemReward(701);
    const history = await getRedemptions();
    const approved = await approveRedemption(1);
    for (const receipt of [requested, history.results[0], approved]) {
      expect(receipt.coin_cost_snapshot).toBe(100);
      expect(receipt.reward).toMatchObject({ fulfillment_kind: 'digital_item', item_definition: 601, cost_coins: 100 });
      expect(receipt.reward.item_definition_detail).toMatchObject({ id: 601, name: 'Fixture promised frame' });
    }
    expect(approved.status).toBe('fulfilled');
    expect(requests).toEqual([
      { method: 'POST', path: '/api/rewards/701/redeem/', body: {} },
      { method: 'POST', path: '/api/redemptions/1/approve/', body: { notes: '' } },
    ]);
  });

  it('retains the category-matched habit’s confirmed co-op reward receipt', async () => {
    const requests = [];
    server.use(http.post('*/api/habits/9/log/', async ({ request }) => {
      requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() });
      return HttpResponse.json(coopCompleted);
    }));

    const receipt = await logHabitTap(9, 1);
    expect(receipt).toEqual(coopCompleted);
    expect(receipt).toMatchObject({ direction: 1, xp_reward: 0, new_strength: 1 });
    expect(receipt.game_event.quest).toMatchObject({
      quest_id: 1, completed: true, new_progress: 1, target: 1,
      rewards: {
        coins: 13, xp: 24,
        items: [{ item_id: 601, item_name: 'Fixture team food', item_icon: 'food', item_catalog_icon: null, quantity: 2, item_rarity: 'common', item_type: 'food', item_catalog_available: true }],
      },
    });
    expect(requests).toEqual([{ method: 'POST', path: '/api/habits/9/log/', body: { direction: 1 } }]);
  });

  it('preserves the server’s completed nonrepeatable quest rejection', async () => {
    const requests = [];
    server.use(http.post('*/api/quests/start/', async ({ request }) => {
      requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() });
      return HttpResponse.json(nonrepeatableRestart, { status: 400 });
    }));

    await expect(startQuest(701, null)).rejects.toMatchObject({
      status: 400, message: nonrepeatableRestart.error, response: nonrepeatableRestart,
    });
    expect(requests).toEqual([{
      method: 'POST', path: '/api/quests/start/', body: { definition_id: 701, scroll_item_id: null },
    }]);
  });

  it('preserves the server’s rejection of a campaign without a saved-work progress source', async () => {
    const requests = [];
    server.use(http.post('*/api/quests/start/', async ({ request }) => {
      requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() });
      return HttpResponse.json(unreachableStart, { status: 400 });
    }));

    await expect(startQuest(702, null)).rejects.toMatchObject({
      status: 400, message: unreachableStart.error, response: unreachableStart,
    });
    expect(requests).toEqual([{
      method: 'POST', path: '/api/quests/start/', body: { definition_id: 702, scroll_item_id: null },
    }]);
  });
});
