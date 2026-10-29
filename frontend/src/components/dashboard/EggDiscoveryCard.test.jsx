import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { buildEggDiscovery, buildEggEnvelope } from '../../test/eggDiscoveries';
import { buildUser } from '../../test/factories';
import EggDiscoveryCard from './EggDiscoveryCard';

describe('Today egg discovery preview', () => {
  it('shows only the selected egg and refreshes its progress on a pulse without looping', async () => {
    let calls = 0;
    server.use(http.get('*/api/egg-discoveries/', () => {
      calls += 1;
      return HttpResponse.json(buildEggEnvelope({ active_id: 1, discoveries: [buildEggDiscovery({ minutes: { reading: calls === 1 ? 30 : 60, movement: 0, practice: 0 } }), buildEggDiscovery({ id: 2, offer_key: 'other', status: 'paused', name: 'Paused egg' })] }));
    }), http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    const view = renderWithProviders(<EggDiscoveryCard />);
    expect(await screen.findByRole('region', { name: 'Your egg discovery' })).toHaveTextContent('30 of 240 minutes recorded');
    expect(screen.queryByText('Paused egg')).toBeNull();
    view.beat({ header: { level: 2 } });
    expect(await screen.findByText('60 of 240 minutes recorded')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View egg discovery' })).toHaveAttribute('href', '/quests?tab=trials');
    await waitFor(() => expect(calls).toBe(2));
  });

  it('invites an explicit choice without automatically selecting an egg', async () => {
    server.use(http.get('*/api/egg-discoveries/', () => HttpResponse.json(buildEggEnvelope())), http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    renderWithProviders(<EggDiscoveryCard />);
    expect(await screen.findByRole('link', { name: 'Choose an egg' })).toHaveAttribute('href', '/quests?tab=trials');
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
});
