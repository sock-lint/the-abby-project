import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import earned from '../../../contracts/api/fixtures/character-progression-earned.json';
import maximum from '../../../contracts/api/fixtures/character-progression-max.json';
import pending from '../../../contracts/api/fixtures/redemption-frozen-promise-pending.json';
import fulfilled from '../../../contracts/api/fixtures/redemption-frozen-promise-fulfilled.json';
import { renderWithProviders, screen } from '../test/render';
import { server } from '../test/server';
import SigilFrontispiece from '../pages/character/SigilFrontispiece';
import { approveRedemption, getCharacterProfile, getRedemptions, redeemReward } from './index';

describe('server-confirmed RPG progression and purchased promises', () => {
  it('shows progress from the actual earned character response', async () => {
    server.use(http.get('*/api/character/', () => HttpResponse.json(earned)));
    const profile = await getCharacterProfile();
    expect(profile).toMatchObject({ level: 2, total_xp: 375, xp_in_level: 75, xp_needed_for_level: 300 });
    renderWithProviders(<SigilFrontispiece profile={profile} onOpenTrophyPicker={() => {}} />);
    expect(screen.getByText('level 2')).toBeInTheDocument();
    expect(screen.getByText('25% toward the next level')).toBeInTheDocument();
  });

  it('recognizes the confirmed maximum without inventing another threshold', async () => {
    server.use(http.get('*/api/character/', () => HttpResponse.json(maximum)));
    const profile = await getCharacterProfile();
    expect(profile).toMatchObject({ level: 6, total_xp: 2500, xp_needed_for_level: 0 });
    const { container } = renderWithProviders(<SigilFrontispiece profile={profile} onOpenTrophyPicker={() => {}} />);
    expect(screen.getByText('Highest level')).toBeInTheDocument();
    expect(container.querySelector('[data-versal]')).toHaveAttribute('data-progress', '100');
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
});
