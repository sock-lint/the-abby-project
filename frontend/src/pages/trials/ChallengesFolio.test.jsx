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
    expect(within(screen.getByRole('article')).getByText(/Goal period/)).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
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

  it('distinguishes repeated completed goals by their saved periods in history', async () => {
    const goals = [
      buildChallengeGoal({ id: 'goal:week-one', name: 'Weekly running', status: 'completed', timezone: 'America/Phoenix', completed_at: '2026-10-19T01:00:00Z' }),
      buildChallengeGoal({ id: 'goal:week-two', name: 'Weekly running', status: 'completed', timezone: 'America/Phoenix', starts_at: '2026-10-19T07:00:00Z', ends_at: '2026-10-26T07:00:00Z', completed_at: '2026-10-26T01:00:00Z' }),
    ];
    const { user } = renderWithProviders(<ChallengesFolio goals={goals} onSelect={vi.fn()} />, { withAuth: false });
    await user.click(screen.getByText('History · 2'));
    const cards = screen.getAllByRole('article', { name: 'Weekly running' });
    expect(cards[0]).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    expect(cards[0]).toHaveTextContent('Completion recorded Oct 18, 2026');
    expect(cards[1]).toHaveTextContent('Goal period Oct 19, 2026 – Oct 25, 2026');
    expect(cards[1]).toHaveTextContent('Completion recorded Oct 25, 2026');
  });

  it('keeps an incomplete prior cycle in history beside the current parent goal', async () => {
    const goals = [
      buildChallengeGoal({ id: 'goal:prior', name: 'Weekly running', status: 'expired', progress: '1', timezone: 'America/Phoenix', completed_at: null }),
      buildChallengeGoal({ id: 'goal:current', name: 'Weekly running', status: 'active', progress: '0', timezone: 'America/Phoenix', starts_at: '2026-10-19T07:00:00Z', ends_at: '2026-10-26T07:00:00Z' }),
    ];
    const { user } = renderWithProviders(<ChallengesFolio goals={goals} isParent onSelect={vi.fn()} />, { withAuth: false });
    expect(within(screen.getByRole('region', { name: 'Parent goals' })).getByText(/Goal period/)).toHaveTextContent('Goal period Oct 19, 2026 – Oct 25, 2026');
    await user.click(screen.getByText('History · 1'));
    const prior = screen.getAllByRole('article', { name: 'Weekly running' }).find((card) => card.textContent.includes('Period ended'));
    expect(prior).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    expect(prior).toHaveTextContent('1 / 2 miles');
    expect(prior).not.toHaveTextContent('Completion recorded');
    expect(within(prior).queryByRole('button', { name: /pin/i })).not.toBeInTheDocument();
  });
});
