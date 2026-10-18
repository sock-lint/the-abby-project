import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardShop from './RewardShop.jsx';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));
beforeEach(() => resolvePedestalImage.mockReturnValue(null));

const reward = {
  id: 1, name: 'Ice Cream', icon: '🍦', cost_coins: 50,
  rarity: 'common', stock: 3, is_active: true,
};

describe('RewardShop', () => {
  it('keeps a quiet introduction above tall offers with their real request and stock', async () => {
    resolvePedestalImage.mockReturnValue({ url: '/synthetic/treasure-card.png', width: 512, height: 512, assetId: 'card-front-treasure', variantId: 'web' });
    const onRedeem = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<RewardShop rewards={[reward]} isParent={false} coinBalance={60} onRedeem={onRedeem} />);
    expect(container.querySelector('[data-achievement-card="tall"]')).toBeInTheDocument();
    expect(container.querySelector('[data-pedestal-image="card-front-treasure"]')).toBeNull();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Choose something to work toward' })).toBeInTheDocument();
    expect(screen.getByText('🍦')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('3 left')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Request reward' }));
    expect(onRedeem).toHaveBeenCalledWith(reward);
  });

  it('keeps the parent shop focused on managing real offers', () => {
    resolvePedestalImage.mockReturnValue({ url: '/synthetic/treasure-card.png', width: 512, height: 512, assetId: 'card-front-treasure', variantId: 'web' });
    const { container } = render(<RewardShop rewards={[reward]} isParent coinBalance={0} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(container.querySelector('[data-pedestal-image="card-front-treasure"]')).toBeNull();
    expect(container.querySelector('[data-achievement-card="tall"]')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Choose something to work toward' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit reward' })).toBeEnabled();
  });

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
    expect(screen.getByRole('button', { name: /request reward/i })).toBeInTheDocument();
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
    expect(screen.getByText(/ask a parent to add one/i)).toBeInTheDocument();
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
    expect(screen.getByText(/choose new reward to add one/i)).toBeInTheDocument();
  });

  it('a zero-match search shows the filtered empty state, not "no rewards yet"', async () => {
    const onClearFilter = vi.fn();
    const user = userEvent.setup();
    render(
      <RewardShop
        rewards={[]}
        isParent={false}
        coinBalance={100}
        filterQuery="lego"
        onClearFilter={onClearFilter}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.queryByText(/ask a parent to add one/i)).toBeNull();
    expect(screen.getByText(/no matches for/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /clear filter/i }));
    expect(onClearFilter).toHaveBeenCalled();
  });

  it('still shows the no-rewards empty state when nothing is filtered', () => {
    render(
      <RewardShop
        rewards={[]}
        isParent={false}
        coinBalance={0}
        filterQuery=""
        onClearFilter={vi.fn()}
        onRedeem={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/ask a parent to add one/i)).toBeInTheDocument();
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
