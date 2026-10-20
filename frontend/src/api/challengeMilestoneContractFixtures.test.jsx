import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import locked from '../../../contracts/api/fixtures/challenges-milestone-locked.json';
import ready from '../../../contracts/api/fixtures/challenges-milestone-ready.json';
import { renderWithProviders, screen, within } from '../test/render';
import { buildUser } from '../test/factories';
import { server } from '../test/server';
import Trials from '../pages/trials';

describe('Native milestone challenge API projections in React', () => {
  it.each([['locked', locked], ['ready', ready]])('shows the actual %s projection without accepting, opening or pinning it', async (_state, response) => {
    const calls = [];
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.all('*/api/challenges/*', ({ request }) => {
        const url = new URL(request.url);
        calls.push({ path: url.pathname, method: request.method });
        expect(request.method).toBe('GET');
        expect(url.pathname).toBe('/api/challenges/');
        return HttpResponse.json(response);
      }),
    );
    const { user } = renderWithProviders(<Trials />, { route: '/quests?tab=trials' });
    const coming = await screen.findByRole('region', { name: 'Coming next' });
    const voyager = response.locked_catalog.find((row) => row.name === 'Reading Voyager');
    expect(within(coming).getByText(voyager.milestone_eligibility.unlocked ? 'Requirements met' : 'Locked challenge')).toBeVisible();
    await user.click(within(coming).getByRole('button', { name: `View requirements for ${voyager.name}` }));
    const dialog = await screen.findByRole('dialog', { name: `${voyager.name} requirements` });
    const requirements = within(dialog).getByRole('list', { name: `${voyager.name} milestone requirements` });
    for (const requirement of voyager.milestone_eligibility.requirements) {
      const row = within(requirements).getAllByRole('listitem').find((item) => item.textContent.includes(requirement.description));
      expect(row).toHaveTextContent(requirement.met ? 'Met' : 'Not yet met');
    }
    expect(within(dialog).getByText(/No deadline is running yet.*56 days after it starts/)).toBeVisible();
    expect(within(dialog).queryByRole('progressbar')).toBeNull();
    expect(within(dialog).queryByRole('button', { name: /Pin|Start|Begin|Log reading/i })).toBeNull();
    expect(calls).toEqual([{ path: '/api/challenges/', method: 'GET' }]);
  });
});
