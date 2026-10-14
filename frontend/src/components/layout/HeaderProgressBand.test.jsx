import { beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { buildChallengeGoal } from '../../test/challenges';
import { buildUser } from '../../test/factories';
import HeaderProgressBand from './HeaderProgressBand';

beforeEach(() => { server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))); });

describe('Pinned challenge header', () => {
  it('stays empty when goals are unpinned, even while they progress', async () => {
    server.use(http.get('*/api/challenges/', () => HttpResponse.json({ results: [buildChallengeGoal()], pin: null })));
    renderWithProviders(<HeaderProgressBand />);
    await waitFor(() => expect(screen.queryByRole('button')).not.toBeInTheDocument());
  });

  it('shows the exact server pin with fractional units and a full touch target', async () => {
    const goal = buildChallengeGoal({ pinned: true });
    server.use(http.get('*/api/challenges/', () => HttpResponse.json({ results: [goal, buildChallengeGoal({ id: 'goal:12', name: 'Other goal' })], pin: goal.id })));
    renderWithProviders(<HeaderProgressBand />);
    const band = await screen.findByRole('button', { name: 'Pinned challenge: Run 2 miles this week · 0.75 / 2 miles' });
    expect(band.className).toContain('min-h-11');
    expect(screen.getByText('0.75 / 2 miles')).toBeVisible();
    expect(screen.queryByText('Other goal')).not.toBeInTheDocument();
  });
});
