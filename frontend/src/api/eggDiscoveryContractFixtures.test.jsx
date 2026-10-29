import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import catalog from '../../../contracts/api/fixtures/egg-discovery-catalog.json';
import ordinary from '../../../contracts/api/fixtures/egg-discovery-ordinary-active.json';
import missed from '../../../contracts/api/fixtures/egg-discovery-rare-missed.json';
import guaranteed from '../../../contracts/api/fixtures/egg-discovery-rare-guaranteed.json';
import seasonal from '../../../contracts/api/fixtures/egg-discovery-season-retained.json';
import paused from '../../../contracts/api/fixtures/egg-discovery-paused.json';
import disabled from '../../../contracts/api/fixtures/egg-discovery-disabled.json';
import { renderWithProviders, screen, within, waitFor } from '../test/render';
import { buildUser } from '../test/factories';
import { server } from '../test/server';
import EggDiscoveryPanel from '../pages/trials/EggDiscoveryPanel';

function mount(response) {
  const requests = [];
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    http.all('*/api/egg-discoveries/*', ({ request }) => {
      requests.push(request.method);
      expect(request.method).toBe('GET');
      return HttpResponse.json(response);
    }),
  );
  return { ...renderWithProviders(<EggDiscoveryPanel />), requests };
}

describe('Real egg discovery API projections in React', () => {
  it('displays eligible ordinary choices and the server explanation for a locked rare egg', async () => {
    const { requests } = mount(catalog);
    for (const offer of catalog.offers) {
      const button = await screen.findByRole('button', { name: `Choose ${offer.name}` });
      if (offer.eligible) expect(button).toBeEnabled();
      else {
        expect(button).toBeDisabled();
        expect(screen.getByText(offer.unavailable_reason)).toBeVisible();
      }
    }
    expect(requests).toEqual(['GET']);
  });

  it('uses real ordinary minutes and requirements without changing or claiming progress', async () => {
    const { requests } = mount(ordinary);
    const discovery = ordinary.discoveries.find((row) => row.id === ordinary.active_id);
    const active = await screen.findByRole('region', { name: 'Your active egg discovery' });
    const minutes = Object.values(discovery.minutes).reduce((sum, value) => sum + value, 0);
    expect(active).toHaveTextContent(`${minutes} of ${discovery.requirements.total_minutes} minutes recorded`);
    expect(active).toHaveTextContent(`at least ${discovery.requirements.min_minutes_per_type} minutes in each of ${discovery.requirements.activity_types_required} activity types`);
    expect(requests).toEqual(['GET']);
  });

  it('shows a persisted miss and its remaining guarantee from the endpoint fixture', async () => {
    mount(missed);
    const discovery = missed.discoveries[0];
    const active = await screen.findByRole('region', { name: 'Your active egg discovery' });
    expect(active).toHaveTextContent(`At most ${discovery.remaining_searches} more searches`);
    expect(within(active).getByRole('list', { name: 'Saved search results' })).toHaveTextContent('Search 1: No egg found');
    expect(active).toHaveTextContent(`${discovery.requirements.chance_percent}% chance`);
  });

  it('presents a guaranteed server receipt and the Hatchery handoff without another payout request', async () => {
    const { requests } = mount(guaranteed);
    await screen.findByText('Earned eggs · 1');
    const discovery = guaranteed.discoveries[0];
    const earned = screen.getByRole('region', { name: `Earned ${discovery.name}` });
    expect(earned).toHaveTextContent('Egg found — guaranteed discovery');
    for (const item of discovery.receipt.items) expect(earned).toHaveTextContent(`${item.item_name} × ${item.quantity}`);
    expect(within(earned).getByRole('link', { name: 'Take your egg to the Hatchery' })).toHaveAttribute('href', '/bestiary?tab=hatchery');
    expect(requests).toEqual(['GET']);
  });

  it.each([['paused', paused], ['season retained', seasonal]])('keeps the real %s accepted promise readable', async (_name, response) => {
    mount(response);
    const discovery = response.discoveries[0];
    expect(await screen.findByRole('heading', { name: discovery.name })).toBeVisible();
    if (discovery.status === 'paused') expect(screen.getByRole('button', { name: `Resume ${discovery.name}` })).toBeEnabled();
    if (discovery.season) expect(screen.getByText('Seasonal discovery saved. You can finish after the season ends.')).toBeVisible();
  });

  it('hides the disabled endpoint projection completely', async () => {
    const { requests } = mount(disabled);
    await waitFor(() => expect(requests).toEqual(['GET']));
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
    expect(screen.queryByRole('heading', { name: 'Egg discoveries' })).toBeNull();
  });
});
