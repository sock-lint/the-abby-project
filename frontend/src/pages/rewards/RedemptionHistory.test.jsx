import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import RedemptionHistory from './RedemptionHistory.jsx';

describe('RedemptionHistory', () => {
  it('returns null when empty', () => {
    const { container } = render(<RedemptionHistory redemptions={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders redemption rows', () => {
    render(
      <RedemptionHistory
        redemptions={[
          { id: 1, user_name: 'Abby', reward: { name: 'Toy', icon: '🧸' }, coin_cost_snapshot: 20, requested_at: '2026-04-10T00:00:00Z', status: 'fulfilled' },
        ]}
        isParent={false}
      />,
    );
    expect(screen.getByText('Toy')).toBeInTheDocument();
    expect(screen.getByText(/fulfilled/i)).toBeInTheDocument();
  });
});
