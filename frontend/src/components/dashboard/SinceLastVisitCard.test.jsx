import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SinceLastVisitCard from './SinceLastVisitCard.jsx';

const summary = (overrides = {}) => ({
  last_seen_at: '2026-06-08T12:00:00Z',
  badges_earned: 0,
  coins_earned: 0,
  approvals: 0,
  ...overrides,
});

describe('SinceLastVisitCard', () => {
  it('renders the away summary with all three parts', () => {
    render(
      <SinceLastVisitCard
        summary={summary({ badges_earned: 3, approvals: 1, coins_earned: 12 })}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Since you were here last: 3 badges earned · 1 approval · +12 coins',
    );
  });

  it('omits zero-count parts', () => {
    render(<SinceLastVisitCard summary={summary({ coins_earned: 5 })} />);
    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('+5 coins');
    expect(status).not.toHaveTextContent('badge');
    expect(status).not.toHaveTextContent('approval');
  });

  it('renders nothing when every count is zero', () => {
    const { container } = render(<SinceLastVisitCard summary={summary()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing on first visit (null summary)', () => {
    const { container } = render(<SinceLastVisitCard summary={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('dismiss hides the card', async () => {
    const user = userEvent.setup();
    render(<SinceLastVisitCard summary={summary({ badges_earned: 1 })} />);
    await user.click(screen.getByRole('button', { name: /dismiss what's new/i }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
