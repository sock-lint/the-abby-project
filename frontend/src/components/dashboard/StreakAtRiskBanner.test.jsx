import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import StreakAtRiskBanner from './StreakAtRiskBanner.jsx';
import { toISODate } from '../../utils/dates';

const yesterday = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return toISODate(d);
};

describe('StreakAtRiskBanner', () => {
  it('warns when a 3+ streak has no activity today', () => {
    render(
      <StreakAtRiskBanner rpg={{ login_streak: 5, last_active_date: yesterday() }} />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Your 5-day streak is waiting',
    );
  });

  it('renders nothing when already active today', () => {
    const { container } = render(
      <StreakAtRiskBanner
        rpg={{ login_streak: 5, last_active_date: toISODate(new Date()) }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing below the 3-day minimum', () => {
    const { container } = render(
      <StreakAtRiskBanner rpg={{ login_streak: 2, last_active_date: yesterday() }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing with no activity history', () => {
    const { container } = render(
      <StreakAtRiskBanner rpg={{ login_streak: 5, last_active_date: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing without an rpg block', () => {
    const { container } = render(<StreakAtRiskBanner rpg={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
