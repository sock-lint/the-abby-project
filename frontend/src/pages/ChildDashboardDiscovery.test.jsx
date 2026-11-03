import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useLocation } from 'react-router-dom';
import { renderWithProviders, screen } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildUser } from '../test/factories';
import { buildChallengeGoal } from '../test/challenges';
import Dashboard from './Dashboard';
import { buildEggDiscovery, buildEggEnvelope } from '../test/eggDiscoveries';

function LocationProbe() { const location = useLocation(); return <p data-testid="discovery-route">{location.pathname}{location.search}</p>; }

describe('Today challenge discovery integration', () => {
  it('foregrounds the chosen discovery without resurfacing earlier pinned egg rewards', async () => {
    const earlier = buildChallengeGoal({ id: 'goal:earlier', name: 'Earlier Wolf Trail', origin: 'catalog', pinned: true, legacy_egg_promise: true });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/egg-discoveries/', () => HttpResponse.json(buildEggEnvelope({ active_id: 1, discoveries: [buildEggDiscovery({ name: 'Chosen Bee Egg' })] }))),
      http.get('*/api/challenges/', () => HttpResponse.json({ results: [earlier], pin: earlier.id, daily_bonus: null })),
    );
    renderWithProviders(<Dashboard />);
    expect(await screen.findByRole('region', { name: 'Your egg discovery' })).toHaveTextContent('Chosen Bee Egg');
    expect(screen.queryByText(earlier.name)).toBeNull();
    expect(screen.queryByRole('link', { name: /Explore challenges/ })).toBeNull();
    expect(screen.queryByText(/preview/i)).toBeNull();
  });

  it('shows the bounded available selection and navigates without recording a details opening', async () => {
    const goals = Array.from({ length: 5 }, (_, index) => buildChallengeGoal({
      id: `goal:${index + 11}`, name: `Available challenge ${index + 1}`,
      origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null, progress: '0',
    }));
    const opened = spyHandler('post', /\/api\/challenges\/[^/]+\/opened\/$/, {});
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/challenges/', () => HttpResponse.json({ results: goals, pin: null, daily_bonus: null })),
      opened.handler,
    );
    const { user } = renderWithProviders(<><Dashboard /><LocationProbe /></>);
    const shortcut = await screen.findByRole('link', { name: /Explore challenges/ });
    expect(shortcut).toHaveTextContent('3 challenges to explore');
    expect(opened.calls).toHaveLength(0);
    await user.click(shortcut);
    expect(screen.getByTestId('discovery-route')).toHaveTextContent('/quests?tab=trials');
    expect(opened.calls).toHaveLength(0);
  });
});
