import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardShop from './RewardShop.jsx';

const reward = {
  id: 1, name: 'Ice Cream', icon: '🍦', cost_coins: 50,
  rarity: 'common', stock: 3, is_active: true,
};

describe('RewardShop', () => {
  it('renders reward cards', () => {
    render(
      <RewardShop
        rewards={[reward]}
        isParent={false}
        coinBalance={60}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText('Ice Cream')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /barter/i })).toBeInTheDocument();
  });

  it('shows disabled state when not enough coins', () => {
    render(
      <RewardShop
        rewards={[reward]}
        isParent={false}
        coinBalance={10}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /not enough coin/i })).toBeDisabled();
  });

  it('shows out of stock', () => {
    render(
      <RewardShop
        rewards={[{ ...reward, stock: 0 }]}
        isParent={false}
        coinBalance={1000}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /out of stock/i })).toBeDisabled();
  });

  it('renders an empty state when no rewards exist (child copy)', () => {
    render(
      <RewardShop
        rewards={[]}
        isParent={false}
        coinBalance={0}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/ask a parent to add some/i)).toBeInTheDocument();
  });

  it('renders an empty state with a parent CTA when no rewards exist', () => {
    render(
      <RewardShop
        rewards={[]}
        isParent={true}
        coinBalance={0}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/head to manage to add some/i)).toBeInTheDocument();
  });

  it('parent can edit/delete', async () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(
      <RewardShop
        rewards={[reward]}
        isParent={true}
        coinBalance={0}
        onRedeem={vi.fn()}
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    );
    await user.click(screen.getByRole('button', { name: /edit reward/i }));
    await user.click(screen.getByRole('button', { name: /delete reward/i }));
    expect(onEdit).toHaveBeenCalled();
    expect(onDelete).toHaveBeenCalled();
  });
});
