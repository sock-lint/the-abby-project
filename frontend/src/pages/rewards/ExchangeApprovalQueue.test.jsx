import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ExchangeApprovalQueue from './ExchangeApprovalQueue.jsx';

describe('ExchangeApprovalQueue', () => {
  it('renders pending exchanges', () => {
    render(
      <ExchangeApprovalQueue
        pending={[{ id: 1, user_name: 'Abby', dollar_amount: '5.00', coin_amount: 50, exchange_rate: 10, created_at: '2026-04-10T00:00:00Z' }]}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );
    expect(screen.getByText(/abby/i)).toBeInTheDocument();
  });

  it('renders nothing when empty', () => {
    const { container } = render(
      <ExchangeApprovalQueue pending={[]} onApprove={vi.fn()} onReject={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
