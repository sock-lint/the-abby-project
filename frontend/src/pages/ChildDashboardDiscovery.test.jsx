import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useLocation } from 'react-router-dom';
import { renderWithProviders, screen } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildUser } from '../test/factories';
import { buildChallengeGoal } from '../test/challenges';
import Dashboard from './Dashboard';

function LocationProbe() { const location = useLocation(); return <p data-testid="discovery-route">{location.pathname}{location.search}</p>; }

describe('Today challenge discovery integration', () => {
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
