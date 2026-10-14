import { beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildParent, buildUser } from '../../test/factories';
import { buildDailyBonus } from '../../test/challenges';
import DailyChallengeCard from './DailyChallengeCard';

beforeEach(() => { server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))); });

describe('Today’s automatic bonus', () => {
  it('shows cumulative short-session minutes and approval timing without a Claim action', async () => {
    renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus()} />);
    expect(await screen.findByRole('heading', { name: "Today's bonus" })).toBeInTheDocument();
    expect(screen.getByText(/Short sessions add together/)).toBeInTheDocument();
    expect(screen.getByText('4 / 10 minutes · Or complete one approved task')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4');
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
  });

  it('displays only server-confirmed award totals and cannot claim twice', async () => {
    const claim = spyHandler('post', /\/api\/challenges\/daily\/claim\/$/, {});
    server.use(claim.handler);
    renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus({ completed: true, awarded: true, coins_awarded: 20, xp_awarded: 40, receipt_id: 'daily:11' })} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Bonus earned · +20 coins · +40 XP');
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
    expect(claim.calls).toHaveLength(0);
  });


  it('loads the automatic daily bonus from the goal list when used on its own', async () => {
    const get = spyHandler('get', /\/api\/challenges\/$/, { results: [], pin: null, daily_bonus: buildDailyBonus() });
    server.use(get.handler);
    renderWithProviders(<DailyChallengeCard />);
    expect(await screen.findByRole('heading', { name: "Today's bonus" })).toBeInTheDocument();
    expect(get.calls).toHaveLength(1);
  });

  it('preserves earlier claimed bonuses without inventing zero-valued receipt totals', async () => {
    renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus({ completed: true, awarded: true, receipt_id: null })} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Bonus already earned');
    expect(screen.queryByText(/\+0 coins/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\+0 XP/)).not.toBeInTheDocument();
  });

  it('does not claim that a completed but unsettled bonus paid', async () => {
    renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus({ completed: true, awarded: false })} />);
    expect(await screen.findByText('Goal complete · Your bonus is being processed.')).toBeInTheDocument();
    expect(screen.queryByText(/Bonus earned/)).not.toBeInTheDocument();
  });

  it('shows the server family deadline and timezone without using client midnight', async () => {
    renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus()} />);
    expect(await screen.findByText('Ends Oct 13 · America/Phoenix')).toBeInTheDocument();
    expect(screen.queryByText(/resets in/i)).not.toBeInTheDocument();
  });

  it('does not fetch a daily challenge for parents', async () => {
    const get = spyHandler('get', /\/api\/challenges\/$/, { daily_bonus: buildDailyBonus() });
    server.use(get.handler, http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    const { container } = renderWithProviders(<DailyChallengeCard />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(get.calls).toHaveLength(0);
  });
});
