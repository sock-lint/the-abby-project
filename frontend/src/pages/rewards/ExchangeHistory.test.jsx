import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ExchangeHistory from './ExchangeHistory.jsx';

describe('ExchangeHistory', () => {
  it('returns null when empty', () => {
    const { container } = render(<ExchangeHistory exchanges={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders exchanges with status', () => {
    render(
      <ExchangeHistory
        exchanges={[
          { id: 1, user_name: 'Abby', dollar_amount: '5', coin_amount: 50, exchange_rate: 10, created_at: '2026-04-10', status: 'approved' },
        ]}
        isParent={true}
      />,
    );
    expect(screen.getByText(/abby/i)).toBeInTheDocument();
    expect(screen.getByText(/approved/i)).toBeInTheDocument();
  });
});
