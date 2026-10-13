import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import { buildChallengeGoal } from '../../test/challenges';
import ChallengeGoalCard, { ChallengeGoalDetail } from './ChallengeGoalCard';

describe('Challenge goal cards', () => {
  it('opens the full goal rather than an inert whole-card target', async () => {
    const select = vi.fn();
    const goal = buildChallengeGoal();
    const { user } = renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={select} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: `View ${goal.name}` }));
    expect(select).toHaveBeenCalledWith(goal);
  });

  it('shows the exact settled bonus instead of the planned reward when boosted', () => {
    renderWithProviders(<ChallengeGoalCard goal={buildChallengeGoal({ status: 'completed', reward_receipt: { status: 'awarded', coins_awarded: 20, xp_awarded: 40 } })} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 20 coins · 40 XP')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pin/i })).not.toBeInTheDocument();
  });

  it('retains ended legacy attempts in history without treating them as active', () => {
    renderWithProviders(<ChallengeGoalCard goal={buildChallengeGoal({ legacy: true, status: 'failed' })} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText('Ended')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pin/i })).not.toBeInTheDocument();
  });

  it('keeps a parent viewing a child goal from opening the child logging form', () => {
    renderWithProviders(<ChallengeGoalDetail goal={buildChallengeGoal()} canAct={false} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByRole('heading', { name: 'What counts' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Log a run' })).not.toBeInTheDocument();
  });
});
