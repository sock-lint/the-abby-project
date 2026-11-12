import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import * as Sentry from '@sentry/react';
import { act, renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildParent, buildUser } from '../../test/factories';
import { buildDailyBonus } from '../../test/challenges';
import { GATEWAY_RETRY_DELAY_MS } from '../../api/client';
import { DEFERRED_RECOVERY_DELAY_MS } from '../../hooks/useApi';
import DailyChallengeCard from './DailyChallengeCard';

beforeEach(() => { server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))); });

describe('Today’s automatic bonus', () => {
  it('shows cumulative short-session minutes and approval timing without a Claim action', async () => {
    const { container } = renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus()} />);
    expect(await screen.findByRole('heading', { name: "Today's bonus" })).toBeInTheDocument();
    expect(container.querySelector('[data-achievement-card="tall"]')).toBeInTheDocument();
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

  // THE-ABBY-PROJECT-41: the standalone card shares GET /api/challenges/, so a
  // deploy-window HTML 200 must wait out the window instead of being reported.
  describe('during a deploy window', () => {
    const html = () => new HttpResponse('<!doctype html><title>starting</title>', {
      status: 200, headers: { 'content-type': 'text/html' },
    });
    beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
    afterEach(() => { vi.useRealTimers(); });

    it('shows the bonus without reporting when the proxy recovers after the client retry', async () => {
      let calls = 0;
      server.use(http.get('*/api/challenges/', () => {
        calls += 1;
        return calls <= 2 ? html() : HttpResponse.json({ results: [], pin: null, daily_bonus: buildDailyBonus() });
      }));
      renderWithProviders(<DailyChallengeCard />);
      await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
      await waitFor(() => expect(calls).toBe(2));
      expect(Sentry.captureException).not.toHaveBeenCalled();
      await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS));
      expect(await screen.findByRole('heading', { name: "Today's bonus" })).toBeInTheDocument();
      expect(calls).toBe(3);
      expect(Sentry.captureException).not.toHaveBeenCalled();
    });
  });

  it('preserves earlier claimed bonuses without inventing zero-valued receipt totals', async () => {
    renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus({ completed: true, awarded: true, receipt_id: null })} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Bonus already earned');
    expect(screen.queryByText(/\+0 coins/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\+0 XP/)).not.toBeInTheDocument();
  });

  it('does not claim that a completed but unsettled bonus paid', async () => {
    const { container } = renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus({ completed: true, awarded: false })} />);
    expect(await screen.findByText('Goal complete · Your bonus is being processed.')).toBeInTheDocument();
    expect(screen.queryByText(/Bonus earned/)).not.toBeInTheDocument();
    expect(container.querySelector('[data-bonus-star]')).toHaveAttribute('data-bonus-star', 'pending');
    expect(container.querySelector('[data-pedestal-image="star-lit"]')).not.toBeInTheDocument();
  });

  it('lights the decorative star only for the confirmed server award', async () => {
    const { container } = renderWithProviders(<DailyChallengeCard challenge={buildDailyBonus({ completed: true, awarded: true, receipt_id: 'daily:42' })} />);
    expect(await screen.findByRole('status')).toHaveTextContent('Bonus earned');
    expect(container.querySelector('[data-bonus-star]')).toHaveAttribute('data-bonus-star', 'awarded');
    expect(container.querySelector('[data-pedestal-image="star-lit"]')).toBeInTheDocument();
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
