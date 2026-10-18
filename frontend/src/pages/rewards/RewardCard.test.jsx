import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardCard from './RewardCard.jsx';
import { resolveCatalogIcon } from '../../catalog/sharedCatalogIcons';

vi.mock('../../catalog/sharedCatalogIcons', () => ({ resolveCatalogIcon: vi.fn() }));
beforeEach(() => { resolveCatalogIcon.mockReturnValue(null); });

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
  it('keeps a digital reward’s exact catalog artwork and live content inside its tall canvas', async () => {
    resolveCatalogIcon.mockImplementation((id) => id === 'item-meat' ? { url: '/synthetic/meat.png' } : null);
    const name = 'An extraordinarily long reward name for the whole family';
    const reward = buildReward({
      name,
      rarity: 'epic',
      fulfillment_kind: 'digital_item',
      item_definition_detail: { name: 'Meat', catalog_icon: 'item-meat', icon: '🍗' },
    });
    const onRedeem = vi.fn();
    const onToggleWishlist = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<RewardCard reward={reward} isParent={false} coinBalance={50} onRedeem={onRedeem} onToggleWishlist={onToggleWishlist} />);
    expect(container.querySelector('[data-achievement-card="tall"]')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Meat' })).toHaveAttribute('src', '/synthetic/meat.png');
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(screen.getByText('epic')).toBeInTheDocument();
    expect(screen.getByText('Adds Meat to inventory')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: `Add ${name} to wishlist` }));
    expect(onToggleWishlist).toHaveBeenCalledWith(reward);
    await user.click(screen.getByRole('button', { name: 'Request reward' }));
    expect(onRedeem).toHaveBeenCalledWith(reward);
  });

  it('keeps a pending request disabled inside the card', () => {
    render(<RewardCard reward={buildReward()} isParent={false} coinBalance={50} pending onRedeem={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Requesting…' })).toBeDisabled();
  });

  it('labels rarity in text so the tier is not conveyed only by card color', () => {
    render(<RewardCard reward={buildReward({ rarity: 'epic' })} isParent coinBalance={100} />);
    expect(screen.getByText('epic')).toBeInTheDocument();
  });

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
    await user.click(screen.getByRole('button', { name: /request reward/i }));
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

  it('keeps requesting a reward available when the balance is unknown', () => {
    // coinBalance === null means the balance fetch failed. Greying every
    // card out with "Not enough coin" would be a lie about money the kid
    // may well have.
    render(
      <RewardCard
        reward={buildReward({ cost_coins: 100 })}
        isParent={false}
        coinBalance={null}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /not enough coin/i })).toBeNull();
    expect(screen.getByRole('button', { name: /^request reward$/i })).toBeEnabled();
  });

  it('labels digital rewards as inventory items', () => {
    render(
      <RewardCard
        reward={buildReward({
          fulfillment_kind: 'digital_item',
          item_definition_detail: { name: 'Streak Freeze' },
        })}
        isParent={false}
        coinBalance={999}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/adds streak freeze to inventory/i)).toBeInTheDocument();
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
    expect(screen.queryByRole('button', { name: /request reward/i })).toBeNull();
    await user.click(screen.getByRole('button', { name: /edit reward/i }));
    expect(onEdit).toHaveBeenCalledWith(reward);
    await user.click(screen.getByRole('button', { name: /delete reward/i }));
    expect(onDelete).toHaveBeenCalledWith(reward.id);
  });
});
