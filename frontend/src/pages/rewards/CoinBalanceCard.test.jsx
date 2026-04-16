import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CoinBalanceCard from './CoinBalanceCard.jsx';

describe('CoinBalanceCard', () => {
  it('renders balance and exchange button for child', async () => {
    const onOpenExchange = vi.fn();
    const user = userEvent.setup();
    render(<CoinBalanceCard coinBalance={42} isParent={false} onOpenExchange={onOpenExchange} />);
    expect(screen.getByText('42')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /exchange money/i }));
    expect(onOpenExchange).toHaveBeenCalled();
  });

  it('hides exchange button for parent', () => {
    render(<CoinBalanceCard coinBalance={0} isParent={true} onOpenExchange={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /exchange money/i })).toBeNull();
  });
});
