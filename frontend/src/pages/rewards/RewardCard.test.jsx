import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardCard from './RewardCard.jsx';

function buildReward(over = {}) {
  return {
    id: 3,
    name: 'Extra screen time',
    description: '30 minutes of Netflix',
    icon: '📺',
    rarity: 'common',
    cost_coins: 20,
    stock: null,
    is_active: true,
    ...over,
  };
}

describe('RewardCard', () => {
  it('fires onRedeem with the reward when child can afford it', async () => {
    const onRedeem = vi.fn();
    const user = userEvent.setup();
    const reward = buildReward();
    render(
      <RewardCard
        reward={reward}
        isParent={false}
        coinBalance={50}
        onRedeem={onRedeem}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('button', { name: /barter/i }));
    expect(onRedeem).toHaveBeenCalledWith(reward);
  });

  it('disables redeem button when the child cannot afford it', () => {
    render(
      <RewardCard
        reward={buildReward({ cost_coins: 100 })}
        isParent={false}
        coinBalance={5}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /not enough coin/i })).toBeDisabled();
  });

  it('disables redeem button when stock is zero', () => {
    render(
      <RewardCard
        reward={buildReward({ stock: 0 })}
        isParent={false}
        coinBalance={999}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /out of stock/i })).toBeDisabled();
  });

  it('hides redeem button for parent and wires edit/delete callbacks', async () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const user = userEvent.setup();
    const reward = buildReward();
    render(
      <RewardCard
        reward={reward}
        isParent={true}
        coinBalance={0}
        onRedeem={vi.fn()}
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    );
    expect(screen.queryByRole('button', { name: /barter/i })).toBeNull();
    await user.click(screen.getByRole('button', { name: /edit reward/i }));
    expect(onEdit).toHaveBeenCalledWith(reward);
    await user.click(screen.getByRole('button', { name: /delete reward/i }));
    expect(onDelete).toHaveBeenCalledWith(reward.id);
  });
});
