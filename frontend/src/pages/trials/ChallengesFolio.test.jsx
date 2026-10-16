import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, within } from '../../test/render';
import { buildChallengeGoal } from '../../test/challenges';
import ChallengesFolio from './ChallengesFolio';

describe('Challenges Task folio', () => {
  it('identifies parent goals by server origin even when catalog names match', () => {
    const goals = [
      buildChallengeGoal({ id: 'goal:catalog', origin: 'catalog', progress: '0', name: 'Run 2 miles' }),
      buildChallengeGoal({ id: 'goal:parent', origin: 'parent', progress: '0', name: 'Run 2 miles' }),
    ];
    renderWithProviders(<ChallengesFolio goals={goals} onSelect={vi.fn()} />, { withAuth: false });
    const parent = screen.getByRole('region', { name: 'Parent goals' });
    expect(within(parent).getAllByRole('article')).toHaveLength(1);
    expect(within(parent).getByText('From your parent')).toBeInTheDocument();
    expect(screen.getAllByRole('article', { name: 'Run 2 miles' })).toHaveLength(1);
    expect(screen.queryByRole('progressbar', { name: 'Challenges progress' })).not.toBeInTheDocument();
  });

  it('preserves a pinned parent goal once and uses its actual progress in the shared summary', () => {
    const goal = buildChallengeGoal({ pinned: true, progress: '1', target: '2', timezone: 'America/Phoenix' });
    renderWithProviders(<ChallengesFolio goals={[goal]} pinnedGoal={goal} onSelect={vi.fn()} />, { withAuth: false });
    expect(screen.getAllByRole('article', { name: goal.name })).toHaveLength(1);
    expect(screen.queryByRole('region', { name: 'Parent goals' })).not.toBeInTheDocument();
    screen.getAllByRole('progressbar', { name: 'Challenges progress' }).forEach((bar) => expect(bar).toHaveAttribute('aria-valuenow', '50'));
    expect(within(screen.getByRole('article')).getByText('Ends Oct 18')).toBeInTheDocument();
  });

  it('opens a background goal for full details without changing its saved progress', async () => {
    const goal = buildChallengeGoal({ origin: 'catalog', progress: '0' });
    const select = vi.fn();
    const { user } = renderWithProviders(<ChallengesFolio goals={[goal]} onSelect={select} />, { withAuth: false });
    await user.click(screen.getByText('Browse bonus challenges'));
    await user.click(await screen.findByRole('button', { name: `View ${goal.name}` }));
    expect(select).toHaveBeenCalledWith(goal);
    expect(goal.progress).toBe('0');
  });
});
