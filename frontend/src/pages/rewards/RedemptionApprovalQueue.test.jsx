import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import RedemptionApprovalQueue from './RedemptionApprovalQueue.jsx';

describe('RedemptionApprovalQueue', () => {
  it('renders pending redemption rows', () => {
    render(
      <RedemptionApprovalQueue
        pending={[{ id: 1, user_name: 'Abby', reward: { name: 'Toy', icon: '🧸' }, coin_cost_snapshot: 20, requested_at: '2026-04-10T00:00:00Z' }]}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );
    expect(screen.getByText(/abby/i)).toBeInTheDocument();
    expect(screen.getByText(/toy/i)).toBeInTheDocument();
  });

  it('renders nothing when empty', () => {
    const { container } = render(
      <RedemptionApprovalQueue pending={[]} onApprove={vi.fn()} onReject={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
