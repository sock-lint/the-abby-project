import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, act } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent, buildUser } from '../test/factories';
import { buildChallengeGoal } from '../test/challenges';
import { useAuth } from './useApi';
import useChallenges from './useChallenges';

function Probe() {
  const { pinnedGoal } = useChallenges();
  const { setUser } = useAuth();
  const { user } = useAuth();
  return <><span>{user?.role}</span><span data-testid="goal-probe">{pinnedGoal?.name || 'No current pin'}</span><button onClick={() => setUser(buildUser({ id: 22 }))}>Switch child</button></>;
}

describe('Scoped challenge reads', () => {
  it('does not read a child challenge list for a parent without a selected child', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    const get = spyHandler('get', /\/api\/challenges\/$/, { results: [] });
    server.use(get.handler);
    renderWithProviders(<Probe />);
    await screen.findByText('parent');
    expect(get.calls).toHaveLength(0);
  });

  it('hides the previous child pin until the new scoped response arrives', async () => {
    let requests = 0;
    let releaseNew;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ id: 7 }))),
      http.get('*/api/challenges/', async () => {
        requests += 1;
        const goal = buildChallengeGoal({ name: requests === 1 ? 'Abby private goal' : 'Beck goal', pinned: true });
        if (requests === 1) return HttpResponse.json({ results: [goal], pin: goal.id });
        return await new Promise((resolve) => { releaseNew = () => resolve(HttpResponse.json({ results: [goal], pin: goal.id })); });
      }),
    );
    const { user } = renderWithProviders(<Probe />);
    await screen.findByText('Abby private goal');
    await user.click(screen.getByRole('button', { name: 'Switch child' }));
    expect(screen.queryByText('Abby private goal')).not.toBeInTheDocument();
    await waitFor(() => expect(requests).toBe(2));
    await act(async () => { releaseNew(); });
    expect(await screen.findByText('Beck goal')).toBeInTheDocument();
  });
});
