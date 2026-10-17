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

  it('distinguishes waiting for handover from the saved delivery receipt', () => {
    render(<RedemptionHistory redemptions={[
      { id: 1, user_name: 'Abby', reward: { name: 'Museum trip' }, coin_cost_snapshot: 30, requested_at: '2026-10-16T18:00:00Z', status: 'approved', parent_notes: 'Saturday after lunch.' },
      { id: 2, user_name: 'Ben', reward: { name: 'Book' }, coin_cost_snapshot: 20, requested_at: '2026-10-15T18:00:00Z', status: 'fulfilled', delivered_at: '2026-10-17T18:00:00Z' },
    ]} isParent />);
    expect(screen.getByText('Awaiting delivery')).toBeInTheDocument();
    expect(screen.getByText('Parent note: Saturday after lunch.')).toBeInTheDocument();
    expect(screen.getByText(/Delivered /)).toBeInTheDocument();
  });
});
