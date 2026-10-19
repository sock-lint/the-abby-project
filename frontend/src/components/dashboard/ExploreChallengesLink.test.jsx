import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import { buildChallengeGoal } from '../../test/challenges';
import ExploreChallengesLink from './ExploreChallengesLink';

describe('Today challenge discovery', () => {
  it('links to the same available selection as Challenges, excluding opened, pinned, repeating and parent goals', () => {
    const base = { origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null, progress: '0' };
    const pinned = buildChallengeGoal({ ...base, id: 'goal:1' });
    const goals = [pinned,
      buildChallengeGoal({ ...base, id: 'goal:2' }), buildChallengeGoal({ ...base, id: 'goal:3' }),
      buildChallengeGoal({ ...base, id: 'goal:4', first_details_opened_at: '2026-10-18T19:00:00Z' }),
      buildChallengeGoal({ ...base, id: 'goal:5', catalog_repeatable: true }),
      buildChallengeGoal({ ...base, id: 'goal:6', origin: 'parent' }),
      buildChallengeGoal({ ...base, id: 'goal:7', status: 'completed' }),
    ];
    renderWithProviders(<ExploreChallengesLink goals={goals} pinnedGoal={pinned} />, { withAuth: false });
    expect(screen.getByRole('link', { name: /Explore challenges/ })).toHaveAttribute('href', '/quests?tab=trials');
    expect(screen.getByText('2 challenges to explore')).toBeInTheDocument();
  });

  it('omits the shortcut when there is no supported available selection', () => {
    renderWithProviders(<ExploreChallengesLink goals={[buildChallengeGoal({ origin: 'catalog' })]} />, { withAuth: false });
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
