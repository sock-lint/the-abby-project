import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import catalog from '../../../contracts/api/fixtures/content-workbench-catalog.json';
import denied from '../../../contracts/api/fixtures/content-workbench-denied.json';
import { getContentWorkbench } from './index';
import ContentWorkbench from '../pages/manage/ContentWorkbench';
import { renderWithProviders } from '../test/render';
import { buildParent } from '../test/factories';
import { server } from '../test/server';

describe('Content workbench shared API contract', () => {
  it('reads real server catalog projections with exact reward and reverse references', async () => {
    const calls = [];
    server.use(http.get('*/api/rpg/content-workbench/', ({ request }) => {
      const url = new URL(request.url);
      calls.push({ path: url.pathname, auth: request.headers.get('Authorization') });
      expect([...url.searchParams.keys()]).toEqual(['_abby_session']);
      return HttpResponse.json(catalog);
    }));
    const response = await getContentWorkbench();
    expect(response).toEqual(catalog);
    expect(calls).toEqual([{ path: '/api/rpg/content-workbench/', auth: 'Token test-session' }]);
    const item = response.catalog.items[0];
    const quest = response.catalog.quests[0];
    expect(quest.values.reward_items).toEqual([{ item_id: item.id, quantity: 1 }]);
    expect(item.used_by.quests).toEqual([{ id: quest.id, name: quest.name, quantity: 1 }]);
    expect(response.simulation.catalog.fingerprint).toMatch(/^[a-f0-9]{64}$/);
    expect(response.simulation.pet_incubation_policy).toEqual({
      duration_seconds: 86400, max_active: 1, clock: 'elapsed_seconds',
      start_strategy: 'first_compatible_pair_during_care',
      claim_strategy: 'next_active_care_visit_at_or_after_ready',
    });
  });

  it('renders the real producer response through the challenge and item editors', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/rpg/content-workbench/', () => HttpResponse.json(catalog)),
    );
    const { user } = renderWithProviders(<ContentWorkbench />);
    await user.click(await screen.findByRole('button', { name: /Practice challenge/ }));
    const editor = screen.getByRole('form', { name: 'Challenge editor' });
    expect(within(editor).getByRole('spinbutton', { name: 'Coin reward' })).toHaveValue(10);
    expect(within(editor).getByRole('spinbutton', { name: 'XP reward' })).toHaveValue(15);
    expect(within(editor).getByRole('combobox', { name: 'Reward item 1' })).toHaveTextContent('Practice snack');
    await user.click(screen.getByRole('button', { name: 'Items', exact: true }));
    await user.click(screen.getByRole('button', { name: /Practice snack/ }));
    const uses = screen.getByRole('region', { name: 'Item connections' });
    expect(within(uses).getByRole('button', { name: 'Practice challenge · 1 awarded' })).toBeVisible();
    expect(within(uses).getByText(/Drop: chore complete/)).toBeVisible();
  });

  it('uses the real permission denial without exposing authoring data', async () => {
    server.use(http.get('*/api/rpg/content-workbench/', () => HttpResponse.json(denied, { status: 403 })));
    await expect(getContentWorkbench()).rejects.toMatchObject({ status: 403, response: denied });
  });
});
