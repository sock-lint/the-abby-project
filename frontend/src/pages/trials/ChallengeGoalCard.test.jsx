import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import { buildChallengeGoal } from '../../test/challenges';
import ChallengeGoalCard, { ChallengeGoalDetail } from './ChallengeGoalCard';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));
beforeEach(() => resolvePedestalImage.mockReturnValue(null));

describe('Challenge goal cards', () => {
  it.each([false, true])('uses decorative card art only in the child view (parent: %s)', (isParent) => {
    resolvePedestalImage.mockReturnValue({ url: '/synthetic/light-card.png', width: 512, height: 512, assetId: 'card-front-light', variantId: 'web' });
    const goal = buildChallengeGoal({ rewards: { coins: 10, xp: 20, items: [] } });
    const { container } = renderWithProviders(<ChallengeGoalCard goal={goal} isParent={isParent} onSelect={() => {}} />, { withAuth: false });
    expect(Boolean(container.querySelector('img'))).toBe(!isParent);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText('Completion bonus · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `View ${goal.name}` })).toBeEnabled();
  });

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

  it.each(['card', 'detail'])('does not report an undelivered preview egg as earned in the %s', (surface) => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'awarded', coins_awarded: 20, xp_awarded: 40, items: [] },
    });
    renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} onSelect={() => {}} />
      : <ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 20 coins · 40 XP')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it.each(['card', 'detail'])('shows the actual delivered item and quantity instead of the frozen preview in the %s', (surface) => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'awarded', coins_awarded: 10, xp_awarded: 20, items: [{ item_name: 'Canvas frame', quantity: 2 }] },
    });
    renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} onSelect={() => {}} />
      : <ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 10 coins · 20 XP · Canvas frame ×2')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it('does not fall back to the preview when an awarded receipt has no saved item details', () => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'awarded', coins_awarded: 10, xp_awarded: 20 },
    });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it.each([0, 12])('does not describe a salvaged egg as delivered or add its %s Coins twice', (salvage) => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: {
        status: 'awarded', coins_awarded: 10 + salvage, xp_awarded: 20,
        items: [{ item_name: 'Egg', quantity: 1, salvaged_to_coins: salvage }],
      },
    });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText(`Bonus earned automatically · ${10 + salvage} coins · 20 XP`)).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it('does not infer delivered items for a completed legacy goal without an award receipt', () => {
    const goal = buildChallengeGoal({
      legacy: true, status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'legacy', coins_awarded: 0, xp_awarded: 0 },
    });
    renderWithProviders(<ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Original completion bonus · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it.each(['active', 'completed'])('keeps the promised item preview while an %s goal has no paid receipt', (status) => {
    const goal = buildChallengeGoal({
      status, rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'pending', coins_awarded: 0, xp_awarded: 0 },
    });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText(`${status === 'active' ? 'Completion bonus' : 'Bonus pending'} · 10 coins · 20 XP · Egg ×1`)).toBeInTheDocument();
    expect(screen.queryByText(/Bonus earned automatically/)).not.toBeInTheDocument();
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
